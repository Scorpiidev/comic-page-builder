"""
Reading comic scripts: pages, panels and who says what.

Writers lay scripts out in many ways, so this reader is forgiving instead of
asking for one format. It knows the shapes that keep coming back:

    PAGE 1 - PANELS: 3        Page 1:        ## PAGE 1: THE DORMANT SANCTUARY
    PANEL 1                   Layer 1-2 Panel 1:      ### Panel 1 (Tall Vertical)
    CAPTION I'm cold.         Faust: Like I said...   * **SFX (delicate):** *blubb*
    MARA (whisper): Psst.     Brother:                (the words on the next line)

Published scripts add more: "PAGE ONE PANEL 1", "P1/ CLOSE ON DAVE", "1.3",
"1) We open on...", balloon numbers ("1 SARA:", "JOHNNY 1:"), a title or a
"Page 3" printed on every typed sheet. Those are read too; lines that only
belong to the paper (running headers, sheet numbers) are left out.

What it can't tell apart is a speaker from a stage note written the same way
("Background: the city burns"). So it doesn't decide: every "label:" it sees
is a *candidate* speaker, Script.speakers() counts them, and the hub asks
which ones really talk. Script.likely_speaker() gives the first guess.

Everything before the first page heading (title, synopsis, cast list) is front
matter: no dialogue comes from it, but names in it are remembered as the cast.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# The kinds a script line can be. The first five are balloon kinds; "floating"
# is lettering with no balloon ("No bubble"), "sfx" is a sound effect, which
# isn't made into a balloon (SFX lettering is its own job).
LINE_KINDS = ("speech", "caption", "thought", "shout", "whisper", "floating", "sfx")


@dataclass(frozen=True)
class ScriptLine:
    speaker: str        # as written, e.g. "MARA"; "" for a caption or a bubble with no name
    text: str           # "\n" where the writer broke the line on purpose
    kind: str = "speech"
    note: str = ""      # the rest of the label: "(O.S.)", "across the top of the panel"
    label: str = ""     # the key the speaker checklist uses (see speaker_key)


@dataclass
class ScriptPanel:
    number: int
    description: str = ""
    lines: list[ScriptLine] = field(default_factory=list)


@dataclass
class ScriptPage:
    number: int
    title: str = ""
    panels: list[ScriptPanel] = field(default_factory=list)

    def lines(self) -> list[ScriptLine]:
        return [line for panel in self.panels for line in panel.lines]


@dataclass
class Script:
    pages: list[ScriptPage] = field(default_factory=list)
    cast: set[str] = field(default_factory=set)  # speaker keys named in the front matter

    def page(self, number: int) -> Optional[ScriptPage]:
        return next((p for p in self.pages if p.number == number), None)

    def speakers(self) -> dict[str, int]:
        """Every label that might be a speaker, with how many lines it has, in order of first use."""
        counts: dict[str, int] = {}
        for page in self.pages:
            for line in page.lines():
                if line.label:
                    counts[line.label] = counts.get(line.label, 0) + 1
        return counts

    def likely_speaker(self, key: str) -> bool:
        """The first guess for the checklist: no stage words, or named in the cast list."""
        return key in self.cast or key in OFF_PANEL_LABELS or not _is_stage_words(key)

    def without(self, not_speakers: set[str]) -> "Script":
        """The script with the lines of labels that aren't speakers dropped (they were stage notes)."""
        pages = [ScriptPage(p.number, p.title,
                            [ScriptPanel(pn.number, pn.description,
                                         [ln for ln in pn.lines if ln.label not in not_speakers])
                             for pn in p.panels])
                 for p in self.pages]
        return Script(pages, set(self.cast))


# ---------- words that mean something ----------

CAPTION_WORDS = {"caption", "captions", "cap", "caps", "narration", "narrative", "narrator", "narrador",
                 "narradora", "narracion", "narración", "box", "text box", "texto", "recuadro"}
SFX_WORDS = {"sfx", "spx", "fx", "f.x", "efx", "s.f.x", "soundfx", "sound", "sound fx", "sound effect", "sound effects",
             "efecto", "efectos", "onomatopeya", "sonido"}
