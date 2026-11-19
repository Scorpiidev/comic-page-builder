"""
Read font files with the standard library: names and cap height.

TrueType and OpenType fonts (.ttf, .otf, and collections .ttc/.otc) are
"sfnt" files: a header, a directory of tables, then the tables. Three tables
are enough here:

    head   unitsPerEm (the size of the em square, often 1000 or 2048)
    name   family, style, full and PostScript names
    OS/2   sCapHeight and sxHeight (table version 2 and later)

So ``cap_ratio = sCapHeight / unitsPerEm``, the number the size advisor needs.
Only those tables are read (the reader seeks to them), so scanning a fonts
folder with 20 MB CJK fonts in it stays quick.
"""

from __future__ import annotations

import json
import os
import struct
import sys
from dataclasses import asdict, dataclass, field
from typing import BinaryIO, Iterable, Optional

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc", ".otc")
CACHE_VERSION = 1


@dataclass(frozen=True)
class FontInfo:
    path: str
    index: int            # face number inside a .ttc collection, else 0
    family: str           # typographic family ("Comic Neue")
    style: str            # typographic style ("Bold Italic")
    full_name: str
    ps_name: str          # PostScript name, what Illustrator and Photoshop ask for
    legacy_family: str    # older apps' family name ("Comic Neue Light"), name ID 1
    units_per_em: int
    cap_height: Optional[int]  # in font units; None when the font doesn't say
    x_height: Optional[int]
    weight: int           # 100-900
    italic: bool
    user_installed: bool = False

    @property
    def cap_ratio(self) -> Optional[float]:
        if not self.cap_height or self.units_per_em <= 0:
            return None
        return self.cap_height / self.units_per_em

    @property
    def key(self) -> str:
        return f"{self.family}|{self.style}"


# ---------- reading ----------
def _u16(b: bytes, o: int) -> int:
    return struct.unpack_from(">H", b, o)[0]


def _i16(b: bytes, o: int) -> int:
    return struct.unpack_from(">h", b, o)[0]


def _u32(b: bytes, o: int) -> int:
    return struct.unpack_from(">I", b, o)[0]


def _read(f: BinaryIO, offset: int, length: int) -> bytes:
    f.seek(offset)
    data = f.read(length)
    if len(data) < length:
        raise ValueError("the file is cut short")
    return data


def _tables(f: BinaryIO, offset: int) -> dict[str, tuple[int, int]]:
    head = _read(f, offset, 12)
    version = head[:4]
    if version not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
        raise ValueError("not a TrueType or OpenType font")
    count = _u16(head, 4)
    directory = _read(f, offset + 12, 16 * count)
    tables = {}
    for i in range(count):
        tag = directory[16 * i:16 * i + 4].decode("latin-1")
        tables[tag] = (_u32(directory, 16 * i + 8), _u32(directory, 16 * i + 12))  # offset, length
    return tables


def _names(data: bytes) -> dict[int, str]:
    """Name ID -> best string, preferring Windows US English, then any Windows, then Mac."""
    count, start = _u16(data, 2), _u16(data, 4)
    best: dict[int, tuple[int, str]] = {}
    for i in range(count):
        rec = 6 + 12 * i
        platform, encoding, language, name_id, length, off = struct.unpack_from(">6H", data, rec)
        raw = data[start + off:start + off + length]
        if platform in (0, 3):
            text = raw.decode("utf-16-be", errors="replace")
            rank = 3 if (platform == 3 and language == 0x409) else 2
        elif platform == 1 and encoding == 0:
            text = raw.decode("mac_roman", errors="replace")
            rank = 1
        else:
            continue
        if text.strip() and rank > best.get(name_id, (0, ""))[0]:
            best[name_id] = (rank, text.strip())
    return {k: v for k, (_r, v) in best.items()}


