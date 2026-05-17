import serial, time, threading, os, io, math, json, uuid
from datetime import datetime
from PIL import Image
from django.conf import settings


class _State:
    def __init__(self):
        self.status        = 'idle'
        self.progress      = 0
        self.total         = 0
        self.message       = 'Готов'
        self.thread        = None
        self._stop         = threading.Event()
        self._ser_lock     = threading.Lock()
        self._ser          = None    # persistent serial, open after calibrate()
        self.origin_set    = False
        # periodic recalibration
        self.recal_idx     = 0       # current pause index (1-based)
        self.recal_total   = 0       # total planned pauses for current job
        self._recal_event  = threading.Event()
        self._recal_action = None    # 'continue' | 'recalibrate'
        # session tracking for log
        self.session_id    = None
        self.job_start     = None

    def reset(self):
        self._stop.clear()
        self._recal_event.clear()
        self._recal_action = None
        self.progress    = 0
        self.total       = 0
        self.recal_idx   = 0
        self.recal_total = 0

    def get_ser(self):
        with self._ser_lock:
            return self._ser

    def set_ser(self, ser):
        with self._ser_lock:
            self._ser = ser

    def close_ser(self):
        with self._ser_lock:
            if self._ser:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None


state = _State()


# ── Recalibration log ───────────────────────────────────────────────────────

def _log_recal(action, recal_idx, recal_total, elapsed_s):
    log_path = os.path.join(settings.BASE_DIR, 'recal_log.jsonl')
    entry = {
        'ts':          datetime.now().isoformat(timespec='seconds'),
        'session_id':  state.session_id,
        'job_start':   state.job_start,
        'recal_idx':   recal_idx,
        'recal_total': recal_total,
        'action':      action,
        'elapsed_s':   round(elapsed_s, 2),
    }
    try:
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except OSError:
        pass


def get_recal_log():
    """Return list of log entries (most recent first)."""
    log_path = os.path.join(settings.BASE_DIR, 'recal_log.jsonl')
    entries = []
    try:
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        pass
    return list(reversed(entries))


# ── G-code generation ────────────────────────────────────────────────────────

def _generate_gcode_for_item(item, power, speed, spacing):
    img_path  = os.path.join(settings.IMAGES_DIR, item['image'])
    x_off     = float(item.get('x', 0))
    y_off     = float(item.get('y', 0))
    width_mm  = float(item.get('w', 0))
    height_mm = float(item.get('h', 0))
    rot       = float(item.get('rot', 0))

    img = Image.open(img_path).convert('L')

    px_per_mm = 1.0 / spacing
    if width_mm > 0 and height_mm > 0:
        tw = int(width_mm * px_per_mm)
        th = int(height_mm * px_per_mm)
    elif width_mm > 0:
        tw = int(width_mm * px_per_mm)
        th = int(tw * img.height / img.width)
    else:
        tw = img.width
        th = img.height
    img = img.resize((tw, th), Image.LANCZOS)

    if rot != 0:
        img = img.rotate(rot, expand=True, fillcolor=255)

    w, h = img.size
    px   = img.load()
    DARK = 128
    cmds = []

    for row in range(h):
        y    = y_off + row * spacing
        segs = []
        in_seg = False
        x0 = 0
        for x in range(w):
            d = px[x, row] < DARK
            if d and not in_seg:
                x0 = x
                in_seg = True
            elif not d and in_seg:
                segs.append((x0, x - 1))
                in_seg = False
        if in_seg:
            segs.append((x0, w - 1))

        if not segs:
            continue

        if row % 2 == 0:
            # Even rows: left → right
            for xs, xe in segs:
                cmds.append(f'G0 X{x_off + xs * spacing:.3f} Y{y:.3f}')
                cmds.append(f'M3 S{power}')
                cmds.append(f'G1 F{speed} X{x_off + xe * spacing:.3f}')
                cmds.append('M5')
        else:
            # Odd rows: right → left (same pixels, reversed scan direction)
            for xs, xe in reversed(segs):
                cmds.append(f'G0 X{x_off + xe * spacing:.3f} Y{y:.3f}')
                cmds.append(f'M3 S{power}')
                cmds.append(f'G1 F{speed} X{x_off + xs * spacing:.3f}')
                cmds.append('M5')

    return cmds