# "OFF PANEL: Do it." is a voice from outside the panel, not a stage note.
OFF_PANEL_LABELS = {"off panel", "off-panel", "off", "voice off panel", "voice off-panel", "off screen", "o.s."}
# "Dialog: words" (or "THORSTEIN DIALOG:") is a balloon whose speaker is the rest of the label, if any.
DIALOG_WORDS = {"dialog", "dialogue", "diálogo", "dialogo", "speech"}
# Words in a label or its (brackets) that change the kind of balloon.
KIND_HINTS = (
    ("caption", ("narration bubble", "narration box", "caption box", "narration", "narrating", "voice over",
                 "voiceover", "v.o", "vo")),
    ("floating", ("no bubble", "no balloon", "no ballon", "bubbleless", "floating", "sin globo", "sin bocadillo")),
    ("whisper", ("whisper", "whispers", "whispering", "whispered", "quiet", "susurro", "susurra", "susurrando")),
    ("thought", ("thought", "thoughts", "thinks", "thinking", "think", "pensamiento", "piensa", "pensando")),
    ("shout", ("shout", "shouts", "shouting", "yell", "yells", "yelling", "scream", "screams", "screaming",
               "burst", "starburst", "loud", "grita", "gritando", "grito")),
)
BUBBLE_WORDS = ("bubble", "balloon", "ballon", "globo", "bocadillo")
# Stage directions written like "Label: ...". Any of these words in a label
# makes the first guess "not a speaker"; the checklist can still say otherwise.
STAGE_WORDS = {
    "shot", "shots", "close", "closeup", "close-up", "medium", "wide", "long", "extreme", "pov", "angle",
    "view", "establishing", "background", "foreground", "midground", "bg", "fg", "mg", "interior",
    "exterior", "int", "ext", "panel", "panels", "page", "pages", "note", "notes", "synopsis",
    "summary", "author", "writer", "artist", "genre", "genres", "characters", "character", "cast",
    "setting", "location", "time", "scene", "format", "purpose", "framing", "palette", "layout",
    "concept", "acting", "aesthetic", "transition", "camera", "description", "insert", "title",
    "logline", "theme", "entry", "export", "canvas", "colour", "color", "script", "count", "size",
    "mood", "lighting", "composition", "action", "beat", "pacing", "reference", "references", "design",
    "specs", "rule", "props", "prop", "art", "inset", "splash", "spread", "tier", "row", "layer",
    "day", "days", "schedule", "sprint", "week", "deadline", "checklist",
    # Seen in published scripts: "CUT TO:", "PULL BACK:", "OPEN ON:", "DISPLAY LETTERING:".
    "cut", "pull", "open", "display", "superimposed", "flashback", "same", "reads", "pic", "headline",
    "logo", "pencils", "inks", "inking", "approved", "letterer", "lettering", "colorist", "colourist",
    "editor", "inker", "penciller", "lett",
    "plano", "fondo", "viñeta", "pagina", "página", "nota", "notas", "personajes", "sinopsis",
}


def _words(s: str) -> list[str]:
    return re.findall(r"[\w'’\-]+", s.lower())


def _is_stage_words(key: str) -> bool:
    return any(w in STAGE_WORDS for w in _words(key))


def speaker_key(name: str) -> str:
    """How speakers are matched: case and spacing don't matter (MARA, Mara, mara)."""
    return " ".join(name.split()).casefold()


# ---------- cleaning a line ----------

_MD_HEADING = re.compile(r"^#{1,6}\s*")
_BULLET = re.compile(r"^(?:[*\-+•·]|\d+[.)])\s+")
_EMPHASIS = re.compile(r"(\*\*|__|\*|_)(?=\S)(.+?)(?<=\S)\1")


def _is_bullet(raw: str) -> bool:
    return bool(_BULLET.match(raw.strip()))


def _clean(raw: str) -> str:
    s = raw.replace(" ", " ").replace("\t", " ").strip()
    # Separator lines (----, ____, ***, ===) mean nothing to a balloon.
    if re.fullmatch(r"[-_*=~·•\s]{3,}", s):
        return ""
    s = _MD_HEADING.sub("", s)
    s = _BULLET.sub("", s)
    # Markdown bold/italic: "**SFX:** *blubb*" -> "SFX: blubb". Twice, for nesting.
    for _ in range(2):
        s = _EMPHASIS.sub(lambda m: m.group(2), s)
    s = s.replace("\\|", "|").replace("\\-", "-")
    return " ".join(s.split())


def _unquote(s: str) -> str:
    s = s.strip()
    pairs = {'"': '"', "“": "”", "'": "'", "‘": "’", "«": "»"}
    if len(s) > 1 and s[0] in pairs and s.endswith(pairs[s[0]]):
        s = s[1:-1].strip()
    return s


# ---------- headings ----------

# "PAGE 1", "Page 1:", "PAGE 1 - PANELS: 3", "PAGE ONE", "PAGES 2-3", "Página 4".
_NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty".split())}
_NUMBER_WORDS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90})
# The second number of a spread ("PAGES 2-3", "PAGES 2&3", "PAGES TWO AND THREE") is kept,
# but not the panel count of "PAGE ONE - 6 PANELS".
_PAGE = re.compile(r"^(?:[^#]{1,60}#\s*\d+\S*\s+)?(?:page|pages|pg\.?|página|pagina|paginas|páginas|pág\.?)\s+(\d+|[a-z]+)\b"
                   r"(?:\s*(?:[-–&/+]|and|y|through|thru)\s*(\d+|[a-z]+)\b(?!\s*panel))?\s*(.*)$", re.I)