def _face(f: BinaryIO, path: str, index: int, offset: int, user: bool) -> FontInfo:
    tables = _tables(f, offset)
    for tag in ("head", "name"):
        if tag not in tables:
            raise ValueError(f"the font has no {tag} table")
    head = _read(f, *tables["head"])
    upem = _u16(head, 18)
    names = _names(_read(f, *tables["name"]))
    cap = xh = None
    weight, italic = 400, False
    if "OS/2" in tables:
        os2 = _read(f, *tables["OS/2"])
        weight = _u16(os2, 4) if len(os2) >= 6 else 400
        italic = bool(_u16(os2, 62) & 1) if len(os2) >= 64 else False
        if _u16(os2, 0) >= 2 and len(os2) >= 90:
            xh = _i16(os2, 86) or None
            cap = _i16(os2, 88) or None
    legacy = names.get(1, os.path.splitext(os.path.basename(path))[0])
    family = names.get(16, legacy)
    style = names.get(17, names.get(2, "Regular"))
    return FontInfo(path=path, index=index, family=family, style=style,
                    full_name=names.get(4, f"{family} {style}"), ps_name=names.get(6, ""),
                    legacy_family=legacy, units_per_em=upem, cap_height=cap, x_height=xh,
                    weight=weight, italic=italic, user_installed=user)


def read_font_file(path: str, user_installed: bool = False) -> list[FontInfo]:
    """Every face in a font file (one, or several for a .ttc collection)."""
    with open(path, "rb") as f:
        tag = _read(f, 0, 4)
        if tag == b"ttcf":
            header = _read(f, 0, 12)
            count = _u32(header, 8)
            offsets = struct.unpack(f">{count}I", _read(f, 12, 4 * count))
            return [_face(f, path, i, off, user_installed) for i, off in enumerate(offsets)]
        return [_face(f, path, 0, 0, user_installed)]


# ---------- finding installed fonts ----------
def default_font_dirs() -> list[tuple[str, bool]]:
    """(folder, installed-for-this-user) pairs where this system keeps fonts."""
    home = os.path.expanduser("~")
    if sys.platform == "win32":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        local = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        # Fonts installed "for me only" (Google Fonts downloads usually land here).
        return [(os.path.join(windir, "Fonts"), False), (os.path.join(local, "Microsoft", "Windows", "Fonts"), True)]
    if sys.platform == "darwin":
        return [("/System/Library/Fonts", False), ("/Library/Fonts", False), (os.path.join(home, "Library", "Fonts"), True)]
    return [("/usr/share/fonts", False), ("/usr/local/share/fonts", False),
            (os.path.join(home, ".local", "share", "fonts"), True), (os.path.join(home, ".fonts"), True)]


@dataclass
class ScanResult:
    fonts: list[FontInfo] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)  # (path, reason)


def _font_files(dirs: Iterable[tuple[str, bool]]):
    for folder, user in dirs:
        if not os.path.isdir(folder):
            continue
        for root, _subdirs, files in os.walk(folder):
            for name in sorted(files):
                if name.lower().endswith(FONT_EXTENSIONS):
                    yield os.path.join(root, name), user


def scan_fonts(dirs: Optional[Iterable[tuple[str, bool]]] = None, cache_path: Optional[str] = None) -> ScanResult:
    """
    All installed fonts, one entry per family + style, sorted by name.

    With ``cache_path``, files that haven't changed since the last scan aren't
    read again. Files that can't be read are listed in ``errors``.
    """
    cache: dict = {}
    if cache_path and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("version") == CACHE_VERSION:
                cache = data.get("files", {})
        except (OSError, ValueError):
            cache = {}
    result, seen, new_cache = ScanResult(), set(), {}
    for path, user in _font_files(dirs if dirs is not None else default_font_dirs()):
        try:
            st = os.stat(path)
            stamp = [st.st_mtime, st.st_size]
            entry = cache.get(path)
            if entry and entry["stamp"] == stamp:
                faces = [FontInfo(**fi) for fi in entry["fonts"]]
            else:
                faces = read_font_file(path, user)
            new_cache[path] = {"stamp": stamp, "fonts": [asdict(fi) for fi in faces]}
        except (OSError, ValueError, struct.error) as e:
            result.errors.append((path, str(e) or type(e).__name__))
            continue
        for fi in faces:
            if fi.key not in seen:  # the same font installed twice: keep the first
                seen.add(fi.key)
                result.fonts.append(fi)
    result.fonts.sort(key=lambda fi: (fi.family.lower(), fi.weight, fi.italic, fi.style.lower()))
    if cache_path:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(cache_path)), exist_ok=True)
            tmp = cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"version": CACHE_VERSION, "files": new_cache}, f)
            os.replace(tmp, cache_path)
        except OSError:
            pass  # a cache that can't be written just means a slower next scan
    return result
