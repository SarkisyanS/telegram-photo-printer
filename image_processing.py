from typing import Optional, Tuple

from PIL import Image, ImageOps


def prepare_for_print(input_path: str, output_path: str, max_size: Optional[Tuple[int, int]] = None) -> str:
    """Нормализует фото перед отправкой на печать.

    Пересохраняет как обычный baseline JPEG в RGB — снимает EXIF-поворот,
    прогрессивное кодирование и нестандартные ICC-профили, которые могли
    ломать generic/driverless-конвертер CUPS при печати через AirPrint.
    """
    with Image.open(input_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode != "RGB":
            img = img.convert("RGB")
        if max_size:
            img.thumbnail(max_size, Image.LANCZOS)
        img.save(output_path, format="JPEG", quality=95)
    return output_path
