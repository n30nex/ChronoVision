from pathlib import Path

from PIL import Image, ImageChops, ImageStat


def validate_image(path: Path, settings) -> tuple[bool, str]:
    if not path.exists():
        return False, "file_missing"
    size_mb = path.stat().st_size / (1024 * 1024)
    if size_mb > settings.max_file_size_mb:
        return False, "file_too_large"
    try:
        with Image.open(path) as img:
            fmt = (img.format or "").upper()
            if fmt not in {"JPEG", "PNG", "JPG"}:
                return False, "unsupported_format"
            width, height = img.size
            if width < settings.image_min_width or height < settings.image_min_height:
                return False, "image_too_small"
            if width > settings.image_max_width or height > settings.image_max_height:
                return False, "image_too_large"
            img.verify()
    except (OSError, ValueError):
        return False, "decode_error"
    return True, "ok"


def is_dark_frame(path: Path, threshold: float = 10.0) -> bool:
    try:
        with Image.open(path) as img:
            img = img.convert("L")
            stat = ImageStat.Stat(img)
            return stat.mean[0] < threshold
    except OSError:
        return True


def diff_percent(path_a: Path, path_b: Path) -> float:
    with Image.open(path_a) as img_a, Image.open(path_b) as img_b:
        img_a = img_a.convert("RGB")
        img_b = img_b.convert("RGB")
        if img_a.size != img_b.size:
            img_b = img_b.resize(img_a.size)
        diff = ImageChops.difference(img_a, img_b).convert("L")
        hist = diff.histogram()
        pixels = img_a.size[0] * img_a.size[1]
        changed = sum(hist[26:])
        if pixels == 0:
            return 0.0
        return (changed / pixels) * 100.0