# Pages headed by the number word alone, "ONE" or "TWO - 4 PANELS" (used only when
# a script has no "PAGE ..." headings at all).
_BARE_PAGE = re.compile(r"^([A-Z]+)(?:\s*[-–—:]\s*(?:\d+|[A-Z]+)\s+PANELS?)?\s*:?$")
# "PANEL 1", "Layer 1-2 Panel 1:", "L2 Wide Panel 4:", "3-4 Panel 6:", "Panel 2 – Middle panel 1:",
# "Viñeta 3". Up to three short words may come first (layers, panel shapes).
_PANEL = re.compile(r"^(?:[\w\-–]{1,12}\s+){0,3}?\(?(?:panel|pan|pic|picture|viñeta|vineta|cuadro)(?![a-zñ])\)?\s*(\d+(?:\.\d+)?|[a-z]+)\b\s*(.*)$", re.I)
# Short panel headings: "P1/ CLOSE ON DAVE" and "1.3" (page 1, panel 3).
_P_SLASH = re.compile(r"^P(\d{1,2})\s*[/.:\-–]\s*(.*)$")
_DOTTED = re.compile(r"^(\d{1,2})\.(\d{1,2})(?:\s+(.*))?$")
# Panels that are only numbered paragraphs: "1) We open on...", "[2] BIG PANEL.", "3. Close on".
_NUMBERED = re.compile(r"^\s*(?:\[(\d{1,2})\]|\((\d{1,2})\)|(\d{1,2})\s*[).\-–])\s+(\S.*)$")


def _number(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token.lower())


def _panel_heading(s: str) -> Optional[tuple[int, str]]:
    """(panel number, the rest) for "PANEL 3: wide shot", "(PANEL) 1.", "Panel 2.3", "PANEL B"."""
    m = _PANEL.match(s)
    if not m or len(s) >= 120:
        return None
    token, rest = m.group(1), m.group(2)
    # A letter only counts on its own ("PANEL A:"), not "...THE PANEL I DESCRIBED".
    if token.isalpha() and len(token) == 1 and not re.match(r"^\s*([:.\-–)]|$)", rest):
        return None
    number = _panel_number(token)
    return (number, rest) if number is not None else None


def _panel_number(token: str) -> Optional[int]:
    """Panels can be lettered too: "PANEL A", "PANEL B"."""
    if len(token) == 1 and token.isupper():
        return ord(token) - ord("A") + 1
    if re.fullmatch(r"\d+\.\d+", token):
        return int(token.split(".")[1])   # "Panel 2.3": page 2, panel 3
    return _number(token)


def _heading_rest(rest: str) -> str:
    """What follows a heading's number: "- PANELS: 3", ": THE TITLE", "(Tall Vertical)"."""
    rest = rest.strip().lstrip(":-–—.").strip()
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1].strip()
    if re.match(r"^panels?\s*:?\s*\d+\s*$", rest, re.I) or re.match(r"^\(?\s*(\d+|[a-z]+)\s+panels?\s*\)?\.?$", rest, re.I):
        return ""
    # "(five panels) (Begin each page on a new sheet...)": the count goes, the note stays.
    rest = re.sub(r"(?i)^\(\s*(\d+|[a-z]+)\s+panels?\s*\)\s*", "", rest)
    return rest


# ---------- labels ----------

# "NAME: words", "NAME (whisper): words", "SFX (organic, delicate): blubb".
# Notes after the name can be in (round), [square] or {curly} brackets.
_LABEL = re.compile(r"^(?P<name>[^:()\[\]{}]{1,60}?)\s*(?P<paren>\((?:[^()]|\([^()]*\))*\)|\[[^\]]*\]|\{[^}]*\})?\s*:\s*(?P<text>.*)$")
# A name alone on its line, the words below: "Brother:" / "MARA" / "MARA (O.S.)".
_ALONE = re.compile(r"^(?P<name>[^:()\[\]{}]{1,40}?)\s*(?P<paren>\([^()]*\)|\[[^\]]*\]|\{[^}]*\})?\s*:?$")


def _name_like(name: str) -> bool:
    """Short enough and plain enough to be a speaker's name (or CAPTION, SFX...)."""
    words = name.split()
    if not 1 <= len(words) <= 4 or len(name) > 32:
        return False
    if any(c in name for c in ",;!?\"“”"):
        return False
    # Full stops only at the end of short words ("Dr.", "Sgt."), not in sentences.
    for w in words:
        if re.fullmatch(r"(?:[^\W\d_]\.){1,4}", w):
            continue   # initials: "F.X.", "V.O.", "J.J."
        if "." in w[:-1] or (w.endswith(".") and len(w) > 4):
            return False
    return bool(re.search(r"[^\W\d_]", name))


def _hints(text: str) -> Optional[str]:
    low = text.lower()
    for kind, words in KIND_HINTS:
        if any(re.search(r"(?<![\w])" + re.escape(w) + r"(?![\w])", low) for w in words):
            return kind
    return None


