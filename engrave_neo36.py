#!/usr/bin/env python3
"""
Laser engraver script for ACMER S2 (4W)
Engraves 'neo36' via raster scan -> GRBL G-code
"""

import serial
import time
import sys
from PIL import Image, ImageDraw, ImageFont

# === Hardware settings ===
PORT = '/dev/ttyUSB0'
BAUD = 115200

# === Engraving settings (wood/plywood defaults) ===
FEED_RATE    = 2500    # mm/min
LASER_POWER  = 650     # 0-1000 (65% of 4W = 2.6W)
LINE_SPACING = 0.12    # mm between scan lines (~8.5 LPI)
TEXT_HEIGHT_MM = 18    # mm
MARGIN_MM    = 2.0     # mm left/top margin

# Font path
FONT_PATH = '/usr/share/fonts/truetype/ubuntu/UbuntuMono-B.ttf'


def generate_image():
    px_per_mm = 1.0 / LINE_SPACING
    height_px = int(TEXT_HEIGHT_MM * px_per_mm)
    canvas_w  = int(95 * px_per_mm)    # ~95mm wide canvas

    img = Image.new('L', (canvas_w, height_px), color=255)
    draw = ImageDraw.Draw(img)

    font = ImageFont.truetype(FONT_PATH, size=height_px - 4)
    draw.text((4, 2), 'neo36', font=font, fill=0)

    # Flip vertically: PIL Y↓ but GRBL Y↑
    img = img.transpose(Image.FLIP_TOP_BOTTOM)

    img.save('/tmp/neo36_preview.png')
    print(f"Preview: /tmp/neo36_preview.png  ({canvas_w*LINE_SPACING:.1f} x {height_px*LINE_SPACING:.1f} mm)")
    return img


def image_to_gcode(img):
    pixels  = img.load()
    w, h    = img.size
    DARK    = 180  # threshold
    lines   = []

    lines += [
        '; neo36 raster engraving — ACMER S2',
        f'; feed={FEED_RATE}mm/min  power={LASER_POWER}/1000  step={LINE_SPACING}mm',
        '$32=1',      # GRBL laser mode
        'G21',        # mm
        'G90',        # absolute
        'M5',         # laser off
        f'G0 F5000 X{MARGIN_MM:.2f} Y{MARGIN_MM:.2f}',
    ]

    for row in range(h):
        y_mm = MARGIN_MM + row * LINE_SPACING

        # collect dark segments
        segs = []
        in_seg = False
        x0 = 0
        for x in range(w):
            dark = pixels[x, row] < DARK
            if dark and not in_seg:
                x0, in_seg = x, True
            elif not dark and in_seg:
                segs.append((x0, x - 1))
                in_seg = False
        if in_seg:
            segs.append((x0, w - 1))

        if not segs:
            continue

        # boustrophedon on odd rows
        if row % 2 == 1:
            segs = [(w - 1 - e, w - 1 - s) for s, e in reversed(segs)]

        for xs, xe in segs:
            x_start = MARGIN_MM + xs * LINE_SPACING
            x_end   = MARGIN_MM + xe * LINE_SPACING
            lines.append(f'G0 X{x_start:.3f} Y{y_mm:.3f}')
            lines.append(f'M3 S{LASER_POWER}')
            lines.append(f'G1 F{FEED_RATE} X{x_end:.3f}')
            lines.append('M5')

    lines += ['M5', 'G0 X0 Y0', '; done']
    return '\n'.join(lines)


