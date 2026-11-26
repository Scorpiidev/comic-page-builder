"""
Comic scripts: reading them and turning their dialogue into balloons (M7).

    reader.py   pages, panels and lines from a script's text, in whatever
                layout the writer used
    sources.py  the text of .txt / .md / .docx / .odt files (PDFs: the hub)
    place.py    a page's lines as balloons, in reading order, in the right panels
"""

from .reader import LINE_KINDS, Script, ScriptLine, ScriptPage, ScriptPanel, read_script, speaker_key
from .sources import SCRIPT_TYPES, clean_pdf_text, script_text
from .place import PlacedPage, ScriptReport, apply_script, balloons_for_page

__all__ = ["LINE_KINDS", "Script", "ScriptLine", "ScriptPage", "ScriptPanel", "read_script", "speaker_key",
           "SCRIPT_TYPES", "clean_pdf_text", "script_text",
           "PlacedPage", "ScriptReport", "apply_script", "balloons_for_page"]