def _strip_hint_words(name: str) -> str:
    """'Faust No Bubble' -> 'Faust'; 'Starburst Bubble' -> ''."""
    low = name
    for _kind, words in KIND_HINTS:
        for w in sorted(words, key=len, reverse=True):
            low = re.sub(r"(?i)(?<![\w])" + re.escape(w) + r"(?![\w])", " ", low)
    for w in BUBBLE_WORDS:
        low = re.sub(r"(?i)(?<![\w])" + w + r"s?(?![\w])", " ", low)
    return " ".join(low.split())


@dataclass
class _Label:
    speaker: str
    kind: str
    note: str
    key: str


def _read_label(name: str, paren: str) -> Optional[_Label]:
    """What a label means, or None if it doesn't look like a label at all."""
    # Balloon numbers in front of the name: "1 SARA:", "12/RIKARD:", "#3 CAP:".
    name = re.sub(r"^#?\d{1,3}\s*[/.)\-–]?\s*(?=[^\W\d_])", "", name.strip())
    paren = (paren or "").strip()
    inner = paren[1:-1].strip() if paren else ""
    if paren.startswith("["):
        inner = ""   # [BL]: an abbreviation for the name, not a note on how it's said
    # "Starburst Bubble, across the top of the Panel": a balloon described, not a person.
    bubble_part, _, where = name.partition(",")
    if any(w in bubble_part.lower() for w in BUBBLE_WORDS) and len(bubble_part.split()) <= 5:
        kind = _hints(bubble_part) or "speech"
        speaker = _strip_hint_words(bubble_part)
        note = ", ".join(x for x in (where.strip(), inner) if x)
        if speaker and not _name_like(speaker):
            return None
        return _Label(speaker, kind, note, speaker_key(speaker) if speaker else "")
    if not _name_like(name):
        return None
    low = name.lower()
    words = [w.strip(".-–—/") for w in low.split()]
    words = [w for w in words if w]
    if low in CAPTION_WORDS or any(w in CAPTION_WORDS for w in words):
        # "CAPTION", "PATIENCE CAP", "CAPTION - SHADOWMAN": a caption box; the
        # narrator's name stays in the key, so each narrator can be unticked.
        return _Label("", "caption", inner, speaker_key(name))
    if low in SFX_WORDS or words[0] in SFX_WORDS:
        return _Label("", "sfx", inner, "")
    if any(w in DIALOG_WORDS for w in words):
        speaker = " ".join(w for w in name.split() if w.lower().strip(".-–—/") not in DIALOG_WORDS)
        kind = _hints(inner) or "speech"
        return _Label(speaker, kind, inner, speaker_key(name))
    kind = _hints(inner) or _hints(name) or "speech"
    speaker = _strip_hint_words(name) if _hints(name) else name
    if not speaker:
        return _Label("", kind, inner, "")
    return _Label(speaker, kind, inner, speaker_key(speaker))


# Labels written without a colon ("CAPTION I'm cold.", as in many PDF scripts).
# Only words that can't start a stage direction count, plus names already
# seen with a colon, so "WIDE SHOT of the city" stays a description.
_BARE_LABELS = CAPTION_WORDS | SFX_WORDS


def _bare_label(line: str, known: set[str]) -> Optional[tuple[_Label, str]]:
    m = re.match(r"^(?P<name>[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9'’.\- ]{0,30}?)\s*(?P<paren>\([^()]*\))?\s+(?P<text>\S.*)$", line)
    if not m:
        return None
    name = m.group("name").strip()
    key = speaker_key(name)
    # Dialogue starts with a capital or punctuation; "SH establishing shot." is description.
    if key in known and m.group("text")[0].islower():
        return None
    # "GORDON IS STRUGGLING ALONG BEHIND, MAYBE..." in a script typed in capitals is description.
    text = m.group("text")
    if key in known and key not in _BARE_LABELS and not re.search(r"[a-zß-ÿ]", text) and len(text.split()) >= 4:
        return None
    if key in _BARE_LABELS or key in known:
        label = _read_label(name, m.group("paren") or "")
        if label is not None:
            return label, m.group("text")
    return None


# ---------- the reader ----------

# Lines that only say there's nothing to letter, or mark a page turn / an ending.
_MARKER = re.compile(r"^\(*\s*(page\s*turn|end|the end|fin|to be continued|more|"
                     r"no (?:dialogue|dialog|dialoggue|copy|text|balloons?|lettering)|silent(?: panel)?|"
                     r"\(?(?:continued|cont'?d)\)?:?\s*(?:\(\d+\))?)\s*\)*\.?$", re.I)


