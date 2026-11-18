"""
Icons drawn from small SVG strings, tinted on the fly.

Keeping the icons as text (instead of image files) means they stay sharp at
any screen scaling and can take any theme colour.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from . import theme

PATHS = {
    "pages": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "builder": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 10h18M12 10v11"/>',
    "type": '<path d="M5 6V4h14v2M12 4v16M9 20h6"/>',
    "balloon": '<path d="M21 11.5a8.5 8.5 0 0 1-12.2 7.6L3 21l1.9-5.8A8.5 8.5 0 1 1 21 11.5z"/>',
    "folder": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    "projects": '<path d="M4 5h6l2 2h8v12H4z"/><path d="M8 3h6l2 2"/>',
    "send": '<path d="M22 2 11 13M22 2l-7 20-4-9-9-4z"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    "star": '<path d="M12 2.5l2.9 6 6.6.9-4.8 4.6 1.2 6.5L12 17.4l-5.9 3.1 1.2-6.5L2.5 9.4l6.6-.9z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "stack": '<rect x="7" y="3" width="13" height="15" rx="1"/><path d="M4 7v14h13"/>',
    "dice": '<rect x="3" y="3" width="18" height="18" rx="4"/><circle cx="8" cy="8" r=".6"/><circle cx="12" cy="12" r=".6"/><circle cx="16" cy="16" r=".6"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "sliders": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>',
    "left": '<path d="M15 5l-7 7 7 7"/>',
    "right": '<path d="M9 5l7 7-7 7"/>',
    "open": '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v1"/><path d="M3 19l3-8h16l-3 8z"/>',
    "alert": '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
    "lock": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
}

MASCOT = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
          '<path d="M32 4C32 4 12 26 12 40a20 20 0 0 0 40 0C52 26 32 4 32 4z" fill="#FF7EB8"/>'
          '<ellipse cx="25" cy="27" rx="3" ry="5" fill="#fff" fill-opacity=".6"/>'
          '<circle cx="25" cy="40" r="3" fill="#3D1F2E"/><circle cx="39" cy="40" r="3" fill="#3D1F2E"/>'
          '<ellipse cx="20" cy="47" rx="4" ry="2.5" fill="#FFB3D1"/><ellipse cx="44" cy="47" rx="4" ry="2.5" fill="#FFB3D1"/>'
          '<path d="M28 47q4 4 8 0" stroke="#3D1F2E" stroke-width="2" stroke-linecap="round" fill="none"/>'
          '<path d="M52 8c.4 2.8 1.2 3.6 4 4-2.8.4-3.6 1.2-4 4-.4-2.8-1.2-3.6-4-4 2.8-.4 3.6-1.2 4-4z" fill="#FF5FA2"/></svg>')


def svg_pixmap(svg: str, w: int, h: int, ratio: float = 2.0) -> QPixmap:
    """Render SVG text to a crisp pixmap (``ratio`` covers high-DPI screens)."""
    pm = QPixmap(int(w * ratio), int(h * ratio))
    pm.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, pm.width(), pm.height()))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


@lru_cache(maxsize=None)
def icon(name: str, color: str = theme.ACCENT_TEXT, size: int = 16) -> QIcon:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
    return QIcon(svg_pixmap(svg, size, size))


@lru_cache(maxsize=None)
def mascot(size: int = 32) -> QPixmap:
    return svg_pixmap(MASCOT, size, size)
