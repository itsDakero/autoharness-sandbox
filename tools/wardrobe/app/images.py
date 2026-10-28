"""Pillow helpers: strip EXIF/GPS, resize, thumbnail, HEIC to JPEG."""
import io

from PIL import Image, ImageOps

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:  # noqa: BLE001 - HEIC just won't open
    pass

Image.MAX_IMAGE_PIXELS = 120_000_000
PHOTO_PX = 1600
THUMB_PX = 400
TAG_PX = 1024


class BadImage(Exception):
    pass


def _jpeg(im, px, quality):
    im = im.copy()
    im.thumbnail((px, px))
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality)  # no exif= argument: nothing is carried over
    return out.getvalue()


def _open(data):
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
        im = ImageOps.exif_transpose(im)
        return im.convert("RGB")  # new pixel data, metadata gone
    except Exception as e:  # noqa: BLE001
        raise BadImage(str(e)) from None


def process(data):
    """Raw upload bytes -> (photo_jpeg, thumb_jpeg). The original is never kept."""
    im = _open(data)
    return _jpeg(im, PHOTO_PX, 85), _jpeg(im, THUMB_PX, 80)


def tag_image(photo_bytes):
    """Stored photo -> 1024 px JPEG for the vision model."""
    return _jpeg(_open(photo_bytes), TAG_PX, 85)