def read_script(text: str) -> Script:
    """Read a script's text (see the module docstring for what it understands)."""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [_clean(r) for r in raw_lines]
    # A bullet is never a heading: "* Page 1: sage green" is a note about page 1.
    bullets = [_is_bullet(r) for r in raw_lines]
    # Numbered paragraphs, read from the raw line because cleaning drops the number.
    numbered = [_NUMBERED.match(r.replace("\t", " ")) for r in raw_lines]
    headers = _running_headers(lines)
    headers |= _sheet_numbers(lines, headers)

    # Which kind of page heading this script uses. "Page 3 of 38" is a footer
    # when the script also has real "PAGE 3" headings, and the heading itself
    # when it has nothing else. "ONE" alone only counts in a script with neither.
    kinds = {h[3] for i, (s, bullet) in enumerate(zip(lines, bullets))
             if not bullet and i not in headers and (h := _page_heading(s))}

    def heading_of(i: int) -> Optional[tuple[int, int, str]]:
        if bullets[i] or i in headers:
            return None
        h = _page_heading(lines[i])
        if h and (h[3] == "page" or "page" not in kinds):
            return h[0], h[1], h[2]
        if not kinds:
            return _bare_page(lines[i])
        return None

    # First pass: names written "NAME:" anywhere, so "NAME words" without
    # the colon is recognised too, and the cast from the front matter.
    known: set[str] = set()
    cast: set[str] = set()
    in_front = True
    for i, s in enumerate(lines):
        if heading_of(i):
            in_front = False
            continue
        s = _label_first(s)
        m = _LABEL.match(s) or _ALONE.match(s)
        if m and ":" in s and "://" not in s:
            label = _read_label(m.group("name"), m.group("paren") or "")
            if label and label.key and label.speaker and not _is_stage_words(label.key):
                (cast if in_front else known).add(label.key)
    known |= cast

    script = Script(cast=cast)
    by_number: dict[int, ScriptPage] = {}
    page: Optional[ScriptPage] = None
    span_end = 0       # the last page number of a spread ("PAGES 2-3")
    panel: Optional[ScriptPanel] = None
    # The line being read: label plus text lines so far, until a blank line or a new label.
    pending: Optional[tuple[_Label, list[str]]] = None
    waiting: Optional[_Label] = None   # a name alone on its line: the words come next
    # Lines before a page's first panel heading go into a stand-in panel 1, which
    # the first real heading then takes over (so it isn't counted twice).
    stand_in: Optional[ScriptPanel] = None

    def flush() -> None:
        nonlocal pending
        if pending is None:
            return
        label, parts = pending
        pending = None
        words = _join(parts)
        note = label.note
        # A writer's aside in brackets at the end ("(Bubbles can be used to
        # transition the panels)") is a note about the balloon, not words in it.
        aside = re.search(r"\s*\(([^()]*)\)\.?\s*$", words)
        if aside and re.search(r"(?i)\b(bubbles?|balloons?|panels?|globos?|viñetas?|transition)\b", aside.group(1)):
            words = words[:aside.start()].rstrip()
            note = ", ".join(x for x in (note, aside.group(1).strip()) if x)
        if not words:
            return
        target = panel_for_dialogue()
        target.lines.append(ScriptLine(label.speaker, words, label.kind, note, label.key))

    def panel_for_dialogue() -> ScriptPanel:
        nonlocal panel, stand_in
        if panel is None:  # dialogue before the first panel heading belongs to panel 1
            panel = stand_in = ScriptPanel(1)
            page.panels.append(panel)
        return panel

    def open_panel(number: int, description: str) -> None:
        nonlocal panel, stand_in, waiting
        flush(); waiting = None
        if stand_in is not None and page.panels == [stand_in]:
            panel = stand_in
            panel.number, panel.description = number, description
        elif panel is not None and panel.number == number and panel in page.panels:
            # The same heading again (scripts typed on many sheets repeat it): carry on.
            if description:
                panel.description = (panel.description + " " + description).strip()
        else:
            panel = ScriptPanel(number, description)
            page.panels.append(panel)
        stand_in = None

    previous = ""   # the last line read, "" after a blank one
    for i, s in enumerate(lines):
        if i in headers:
            continue   # a running header or footer: not even a break in the text
        # Inside a wrapped sentence ("...AS THE\nJOKER ENTERS"), a name at the start
        # of a line is just the next word, not a label without its colon.
        mid_sentence = bool(previous) and not previous.endswith((".", "!", "?", "…", '"', "”", ")", ":", "]", "*"))
        previous = s
        heading = heading_of(i)
        if heading:
            flush(); waiting = None
            number, end, title = heading
            both = _panel_heading(title)   # "PAGE ONE PANEL 1", "Page 1 Panel 2"
            if page is not None and number > span_end + 4:
                pass   # "page 24" in the middle of page 9 is a reference to it, not its heading
            elif page is not None and page.number <= number <= span_end:
                pass   # the same page again: "PAGE ONE, continued", or the next panel of it
            elif page is not None and number < page.number and number != 1:
                pass   # a printed-page header lagging behind the story page: ignore it
            elif number in by_number:
                # The script starts over (an outline came first): carry on in that page.
                page = by_number[number]
                span_end = number
                panel = page.panels[-1] if page.panels else None
                stand_in = None
            else:
                page = ScriptPage(number, "" if both else title)
                script.pages.append(page)
                by_number[number] = page
                span_end = max(number, end)
                panel = stand_in = None
            if both:
                open_panel(both[0], _heading_rest(both[1]))
            continue
        if page is None:
            continue  # front matter
        ph = _panel_heading(s)
        if ph:
            open_panel(ph[0], _heading_rest(ph[1]))
            continue
        m = _P_SLASH.match(s) or _DOTTED.match(s)
        if m and (m.re is _P_SLASH or int(m.group(1)) == page.number):
            number = int(m.group(1) if m.re is _P_SLASH else m.group(2))
            open_panel(number, (m.group(m.re.groups) or "").strip())
            continue
        if not s:
            flush()
            continue
        if _MARKER.match(s):
            flush(); waiting = None
            continue
        if waiting is not None and _match_label(s, known, bare=not mid_sentence) is not None:
            # The "name" alone was a line of description in capitals after all.
            waiting = None
        if waiting is not None:
            if _only_directive(s):     # "Page Transition Text:" / "Thud!" / "No Bubble."
                waiting = _Label(waiting.speaker, _hints(s), waiting.note, waiting.key)
                continue
            pending = (waiting, [s]); waiting = None
            continue
        # A directive line right after a line ("No Bubble.") changes that line's kind.
        if pending is not None and _only_directive(s):
            label, parts = pending
            pending = (_Label(label.speaker, _hints(s), label.note, label.key), parts)
            continue
        label_text = _match_label(s, known, bare=not mid_sentence)
        if label_text is not None:
            flush()
            label, rest = label_text
            if rest:
                pending = (label, [rest])
            else:
                waiting = label
            continue
        # "1) We open on..." is the next panel when the numbers follow on.
        n = numbered[i]
        if n:
            number = int(next(g for g in n.groups()[:3] if g))
            last = panel.number if panel is not None and panel is not stand_in else 0
            if number == last + 1:
                open_panel(number, n.group(4).strip())
                continue
        if pending is not None:
            pending[1].append(s)   # the line goes on (a PDF wraps long lines)
            continue
        # Anything else is panel description.
        if panel is not None:
            panel.description = (panel.description + " " + s).strip() if panel.description else s
    flush()
    _drop_balloon_numbers(script)
    return script


