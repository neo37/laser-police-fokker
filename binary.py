import os
import sys
from PIL import Image, ImageEnhance

# Расширения изображений, которые обрабатываем
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')

# Значения контрастности по умолчанию (три варианта)
DEFAULT_CONTRAST_FACTORS = [0.5, 1.0, 1.5]

def process_images(contrast_factors):
    folder = os.getcwd()  # текущая директория, откуда запущен скрипт
    image_files = [f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXT)]

    if not image_files:
        print("В текущей папке нет изображений.")
        return

    for file in image_files:
        filepath = os.path.join(folder, file)
        try:
            with Image.open(filepath) as img:
                # Конвертируем в RGB, чтобы избежать проблем с режимами (например, CMYK или P)
                if img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')

                enhancer = ImageEnhance.Contrast(img)
                name, ext = os.path.splitext(file)

                for factor in contrast_factors:
                    out_img = enhancer.enhance(factor)
                    out_filename = f"{name}_contrast_{factor}{ext}"
                    out_path = os.path.join(folder, out_filename)
                    out_img.save(out_path)
                    print(f"Создано: {out_filename} (контраст = {factor})")

        except Exception as e:
            print(f"Ошибка при обработке {file}: {e}")

if __name__ == "__main__":
    # Если переданы аргументы командной строки, используем их как коэффициенты
    if len(sys.argv) > 1:
        try:
            factors = [float(arg) for arg in sys.argv[1:]]
        except ValueError:
            print("Ошибка: аргументы должны быть числами. Использую значения по умолчанию.")
            factors = DEFAULT_CONTRAST_FACTORS
    else:
        factors = DEFAULT_CONTRAST_FACTORS

    print(f"Запуск с коэффициентами контраста: {factors}")
    process_images(factors)
