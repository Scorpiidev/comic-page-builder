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



# ---------- layouts from published scripts (written fresh, the shapes only) ----------

def _speakers(script):
    return [(ln.speaker, ln.kind, ln.text) for p in script.pages for ln in p.lines()]


def test_page_and_panel_on_one_line_and_repeated_headings():
    s = read_script("PAGE ONE PANEL 1\nA dock.\nMARA: Cold.\n\nPage 1 panel 2\nJUN: Yes.\n\n"
                    "PAGE ONE, continued\n(PANEL) 3.\nMARA: Go.\n\nPAGE TWO\nPanel 2.1: Close on JUN.\nJUN: Fine.\n")
    assert [(p.number, [pn.number for pn in p.panels]) for p in s.pages] == [(1, [1, 2, 3]), (2, [1])]
    assert s.pages[0].panels[0].description == "A dock."


def test_running_headers_footers_and_sheet_numbers_are_not_script():
    sheet = "COLD SNAP #1 / Script / Page {n}\n"
    text = ("PAGE ONE\nPANEL 1\nMARA: It was cold, and the\n" + sheet.format(n=1) + "wind kept on.\nSam Writer\n\n"
            "PANEL 2\nJUN: Go.\n" + sheet.format(n=2) + "\nSam Writer\n12\n"
            "PAGE TWO\nPANEL 1\nMARA: Again.\nSam Writer\nPage 3 of 9\n" + sheet.format(n=3) + "\n"
            "PAGE THREE\nPANEL 1\nJUN: End.\nSam Writer\nSam Writer\n")
    s = read_script(text)
    assert [p.number for p in s.pages] == [1, 2, 3]
    assert s.pages[0].panels[0].lines[0].text == "It was cold, and the wind kept on."
    assert all("Sam Writer" not in ln.text and "Script" not in ln.text for _, _, ln in [(0, 0, l) for p in s.pages for l in p.lines()])


def test_story_headings_win_over_sheet_numbers():
    # "Page N" at the foot of each typed sheet runs on its own count.
    text = ""
    for story, sheets in ((1, [1]), (2, [2, 3]), (3, [4]), (4, [5, 6])):
        words = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR"}[story]
        text += f"PAGE {words}\nPANEL 1\nMARA: Line {story}.\n"
        for n in sheets:
            text += f"JUN: More {story}.\nPage {n}\n"
    s = read_script(text)
    assert [p.number for p in s.pages] == [1, 2, 3, 4]
    assert [ln.text for ln in s.pages[1].lines()] == ["Line 2.", "More 2.", "More 2."]


def test_page_of_total_is_the_heading_when_there_is_nothing_else():
    s = read_script("Page 1 of 2\nPanel 1:\nNarration:\nLong ago.\nPage 2 of 2\nPanel 1:\nCROM: Ha!\n")
    assert [p.number for p in s.pages] == [1, 2]
    assert s.pages[0].lines()[0].kind == "caption"


def test_number_words_spreads_and_bare_page_numbers():
    s = read_script("PAGE TWENTY-ONE\nPANEL 1\nA: One.\nPAGES TWENTY-TWO & 23\nPANEL 1\nA: Two.\n"
                    "Page 23\nPANEL 2\nA: Still the spread.\nPAGE TWENTY FOUR\nPANEL 1\nA: Four.\n")
    assert [p.number for p in s.pages] == [21, 22, 24]
    assert [pn.number for pn in s.pages[1].panels] == [1, 2]
    bare = read_script("TITLE\n\nONE\n\nPanel 1: A city.\n\nCAPTION: Here.\n\nTWO - 4 PANELS\n\nPanel 1: A room.\n\nGOD: Hi.\n")
    assert [p.number for p in bare.pages] == [1, 2]


def test_a_sentence_that_starts_with_page_is_not_a_heading():
    s = read_script("PAGE 1\nPANEL 1\nTHE SAME CITY AS ON\nPAGE ONE, IT LOOKS GRIM AND WINDSWEPT AND DERELICT.\n"
                    "MARA: Hm.\nPAGE 2\nPANEL 1\nSEE PAGE 9 FOR THE STATUE, WHICH WE WILL COME BACK TO LATER ON.\nJUN: Ok.\n")
    assert [p.number for p in s.pages] == [1, 2]


