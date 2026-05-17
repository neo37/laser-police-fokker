import json, os, base64, time, mimetypes, io
from PIL import Image
import numpy as np
from django.http import JsonResponse, StreamingHttpResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from django.conf import settings
from . import engraver


def index(request):
    ctx = {
        'work_w':        settings.WORK_WIDTH_MM,
        'work_h':        settings.WORK_HEIGHT_MM,
        'def_power':     settings.DEFAULT_POWER,
        'def_power_pct': settings.DEFAULT_POWER // 10,
        'def_speed':     settings.DEFAULT_SPEED,
        'def_spacing':   settings.DEFAULT_SPACING,
    }
    return render(request, 'laser/index.html', ctx)


def api_images(request):
    imgs = engraver.list_images(settings.IMAGES_DIR)
    return JsonResponse({'images': imgs})


@csrf_exempt
def api_preview(request):
    d      = json.loads(request.body)
    layout = d.get('layout')
    if layout is not None:
        png = engraver.make_preview(layout, settings.WORK_WIDTH_MM, settings.WORK_HEIGHT_MM)
        return JsonResponse({'preview': 'data:image/png;base64,' + base64.b64encode(png).decode()})

    img_path = os.path.join(settings.IMAGES_DIR, d.get('image', ''))
    if not os.path.exists(img_path):
        return JsonResponse({'error': 'not found'}, status=404)
    name = os.path.basename(img_path)
    legacy_layout = [{
        'image': name,
        'x':     float(d.get('x', 0)),
        'y':     float(d.get('y', 0)),
        'w':     float(d.get('width_mm', 60)),
        'h':     float(d.get('width_mm', 60)),
        'rot':   0.0,
    }]
    png = engraver.make_preview(legacy_layout, settings.WORK_WIDTH_MM, settings.WORK_HEIGHT_MM)
    return JsonResponse({'preview': 'data:image/png;base64,' + base64.b64encode(png).decode()})


@csrf_exempt
def api_engrave(request):
    d        = json.loads(request.body)
    img_path = os.path.join(settings.IMAGES_DIR, d.get('image', ''))
    if not os.path.exists(img_path):
        return JsonResponse({'ok': False, 'msg': 'Файл не найден'})
    ok, msg = engraver.start(
        img_path  = img_path,
        power     = int(d.get('power',    settings.DEFAULT_POWER)),
        speed     = int(d.get('speed',    settings.DEFAULT_SPEED)),
        spacing   = float(d.get('spacing', settings.DEFAULT_SPACING)),
        x_off     = float(d.get('x', 0)),
        y_off     = float(d.get('y', 0)),
        width_mm  = float(d.get('width_mm', 0)),
    )
    return JsonResponse({'ok': ok, 'msg': msg})


@csrf_exempt
def api_engrave_layout(request):
    d           = json.loads(request.body)
    layout      = d.get('layout', [])
    power       = int(d.get('power',       settings.DEFAULT_POWER))
    speed       = int(d.get('speed',       settings.DEFAULT_SPEED))
    spacing     = float(d.get('spacing',   settings.DEFAULT_SPACING))
    recal_count = int(d.get('recal_count', 0))
    if not layout:
        return JsonResponse({'ok': False, 'msg': 'Нет изображений в макете'})
    ok, msg = engraver.start_layout(layout, power, speed, spacing, recal_count)
    return JsonResponse({'ok': ok, 'msg': msg})


@csrf_exempt
def api_stop(request):
    engraver.stop()
    return JsonResponse({'ok': True})


def api_status(request):
    return JsonResponse(engraver.get_status())


def api_stream(request):
    def events():
        while True:
            s = engraver.get_status()
            yield f"data: {json.dumps(s)}\n\n"
            if s['status'] in ('done', 'error', 'stopped', 'idle'):
                break
            time.sleep(0.4)
    return StreamingHttpResponse(events(), content_type='text/event-stream')


