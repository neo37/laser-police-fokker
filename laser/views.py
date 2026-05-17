import json, os, base64, time, mimetypes
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


def media_img(request, name):
    path = os.path.join(settings.IMAGES_DIR, os.path.basename(name))
    if not os.path.exists(path):
        raise Http404
    mime, _ = mimetypes.guess_type(path)
    with open(path, 'rb') as f:
        return HttpResponse(f.read(), content_type=mime or 'image/png')
