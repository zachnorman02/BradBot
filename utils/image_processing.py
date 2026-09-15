"""Image normalization for role icon uploads.

Discord role icons must be under 256 KB and are only ever shown tiny
(Discord itself recommends 64x64), so raw user uploads need to be
recompressed (and sometimes downscaled) before being handed to the API.
They also need to go through Pillow at all if we want transparency to
reliably survive: passing an uploaded PNG's bytes straight through
preserves whatever encoding the user's tool produced it with (indexed "P"
mode with a tRNS chunk, odd color profiles, etc.), and some of those don't
round-trip through Discord's own image pipeline -- the alpha gets dropped
and the "transparent" areas render solid black instead. Re-encoding through
Pillow as a real RGBA PNG sidesteps that.
"""
import logging
from io import BytesIO

from PIL import Image

logger = logging.getLogger(__name__)

MAX_ROLE_ICON_BYTES = 256 * 1024
# Sanity ceiling only -- bounds worst-case processing cost on an absurdly
# large upload. Real compression happens via quantize/JPEG quality below;
# most uploads never hit this, since color reduction alone usually gets a
# role icon under the size limit without losing any resolution.
SANITY_MAX_DIMENSION = 1024
# Refuse to even decode an input above this many pixels. Image.open() only
# parses the header, so this check happens before the expensive part;
# without it, a small file that declares an enormous pixel grid (a classic
# "decompression bomb") gets fully decoded into memory before anything
# here gets a chance to shrink it back down. Ordinary uploads -- even a
# large photo -- land nowhere near this.
MAX_INPUT_PIXELS = 40_000_000  # ~40 MP, e.g. an 8000x5000 image
MIN_DIMENSION = 32  # last-resort floor if quantize/quality alone can't hit the size limit
MIN_JPEG_QUALITY = 35
# Palette sizes to try, largest first, when a transparent PNG needs to shrink.
# Same idea as pngquant/TinyPNG: dropping to fewer colors usually cuts file
# size far more than resizing does, without touching the actual dimensions.
QUANTIZE_STEPS = (256, 192, 128, 96, 64, 48, 32)


def _has_alpha(image: Image.Image) -> bool:
    if image.mode in ("RGBA", "LA"):
        return True
    # A grayscale/RGB/palette PNG can still carry a tRNS chunk marking one
    # color value as transparent -- Pillow surfaces that as `info`, not mode.
    return "transparency" in image.info


def _encode_png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def _encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True)
    return buffer.getvalue()


def _clear_fully_transparent(image: Image.Image) -> Image.Image:
    """Zero out RGB wherever alpha is exactly 0.

    Editors/exporters often leave stray color data under fully-transparent
    pixels (e.g. whatever was last drawn there). It's invisible to any
    correct alpha-aware renderer, but it's dead weight for compression --
    zeroing it turns "transparent" into one uniform value the encoder can
    flatten instead of a field of pointless colors -- and it removes the
    one thing a not-quite-alpha-aware renderer could latch onto and show
    as a solid background. Partially-transparent (anti-aliased edge)
    pixels are left alone since their RGB still matters for blending.
    """
    mask = image.getchannel("A").point(lambda a: 255 if a == 0 else 0)
    return Image.composite(Image.new("RGBA", image.size, (0, 0, 0, 0)), image, mask)


def _quantize(image: Image.Image, colors: int) -> Image.Image:
    # FASTOCTREE is the quantize method that understands a source alpha
    # channel; the default (MEDIANCUT) would just drop it.
    return image.quantize(colors=colors, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)


def _shrink(image: Image.Image) -> Image.Image | None:
    """One resize step down, or None if we're already at the size floor."""
    new_size = tuple(max(MIN_DIMENSION, int(dim * 0.85)) for dim in image.size)
    if new_size == image.size:
        return None
    return image.resize(new_size, Image.LANCZOS)


def _compress_transparent(image: Image.Image, max_bytes: int) -> bytes:
    encoded = _encode_png(image)
    if len(encoded) <= max_bytes:
        return encoded

    for colors in QUANTIZE_STEPS:
        encoded = _encode_png(_quantize(image, colors))
        if len(encoded) <= max_bytes:
            return encoded

    # Palette reduction alone wasn't enough -- keep shrinking dimensions
    # (at the smallest palette already tried) until it fits or bottoms out.
    while len(encoded) > max_bytes:
        smaller = _shrink(image)
        if smaller is None:
            break
        image = smaller
        encoded = _encode_png(_quantize(image, QUANTIZE_STEPS[-1]))

    return encoded


def _compress_opaque(image: Image.Image, max_bytes: int) -> bytes:
    quality = 90
    encoded = _encode_jpeg(image, quality)

    while len(encoded) > max_bytes:
        if quality > MIN_JPEG_QUALITY:
            quality = max(MIN_JPEG_QUALITY, quality - 15)
        else:
            smaller = _shrink(image)
            if smaller is None:
                break
            image = smaller
            quality = 90
        encoded = _encode_jpeg(image, quality)

    return encoded


def prepare_role_icon(data: bytes, *, max_bytes: int = MAX_ROLE_ICON_BYTES) -> bytes:
    """Re-encode an uploaded image so it's a valid, correctly-sized role icon.

    Transparent images are always normalized to a real RGBA PNG (fixing
    encodings that would otherwise render as a black background). If that's
    still over the size limit, colors are quantized down before dimensions
    are ever touched, same as a PNG-compressor website would do. Opaque
    images are recompressed as JPEG with progressively lower quality, then
    downscaled if quality alone can't get there. Animated images (e.g. GIF)
    are left untouched since shrinking them safely would mean recompressing
    every frame -- Discord's own upload validation is left to reject them
    if they don't fit.

    Falls back to returning `data` unchanged if Pillow can't read it,
    leaving the original error handling (Discord rejects the bytes) as the
    safety net.
    """
    try:
        image = Image.open(BytesIO(data))
        width, height = image.size
        if width * height > MAX_INPUT_PIXELS:
            logger.warning(f"Uploaded icon is {width}x{height}; refusing to decode, using as-is")
            return data
        image.load()
    except Exception as e:
        logger.warning(f"Could not process uploaded icon image, using as-is: {e}")
        return data

    if getattr(image, "is_animated", False):
        return data

    has_alpha = _has_alpha(image)
    image = image.convert("RGBA" if has_alpha else "RGB")
    if has_alpha:
        image = _clear_fully_transparent(image)

    if max(image.size) > SANITY_MAX_DIMENSION:
        image.thumbnail((SANITY_MAX_DIMENSION, SANITY_MAX_DIMENSION), Image.LANCZOS)

    if has_alpha:
        return _compress_transparent(image, max_bytes)
    return _compress_opaque(image, max_bytes)
