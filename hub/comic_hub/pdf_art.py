"""
PDF pages as images, for importing drawn pages (D7), and PDF scripts as text (M7).

Uses pypdfium2 (Apache-2.0 / BSD-3-Clause): Chrome's PDF engine, packaged
small. It's imported only when you actually import a PDF, so the hub starts
without it. Qt's own PDF module would need the much bigger PySide6-Addons,
and PyMuPDF is AGPL.
"""

from __future__ import annotations

INSTALL_HINT = "PDF import needs pypdfium2. Install it with:  python -m pip install pypdfium2"


def available() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except ImportError:
        return False
    return True


def page_count(path: str) -> int:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        return len(pdf)
    finally:
        pdf.close()


def render_page(path: str, index: int, dpi: int, out_png: str) -> None:
    """Render one PDF page (0-based) to a PNG at its real size and ``dpi``."""
    import pypdfium2 as pdfium
    import pypdfium2.raw as pdfium_c
    from PySide6.QtGui import QImage

    pdf = pdfium.PdfDocument(path)
    try:
        page = pdf[index]
        # PDF sizes are in points (1/72 inch), so dpi/72 renders at real size.
        bitmap = page.render(scale=dpi / 72, fill_color=(255, 255, 255, 255),
                             force_bitmap_format=pdfium_c.FPDFBitmap_BGRA, rev_byteorder=True)
        img = QImage(bitmap.buffer, bitmap.width, bitmap.height, bitmap.stride, QImage.Format_RGBA8888)
        img = img.convertToFormat(QImage.Format_RGB888)  # copies out of pdfium's buffer; pages are opaque
        # Stored in the PNG (pHYs), so the core reads the real size back.
        dpm = round(dpi / 0.0254)
        img.setDotsPerMeterX(dpm); img.setDotsPerMeterY(dpm)
        if not img.save(out_png, "PNG"):
            raise OSError(f"couldn't write {out_png}")
        page.close()
    finally:
        pdf.close()


def pdf_text(path: str) -> str:
    """All the text of a PDF, page after page (for reading a comic script)."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(path)
    try:
        parts = []
        for i in range(len(pdf)):
            page = pdf[i]
            text = page.get_textpage()
            parts.append(text.get_text_range())
            text.close(); page.close()
        return "\n".join(parts)
    finally:
        pdf.close()
