"""
Drawn pages: a page whose art already exists as an image (D7).

The image isn't copied into page.svg: it stays a file beside it
(``pages/007/page_07_art.png``), linked from an ``<image>`` in the
``cpb-art`` layer, under the panels and letters. That way a 600 dpi page
doesn't turn page.svg into a 100 MB file, and repainting the art never
touches the lettering.

The page gets the image's real size: pixels divided by the image's own
resolution (or the project's when the file doesn't store one). PDFs are
turned into images by the hub first, since reading PDFs needs a library.

This module reads image headers with the standard library only, like the
rest of the core: PNG (IHDR, pHYs), JPEG (SOF, JFIF density) and WebP
(VP8, VP8L, VP8X; WebP stores no resolution).
"""

from __future__ import annotations

import os
import struct
from dataclasses import dataclass
from typing import Optional

from .geometry import PageSize, Rect
from .units import MM_PER_INCH

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")


@dataclass(frozen=True)
class ImageInfo:
    width: int                 # pixels
    height: int
    dpi: Optional[float]       # None when the file doesn't say
    format: str                # "png" | "jpeg" | "webp"


@dataclass(frozen=True)
class Art:
    """A linked image on a page, placed in canvas mm."""

    href: str                  # file name relative to page.svg, forward slashes
    rect: Rect
    px_w: int
    px_h: int


def _png(f) -> ImageInfo:
    f.seek(8)
    width = height = None
    dpi = None
    while True:
        head = f.read(8)
        if len(head) < 8:
            break
        length, kind = struct.unpack(">I4s", head)
        data = f.read(length)
        f.read(4)  # CRC
        if kind == b"IHDR":
            width, height = struct.unpack(">II", data[:8])
        elif kind == b"pHYs" and len(data) >= 9:
            ppu_x, _ppu_y, unit = struct.unpack(">IIB", data[:9])
            if unit == 1 and ppu_x:  # pixels per metre
                dpi = ppu_x * 0.0254
        elif kind in (b"IDAT", b"IEND"):
            break  # pHYs must come before the image data
    if not width:
        raise ValueError("the PNG has no size (IHDR)")
    return ImageInfo(width, height, round(dpi, 2) if dpi else None, "png")


def _jpeg(f) -> ImageInfo:
    f.seek(2)
    dpi = None
    while True:
        marker = f.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            raise ValueError("the JPEG is damaged (lost its markers)")
        kind = marker[1]
        if kind in (0xD8, 0x01) or 0xD0 <= kind <= 0xD7:
            continue  # markers without a length
        (length,) = struct.unpack(">H", f.read(2))
        data = f.read(length - 2)
        if kind == 0xE0 and data[:5] == b"JFIF\0" and len(data) >= 12:
            units, xd, _yd = struct.unpack(">BHH", data[7:12])
            if xd:
                dpi = xd if units == 1 else xd * 2.54 if units == 2 else None
        # Start-of-frame markers (C0-CF, except DHT C4, JPG C8 and DAC CC) carry the size.
        if 0xC0 <= kind <= 0xCF and kind not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", data[1:5])
            return ImageInfo(width, height, round(dpi, 2) if dpi else None, "jpeg")


def _webp(f) -> ImageInfo:
    f.seek(12)
    kind = f.read(4)
    f.read(4)  # chunk size
    data = f.read(10)
    if kind == b"VP8X":
        w = 1 + int.from_bytes(data[4:7], "little")
        h = 1 + int.from_bytes(data[7:10], "little")
    elif kind == b"VP8L":
        bits = int.from_bytes(data[1:5], "little")
        w, h = (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    elif kind == b"VP8 ":
        w, h = (struct.unpack("<H", data[6:8])[0] & 0x3FFF, struct.unpack("<H", data[8:10])[0] & 0x3FFF)
    else:
        raise ValueError("this WebP flavour isn't supported")
    return ImageInfo(w, h, None, "webp")


def image_info(path: str) -> ImageInfo:
    """Size and resolution of a PNG, JPEG or WebP file, from its header."""
    with open(path, "rb") as f:
        sig = f.read(12)
        if sig[:8] == b"\x89PNG\r\n\x1a\n":
            return _png(f)
        if sig[:2] == b"\xff\xd8":
            return _jpeg(f)
        if sig[:4] == b"RIFF" and sig[8:12] == b"WEBP":
            return _webp(f)
    raise ValueError(f"{os.path.basename(path)} isn't a PNG, JPEG or WebP image")


def art_size(info: ImageInfo, *, dpi: Optional[float], fallback_dpi: int, bleed: float,
             includes_bleed: bool, safe: float, margin: float) -> tuple[PageSize, Rect]:
    """
    The page size for an image, and where the image sits on the canvas.

    ``dpi`` overrides the file's own resolution. With ``includes_bleed``
    the image is the whole canvas (trim + bleed, as when you painted to the
    edge); otherwise it is the trim, and the bleed around it stays white.
    """
    res = dpi or info.dpi or fallback_dpi
    w_mm, h_mm = info.width * MM_PER_INCH / res, info.height * MM_PER_INCH / res
    if includes_bleed:
        trim_w, trim_h = w_mm - 2 * bleed, h_mm - 2 * bleed
        if trim_w <= 0 or trim_h <= 0:
            raise ValueError("the image is smaller than its own bleed; check its resolution")
        rect = Rect(0.0, 0.0, w_mm, h_mm)
    else:
        trim_w, trim_h = w_mm, h_mm
        rect = Rect(bleed, bleed, w_mm, h_mm)
    # Margins and safe area only steer panels and guides; a drawn page has
    # no generated panels, so they're shrunk rather than refusing a small image.
    short = min(trim_w, trim_h)
    size = PageSize(trim_w=round(trim_w, 3), trim_h=round(trim_h, 3), bleed=bleed,
                    safe=min(safe, short / 2 - 0.5), margin=min(margin, short / 2 - 0.5),
                    dpi=max(72, min(2400, round(res))))
    rect = Rect(round(rect.x, 3), round(rect.y, 3), round(rect.w, 3), round(rect.h, 3))
    return size, rect
