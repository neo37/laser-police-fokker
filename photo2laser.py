#!/usr/bin/env python3
"""
photo2laser.py — конвертация RGB-фото в бинарное изображение для лазерной гравировки.

Поддерживаемые методы дизеринга:
  floyd-steinberg  — диффузия ошибки, лучшая детализация (по умолчанию)
  atkinson         — мягче тени, популярен для гравировки
  bayer            — регулярная сетка точек, предсказуемый результат
  threshold        — простой порог, самый быстрый

Использование:
  python3 photo2laser.py фото.jpg гравировка.png
  python3 photo2laser.py фото.jpg гравировка.png --method atkinson --contrast 1.4
  python3 photo2laser.py фото.jpg гравировка.png --method bayer --invert --dpi 254
  python3 photo2laser.py фото.jpg гравировка.png --gamma 1.8 --sharpen --width-mm 80
"""

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter


# ---------------------------------------------------------------------------
# Алгоритмы дизеринга
# ---------------------------------------------------------------------------

def floyd_steinberg(arr: np.ndarray) -> np.ndarray:
    """Floyd-Steinberg error diffusion."""
    img = arr.astype(np.float32)
    h, w = img.shape
    for y in range(h):
        for x in range(w):
            old = img[y, x]
            new = 255.0 if old >= 128.0 else 0.0
            img[y, x] = new
            err = old - new
            if x + 1 < w:
                img[y, x + 1]     += err * 7 / 16
            if y + 1 < h:
                if x > 0:
                    img[y + 1, x - 1] += err * 3 / 16
                img[y + 1, x]     += err * 5 / 16
                if x + 1 < w:
                    img[y + 1, x + 1] += err * 1 / 16
    return (img >= 128).astype(np.uint8) * 255


