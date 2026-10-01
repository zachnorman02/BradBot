"""Unit tests for utils.image_processing (no live Discord connection needed)."""
import os
import sys
import random
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

from utils.image_processing import (
    prepare_role_icon,
    _has_alpha,
    _clear_fully_transparent,
    MAX_ROLE_ICON_BYTES,
    MAX_INPUT_PIXELS,
)


def _png_bytes(image: Image.Image) -> bytes:
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def test_has_alpha_detects_rgba_mode():
    assert _has_alpha(Image.new("RGBA", (4, 4))) is True


def test_has_alpha_false_for_opaque_rgb():
    assert _has_alpha(Image.new("RGB", (4, 4))) is False


def test_has_alpha_detects_palette_transparency():
    img = Image.new("RGBA", (4, 4), (255, 0, 0, 0))
    # Round-trip through a real PNG so the palette mode picks up a genuine
    # tRNS chunk the way an uploaded file would.
    paletted = Image.open(BytesIO(_png_bytes(img.convert("P", palette=Image.ADAPTIVE))))
    assert _has_alpha(paletted) is True


def test_has_alpha_detects_rgb_with_trns_chunk():
    img = Image.new("RGB", (10, 10), (255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG", transparency=(255, 255, 255))
    reopened = Image.open(BytesIO(buf.getvalue()))
    assert _has_alpha(reopened) is True


def test_clear_fully_transparent_zeroes_rgb_under_zero_alpha():
    img = Image.new("RGBA", (2, 1))
    img.putpixel((0, 0), (200, 100, 50, 0))  # fully transparent, but with stray color
    img.putpixel((1, 0), (10, 20, 30, 255))  # fully opaque
    cleared = _clear_fully_transparent(img)
    assert cleared.getpixel((0, 0)) == (0, 0, 0, 0)
    assert cleared.getpixel((1, 0)) == (10, 20, 30, 255)


def test_clear_fully_transparent_leaves_partial_alpha_untouched():
    img = Image.new("RGBA", (1, 1), (10, 20, 30, 128))
    cleared = _clear_fully_transparent(img)
    assert cleared.getpixel((0, 0)) == (10, 20, 30, 128)


def test_prepare_role_icon_preserves_transparency():
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    for x in range(64):
        for y in range(64):
            if (x // 8 + y // 8) % 2 == 0:
                img.putpixel((x, y), (255, 0, 0, 255))
    out = prepare_role_icon(_png_bytes(img))
    out_img = Image.open(BytesIO(out)).convert("RGBA")
    assert out_img.mode == "RGBA"
    extrema = out_img.getchannel("A").getextrema()
    assert extrema == (0, 255)


def test_prepare_role_icon_normalizes_trns_background_to_real_alpha():
    # A grayscale/RGB image with a tRNS chunk (not RGBA mode) should come
    # out the other side as a real alpha channel, not a flattened opaque
    # image -- this is the original transparency bug this module exists to fix.
    img = Image.new("RGB", (40, 40), (255, 255, 255))
    for x in range(10, 30):
        for y in range(10, 30):
            img.putpixel((x, y), (200, 30, 30))
    buf = BytesIO()
    img.save(buf, format="PNG", transparency=(255, 255, 255))

    out = prepare_role_icon(buf.getvalue())
    out_img = Image.open(BytesIO(out)).convert("RGBA")
    assert out_img.getpixel((0, 0))[3] == 0  # corner (was white) is transparent
    assert out_img.getpixel((20, 20))[3] == 255  # center (was red) is opaque


def test_prepare_role_icon_compresses_oversized_opaque_image():
    random.seed(0)
    img = Image.new("RGB", (1200, 1200))
    pixels = img.load()
    for x in range(0, 1200, 4):
        for y in range(0, 1200, 4):
            pixels[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    raw = _png_bytes(img)
    out = prepare_role_icon(raw)
    assert len(out) < len(raw)
    assert len(out) <= MAX_ROLE_ICON_BYTES


def test_prepare_role_icon_compresses_oversized_transparent_image_via_quantize_not_resize():
    random.seed(1)
    img = Image.new("RGBA", (300, 300))
    pixels = img.load()
    for x in range(300):
        for y in range(300):
            n = random.randint(-15, 15)
            a = 255 if (x - 150) ** 2 + (y - 150) ** 2 < 130 ** 2 else 0
            pixels[x, y] = (max(0, min(255, x + n)), max(0, min(255, y + n)), 90, a)
    raw = _png_bytes(img)
    out = prepare_role_icon(raw)
    out_img = Image.open(BytesIO(out))
    assert len(out) <= MAX_ROLE_ICON_BYTES
    # Quantization should have been enough -- dimensions should be untouched.
    assert out_img.size == (300, 300)
    # Must stay a true RGBA PNG, not an indexed P-mode image with a tRNS
    # chunk (the exact encoding this module exists to avoid producing).
    assert out_img.convert("RGBA").mode == "RGBA"
    raw_img_mode_after_quantize_check = Image.open(BytesIO(out))
    assert raw_img_mode_after_quantize_check.mode != "P"


def test_prepare_role_icon_passes_through_animated_gif_unchanged():
    frame1 = Image.new("RGB", (20, 20), (0, 0, 0))
    frame2 = Image.new("RGB", (20, 20), (255, 255, 255))
    buf = BytesIO()
    frame1.save(buf, format="GIF", save_all=True, append_images=[frame2], loop=0)
    raw = buf.getvalue()
    assert prepare_role_icon(raw) == raw


def test_prepare_role_icon_refuses_to_decode_decompression_bomb_scale_input():
    # A declared-size image above MAX_INPUT_PIXELS should be refused before
    # ever being decoded -- returning the original bytes unchanged rather
    # than attempting a (potentially enormous) decode.
    width = 20000
    height = (MAX_INPUT_PIXELS // width) + 100  # safely over the pixel limit
    img = Image.new("RGB", (width, height))
    raw = _png_bytes(img)
    assert prepare_role_icon(raw) == raw


def test_prepare_role_icon_returns_input_unchanged_for_unparseable_data():
    garbage = b"this is not an image"
    assert prepare_role_icon(garbage) == garbage