def test_an_outline_before_the_script_merges_into_the_same_pages():
    s = read_script("PAGE ONE - 6 PANELS\nMara wakes up.\nPAGE TWO - 4 PANELS\nShe leaves.\n\n"
                    "PAGE 1 - 6 PANELS\nPANEL 1\nMARA: Morning.\nPAGE 2\nPANEL 1\nMARA: Bye.\n")
    assert [p.number for p in s.pages] == [1, 2]
    assert [ln.text for ln in s.pages[0].lines()] == ["Morning."]


def test_balloon_numbers_before_and_after_names():
    s = read_script("PAGE 1\nPANEL 1\n1 MARA: Hi.\n2. JUN (OFF): Yo.\n3 (IN-PANEL) CAPTION: Meanwhile.\n4/MARA: Ok.\n")
    assert [(ln.speaker, ln.kind) for ln in s.pages[0].lines()] == [
        ("MARA", "speech"), ("JUN", "speech"), ("", "caption"), ("MARA", "speech")]
    assert s.pages[0].lines()[2].note == "IN-PANEL"
    counted = read_script("PAGE 1\nPANEL 1\nJOHNNY 1: A.\nNATALIE 2: B.\nPANEL 2\nNATALIE 1: C.\nJOHNNY 2: D.\n"
                          "PANEL 3\nGUARD 1: Halt.\nGUARD 2: Who goes?\n")
    assert [ln.speaker for ln in counted.pages[0].lines()] == ["JOHNNY", "NATALIE", "NATALIE", "JOHNNY", "GUARD", "GUARD"]
    alone = read_script("PAGE 1\nPANEL 1\nGUARD 1: Halt.\nGUARD 2: Who goes?\n")
    assert [ln.speaker for ln in alone.pages[0].lines()] == ["GUARD 1", "GUARD 2"]  # two guards, not balloon numbers


def test_short_and_numbered_panel_headings():
    s = read_script("PAGE ONE\n\nP1/ CLOSE ON DAVE.\n\nDAVE; Don't look.\n\nP2/ WIDER.\n\nFLOP; Look!\n")
    assert [(pn.number, pn.description) for pn in s.pages[0].panels] == [(1, "CLOSE ON DAVE."), (2, "WIDER.")]
    assert [ln.speaker for ln in s.pages[0].lines()] == ["DAVE", "FLOP"]
    dotted = read_script("PAGE 1\n\n1.1\n\nA river at night.\n\nNO DIALOGUE.\n\n1.2\n\nKIRK: Run.\n")
    assert [pn.number for pn in dotted.pages[0].panels] == [1, 2] and len(dotted.pages[0].lines()) == 1
    paras = read_script("PAGE ONE\n\n1) We open on a bench outside the office.\n\n"
                        "2) A long narrow panel of Steve.\n\nSTEVE: Here goes.\n\n[3] BIG PANEL.\n")
    assert [pn.number for pn in paras.pages[0].panels] == [1, 2, 3]
    lettered = read_script("PAGE 1\nPANEL A: Wide.\nROSS: Now.\nPANEL B:\nDOC: Later.\nPic 3\nROSS: Fine.\n")
    assert [pn.number for pn in lettered.pages[0].panels] == [1, 2, 3]


def test_label_words_seen_in_published_scripts():
    s = read_script("PAGE 1\nPANEL 1\nJACKIE CAPTION: I remember.\nCAPTION - SHADOWMAN: Night.\nDialog: Who's there?\n"
                    "THORSTEIN DIALOG: Me.\nOFF PANEL: Do it.\nSPX: BLAM\nF.X. (BLAST): BOOM\nSilent panel\nCUT TO: the door.\n")
    lines = s.pages[0].lines()
    assert [(ln.kind, ln.speaker) for ln in lines] == [
        ("caption", ""), ("caption", ""), ("speech", ""), ("speech", "THORSTEIN"), ("speech", "OFF PANEL"),
        ("sfx", ""), ("sfx", ""), ("speech", "CUT TO")]
    assert lines[0].label == "jackie caption"
    assert s.likely_speaker("off panel") and not s.likely_speaker("cut to")


def test_names_inside_capital_letter_description_are_not_labels():
    s = read_script("PAGE 1\nPANEL 1\nNOW WE CHANGE ANGLE SO THAT WE SEE THE CAR, AS\nGORDON STEPS OUT OF IT INTO THE RAIN.\n"
                    "GORDON IS STRUGGLING ALONG BEHIND THE OTHERS NOW.\nGORDON: Wait for me.\n")
    assert _speakers(s) == [("GORDON", "speech", "Wait for me.")]