def _generate_gcode_layout(layout, power, speed, spacing):
    cmds = ['$32=1', 'G21', 'G90', 'M5']
    for item in layout:
        cmds.extend(_generate_gcode_for_item(item, power, speed, spacing))
    cmds += ['M5', 'G0 X0 Y0']
    return cmds


# ── Serial helpers ───────────────────────────────────────────────────────────

def _readline_ok(ser, stop_event, timeout=30):
    start = time.time()
    buf   = b''
    while time.time() - start < timeout:
        if stop_event.is_set():
            return False
        try:
            if ser.in_waiting:
                ch = ser.read(1)
                buf += ch
                if ch == b'\n':
                    line = buf.decode('utf-8', errors='replace').strip()
                    buf  = b''
                    if 'ok' in line.lower():
                        return True
                    if 'error' in line.lower():
                        return False
            else:
                time.sleep(0.005)
        except OSError:
            time.sleep(0.05)
    return True


def _open_fresh_serial():
    """Open serial with full Arduino reset cycle."""
    ser = serial.Serial(settings.GRBL_PORT, settings.GRBL_BAUD, timeout=3)
    time.sleep(2)
    ser.flushInput()
    return ser


# ── Calibration ──────────────────────────────────────────────────────────────

def calibrate():
    """
    Connect to GRBL, soft-reset, unlock, set G92 X0 Y0.
    Keeps the serial port open so the next engrave can return to this origin
    without a reset (which would lose the position reference).
    """
    if state.thread and state.thread.is_alive():
        return False, 'Идёт гравировка, подождите'

    state.close_ser()
    state.origin_set = False
    state.status  = 'calibrating'
    state.message = 'Подключение для юстировки...'

    try:
        ser = _open_fresh_serial()

        state.message = 'Сброс GRBL...'
        ser.write(b'\x18')
        time.sleep(2)
        ser.flushInput()

        ser.write(b'$X\n')
        time.sleep(0.5)
        ser.flushInput()

        ser.write(b'G92 X0 Y0\n')
        time.sleep(0.3)
        ser.flushInput()

        state.set_ser(ser)
        state.origin_set = True
        state.status  = 'idle'
        state.message = 'Юстировка выполнена — позиция 0,0 задана'
        return True, 'Юстировка выполнена'

    except serial.SerialException as e:
        state.status  = 'error'
        state.message = f'Порт недоступен: {e}'
        return False, f'Порт недоступен: {e}'
    except Exception as e:
        state.status  = 'error'
        state.message = f'Ошибка юстировки: {e}'
        return False, f'Ошибка юстировки: {e}'


def resume_recal(action):
    """
    Called from HTTP handler to unblock a recalibration pause.
    action: 'continue' | 'recalibrate'
    """
    if state.status != 'recalibrating':
        return False, 'Нет активной паузы юстировки'
    state._recal_action = action
    state._recal_event.set()
    return True, 'OK'


# ── Engraving worker ─────────────────────────────────────────────────────────

def _do_recal_pause(ser, seg_i, recal_count, t0):
    """Execute one recalibration pause: move to origin, wait for user."""
    ser.write(b'M5\n')
    time.sleep(0.1)
    ser.write(b'G0 X0 Y0\n')
    _readline_ok(ser, state._stop, timeout=60)

    state.status      = 'recalibrating'
    state.recal_idx   = seg_i + 1
    state.recal_total = recal_count
    state.message     = (
        f'Пауза юстировки {seg_i + 1}/{recal_count} — '
        f'выставьте 0,0 вручную и нажмите «Продолжить» или «Переюстировать»'
    )

    state._recal_event.clear()
    state._recal_event.wait()   # blocks until resume_recal() is called

    action = state._recal_action
    elapsed = time.time() - t0
    _log_recal(action, seg_i + 1, recal_count, elapsed)

    if action == 'recalibrate':
        ser.write(b'G92 X0 Y0\n')
        time.sleep(0.3)
        ser.flushInput()
        state.origin_set = True

    state.status = 'engraving'


