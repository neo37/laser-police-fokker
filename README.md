# LASER POLICE FOKKER

> Веб-интерфейс управления лазерным гравёром на базе GRBL — с юстировкой, периодической калибровкой и экспортом G-code.

> Web control interface for GRBL-based laser engraver — with calibration, periodic re-zeroing and G-code export.

---

## Оборудование / Hardware

**Лазерный гравёр [ACMER S2](https://www.acmerlaser.com/)**  
Рабочая зона 300×300 мм, контроллер GRBL 1.1, подключение USB→Serial.

**Laser engraver [ACMER S2](https://www.acmerlaser.com/)**  
300×300 mm work area, GRBL 1.1 controller, USB→Serial connection.

---

## Возможности / Features

### RU

- **Канвас с drag-and-drop** — размещай, масштабируй и вращай изображения прямо на рабочей зоне
- **Юстировка стола** — вручную выставь лазер в 0,0, нажми кнопку — система запомнит точку и при следующем запуске вернётся туда без сброса контроллера
- **Периодические паузы калибровки** — задай количество остановок за сессию; машина равномерно паузирует, возвращается в 0,0 и ждёт подтверждения («Продолжить» или «Переюстировать»)
- **Лог юстировок** — все события записываются в `recal_log.jsonl` для сбора статистики накопленной ошибки позиционирования
- **Экспорт G-code** — сгенерируй `.gcode` файл перед запуском, посмотри его на отдельной странице с подсветкой синтаксиса
- **Галерея изображений** — загружай PNG/JPG прямо из браузера
- **Оценка времени** гравировки в реальном времени
- **SSE-поток статуса** — прогресс обновляется без перезагрузки страницы

### EN

- **Drag-and-drop canvas** — place, scale and rotate images directly on the work area
- **Table calibration** — manually position the laser at 0,0, press the button — the system remembers the point and returns to it on the next job without resetting the controller
- **Periodic re-calibration pauses** — set the number of stops per session; the machine pauses at equal intervals, returns to 0,0 and waits for confirmation ("Continue" or "Re-zero")
- **Calibration log** — all events written to `recal_log.jsonl` for accumulated positioning error statistics
- **G-code export** — generate a `.gcode` file before starting, view it on a dedicated page with syntax highlighting
- **Image gallery** — upload PNG/JPG directly from the browser
- **Real-time time estimation**
- **SSE status stream** — progress updates without page reload

---

## Стек / Stack

| Компонент | Версия | Ссылка |
|-----------|--------|--------|
| Python | 3.12 | https://www.python.org/ |
| Django | 5.x | https://www.djangoproject.com/ |
| Pillow | 10.x | https://python-pillow.org/ |
| pyserial | 3.x | https://github.com/pyserial/pyserial |
| GRBL | 1.1 | https://github.com/gnea/grbl |
| python-dotenv | — | https://github.com/theskumar/python-dotenv |

---

## Установка / Installation

```bash
git clone https://github.com/neo37/laser-police-fokker.git
cd laser-police-fokker

python3 -m venv venv
source venv/bin/activate
pip install django pillow pyserial python-dotenv

cp .env.example .env
# отредактируй .env под свой порт / edit .env for your port

python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

Открой в браузере: `http://localhost:8000`

---

## Конфигурация / Configuration

Создай файл `.env` в корне проекта:

```env
SECRET_KEY=your-secret-key-here
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

---

## Юстировка / Calibration workflow

**RU:** Вручную двигай лазерную головку в нужную начальную точку → нажми **«⊕ Задать 0,0»** → система отправит `G92 X0 Y0` в GRBL и сохранит соединение открытым → при запуске гравировки машина вернётся в эту точку командой `G0 X0 Y0` без сброса контроллера.

**EN:** Manually slide the laser head to your desired origin → press **"⊕ Set 0,0"** → the system sends `G92 X0 Y0` to GRBL and keeps the connection open → on engrave start the machine returns to that point via `G0 X0 Y0` without controller reset.

---

## Лог калибровок / Calibration log

Файл `recal_log.jsonl` (один JSON на строку):

```json
{"ts": "2026-05-17T03:45:12", "session_id": "a3f1bc2e", "job_start": "2026-05-17T03:30:00", "recal_idx": 1, "recal_total": 3, "action": "approved", "elapsed_s": 142.3}
{"ts": "2026-05-17T03:52:44", "session_id": "a3f1bc2e", "job_start": "2026-05-17T03:30:00", "recal_idx": 2, "recal_total": 3, "action": "recalibrated", "elapsed_s": 624.1}
```

`action: "approved"` — пользователь подтвердил, дрейфа нет  
`action: "recalibrated"` — пользователь скорректировал 0,0 (дрейф обнаружен)

---

## API

| Метод | URL | Описание |
|-------|-----|----------|
| POST | `/api/calibrate/` | Юстировка — установить 0,0 |
| POST | `/api/engrave-layout/` | Запуск гравировки |
| POST | `/api/resume-recal/` | Продолжить/переюстировать паузу |
| POST | `/api/stop/` | Стоп |
| GET | `/api/status/` | Текущий статус |
| GET | `/api/stream/` | SSE поток статуса |
| POST | `/api/save-gcode/` | Сохранить G-code файл |
| GET | `/gcode/<filename>` | Просмотр G-code |
| GET | `/api/recal-log/` | Лог юстировок |

---

## Лицензия / License

MIT — используй как хочешь.

---

*Сделано для ACMER S2. Работает с любым GRBL-совместимым станком.*  
*Built for ACMER S2. Works with any GRBL-compatible machine.*