class GRBL:
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baud, timeout=2)
        time.sleep(2)
        self.ser.flushInput()

    def _readline_raw(self, timeout=2):
        start = time.time()
        buf = b''
        while time.time() - start < timeout:
            try:
                if self.ser.in_waiting:
                    ch = self.ser.read(1)
                    buf += ch
                    if ch == b'\n':
                        return buf.decode('utf-8', errors='replace').strip()
            except OSError:
                time.sleep(0.05)
        return buf.decode('utf-8', errors='replace').strip()

    def send(self, cmd, timeout=15):
        try:
            self.ser.write((cmd.strip() + '\n').encode())
        except OSError as e:
            print(f"  Write error: {e}")
            return []
        responses = []
        start = time.time()
        while time.time() - start < timeout:
            line = self._readline_raw(timeout=0.3)
            if line:
                responses.append(line)
                if 'ok' in line.lower() or 'error' in line.lower():
                    return responses
        return responses

    def raw_send(self, data):
        """Send raw bytes (for special GRBL commands like ~ Ctrl+X)"""
        try:
            self.ser.write(data)
            time.sleep(0.3)
            self.ser.flushInput()
        except OSError:
            pass

    def status(self):
        try:
            self.ser.write(b'?')
            return self._readline_raw(2)
        except OSError:
            return 'error'

    def wake(self):
        try:
            self.ser.write(b'\r\n')
            time.sleep(0.5)
            self.ser.flushInput()
        except OSError:
            pass

    def reset_and_unlock(self):
        """Soft reset + unlock from Alarm/Door states"""
        print("  Soft reset (Ctrl+X)...")
        self.raw_send(b'\x18')   # Ctrl+X = GRBL soft reset
        time.sleep(2)
        self.ser.flushInput()

        status = self.status()
        print(f"  After reset: {status}")

        if 'Door' in status:
            print("  Door hold detected — sending cycle-start (~)...")
            self.raw_send(b'~')   # cycle start / resume
            time.sleep(1)
            status = self.status()
            print(f"  After cycle-start: {status}")

        if 'Alarm' in status:
            print("  Alarm state — sending $X to unlock...")
            self.send('$X')
            time.sleep(0.5)
            status = self.status()
            print(f"  After $X: {status}")

        return status

    def stream_gcode(self, gcode_str):
        lines = [l.strip() for l in gcode_str.splitlines()
                 if l.strip() and not l.strip().startswith(';')]
        total = len(lines)
        print(f"Streaming {total} G-code lines to engraver...")
        errors = 0
        for i, cmd in enumerate(lines):
            resp = self.send(cmd, timeout=30)
            if any('error' in r.lower() for r in resp):
                print(f"  GRBL error at line {i}: {cmd!r} -> {resp}")
                errors += 1
                if errors > 5:
                    print("Too many errors, aborting.")
                    return False
            if i % 300 == 0 and i > 0:
                pct = 100 * i // total
                print(f"  {pct}% ({i}/{total})")
        return True

    def close(self):
        self.ser.close()


def main():
    print("=== ACMER S2 Laser Engraver — 'neo36' ===\n")

    # 1. Generate image + G-code
    print("Rendering text image...")
    img = generate_image()

    print("Generating G-code...")
    gcode = image_to_gcode(img)

    gcode_path = '/tmp/neo36.gcode'
    with open(gcode_path, 'w') as f:
        f.write(gcode)
    line_count = len([l for l in gcode.splitlines() if l.strip() and not l.startswith(';')])
    print(f"G-code saved: {gcode_path}  ({line_count} commands)\n")

    # 2. Connect
    print(f"Connecting to {PORT} @ {BAUD}...")
    try:
        ctrl = GRBL(PORT, BAUD)
    except serial.SerialException as e:
        print(f"ERROR: Cannot open {PORT}: {e}")
        sys.exit(1)

    ctrl.wake()
    status = ctrl.status()
    print(f"GRBL status: {status}")

    if 'Door' in status or 'Alarm' in status:
        status = ctrl.reset_and_unlock()

    if 'Door' in status or 'Alarm' in status:
        print(f"ERROR: Cannot clear GRBL state: {status}")
        ctrl.close()
        sys.exit(1)

    # 3. Settings summary
    print("\n--- Engraving settings ---")
    print(f"  Text:         neo36")
    print(f"  Height:       {TEXT_HEIGHT_MM} mm")
    print(f"  Feed rate:    {FEED_RATE} mm/min")
    print(f"  Laser power:  {LASER_POWER}/1000 ({LASER_POWER//10}%)")
    print(f"  Line spacing: {LINE_SPACING} mm")
    print(f"  Work origin:  X{MARGIN_MM} Y{MARGIN_MM} (current position = 0,0)")
    print("--------------------------\n")

    # 4. Stream G-code
    ok = ctrl.stream_gcode(gcode)
    ctrl.close()

    if ok:
        print("\nEngraving complete!")
    else:
        print("\nEngraving finished with errors.")
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