# ── Calibration ──────────────────────────────────────────────────────────────

@csrf_exempt
def api_calibrate(request):
    ok, msg = engraver.calibrate()
    return JsonResponse({'ok': ok, 'msg': msg, 'origin_set': engraver.state.origin_set})


@csrf_exempt
def api_resume_recal(request):
    d      = json.loads(request.body)
    action = d.get('action', 'continue')
    if action not in ('continue', 'recalibrate'):
        return JsonResponse({'ok': False, 'msg': 'invalid action'})
    ok, msg = engraver.resume_recal(action)
    return JsonResponse({'ok': ok, 'msg': msg})


# ── Recalibration log ────────────────────────────────────────────────────────

def api_recal_log(request):
    entries = engraver.get_recal_log()
    return JsonResponse({'entries': entries})


# ── G-code file ──────────────────────────────────────────────────────────────

@csrf_exempt
def api_save_gcode(request):
    d       = json.loads(request.body)
    layout  = d.get('layout', [])
    power   = int(d.get('power',   settings.DEFAULT_POWER))
    speed   = int(d.get('speed',   settings.DEFAULT_SPEED))
    spacing = float(d.get('spacing', settings.DEFAULT_SPACING))
    if not layout:
        return JsonResponse({'ok': False, 'msg': 'Нет изображений'})
    ok, result = engraver.save_gcode(layout, power, speed, spacing)
    if ok:
        return JsonResponse({'ok': True, 'filename': result})
    return JsonResponse({'ok': False, 'msg': result})


def api_gcode_list(request):
    return JsonResponse({'files': engraver.get_gcode_list()})


def gcode_view(request, filename):
    lines = engraver.read_gcode_file(filename)
    if lines is None:
        raise Http404
    return render(request, 'laser/gcode.html', {
        'filename': filename,
        'lines':    lines,
        'total':    len(lines),
    })


def gcode_download(request, filename):
    safe = os.path.basename(filename)
    if not safe.endswith('.gcode'):
        raise Http404
    path = os.path.join(settings.BASE_DIR, safe)
    if not os.path.exists(path):
        raise Http404
    with open(path, 'rb') as f:
        resp = HttpResponse(f.read(), content_type='text/plain; charset=utf-8')
    resp['Content-Disposition'] = f'attachment; filename="{safe}"'
    return resp


# ── Upload / media ───────────────────────────────────────────────────────────

@csrf_exempt
def api_upload(request):
    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'ok': False, 'msg': 'Нет файла'})
    dest = os.path.join(settings.IMAGES_DIR, f.name)
    with open(dest, 'wb') as out:
        for chunk in f.chunks():
            out.write(chunk)
    return JsonResponse({'ok': True, 'name': f.name})