def _page_heading(s: str) -> Optional[tuple[int, int, str, str]]:
    """(number, last number of a spread, title, "page" or "of" for "Page 3 of 38")."""
    m = _PAGE.match(s)
    if not m or len(s) > 140:
        return None
    number = _number(m.group(1))
    if number is None:
        return None   # "Page Transition Text:", "page turn"
    end = _number(m.group(2)) if m.group(2) else None
    rest = m.group(3).strip()
    if end is not None and end < 10 and number >= 20 and number % 10 == 0 and not m.group(2).isdigit():
        number, end = number + end, None   # "TWENTY-ONE" read as a spread of 20 and 1
        spread = re.match(r"(?i)^(?:[-–&/+]|and|y|through|thru)\s*(\d+|[a-z]+)\b(?:[\s\-](one|two|three|four|five|six|seven|eight|nine)\b)?\s*(.*)$", rest)
        if spread and _number(spread.group(1)) is not None:
            end = _number(spread.group(1)) + (_NUMBER_WORDS[spread.group(2).lower()] if spread.group(2) else 0)
            rest = spread.group(3)
    # "PAGE THIRTY ONE", "Page twenty-two": a second number word.
    tens = re.match(r"(?i)^[\s\-]?(one|two|three|four|five|six|seven|eight|nine)\b\s*(.*)$", rest)
    if tens and number >= 20 and number % 10 == 0 and not m.group(2):
        number += _NUMBER_WORDS[tens.group(1).lower()]
        rest = tens.group(2)
    if end is None and number >= 20:
        # "PAGES THIRTY-FIVE THROUGH THIRTY-SIX"
        spread = re.match(r"(?i)^(?:[-–&/+]|and|y|through|thru)\s*(\d+|[a-z]+)\b(?:[\s\-](one|two|three|four|five|six|seven|eight|nine)\b)?\s*(.*)$", rest)
        if spread and _number(spread.group(1)) is not None:
            end = _number(spread.group(1)) + (_NUMBER_WORDS[spread.group(2).lower()] if spread.group(2) else 0)
            rest = spread.group(3)
    if re.match(r"(?i)^of\s+\d+\s*$", rest):
        return number, number, "", "of"
    # "PAGE ONE. THIS KIDDY SUPREMA, AS SHE FLIES DOWN..." is a sentence, not a heading.
    if len(re.sub(r"\([^()]*\)?", "", rest)) > 50:
        return None
    # "PAGE ONE, IT LOOKS GRIM AND WINDSWEPT" too; "PAGE ONE, continued" is still page one.
    if (rest.startswith(",") and len(rest.split()) >= 6
            and not re.match(r"(?i)^,\s*(cont|panel|pic|pan|revised|no art)", rest)):
        return None
    # "Page 1 panel 2" names a panel too; "PAGE 1 - PANELS: 3" only counts them.
    if re.match(r"(?i)^[,.:\-–\s]*(?:panel|pic|pan)\s*\d", rest):
        return number, max(number, end or number), rest.lstrip(",.:-– "), "page"
    return number, max(number, end or number), _heading_rest(rest), "page"


