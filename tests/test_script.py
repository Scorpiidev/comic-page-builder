"""Reading comic scripts and turning their lines into balloons (M7)."""

import os
import zipfile

import pytest

from cpb_core.project import create_project, load_project
from cpb_core.script import apply_script, balloons_for_page, read_script, script_text
from cpb_core.svg import read_page

# Three layouts seen in real scripts, written fresh for the tests.
WRITING_BUBBLES_STYLE = """COLD SNAP
written by Someone
PAGE 1 - PANELS: 2
PANEL 1
EXTERIOR, NIGHT. WIDE SHOT of a FROZEN FIELD. A GLIMMER of light
far away near the trees.
CAPTION I should say that I'm cold.
I mean, my elders were always saying how cold they
were.
PANEL 2
CLOSEUP of the FIRE.
SWITCHING ON.
SFX: KRAAAK
CAPTION: Truth is, I don't really understand what that word
means.
(CONTINUED)
CONTINUED: (2)
PAGE TURN
PAGE 2 - PANELS: 1
PANEL 1
LARGEST PANEL on the page.
NARRATION The cold, again.
"""

DRAGONMASTER_STYLE = """Desperate One-Shot
Characters:
Brother: Young, tired.
Hero: Tall.
https://example.com/more
________________
Page 1:
\tLayer 1-2 Panel 1:
\tPulled Back Shot: Train door opening, as Brother rushes out.
\tLayer 3 Panel 2:
\tBackground: Hero staring down.
Foreground: Brother visibly frightened.
\tBrother:
\tSorry!!
\t
\tLayer 4 Wide Panel 3:
\tShot of the bag.
\tPage Transition Text:
\tThud!
\tNo Bubble.
________________
Page 2:
Panel 1 – Top wide panel:
Starburst Bubble, across the top of the Panel: We have a big winner!
Panel 2:
Hero (whispering): Run.
Hero No Bubble: Uh-oh.
Brother: No! I have to... (Bubbles can be used to transition the panels)
Narration Bubble.
Hero {Small}: fine.
"""

MARKDOWN_STYLE = """# THE BREATH

**Format:** 2 Pages | Silent

## CHECKLIST
* **Page 1:** Sage green, mossy olive.
* **Page 2:** Violet.

---

## PAGE 1: THE DORMANT SANCTUARY

**Palette:** Earthy sage green.

### Panel 1 (Tall Vertical — Left Column)

* **Framing:** Full-length still-life study of **The Relic**.
* **Purpose:** Sets the tone.

### Panel 2 (Close-Up — Bottom Right)

* **Framing:** Tight shot on the water.
* **SFX (Hand-lettered, organic & delicate):** *blubb*

## PAGE 2: THE AWAKENING

### Panel 1

* **RITUALIST (thought):** *Not yet.*
"""


def test_writing_bubbles_layout_captions_wrap_and_markers():
    s = read_script(WRITING_BUBBLES_STYLE)
    assert [p.number for p in s.pages] == [1, 2]
    p1 = s.pages[0]
    assert [pn.number for pn in p1.panels] == [1, 2]
    first = p1.panels[0].lines[0]
    assert first.kind == "caption"
    # A short sentence was broken by the writer; the rest was wrapped by the page.
    assert first.text == "I should say that I'm cold.\nI mean, my elders were always saying how cold they were."
    assert "FROZEN FIELD" in p1.panels[0].description
    kinds = [(ln.kind, ln.text) for ln in p1.panels[1].lines]
    # A capitals line ending in a full stop is description, not a speaker; markers vanish.
    assert kinds == [("sfx", "KRAAAK"), ("caption", "Truth is, I don't really understand what that word means.")]
    assert s.pages[1].panels[0].lines[0].kind == "caption"