def _dither(arr, method, threshold):
    if method == 'threshold':
        return (arr >= threshold).astype(np.uint8) * 255
    if method == 'floyd-steinberg':
        img = arr.astype(np.float32)
        h, w = img.shape
        for y in range(h):
            for x in range(w):
                old = img[y, x]; new = 255. if old >= 128. else 0.
                img[y, x] = new; err = old - new
                if x+1 < w:                img[y, x+1]   += err*7/16
                if y+1 < h:
                    if x > 0:              img[y+1, x-1] += err*3/16
                    img[y+1, x]            += err*5/16
                    if x+1 < w:            img[y+1, x+1] += err*1/16
        return (img >= 128).astype(np.uint8) * 255
    if method == 'atkinson':
        img = arr.astype(np.float32)
        h, w = img.shape
        for y in range(h):
            for x in range(w):
                old = img[y, x]; new = 255. if old >= 128. else 0.
                img[y, x] = new; err = (old-new)/8.
                for dy, dx in [(0,1),(0,2),(1,-1),(1,0),(1,1),(2,0)]:
                    ny, nx = y+dy, x+dx
                    if 0 <= ny < h and 0 <= nx < w: img[ny, nx] += err
        return (img >= 128).astype(np.uint8) * 255
    if method == 'bayer':
        size = 8
        m = np.array([[0,2],[3,1]], dtype=np.float32); cur = 2
        while cur < size:
            m = np.asarray(np.bmat([[4*m,4*m+2],[4*m+3,4*m+1]]), dtype=np.float32); cur *= 2
        m = (m+.5)/(cur*cur)*255.
        h, w = arr.shape
        tiled = np.tile(m, (h//cur+1, w//cur+1))[:h, :w]
        return (arr.astype(np.float32) > tiled).astype(np.uint8) * 255
    return (arr >= threshold).astype(np.uint8) * 255


@csrf_exempt
def api_convert_bw(request):
    from PIL import ImageEnhance, ImageFilter
    d          = json.loads(request.body)
    name       = os.path.basename(d.get('image', ''))
    method     = d.get('method',     'floyd-steinberg')
    threshold  = max(0, min(255, int(d.get('threshold', 128))))
    brightness = float(d.get('brightness', 1.0))
    contrast   = float(d.get('contrast',   1.0))
    gamma      = float(d.get('gamma',      1.0))
    blur_r     = float(d.get('blur',       0.0))
    sharpen    = bool(d.get('sharpen',     False))
    invert     = bool(d.get('invert',      False))
    mode       = d.get('mode', 'bw')
    save       = d.get('save', True)

    src_path = os.path.join(settings.IMAGES_DIR, name)
    if not os.path.exists(src_path):
        return JsonResponse({'ok': False, 'msg': 'Файл не найден'})

    img = Image.open(src_path).convert('RGB')
    if brightness != 1.0: img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast   != 1.0: img = ImageEnhance.Contrast(img).enhance(contrast)
    if blur_r     >  0.0: img = img.filter(ImageFilter.GaussianBlur(radius=blur_r))
    if sharpen:            img = img.filter(ImageFilter.SHARPEN)

    gray = img.convert('L')
    if gamma != 1.0:
        gray = gray.point([int((i/255.)**(1./gamma)*255) for i in range(256)])

    arr    = np.array(gray)
    binary = _dither(arr, method, threshold)
    if invert: binary = 255 - binary

    wm = binary >= 128; bm = ~wm

    if mode == 'bw':
        out = np.zeros((*binary.shape, 3), dtype=np.uint8)
        out[wm] = [255,255,255]
        result  = Image.fromarray(out, 'RGB')
    elif mode == 'transparent_white':
        out = np.zeros((*binary.shape, 4), dtype=np.uint8)
        out[bm] = [0,0,0,255]
        result  = Image.fromarray(out, 'RGBA')
    elif mode == 'transparent_black':
        out = np.zeros((*binary.shape, 4), dtype=np.uint8)
        out[wm] = [255,255,255,255]
        result  = Image.fromarray(out, 'RGBA')
    else:
        return JsonResponse({'ok': False, 'msg': 'Неизвестный режим'})

    buf = io.BytesIO()
    result.save(buf, 'PNG')
    preview = 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()

    saved_as = None
    if save:
        stem     = os.path.splitext(name)[0]
        mode_sfx = {'bw':'bw','transparent_white':'tw','transparent_black':'tb'}[mode]
        saved_as = f'{stem}_{method[:3]}_{mode_sfx}_t{threshold}.png'
        result.save(os.path.join(settings.IMAGES_DIR, saved_as), 'PNG')

    return JsonResponse({
        'ok': True, 'preview': preview, 'saved_as': saved_as,
        'black_pct': int(np.sum(bm)/bm.size*100),
    })


def media_img(request, name):
    path = os.path.join(settings.IMAGES_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise Http404
    mime, _ = mimetypes.guess_type(path)
    with open(path, 'rb') as f:
        return HttpResponse(f.read(), content_type=mime or 'image/png')
