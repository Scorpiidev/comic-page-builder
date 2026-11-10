"""Named trim sizes, in millimetres (width, height), portrait."""

from __future__ import annotations

# From the plugin's papersizes.json (ComicCreator), plus two comic formats.
PAPER_SIZES: dict[str, tuple[float, float]] = {
    "US Comic": (168, 260),      # 6.625 x 10.25 in, the standard US comic trim
    "Manga (B6)": (128, 182),    # tankobon
    "Commercial": (220, 310),
    "ISO A3": (297, 420),
    "ISO A4": (210, 297),
    "ISO A5": (148, 210),
    "ISO B3": (353, 500),
    "ISO B4": (250, 353),
    "ISO B5": (176, 250),
    "JIS B3": (364, 515),
    "JIS B4": (257, 364),
    "JIS B5": (182, 257),
    "Postcard": (100, 148),
}


def paper_size(name: str) -> tuple[float, float]:
    """Look up a trim size by name, ignoring case."""
    for key, value in PAPER_SIZES.items():
        if key.lower() == name.strip().lower():
            return value
    raise ValueError(f"Unknown paper size {name!r}. Known sizes: {', '.join(PAPER_SIZES)}")