def test_dragonmaster_layout_names_on_their_own_line_and_bubble_notes():
    s = read_script(DRAGONMASTER_STYLE)
    assert s.cast == {"brother", "hero"}          # the link isn't a character
    p1, p2 = s.pages
    assert [pn.number for pn in p1.panels] == [1, 2, 3]
    sorry = [ln for ln in p1.lines() if ln.speaker == "Brother"]
    assert [ln.text for ln in sorry] == ["Sorry!!"]
    thud = p1.panels[2].lines[0]
    assert (thud.text, thud.kind) == ("Thud!", "floating")
    lines = p2.lines()
    assert (lines[0].kind, lines[0].speaker, lines[0].note) == ("shout", "", "across the top of the Panel")
    assert (lines[1].speaker, lines[1].kind) == ("Hero", "whisper")
    assert (lines[2].speaker, lines[2].kind, lines[2].text) == ("Hero", "floating", "Uh-oh.")
    assert (lines[3].kind, lines[3].text) == ("caption", "No! I have to...")
    assert lines[3].note == "Bubbles can be used to transition the panels"
    assert (lines[4].speaker, lines[4].note) == ("Hero", "Small")
    # Stage notes are candidates too, but the first guess says they don't talk.
    speakers = s.speakers()
    assert speakers["background"] == 1 and not s.likely_speaker("background")
    assert not s.likely_speaker("pulled back shot")
    assert s.likely_speaker("brother") and s.likely_speaker("hero")


def test_markdown_layout_bullets_are_not_headings():
    s = read_script(MARKDOWN_STYLE)
    assert [(p.number, p.title) for p in s.pages] == [(1, "THE DORMANT SANCTUARY"), (2, "THE AWAKENING")]
    p1 = s.pages[0]
    assert p1.panels[0].description == "Tall Vertical — Left Column"
    sfx = p1.panels[1].lines[-1]
    assert (sfx.kind, sfx.text, sfx.note) == ("sfx", "blubb", "Hand-lettered, organic & delicate")
    assert not s.likely_speaker("framing") and not s.likely_speaker("purpose")
    ritualist = s.pages[1].lines()[0]
    assert (ritualist.speaker, ritualist.kind, ritualist.text) == ("RITUALIST", "thought", "Not yet.")


def test_unticked_labels_drop_out():
    s = read_script(DRAGONMASTER_STYLE).without({"background", "foreground", "pulled back shot"})
    assert all(ln.label not in {"background", "foreground"} for p in s.pages for ln in p.lines())
    assert any(ln.speaker == "Brother" for ln in s.pages[0].lines())


def test_docx_and_odt_are_read_paragraph_by_paragraph(tmp_path):
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    body = "".join(f'<w:p><w:r><w:t>{t}</w:t></w:r></w:p>' for t in ("PAGE 1", "PANEL 1", "MARA: Did you see that?"))
    path = tmp_path / "s.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{w}"><w:body>{body}</w:body></w:document>')
    assert read_script(script_text(str(path))).pages[0].lines()[0].text == "Did you see that?"
    t = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
    paras = "".join(f"<text:p>{x}</text:p>" for x in ("PAGE 1", "PANEL 1", "JUN<text:tab/>(whisper): Don't move."))
    odt = tmp_path / "s.odt"
    with zipfile.ZipFile(odt, "w") as z:
        z.writestr("content.xml", f'<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
                                  f'xmlns:text="{t}"><office:body>{paras}</office:body></office:document-content>')
    line = read_script(script_text(str(odt))).pages[0].lines()[0]
    assert (line.speaker, line.kind) == ("JUN", "whisper")
    txt = tmp_path / "old.txt"
    txt.write_bytes("PAGE 1\nPANEL 1\nJOSÉ: ¿Qué?\n".encode("cp1252"))
    assert read_script(script_text(str(txt))).pages[0].lines()[0].speaker == "JOSÉ"


def _project(tmp_path, pages=3):
    return create_project(str(tmp_path / "Comic"), "Comic", blank_pages=pages, seed=5)