def _bare_page(s: str) -> Optional[tuple[int, int, str]]:
    m = _BARE_PAGE.match(s)
    if not m:
        return None
    number = _NUMBER_WORDS.get(m.group(1).lower())
    return (number, number, "") if number else None


_PAGE_NUMBER = re.compile(r"^(?:\(?\d{1,3}\)?|-\s*\d{1,3}\s*-|\d{1,3}\s*/\s*\d{1,3})$")


def _running_headers(lines: list[str]) -> set[int]:
    """
    Lines printed on every sheet of the script, like "FANTASTIC FOUR #60 / Script /
    Page 2" or a title right above each "Page 2". They repeat (the numbers
    aside) and carry a number or sit right above a page heading.
    """
    def shape(s: str) -> str:
        return re.sub(r"\d+", "#", s.casefold())
    counts: dict[str, int] = {}
    exact: dict[str, int] = {}
    for s in lines:
        if s:
            counts[shape(s)] = counts.get(shape(s), 0) + 1
            exact[s] = exact.get(s, 0) + 1
    # "D. Grayson B:GK 15 2", "... 15 3", "... 15 4": a sheet counter at the end of the line.
    counters: dict[str, list[int]] = {}
    for s in lines:
        m = re.search(r"(\d+)$", s)
        if m:
            counters.setdefault(shape(s), []).append(int(m.group(1)))
    counting = {k for k, v in counters.items() if len(v) >= 3 and all(b > a for a, b in zip(v, v[1:]))}
    nonblank = [i for i, s in enumerate(lines) if s]
    # Page numbers alone on a line are never script, and they mark where a sheet ends.
    out: set[int] = {i for i in nonblank if _PAGE_NUMBER.match(lines[i])}
    for k, i in enumerate(nonblank):
        s = lines[i]
        if i in out or counts[shape(s)] < 3 or _page_heading(s) or _panel_heading(s) or _MARKER.match(s):
            continue
        prv = lines[nonblank[k - 1]] if k > 0 else ""
        nxt = lines[nonblank[k + 1]] if k + 1 < len(nonblank) else ""
        # A number alone isn't enough ("A: Line 1." could repeat): it has to look like a header too.
        looks_printed = re.search(r"\d", s) and re.search(r"(?i)\b(page|pg|script|draft|issue|ms|of)\b|[#/|©]", s)
        # "Richard Douek" at the foot of every sheet: a name in Title Case, many times over.
        signature = (counts[shape(s)] >= 5 and not s.isupper() and _LABEL.match(s) is None
                     and re.fullmatch(r"(?:[A-Z][\w'’.\-]*\s*){1,5}", s))
        # Above a heading, the very same words each time (a title over "Page 6").
        above = exact[s] >= 3 and _page_heading(nxt)
        if (looks_printed or signature or above or shape(s) in counting
                or _PAGE_NUMBER.match(prv) or _PAGE_NUMBER.match(nxt)):
            out.add(i)
    return out


def _sheet_numbers(lines: list[str], skip: set[int]) -> set[int]:
    """
    Some scripts number their sheets as well as their story pages: "PAGE ONE"
    heads the story page, "Page 1" sits at the foot of every typed sheet. Both
    look like page headings. The story's own headings are the ones a panel
    follows; when one way of writing them clearly is and another clearly
    isn't, the other is the sheet numbers.
    """
    def style(s: str) -> tuple[str, bool]:
        word = s.split()[0]
        case = "upper" if word.isupper() else "title" if word[:1].isupper() else "lower"
        return case, bool(re.match(r"^\S+\s+\d", s))
    nonblank = [i for i, s in enumerate(lines) if s and i not in skip]
    groups: dict[tuple[str, bool], list[int]] = {}
    followed: dict[tuple[str, bool], int] = {}
    for k, i in enumerate(nonblank):
        h = _page_heading(lines[i])
        if not h or h[3] != "page":
            continue
        key = style(lines[i])
        groups.setdefault(key, []).append(i)
        nxt = []
        for j in nonblank[k + 1:k + 4]:
            if _page_heading(lines[j]):
                break   # another heading straight after: that one is followed, not this
            nxt.append(lines[j])
        if _panel_heading(h[2]) or any(_panel_heading(s) or _P_SLASH.match(s) or _DOTTED.match(s) or _NUMBERED.match(s)
                                       for s in nxt):
            followed[key] = followed.get(key, 0) + 1
    if len(groups) < 2:
        return set()
    score = {key: followed.get(key, 0) / len(idx) for key, idx in groups.items()}
    big = [key for key in groups if len(groups[key]) >= 3]
    if not big:
        return set()
    best = max(big, key=lambda key: (score[key], len(groups[key])))
    if score[best] < 0.5:
        return set()
    return {i for key, idx in groups.items()
            if key != best and score[key] < 0.6 * score[best] and len(idx) >= 3 for i in idx}


