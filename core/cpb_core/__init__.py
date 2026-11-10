"""
cpb_core: the app-independent heart of the comic pipeline.

Everything in this package is plain Python (standard library only), so the
same code runs inside the hub app, inside Krita's bundled Python, and in
tests. It never imports Qt, Krita, or any Adobe API.

All lengths are millimetres unless a name says otherwise (``_pt``, ``_px``).
"""

__version__ = "0.1.0"