def test_balloons_land_in_their_panels_in_reading_order(tmp_path):
    project = _project(tmp_path)
    page = project.load_page(1)
    script = read_script("PAGE 1\nPANEL 1\nCAPTION: Meanwhile.\nMARA: Did you see that?\nJUN: No.\n")
    placed = balloons_for_page(script.pages[0], page, font_for=lambda role: project.balloon_font(role) or __import__("cpb_core.balloons", fromlist=["BalloonFont"]).BalloonFont())
    assert [b.number for b in placed.balloons] == [1, 2, 3]
    assert [b.kind for b in placed.balloons] == ["caption", "speech", "speech"]
    assert placed.balloons[0].role == "caption" and placed.balloons[1].role == "dialogue"
    r = sorted(page.panels(), key=lambda p: p.index)[0].rect
    for b in placed.balloons:
        assert r.x <= b.cx - b.rx and b.cx + b.rx <= r.x + r.w + 1e-6
        assert r.y <= b.cy - b.ry
    first, second = placed.balloons[0], placed.balloons[1]
    # Reading order: the second is to the right on the same row, or on a row below.
    assert second.cx > first.cx or second.cy > first.cy
    assert first.tail is None and second.tail is not None and second.tail.tip_y > second.cy + second.ry


def test_manga_pages_start_on_the_right(tmp_path):
    from cpb_core.balloons import BalloonFont
    project = _project(tmp_path)
    page = project.load_page(1)
    script = read_script("PAGE 1\nPANEL 1\nA: Hi.\n")
    ltr = balloons_for_page(script.pages[0], page, font_for=lambda r: BalloonFont(), reading="ltr").balloons[0]
    rtl = balloons_for_page(script.pages[0], page, font_for=lambda r: BalloonFont(), reading="rtl").balloons[0]
    assert rtl.cx > ltr.cx


def test_too_many_script_panels_go_into_the_last_and_say_so(tmp_path):
    from cpb_core.balloons import BalloonFont
    project = _project(tmp_path)
    page = project.load_page(1)
    n = len(page.panels())
    text = "PAGE 1\n" + "".join(f"PANEL {i}\nA: Line {i}.\n" for i in range(1, n + 3))
    placed = balloons_for_page(read_script(text).pages[0], page, font_for=lambda r: BalloonFont())
    assert len(placed.balloons) == n + 2
    assert any("went into panel" in w for w in placed.warnings)


def test_apply_script_saves_skips_and_reports(tmp_path):
    project = _project(tmp_path, pages=2)
    text = ("PAGE 1\nPANEL 1\nMARA: One.\nSFX: BANG\nBackground: smoke.\n"
            "PAGE 2\nPANEL 1\nJUN: Two.\nPAGE 3\nPANEL 1\nMARA: Three.\n")
    script = read_script(text)
    report = apply_script(project, script, not_speakers=frozenset({"background"}))
    assert report.pages == [1, 2] and report.balloons == 2 and report.missing == [3]
    assert [ln.text for ln in report.sfx[1]] == ["BANG"]
    saved = read_page(project.page_path(1)).page.balloons
    assert [b.text for b in saved] == ["One."]
    # Running it again doesn't double anything...
    again = apply_script(project, script, not_speakers=frozenset({"background"}))
    assert again.skipped == [1, 2] and again.balloons == 0
    # ...unless asked to add, and then numbers carry on.
    more = apply_script(project, script, existing="add", pages={1})
    nums = [b.number for b in read_page(project.page_path(1)).page.balloons]
    assert more.pages == [1] and nums == [1, 2, 3]  # One., then One. and smoke. (background ticked this time)


def test_first_page_offsets_the_script(tmp_path):
    project = _project(tmp_path, pages=3)
    report = apply_script(project, read_script("PAGE 1\nPANEL 1\nMARA: Hi.\n"), first_page=3)
    assert report.pages == [3]


def test_project_remembers_its_script(tmp_path):
    project = _project(tmp_path, pages=1)
    project.script = {"file": "script/s.txt", "first_page": 1, "not_speakers": ["background"]}
    project.save()
    assert load_project(project.folder).script["not_speakers"] == ["background"]