def _worker_layout(layout, power, speed, spacing, recal_count):
    try:
        state.status  = 'connecting'
        state.message = 'Подключение к граверу...'

        existing = state.get_ser()
        if state.origin_set and existing and existing.is_open:
            # Calibrated session: reuse connection, return to calibrated origin
            ser = existing
            state.status  = 'homing'
            state.message = 'Возврат к началу (0,0)...'
            ser.write(b'$X\n')
            time.sleep(0.3)
            ser.flushInput()
            ser.write(b'G0 X0 Y0\n')
            _readline_ok(ser, state._stop, timeout=60)
        else:
            # No calibration: fresh connect, reset, set current pos as origin
            ser = _open_fresh_serial()
            state.set_ser(ser)
            state.status  = 'homing'
            state.message = 'Сброс и обнуление...'
            ser.write(b'\x18')
            time.sleep(2)
            ser.flushInput()
            ser.write(b'$X\n')
            time.sleep(1)
            ser.flushInput()
            ser.write(b'G92 X0 Y0\n')
            time.sleep(0.5)

        state.status  = 'generating'
        state.message = 'Генерация G-кода...'
        cmds       = _generate_gcode_layout(layout, power, speed, spacing)
        state.total = len(cmds)

        # Split into segments for periodic recalibration
        if recal_count > 0:
            seg_size = max(1, len(cmds) // (recal_count + 1))
            segments = [cmds[i * seg_size:(i + 1) * seg_size] for i in range(recal_count)]
            segments.append(cmds[recal_count * seg_size:])
        else:
            segments = [cmds]

        state.status  = 'engraving'
        errors        = 0
        t0            = time.time()
        done_cmds     = 0

        for seg_i, segment in enumerate(segments):
            for cmd in segment:
                if state._stop.is_set():
                    ser.write(b'\x18')
                    ser.write(b'M5\n')
                    state.status      = 'stopped'
                    state.message     = 'Остановлено пользователем'
                    state.origin_set  = False
                    state.close_ser()
                    return

                ser.write((cmd + '\n').encode())
                ok = _readline_ok(ser, state._stop)
                if not ok:
                    errors += 1
                    if errors > 5:
                        state.status  = 'error'
                        state.message = 'Слишком много ошибок GRBL'
                        ser.write(b'\x18')
                        state.origin_set = False
                        state.close_ser()
                        return

                done_cmds += 1
                state.progress = int(100 * done_cmds / state.total)

                if done_cmds % 200 == 0:
                    elapsed = time.time() - t0
                    eta = int(elapsed / done_cmds * (state.total - done_cmds))
                    state.message = f'Гравировка {state.progress}% — осталось ~{eta}с'

            # Recalibration pause after segment (except after the last one)
            if seg_i < len(segments) - 1:
                if state._stop.is_set():
                    break
                _do_recal_pause(ser, seg_i, recal_count, t0)

        state.status   = 'done'
        state.progress = 100
        state.message  = 'Готово!'
        state.origin_set = False
        state.close_ser()

    except serial.SerialException as e:
        state.status  = 'error'
        state.message = f'Порт недоступен: {e}'
        state.origin_set = False
        state.close_ser()
    except Exception as e:
        state.status  = 'error'
        state.message = f'Ошибка: {e}'
        state.origin_set = False
        state.close_ser()


# ── G-code file export ───────────────────────────────────────────────────────

def save_gcode(layout, power, speed, spacing):
    """Generate G-code for layout and save to timestamped file. Returns (ok, filename|error)."""
    try:
        cmds     = _generate_gcode_layout(layout, power, speed, spacing)
        filename = f'output_{datetime.now().strftime("%Y%m%d_%H%M%S")}.gcode'
        path     = os.path.join(settings.BASE_DIR, filename)
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(cmds) + '\n')
        return True, filename
    except Exception as e:
        return False, str(e)


