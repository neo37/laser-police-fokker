# LASER POLICE FOKKER

*"The laser does not care about your feelings. It cares about photons, focal length, and whether the G-code is syntactically correct."*

---

Consider, for a moment, the humble stepper motor. Inside a chassis of powder-coated steel, two of them sit at perpendicular angles to each other, translating digital pulse sequences into physical displacement with a precision that would have seemed frankly miraculous to anyone who has ever tried to draw a straight line by hand. The laser itself — a diode pumping out somewhere between 5 and 10 watts of coherent light at 450 nm, which is to say a very aggressive shade of blue — is bolted to a gantry that rides those steppers, and together this arrangement constitutes what the marketing department of [ACMER](https://www.acmerlaser.com/) has chosen to call the S2.

The S2 speaks [GRBL](https://github.com/gnea/grbl). GRBL is a dialect of G-code, which is itself a programming language invented in the 1950s by MIT researchers who could not have imagined that it would one day be used to etch images of cats onto pieces of wood in people's apartments. GRBL runs on an ATmega328P — the same chip inside every Arduino Uno that has ever been purchased with the best of intentions and left in a drawer — and communicates over USB-serial at 115200 baud, which is fast enough that the latency is not your bottleneck. Your bottleneck is the speed at which you are willing to move a laser across a surface without setting it on fire.

**LASER POLICE FOKKER** is the web application that sits between you and all of this.

---

## What It Actually Does

### На русском

Это Django-приложение, которое превращает браузер в пульт управления лазерным гравёром. Ты загружаешь изображения, раскладываешь их на холсте, выставляешь параметры — и машина работает. Но главное не это.

Главное — **юстировка**. Любой, кто работал с ЧПУ-станком без концевых выключателей, знает проблему: после каждого включения контроллер не имеет ни малейшего представления о том, где находится рабочий орган в пространстве. Стандартное решение — «мы стартуем оттуда, где стоим». Это работает для одного запуска. Для серийной работы — не очень.

**LASER POLICE FOKKER** решает это через механизм постоянного соединения: ты вручную ставишь лазер в нужную точку, нажимаешь «Задать 0,0» — контроллер получает `G92 X0 Y0` и запоминает. Соединение остаётся открытым. При следующем запуске гравировки машина командой `G0 X0 Y0` возвращается именно туда, не теряя контекст из-за DTR-сброса Arduino.

Дополнительно — **периодические паузы калибровки**. Ты задаёшь количество остановок за сессию. Машина равномерно паузирует, возвращается в ноль, ждёт. Ты смотришь, совпадает ли лазер с реперной точкой. Нажимаешь «Продолжить» или «Переюстировать». Всё это логируется в JSONL — чтобы потом посчитать, через сколько минут работы начинается статистически значимый дрейф.

### In English

This is a [Django](https://www.djangoproject.com/) application. It presents you with a canvas — a 2D representation of your 300×300 mm work area, rendered in a dark color scheme appropriate for people who take their tools seriously — onto which you drag images, resize them, rotate them, and generally compose the layout of your engraving job before committing photons to substrate.

The calibration system — and this is the part that required actual thought — addresses the fundamental epistemic problem of a GRBL controller that has been power-cycled: it does not know where it is. Conventional wisdom says you just set `G92 X0 Y0` at the start of every job, declaring "here, wherever here happens to be, is zero." This works. It is also, if you are doing precision repeat work, a source of cumulative error that will drive you slowly insane.

The solution implemented here involves keeping the serial connection alive across the calibration-to-engrave cycle, thereby preventing the Arduino's DTR line from triggering a reset that would flush the coordinate context. Calibrate once, engrave many times, return to the same physical point each time via `G0 X0 Y0`. The controller remembers because we never gave it the opportunity to forget.

The periodic re-calibration pause system generates a `recal_log.jsonl` file — one JSON object per line, because CSV is for people who haven't thought carefully about nested data — that records, for each pause, whether the operator found the machine to be on-target ("approved") or needed to re-zero ("recalibrated"), along with elapsed time. Plot this data across enough sessions and you will have an empirical model of your machine's positional drift. This is the kind of thing that seems obsessive until the moment you actually need it.

---

## Hardware

**[ACMER S2 Laser Engraver](https://www.acmerlaser.com/)**  
300×300 mm work area · GRBL 1.1 · USB Serial · ~10W diode laser @ 450nm

The S2 is a competent machine. It will not embarrass you. The frame is rigid enough that flexion is not a significant source of error. The stepper drivers are not exceptional but are not bad. The laser module is what it is — a component chosen by a procurement department somewhere in Shenzhen that nonetheless delivers consistent results when you give it sensible G-code and do not ask it to move faster than physics permits.

---

## Stack

| Component | What it is | Link |
|-----------|-----------|------|
| **Python 3.12** | The language. Still the right choice for hardware control in 2026, despite what the Rust evangelists will tell you. | https://www.python.org/ |
| **Django** | A web framework so thoroughly documented that its documentation has documentation. | https://www.djangoproject.com/ |
| **Pillow** | PIL's maintained fork. Handles image loading, resizing, rotation, and the conversion of pixel darkness values into G-code laser-on segments. | https://python-pillow.org/ |
| **pyserial** | Serial port communication. The layer between Python strings and the electrons that move stepper motors. | https://github.com/pyserial/pyserial |
| **GRBL 1.1** | The firmware. Runs on the ATmega328P inside the controller. Accepts G-code, produces motion. | https://github.com/gnea/grbl |
| **python-dotenv** | Configuration from `.env` files. Because hardcoding port names is the kind of thing that ends friendships. | https://github.com/theskumar/python-dotenv |

---

## Installation

```bash
git clone https://github.com/neo37/laser-police-fokker.git
cd laser-police-fokker

python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install django pillow pyserial python-dotenv

cp .env.example .env
# Edit .env — at minimum, set GRBL_PORT to wherever your machine appears
# On Linux this is typically /dev/ttyUSB0
# On macOS it will be something like /dev/tty.usbserial-XXXX
# On Windows, COM3 or similar

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Navigate to `http://localhost:8000`. The application will be there, waiting, in the way that software waits — which is to say it is executing an event loop.

---

## Configuration (`.env`)

```env
SECRET_KEY=generate-something-unguessable-here
DEBUG=True
GRBL_PORT=/dev/ttyUSB0
GRBL_BAUD=115200
WORK_WIDTH_MM=300
WORK_HEIGHT_MM=300
IMAGES_DIR=/path/to/your/images
DEFAULT_POWER=650
DEFAULT_SPEED=2500
DEFAULT_LINE_SPACING=0.12
```

`DEFAULT_POWER` is on a scale of 0–1000 (GRBL S-value). 650 is roughly 65%. Start lower and work up. Burning through your workpiece is irreversible. This is not a metaphor; it is a practical observation about the conservation of material.

`DEFAULT_LINE_SPACING` of 0.12 mm means your engraving will have approximately 8 lines per millimeter. This produces results that look good on wood and leather. For finer materials, go lower. For faster results at the cost of visible scan lines, go higher. There is no objectively correct value — there is only the value appropriate for your specific combination of material, power, and patience.

---

## Calibration — A Technical Note

The core of the calibration system is the observation that Arduino-based GRBL controllers reset when you open a serial connection (the DTR line asserts, the microcontroller reboots, your coordinate context evaporates). This means that `G92 X0 Y0` set during one connection is gone before the next connection even finishes establishing.

The solution: open the connection during calibration and *do not close it*. The `state._ser` object persists in memory. When you press Engrave, the worker thread checks `state.origin_set` and, if true, reuses the existing connection — executing `G0 X0 Y0` to return to the calibrated origin before beginning the job.

If the connection drops (power cycle, cable pulled, cosmic ray event), `state.origin_set` becomes False and the system falls back to the conventional "wherever you are is zero" behavior. It degrades gracefully, which is the best you can ask of any system that involves hardware.

---

## The Calibration Log

`recal_log.jsonl` — one JSON object per pause event:

```json
{"ts": "2026-05-17T03:45:12", "session_id": "a3f1bc2e", "recal_idx": 1, "recal_total": 3, "action": "approved", "elapsed_s": 142.3}
{"ts": "2026-05-17T03:52:44", "session_id": "a3f1bc2e", "recal_idx": 2, "recal_total": 3, "action": "recalibrated", "elapsed_s": 624.1}
```

`"approved"` — the operator inspected the 0,0 position and found it acceptable. The machine had not drifted meaningfully.

`"recalibrated"` — the operator found drift, corrected the position, and issued a new `G92 X0 Y0`. The `elapsed_s` value tells you how long the machine had been running before drift became detectable.

Across enough sessions, this data will tell you whether your machine drifts at all, how fast, and whether the drift correlates with elapsed time, temperature, or the particular alignment of Mercury.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/calibrate/` | Connect, reset, unlock, `G92 X0 Y0`. Keeps connection open. |
| `POST` | `/api/engrave-layout/` | Start engraving job with layout JSON |
| `POST` | `/api/resume-recal/` | Unblock calibration pause (`action`: `continue` or `recalibrate`) |
| `POST` | `/api/stop/` | Emergency stop |
| `GET`  | `/api/status/` | Current machine state |
| `GET`  | `/api/stream/` | SSE event stream |
| `POST` | `/api/save-gcode/` | Generate and save `.gcode` file |
| `GET`  | `/gcode/<filename>` | G-code viewer with syntax highlighting |
| `GET`  | `/api/recal-log/` | Calibration log entries |

---

## License

MIT. Use it, modify it, engrave it onto something.

---

*Built for the [ACMER S2](https://www.acmerlaser.com/). Works with any GRBL-compatible machine.*

*Dedicated to Victor Pelevin, Andrei Gorohov and Neal Stephenson —  
three writers who understood that the interface between human intention and physical reality  
is always more complicated than the documentation suggests.*
