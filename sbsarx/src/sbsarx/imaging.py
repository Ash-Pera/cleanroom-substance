"""Turning a resource's bytes into an image file.

Raw resources are uncompressed, planar-free, top-down pixel data with no mipmaps and no
padding: `width * height * channels * bytes_per_channel` bytes and nothing else. JPEG
resources are ordinary JFIF files. So decoding needs no format-specific cleverness —
only the geometry the descriptor already states.

Pillow and NumPy are optional. Without them `raw_to_png` is unavailable, but JPEG
resources can still be written out byte for byte.
"""
from __future__ import annotations

from .resources import Resource

_MODES = {
    ("L8"): ("L", "u1"),
    ("L16"): ("I;16", "<u2"),
    ("RGB8"): ("RGB", "u1"),
    ("RGBA8"): ("RGBA", "u1"),
    ("RGB16"): ("RGB", "<u2"),
    ("RGBA16"): ("RGBA", "<u2"),
    ("L32F"): ("F", "<f4"),
    ("RGB32F"): ("RGB", "<f4"),
    ("RGBA32F"): ("RGBA", "<f4"),
}


class MissingImageSupport(RuntimeError):
    pass


def available() -> bool:
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def to_pillow(res: Resource, data: bytes):
    """Decode one resource's payload into a Pillow image."""
    if res.is_jpeg:
        import io

        from PIL import Image
        return Image.open(io.BytesIO(data))

    try:
        import numpy as np
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise MissingImageSupport(
            "decoding raw resources needs Pillow and NumPy "
            "(pip install 'sbsarx[images]')"
        ) from exc

    mode, dtype = _MODES[res.format]
    array = np.frombuffer(data, dtype=dtype)
    shape = (res.height, res.width) if res.channels == 1 else (res.height, res.width, res.channels)
    array = array.reshape(shape)

    if res.depth == 32:
        # PNG cannot hold floating point. Values are mostly but not entirely inside
        # [0, 1] -- displacement and normal data goes outside it -- so the range is
        # clipped rather than rescaled, which keeps the common case exact.
        clipped = np.clip(array, 0.0, 1.0)
        if res.channels == 1:
            return Image.fromarray((clipped * 65535).astype("<u2"), mode="I;16")
        return Image.fromarray((clipped * 255).astype("u1"),
                               mode="RGB" if res.channels == 3 else "RGBA")

    if res.depth == 16:
        # Pillow has no 16-bit RGBA mode. Grayscale keeps its full precision as I;16;
        # colour is reduced to 8 bits, which is lossy and is reported by the caller.
        if res.channels == 1:
            return Image.fromarray(array, mode="I;16")
        return Image.fromarray((array >> 8).astype("u1"),
                               mode="RGB" if res.channels == 3 else "RGBA")
    return Image.fromarray(array, mode=mode)


def suggested_name(res: Resource) -> str:
    """A stable, self-describing filename: index, format and geometry, nothing inferred."""
    return "%02d_%s_%dx%d" % (res.index, res.format.lower(), res.width, res.height)


def lossy_on_write(res: Resource) -> bool:
    """True when writing a PNG loses precision the file actually carries."""
    return res.format in ("RGB16", "RGBA16", "L32F", "RGB32F", "RGBA32F")
