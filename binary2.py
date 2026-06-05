import os
import sys
from PIL import Image, ImageDraw
import qrcode

# Расширения изображений, которые обрабатываем (для получения размера)
IMAGE_EXT = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp')

# Данные для QR-кода (можно переопределить аргументом)
DEFAULT_QR_DATA = "https://github.com/yourname"

def create_colored_image_with_qr(size, color, qr_data, qr_size=150, margin=20):
    """
    Создаёт изображение заданного цвета с QR-кодом в правом нижнем углу.
    :param size: (width, height)
    :param color: 'black' или 'white'
    :param qr_data: строка для QR
    :param qr_size: размер QR в пикселях
    :param margin: отступ от краёв
    :return: PIL Image
    """
    # Фон
    if color == 'black':
        bg_color = (0, 0, 0)
        qr_fill = "white"
        qr_back = "black"
    else:  # white
        bg_color = (255, 255, 255)
        qr_fill = "black"
        qr_back = "white"

    img = Image.new('RGB', size, color=bg_color)

    # Создаём QR-код
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(qr_data)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=qr_fill, back_color=qr_back).convert('RGB')

    # Масштабируем
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.LANCZOS)

    # Позиция
    x = size[0] - qr_size - margin
    y = size[1] - qr_size - margin

    img.paste(qr_img, (x, y))
    return img

def process_images(qr_data):
    folder = os.getcwd()
    image_files = [f for f in os.listdir(folder) if f.lower().endswith(IMAGE_EXT)]

    if not image_files:
        print("В текущей папке нет изображений.")
        return

    for file in image_files:
        filepath = os.path.join(folder, file)
        try:
            with Image.open(filepath) as img:
                size = img.size  # (width, height)

            name, ext = os.path.splitext(file)

            # Чёрное изображение с QR
            black_img = create_colored_image_with_qr(size, 'black', qr_data)
            black_filename = f"{name}_black_with_qr{ext}"
            black_path = os.path.join(folder, black_filename)
            black_img.save(black_path)
            print(f"Создано: {black_filename} (чёрный фон, QR: {qr_data})")

            # Белое изображение с QR
            white_img = create_colored_image_with_qr(size, 'white', qr_data)
            white_filename = f"{name}_white_with_qr{ext}"
            white_path = os.path.join(folder, white_filename)
            white_img.save(white_path)
            print(f"Создано: {white_filename} (белый фон, QR: {qr_data})")

        except Exception as e:
            print(f"Ошибка при обработке {file}: {e}")

if __name__ == "__main__":
    qr_data = DEFAULT_QR_DATA
    if len(sys.argv) > 1:
        qr_data = sys.argv[1]  # первый аргумент — текст для QR
    print(f"QR-код содержит: {qr_data}")
    process_images(qr_data)
