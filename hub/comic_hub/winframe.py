"""
A pink title bar on Windows 11, without faking the window frame.

Windows 11 (build 22000+) lets an app colour its own title bar through
DwmSetWindowAttribute. That keeps every native behaviour (snap layouts,
shadows, dragging) while matching the Aero pink theme. On older Windows and
on other systems this does nothing.
"""

from __future__ import annotations

import sys

DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36


def _colorref(hex_color: str) -> int:
    """'#rrggbb' -> Windows COLORREF (0x00BBGGRR)."""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return (b << 16) | (g << 8) | r


def tint_title_bar(widget, caption: str = "#f7ccdb", text: str = "#4a3340", border: str = "#c98aa3") -> bool:
    """Colour the window's title bar. Returns False when the system can't."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        hwnd = wintypes.HWND(int(widget.winId()))
        dwm = ctypes.windll.dwmapi
        ok = True
        for attr, color in ((DWMWA_CAPTION_COLOR, caption), (DWMWA_TEXT_COLOR, text), (DWMWA_BORDER_COLOR, border)):
            value = ctypes.c_uint(_colorref(color))
            ok &= dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0
        return ok
    except Exception:  # an older Windows without these attributes: keep the default title bar
        return False
