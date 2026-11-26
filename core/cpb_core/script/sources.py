"""
Getting a script's text out of the file it was written in.

Plain text, Markdown and Fountain are read as they are. Word (.docx) and
LibreOffice (.odt) files are zip archives of XML, so the standard library
reads them too: one line per paragraph, which is what the reader expects.
PDFs need a PDF engine, which the core doesn't have (standard library only),
so the hub extracts their text with pypdfium2 and passes it to read_script.
A Google Doc: File > Download > Plain text (.txt) or Word (.docx).
"""

from __future__ import annotations

import os
import re
import zipfile
from xml.etree import ElementTree

TEXT_TYPES = (".txt", ".md", ".markdown", ".fountain", ".text")
DOC_TYPES = (".docx", ".odt")
SCRIPT_TYPES = TEXT_TYPES + DOC_TYPES + (".pdf",)

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"


def script_text(path: str) -> str:
    """The text of a script file. PDFs raise ValueError: the hub reads those."""
    ext = os.path.splitext(path)[1].lower()
    if ext in DOC_TYPES:
        try:
            return _docx_text(path) if ext == ".docx" else _odt_text(path)
        except (zipfile.BadZipFile, KeyError, ElementTree.ParseError) as e:
            raise ValueError(f"{os.path.basename(path)} can't be read as a {ext} file ({e})") from None
    if ext == ".pdf":
        raise ValueError("PDF scripts are read by the hub (they need pypdfium2)")
    with open(path, "rb") as f:
        data = f.read()
    # UTF-8 first (with or without Notepad's BOM); old Windows files are often cp1252.
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _docx_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("word/document.xml"))
    out = []
    for p in root.iter(_W + "p"):
        parts = []
        for el in p.iter():
            if el.tag == _W + "t":
                parts.append(el.text or "")
            elif el.tag == _W + "tab":
                parts.append("\t")
            elif el.tag in (_W + "br", _W + "cr"):
                parts.append("\n")
        out.append("".join(parts))
    return "\n".join(out)


def _odt_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        root = ElementTree.fromstring(z.read("content.xml"))
    out = []
    for p in root.iter():
        if p.tag in (_TEXT + "p", _TEXT + "h"):
            out.append(_odt_inline(p))
    return "\n".join(out)


def _odt_inline(el) -> str:
    parts = [el.text or ""]
    for child in el:
        if child.tag == _TEXT + "tab":
            parts.append("\t")
        elif child.tag == _TEXT + "line-break":
            parts.append("\n")
        elif child.tag == _TEXT + "s":
            parts.append(" " * int(child.get(_TEXT + "c", "1")))
        else:
            parts.append(_odt_inline(child))
        parts.append(child.tail or "")
    return "".join(parts)


def clean_pdf_text(text: str) -> str:
    """
    PDF text comes with page footers like "3" or "3 / 7" on their own lines; drop those.
    "Page 3 of 7" stays: some scripts head their pages that way, and the
    reader tells a heading from a footer by the rest of the script.
    """
    # The reader drops page numbers itself, and uses them to find the running
    # headers and footers beside them ("Richard Douek" over every "12"), so
    # this only evens out line endings.
    return text.replace("\r\n", "\n")
