"""
Reading comic scripts: pages, panels and who says what.

Writers lay scripts out in many ways, so this reader is forgiving instead of
asking for one format. It knows the shapes that keep coming back:

    PAGE 1 - PANELS: 3        Page 1:        ## PAGE 1: THE DORMANT SANCTUARY
    PANEL 1                   Layer 1-2 Panel 1:      ### Panel 1 (Tall Vertical)
    CAPTION I'm cold.         Faust: Like I said...   * **SFX (delicate):** *blubb*
    MARA (whisper): Psst.     Brother:                (the words on the next line)

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
        return key in self.cast or not _is_stage_words(key)

    def without(self, not_speakers: set[str]) -> "Script":
        """The script with the lines of labels that aren't speakers dropped (they were stage notes)."""
        pages = [ScriptPage(p.number, p.title,
                            [ScriptPanel(pn.number, pn.description,
                                         [ln for ln in pn.lines if ln.label not in not_speakers])
                             for pn in p.panels])
                 for p in self.pages]
        return Script(pages, set(self.cast))


# ---------- words that mean something ----------

CAPTION_WORDS = {"caption", "captions", "cap", "narration", "narrator", "narrador", "narradora",
                 "narracion", "narración", "box", "text box", "texto", "recuadro"}
SFX_WORDS = {"sfx", "fx", "sound", "sound effect", "sound effects", "efecto", "efectos", "onomatopeya", "sonido"}
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
_PAGE = re.compile(r"^(?:page|pages|pg\.?|página|pagina|paginas|páginas|pág\.?)\s+(\d+|[a-z]+)\b(?:\s*[-–&]\s*\d+)?\s*(.*)$", re.I)
# "PANEL 1", "Layer 1-2 Panel 1:", "L2 Wide Panel 4:", "3-4 Panel 6:", "Panel 2 – Middle panel 1:",
# "Viñeta 3". Up to three short words may come first (layers, panel shapes).
_PANEL = re.compile(r"^(?:[\w\-–]{1,12}\s+){0,3}?(?:panel|viñeta|vineta|cuadro)\s*(\d+|[a-z]+)\b\s*(.*)$", re.I)


def _number(token: str) -> Optional[int]:
    if token.isdigit():
        return int(token)
    return _NUMBER_WORDS.get(token.lower())


def _heading_rest(rest: str) -> str:
    """What follows a heading's number: "- PANELS: 3", ": THE TITLE", "(Tall Vertical)"."""
    rest = rest.strip().lstrip(":-–—.").strip()
    if rest.startswith("(") and rest.endswith(")"):
        rest = rest[1:-1].strip()
    if re.match(r"^panels?\s*:?\s*\d+\s*$", rest, re.I):
        return ""
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
    name = name.strip()
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
    if low in CAPTION_WORDS or low.split()[0] in CAPTION_WORDS and len(low.split()) <= 2:
        # A narrator has a key too, so a script that calls stage notes "Narrator" can be unticked.
        return _Label("", "caption", inner, speaker_key(name))
    if low in SFX_WORDS or low.split()[0] in SFX_WORDS:
        return _Label("", "sfx", inner, "")
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
    if key in _BARE_LABELS or key in known:
        label = _read_label(name, m.group("paren") or "")
        if label is not None:
            return label, m.group("text")
    return None


# ---------- the reader ----------

def read_script(text: str) -> Script:
    """Read a script's text (see the module docstring for what it understands)."""
    raw_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = [_clean(r) for r in raw_lines]
    # A bullet is never a heading: "* Page 1: sage green" is a note about page 1.
    bullets = [_is_bullet(r) for r in raw_lines]

    # First pass: names written "NAME:" anywhere, so "NAME words" without
    # the colon is recognised too, and the cast from the front matter.
    known: set[str] = set()
    cast: set[str] = set()
    in_front = True
    for s, bullet in zip(lines, bullets):
        if not bullet and _page_heading(s):
            in_front = False
            continue
        m = _LABEL.match(s) or _ALONE.match(s)
        if m and ":" in s and "://" not in s:
            label = _read_label(m.group("name"), m.group("paren") or "")
            if label and label.key and label.speaker and not _is_stage_words(label.key):
                (cast if in_front else known).add(label.key)
    known |= cast

    script = Script(cast=cast)
    page: Optional[ScriptPage] = None
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

    for s, bullet in zip(lines, bullets):
        heading = None if bullet else _page_heading(s)
        if heading:
            flush(); waiting = None
            number, title = heading
            page = ScriptPage(number, title)
            script.pages.append(page)
            panel = stand_in = None
            continue
        if page is None:
            continue  # front matter
        m = _PANEL.match(s)
        if m and _number(m.group(1)) is not None and len(s) < 120:
            flush(); waiting = None
            if stand_in is not None and page.panels == [stand_in]:
                panel = stand_in
                panel.number, panel.description = _number(m.group(1)), _heading_rest(m.group(2))
            else:
                panel = ScriptPanel(_number(m.group(1)), _heading_rest(m.group(2)))
                page.panels.append(panel)
            stand_in = None
            continue
        if not s:
            flush()
            continue
        # Page turns, endings and screenplay-style "(CONTINUED)" / "CONTINUED: (3)" markers.
        if re.match(r"^(page\s*turn|end|the end|fin|to be continued|\(?(continued|cont'?d)\)?:?\s*(\(\d+\))?)\.?$", s, re.I):
            flush(); waiting = None
            continue
        if waiting is not None and _match_label(s, known) is not None:
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
        label_text = _match_label(s, known)
        if label_text is not None:
            flush()
            label, rest = label_text
            if rest:
                pending = (label, [rest])
            else:
                waiting = label
            continue
        if pending is not None:
            pending[1].append(s)   # the line goes on (a PDF wraps long lines)
            continue
        # Anything else is panel description.
        if panel is not None:
            panel.description = (panel.description + " " + s).strip() if panel.description else s
    flush()
    return script


def _page_heading(s: str) -> Optional[tuple[int, str]]:
    m = _PAGE.match(s)
    if not m or len(s) > 100:
        return None
    number = _number(m.group(1))
    if number is None:
        return None   # "Page Transition Text:", "page turn"
    return number, _heading_rest(m.group(2))


def _match_label(s: str, known: set[str]) -> Optional[tuple[_Label, str]]:
    m = _LABEL.match(s)
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
    bare = _bare_label(s, known)
    if bare is not None:
        return bare[0], _unquote(bare[1])
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