def atkinson(arr: np.ndarray) -> np.ndarray:
    """Atkinson dithering — светлее теней, хорош для фото."""
    img = arr.astype(np.float32)
    h, w = img.shape
    for y in range(h):
        for x in range(w):
            old = img[y, x]
            new = 255.0 if old >= 128.0 else 0.0
            img[y, x] = new
            err = (old - new) / 8.0
            for dy, dx in [(0, 1), (0, 2), (1, -1), (1, 0), (1, 1), (2, 0)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    img[ny, nx] += err
    return (img >= 128).astype(np.uint8) * 255


def bayer(arr: np.ndarray, size: int = 8) -> np.ndarray:
    """Ordered (Bayer matrix) dithering."""
    base = np.array([[0, 2], [3, 1]], dtype=np.float32)
    m = base
    cur = 2
    while cur < size:
        m = np.bmat([[4 * m, 4 * m + 2], [4 * m + 3, 4 * m + 1]])
        cur *= 2
    m = np.asarray(m, dtype=np.float32)
    m = (m + 0.5) / (cur * cur) * 255.0
    h, w = arr.shape
    tiled = np.tile(m, (h // cur + 1, w // cur + 1))[:h, :w]
    return (arr.astype(np.float32) > tiled).astype(np.uint8) * 255


def simple_threshold(arr: np.ndarray, level: int = 128) -> np.ndarray:
    """Простой порог."""
    return (arr >= level).astype(np.uint8) * 255


METHODS = {
    'floyd-steinberg': floyd_steinberg,
    'atkinson':        atkinson,
    'bayer':           bayer,
    'threshold':       simple_threshold,
}


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------

def process(
    input_path: str,
    output_path: str,
    method: str = 'floyd-steinberg',
    threshold_level: int = 128,
    brightness: float = 1.0,
    contrast: float = 1.0,
    gamma: float = 1.0,
    blur: float = 0.0,
    sharpen: bool = False,
    invert: bool = False,
    dpi: int | None = None,
    width_mm: float | None = None,
    scale: float = 1.0,
) -> None:
    img = Image.open(input_path).convert('RGB')
    print(f"Входное изображение: {img.width}×{img.height} px")

    # Масштабирование по физической ширине гравировки
    if width_mm is not None:
        if dpi is None:
            dpi = 254  # 10 точек/мм
        px_per_mm = dpi / 25.4
        target_w = int(width_mm * px_per_mm)
        target_h = int(img.height * target_w / img.width)
        img = img.resize((target_w, target_h), Image.LANCZOS)
        print(f"  → {target_w}×{target_h} px при {dpi} DPI ({width_mm} мм шириной)")
    elif scale != 1.0:
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)

    if brightness != 1.0:
        img = ImageEnhance.Brightness(img).enhance(brightness)
    if contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(contrast)
    if blur > 0.0:
        img = img.filter(ImageFilter.GaussianBlur(radius=blur))
    if sharpen:
        img = img.filter(ImageFilter.SHARPEN)

    gray = img.convert('L')

    if gamma != 1.0:
        table = [int((i / 255.0) ** (1.0 / gamma) * 255) for i in range(256)]
        gray = gray.point(table)

    arr = np.array(gray)

    if method == 'threshold':
        result = simple_threshold(arr, threshold_level)
    else:
        result = METHODS[method](arr)

    if invert:
        result = 255 - result

    out = Image.fromarray(result, mode='L').convert('1')

    save_kwargs: dict = {}
    if dpi:
        save_kwargs['dpi'] = (dpi, dpi)

    out.save(output_path, **save_kwargs)

    # Статистика
    black_px = int(np.sum(result == 0))
    total_px = result.size
    fill = black_px / total_px * 100
    print(f"Выходное изображение: {out.width}×{out.height} px")
    print(f"  Метод: {method}  |  Заполнение: {fill:.1f}%  |  Инверт: {invert}")
    if dpi:
        print(f"  DPI: {dpi}  |  Размер: {out.width/dpi*25.4:.1f}×{out.height/dpi*25.4:.1f} мм")
    print(f"Сохранено → {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog='photo2laser',
        description='Конвертация RGB-фото в бинарное изображение для лазерной гравировки',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument('input',  help='Входной файл (JPG, PNG, BMP, …)')
    parser.add_argument('output', help='Выходной файл (рекомендуется PNG)')

    parser.add_argument('-m', '--method',
        choices=list(METHODS), default='floyd-steinberg',
        help='Метод дизеринга (по умолчанию: floyd-steinberg)')
    parser.add_argument('-t', '--threshold', type=int, default=128,
        metavar='0-255', help='Порог для метода threshold (по умолчанию: 128)')

    parser.add_argument('-b', '--brightness', type=float, default=1.0,
        help='Яркость: 0.5=темнее, 2.0=светлее (по умолчанию: 1.0)')
    parser.add_argument('-c', '--contrast', type=float, default=1.0,
        help='Контрастность: 1.5=больше контраста (по умолчанию: 1.0)')
    parser.add_argument('-g', '--gamma', type=float, default=1.0,
        help='Гамма: >1 светлее полутона, <1 темнее (по умолчанию: 1.0)')
    parser.add_argument('--blur', type=float, default=0.0,
        help='Радиус Гауссова размытия перед обработкой (по умолчанию: 0)')
    parser.add_argument('-s', '--sharpen', action='store_true',
        help='Применить резкость перед обработкой')
    parser.add_argument('-i', '--invert', action='store_true',
        help='Инвертировать вывод (поменять белое и чёрное)')

    parser.add_argument('--dpi', type=int, default=None,
        help='DPI выходного файла, например 254 (10 точек/мм)')
    parser.add_argument('--width-mm', type=float, default=None,
        help='Целевая ширина гравировки в мм (масштабирует изображение)')
    parser.add_argument('--scale', type=float, default=1.0,
        help='Произвольный масштаб (по умолчанию: 1.0)')

    args = parser.parse_args()

    if not Path(args.input).exists():
        print(f'Ошибка: файл не найден: {args.input}', file=sys.stderr)
        sys.exit(1)

    process(
        input_path=args.input,
        output_path=args.output,
        method=args.method,
        threshold_level=args.threshold,
        brightness=args.brightness,
        contrast=args.contrast,
        gamma=args.gamma,
        blur=args.blur,
        sharpen=args.sharpen,
        invert=args.invert,
        dpi=args.dpi,
        width_mm=args.width_mm,
        scale=args.scale,
    )


if __name__ == '__main__':
    main()