def get_gcode_list():
    """Return list of saved gcode files, newest first."""
    result = []
    try:
        for name in sorted(os.listdir(settings.BASE_DIR), reverse=True):
            if name.endswith('.gcode'):
                path = os.path.join(settings.BASE_DIR, name)
                result.append({'name': name, 'size': os.path.getsize(path)})
    except OSError:
        pass
    return result


def read_gcode_file(filename):
    """Return lines of a gcode file (safe: only .gcode from BASE_DIR)."""
    safe = os.path.basename(filename)
    if not safe.endswith('.gcode'):
        return None
    path = os.path.join(settings.BASE_DIR, safe)
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return f.readlines()


# ── Public API ───────────────────────────────────────────────────────────────

def start_layout(layout, power, speed, spacing, recal_count=0):
    if state.thread and state.thread.is_alive():
        return False, 'Уже выполняется'
    state.reset()
    state.session_id = str(uuid.uuid4())[:8]
    state.job_start  = datetime.now().isoformat(timespec='seconds')
    state.recal_total = recal_count
    state.thread = threading.Thread(
        target=_worker_layout,
        args=(layout, power, speed, spacing, recal_count),
        daemon=True,
    )
    state.thread.start()
    return True, 'Запущено'


def start(img_path, power, speed, spacing, x_off, y_off, width_mm):
    """Backward-compatible single-image start."""
    img = Image.open(img_path)
    if width_mm > 0:
        aspect    = img.height / img.width
        height_mm = width_mm * aspect
    else:
        height_mm = 60.0
        width_mm  = 60.0

    layout = [{
        'image': os.path.basename(img_path),
        'x':     x_off,
        'y':     y_off,
        'w':     width_mm,
        'h':     height_mm,
        'rot':   0.0,
    }]
    return start_layout(layout, power, speed, spacing)


def stop():
    state._stop.set()
    # Unblock any waiting recal pause
    state._recal_action = 'continue'
    state._recal_event.set()
    return True


def get_status():
    return {
        'status':       state.status,
        'progress':     state.progress,
        'total':        state.total,
        'message':      state.message,
        'origin_set':   state.origin_set,
        'recal_idx':    state.recal_idx,
        'recal_total':  state.recal_total,
    }


def list_images(directory):
    exts   = {'.png', '.jpg', '.jpeg', '.bmp', '.gif'}
    result = []
    try:
        for f in sorted(os.listdir(directory)):
            if os.path.splitext(f)[1].lower() in exts:
                result.append(f)
    except OSError:
        pass
    return result


def make_preview(layout, work_w=300, work_h=300, canvas_px=600):
    scale    = canvas_px / work_w
    canvas_h = int(work_h * scale)
    canvas   = Image.new('RGB', (canvas_px, canvas_h), (20, 20, 20))

    for item in layout:
        img_path  = os.path.join(settings.IMAGES_DIR, item['image'])
        if not os.path.exists(img_path):
            continue
        x_off     = float(item.get('x', 0))
        y_off     = float(item.get('y', 0))
        width_mm  = float(item.get('w', 60))
        height_mm = float(item.get('h', 60))
        rot       = float(item.get('rot', 0))

        img = Image.open(img_path).convert('RGBA')
        tw  = max(1, int(width_mm  * scale))
        th  = max(1, int(height_mm * scale))
        img = img.resize((tw, th), Image.LANCZOS)

        if rot != 0:
            img = img.rotate(rot, expand=True, fillcolor=(255, 255, 255, 0))

        cx_px   = int((x_off + width_mm / 2) * scale)
        rot_w, rot_h = img.size
        cy_mm   = y_off + height_mm / 2
        cy_px   = canvas_h - int(cy_mm * scale)
        paste_x = cx_px - rot_w // 2
        paste_y = cy_px - rot_h // 2

        canvas.paste(img, (paste_x, paste_y), img)

    buf = io.BytesIO()
    canvas.save(buf, 'PNG')
    return buf.getvalue()
