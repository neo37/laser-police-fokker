import sys
import argparse
from datetime import datetime
import numpy as np
from PIL import Image, ImageFilter

# Контурное бинарное изображение для лазерного гравёра.
# Любой RGB -> grayscale -> детектор краёв (Собель) -> порог -> только 0 и 255.


def to_contour(img, thresh=40, blur=1.0, invert=False, line_white=False):
    """
    :param img: PIL.Image
    :param thresh: порог силы края (0..255), выше -> меньше линий
    :param blur: предварительное размытие (px) для подавления шума, 0 = выкл
    :param invert: поменять местами фон/линии
    :param line_white: True -> белая линия на чёрном (фон 0, линия 255);
                       False -> чёрная линия на белом (фон 255, линия 0) — под гравёр
    :return: PIL.Image режима 'L' с значениями только 0 и 255
    """
    g = img.convert('L')
    if blur and blur > 0:
        g = g.filter(ImageFilter.GaussianBlur(blur))

    a = np.asarray(g, dtype=np.float32)

    # Собель по X и Y
    kx = np.array([[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]], dtype=np.float32)
    ky = np.array([[-1, -2, -1], [0, 0, 0], [1, 2, 1]], dtype=np.float32)

    gx = _convolve(a, kx)
    gy = _convolve(a, ky)
    mag = np.hypot(gx, gy)

    # Бинаризация: край -> True
    edge = mag >= thresh
    if invert:
        edge = ~edge

    if line_white:
        out = np.where(edge, 255, 0).astype(np.uint8)      # линия 255 на фоне 0
    else:
        out = np.where(edge, 0, 255).astype(np.uint8)      # линия 0 на фоне 255

    return Image.fromarray(out, mode='L')


def _convolve(a, k):
    """Свёртка 3x3 с краевым паддингом, без scipy."""
    p = np.pad(a, 1, mode='edge')
    out = np.zeros_like(a)
    for i in range(3):
        for j in range(3):
            out += k[i, j] * p[i:i + a.shape[0], j:j + a.shape[1]]
    return out


def main():
    ap = argparse.ArgumentParser(description="RGB -> контурное бинарное изображение (0/255) для лазера")
    ap.add_argument("input", help="входной файл (любой RGB)")
    ap.add_argument("-o", "--output", help="выходной файл (по умолч. <имя>_contour.png)")
    ap.add_argument("-t", "--thresh", type=int, default=40, help="порог края 0..255 (по умолч. 40)")
    ap.add_argument("-b", "--blur", type=float, default=1.0, help="предв. размытие px (по умолч. 1.0)")
    ap.add_argument("--invert", action="store_true", help="инвертировать фон/линии")
    ap.add_argument("--white-line", action="store_true", help="белая линия на чёрном фоне")
    args = ap.parse_args()

    out = args.output
    if not out:
        base = args.input.rsplit('.', 1)[0]
        # Параметры + дата-время в имя файла, через _
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        parts = [f"t{args.thresh}", f"b{args.blur}",
                 "white-line" if args.white_line else "black-line"]
        if args.invert:
            parts.append("inv")
        out = f"{base}_contour_{'_'.join(parts)}_{ts}.png"

    img = Image.open(args.input)
    res = to_contour(img, thresh=args.thresh, blur=args.blur,
                     invert=args.invert, line_white=args.white_line)
    res.save(out)
    print(f"Сохранено: {out}  ({res.size[0]}x{res.size[1]}, порог={args.thresh})")


if __name__ == "__main__":
    main()