def _drop_balloon_numbers(script: Script) -> None:
    """
    "JOHNNY 1:", "NATALIE 2:" in one panel are balloons 1 and 2, not two
    Johnnies. Numbers that count up across different speakers in a panel,
    in two panels or more, are balloon numbers: they're dropped everywhere.
    (CAPEKILLER 1 and CAPEKILLER 2 talking to each other stay apart.)
    """
    tail = re.compile(r"^(.*\S)\s+(\d{1,2})$")
    evidence = 0
    for page in script.pages:
        for panel in page.panels:
            seen = [(m.group(1), int(m.group(2))) for ln in panel.lines if (m := tail.match(ln.label))]
            if len(seen) >= 2 and len({b for b, _ in seen}) >= 2 and all(
                    b2 > b1 for (_, b1), (_, b2) in zip(seen, seen[1:])):
                evidence += 1
    if evidence < 2:
        return
    for page in script.pages:
        for panel in page.panels:
            fixed = []
            for ln in panel.lines:
                m = tail.match(ln.label)
                if m:
                    speaker = re.sub(r"\s+\d{1,2}$", "", ln.speaker)
                    ln = ScriptLine(speaker, ln.text, ln.kind, ln.note, m.group(1))
                fixed.append(ln)
            panel.lines = fixed


def _label_first(s: str) -> str:
    """'3 (IN-PANEL) CAPTION: words' -> 'CAPTION (IN-PANEL): words', so the label reads as usual."""
    return re.sub(r"^(?:#?\d{1,3}\s*[/.)\-–]?\s*)?(\([^()]{1,30}\))\s*([^:()\[\]{}]{1,40}?)\s*:",
                  lambda m: m.group(2) + " " + m.group(1) + ":", s)


def _match_label(s: str, known: set[str], bare: bool = True) -> Optional[tuple[_Label, str]]:
    s = _label_first(s)
    m = _LABEL.match(s)
    if not m:
        # "DAVE; Don't look." Some writers use a semicolon; only names in capitals count.
        m = re.match(r"^(?P<name>[A-Z][A-Z0-9 .'’\-]{0,30}?)\s*(?P<paren>\([^()]*\))?\s*;\s*(?P<text>\S.*)$", s)
    if m and m.group("text").startswith("//"):
        return None   # a link (https://...), not a speaker
    if m:
        label = _read_label(m.group("name"), m.group("paren") or "")
        if label is not None:
            return label, _unquote(m.group("text"))
        return None
    m = _ALONE.match(s)
    if m and _alone_is_name(m.group("name"), m.group("paren"), known):
        label = _read_label(m.group("name"), m.group("paren") or "")
        if label is not None:
            return label, ""
    found = _bare_label(s, known) if bare else None
    if found is not None:
        return found[0], _unquote(found[1])
    return None


def _alone_is_name(name: str, paren: Optional[str], known: set[str]) -> bool:
    """A name on its own line, without a colon, has to be in capitals or already known."""
    name = name.strip()
    key = speaker_key(name)
    if key in known or key in _BARE_LABELS:
        return True
    if name.endswith((".", "!", "?", ",")):
        return False  # names don't end sentences: that's a wrapped line of description
    letters = [c for c in name if c.isalpha()]
    return bool(letters) and all(c.isupper() for c in letters) and len(name.split()) <= 3 and len(letters) >= 2


def _only_directive(s: str) -> bool:
    """A line that only says what kind of balloon this is: "No Bubble.", "(whisper)"."""
    bare = s.strip(" .()[]-–").lower()
    return bool(bare) and _hints(bare) is not None and len(bare.split()) <= 3 and not _strip_hint_words(bare)


def _join(parts: list[str]) -> str:
    """
    Text lines of one balloon, joined. A line that ends a sentence and is
    clearly shorter than the longest was broken by the writer, so it keeps
    its break; the others were wrapped by the page (PDFs) and are joined.
    """
    parts = [_unquote(p) for p in parts if p.strip()]
    if not parts:
        return ""
    longest = max(len(p) for p in parts)
    out = parts[0]
    for prev, nxt in zip(parts, parts[1:]):
        deliberate = prev.rstrip().endswith((".", "!", "?", "…", '"', "”", ")", "-", "—")) and len(prev) < 0.8 * longest
        out += ("\n" if deliberate else " ") + nxt
    return out
