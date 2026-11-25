"""
Projects: a comic as a folder on disk.

    MyComic/
        project.json            the manifest (this module reads and writes it)
        pages/007/page_07.svg   one folder per page, so page_07.psd / .ai sit beside it
        script/  characters/  environment/  reference/  exports/

The manifest holds the project's defaults (page size, panel style, gutter,
reading order) and the page list with each page's status. Each page's SVG is
still the truth for that page's own layout.

The file carries the page number, not just the folder: Photoshop and
Illustrator name a document after its file, so with every file called
page.svg, three open pages all showed up as "page".
"""

from __future__ import annotations

import json
import os
import random
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Callable, Optional

from .balloons import BalloonFont
from .build import page_from_bsp, plan_batch
from .geometry import PageSize
from .lettering import ROLES, LetteringPreset
from .model import Page, PanelStyle
from .svg import read_page, write_page

FORMAT = "cpb-project"
FORMAT_VERSION = 1
MANIFEST = "project.json"
STATUSES = ("thumbs", "pencils", "inks", "colors", "letters", "done")
FOLDERS = ("pages", "script", "characters", "environment", "reference", "exports")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def page_file(number: int) -> str:
    """A page's SVG relative to the project folder, with forward slashes (as stored).

    The name matches what the hub shows (page_07), while the folder keeps
    three digits so folders sort right in Explorer.
    """
    return f"pages/{number:03d}/page_{number:02d}.svg"


@dataclass
class PageEntry:
    number: int
    status: str = "thumbs"
    modified: str = field(default_factory=_now)

    @property
    def file(self) -> str:
        return page_file(self.number)


@dataclass
class Project:
    folder: str  # where it lives on disk; not stored in the manifest
    name: str
    chapter: str = "Chapter 1"
    reading: str = "ltr"
    work_scale: int = 2  # you draw at this multiple of print size (the lettering advisor uses it)
    paper: str = "US Comic"
    size: PageSize = field(default_factory=lambda: PageSize(168, 260))
    style: PanelStyle = field(default_factory=PanelStyle)
    gutter: float = 3.0
    folders: tuple[str, ...] = FOLDERS
    pages: list[PageEntry] = field(default_factory=list)
    modified: str = field(default_factory=_now)
    # Text role -> chosen font and size, e.g. {"dialogue": LetteringPreset(...)}.
    lettering: dict = field(default_factory=dict)

    # ---------- pages ----------
    def page_path(self, number: int) -> str:
        return os.path.join(self.folder, *page_file(number).split("/"))

    def entry(self, number: int) -> PageEntry:
        for e in self.pages:
            if e.number == number:
                return e
        raise KeyError(f"there's no page {number} in {self.name}")

    def next_number(self) -> int:
        return max((e.number for e in self.pages), default=0) + 1

    def load_page(self, number: int) -> Page:
        return read_page(self.page_path(number)).page

    def save_page(self, page: Page, status: Optional[str] = None) -> PageEntry:
        """
        Write a page into the project and record it in the manifest.

        If the page's SVG already exists, it's updated in place: anything added
        in another app (Illustrator, Inkscape...) is kept, per the ownership rule.
        """
        path = self.page_path(page.number)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if os.path.exists(path):
            doc = read_page(path)
            text = doc.to_svg(page)
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        else:
            write_page(page, path)
        try:
            e = self.entry(page.number)
            e.modified = _now()
        except KeyError:
            e = PageEntry(page.number)
            self.pages.append(e)
            self.pages.sort(key=lambda x: x.number)
        if status is not None:
            self.set_status(page.number, status, save=False)
        self.save()
        return e

    def save_balloons(self, number: int, balloons) -> PageEntry:
        """Write only a page's Letters layer (see PageDocument.letters_svg) and note it in the manifest."""
        path = self.page_path(number)
        text = read_page(path).letters_svg(balloons)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        e = self.entry(number)
        e.modified = _now()
        self.save()
        return e

    def balloon_font(self, role: str) -> Optional[BalloonFont]:
        """
        The font a new balloon of this text role gets, from the Lettering presets.

        None when the role has no preset yet. Page mm are print mm (pages are
        built at the print trim size), so the preset's print size is used
        as is; work_scale only matters when you type a size into a canvas
        that's bigger than print.
        """
        preset = self.lettering.get(role) or (self.lettering.get("dialogue") if role != "sfx" else None)
        if preset is None:
            return None
        return BalloonFont(family=preset.family, style=preset.style, ps_name=preset.ps_name,
                           size_pt=preset.size_pt, cap_ratio=preset.cap_ratio)

    def new_page(self, panels: int = 5, *, mode: str = "auto", seed: Optional[int] = None,
                 status: str = "thumbs") -> Page:
        """Add a page with a random layout, using the project's defaults."""
        page = page_from_bsp(self.next_number(), self.size, panels, mode=mode, seed=seed,
                             gutter=self.gutter, reading=self.reading, style=self.style)
        self.save_page(page, status)
        return page

    def add_batch(self, count: int, *, mode: str = "auto", min_panels: int = 4, max_panels: int = 6,
                  status: str = "thumbs", seed: Optional[int] = None,
                  same_as: Optional[int] = None,
                  progress: Optional[Callable[[int, int], None]] = None) -> list[Page]:
        """
        Add several pages. Numbering continues after the last page, so nothing
        is overwritten. ``same_as`` copies that page's layout to every new page.
        ``progress(done, total)`` is called after each page, for progress bars.
        """
        recipe = self.load_page(same_as).layout if same_as is not None else None
        plan = plan_batch(count, mode=mode, min_panels=min_panels, max_panels=max_panels,
                          seed=seed, same_as=recipe)
        made = []
        for r in plan:
            page = page_from_bsp(self.next_number(), self.size, r["panels"], mode=r["mode"],
                                 seed=r["seed"], snap=r["snap"], gutter=self.gutter,
                                 reading=self.reading, style=self.style)
            self.save_page(page, status)
            made.append(page)
            if progress:
                progress(len(made), len(plan))
        return made

    def set_status(self, number: int, status: str, save: bool = True) -> None:
        if status not in STATUSES:
            raise ValueError(f"status must be one of: {', '.join(STATUSES)}")
        e = self.entry(number)
        e.status = status
        e.modified = _now()
        if save:
            self.save()

    # ---------- manifest ----------
    def to_json(self) -> dict:
        s = self.size
        return {
            "format": FORMAT, "version": FORMAT_VERSION,
            "name": self.name, "chapter": self.chapter,
            "reading_direction": self.reading, "work_scale": self.work_scale,
            "page_size": {"paper": self.paper, "trim_w": s.trim_w, "trim_h": s.trim_h, "bleed": s.bleed,
                          "safe": s.safe, "margin": s.margin, "dpi": s.dpi},
            "panel_style": {"stroke": self.style.stroke, "stroke_width": self.style.stroke_width,
                            "fill": self.style.fill, "corner_radius": self.style.corner_radius},
            "gutter": self.gutter,
            "lettering": {role: preset.to_json() for role, preset in sorted(self.lettering.items())},
            "folders": list(self.folders),
            "modified": self.modified,
            "pages": [{"number": e.number, "file": e.file, "status": e.status, "modified": e.modified}
                      for e in self.pages],
        }

    def save(self) -> None:
        """Write project.json safely: a crash mid-write can't leave half a file."""
        self.modified = _now()
        path = os.path.join(self.folder, MANIFEST)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.to_json(), f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)


def create_project(folder: str, name: str, *, chapter: str = "Chapter 1", reading: str = "ltr",
                   work_scale: int = 2, paper: str = "US Comic", size: Optional[PageSize] = None,
                   style: Optional[PanelStyle] = None, gutter: float = 3.0,
                   folders: tuple[str, ...] = FOLDERS, blank_pages: int = 0,
                   seed: Optional[int] = None) -> Project:
    """
    Make a new project folder with its manifest and subfolders.

    Refuses to touch a folder that already has a project.json, so an
    existing comic can never be overwritten by mistake.
    """
    if not name.strip():
        raise ValueError("the project needs a name")
    if os.path.exists(os.path.join(folder, MANIFEST)):
        raise ValueError(f"{folder} already has a project in it")
    folders = tuple(dict.fromkeys(("pages",) + tuple(folders)))  # pages is required, keep order
    unknown = set(folders) - set(FOLDERS)
    if unknown:
        raise ValueError(f"unknown folders: {', '.join(sorted(unknown))}")
    os.makedirs(folder, exist_ok=True)
    for sub in folders:
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    project = Project(folder=folder, name=name.strip(), chapter=chapter, reading=reading,
                      work_scale=work_scale, paper=paper, size=size or PageSize(168, 260),
                      style=style or PanelStyle(), gutter=gutter, folders=folders)
    project.save()
    if blank_pages:
        rng = random.Random(seed)
        for _ in range(blank_pages):
            project.new_page(rng.randint(3, 6), seed=rng.randrange(10_000, 100_000))
    return project


def load_project(folder: str) -> Project:
    """Open a project folder. Raises ValueError with a plain reason if it isn't one."""
    path = os.path.join(folder, MANIFEST)
    if not os.path.exists(path):
        raise ValueError(f"{folder} isn't a comic project (it has no {MANIFEST})")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"{MANIFEST} is damaged ({e})") from None
    if data.get("format") != FORMAT:
        raise ValueError(f"{MANIFEST} isn't a Comic Page Builder project")
    if data.get("version", 1) > FORMAT_VERSION:
        raise ValueError("this project was saved by a newer version; update Comic Page Builder")
    ps, st = data.get("page_size", {}), data.get("panel_style", {})
    try:
        project = Project(
            folder=folder, name=data["name"], chapter=data.get("chapter", "Chapter 1"),
            reading=data.get("reading_direction", "ltr"), work_scale=int(data.get("work_scale", 2)),
            paper=ps.get("paper", "Custom"),
            size=PageSize(trim_w=ps["trim_w"], trim_h=ps["trim_h"], bleed=ps.get("bleed", 3),
                          safe=ps.get("safe", 5), margin=ps.get("margin", 8), dpi=ps.get("dpi", 600)),
            style=PanelStyle(stroke=st.get("stroke", "#1b1b1b"), stroke_width=st.get("stroke_width", 0.6),
                             fill=st.get("fill"), corner_radius=st.get("corner_radius", 0.0)),
            gutter=data.get("gutter", 3.0), folders=tuple(data.get("folders", FOLDERS)),
            modified=data.get("modified", _now()),
            lettering={role: LetteringPreset.from_json(v) for role, v in data.get("lettering", {}).items()},
            pages=sorted((PageEntry(p["number"], p.get("status", "thumbs"), p.get("modified", _now()))
                          for p in data.get("pages", [])), key=lambda e: e.number),
        )
    except (KeyError, TypeError) as e:
        raise ValueError(f"{MANIFEST} is missing a value ({e})") from None
    if _rename_old_page_files(project):
        project.save()  # so project.json lists the new file names
    return project


def _rename_old_page_files(project: Project) -> bool:
    """
    The first M3 hub called every page file page.svg. Rename those once.

    Only the hub's own page.svg is renamed: a page.psd or .ai beside it is
    the user's file and stays as it is. A file that can't be renamed right
    now (open in another app, say) is skipped and tried again next time.
    Returns True if anything was renamed.
    """
    renamed = False
    for e in project.pages:
        new = project.page_path(e.number)
        old = os.path.join(os.path.dirname(new), "page.svg")
        if os.path.exists(old) and not os.path.exists(new):
            try:
                os.rename(old, new)
                renamed = True
            except OSError:
                pass
    return renamed


def update_settings(project: Project, **changes) -> Project:
    """Change project defaults (name, size, style...). Existing pages keep their own size."""
    allowed = {"name", "chapter", "reading", "work_scale", "paper", "size", "style", "gutter", "folders", "lettering"}
    bad = set(changes) - allowed
    if bad:
        raise ValueError(f"can't change: {', '.join(sorted(bad))}")
    updated = replace(project, **changes)
    for sub in updated.folders:
        os.makedirs(os.path.join(updated.folder, sub), exist_ok=True)
    updated.save()
    return updated


def set_lettering_preset(project: Project, role: str, preset: LetteringPreset) -> None:
    """Save the project's font and size for a text role (dialogue, caption, whisper, sfx)."""
    if role not in ROLES:
        raise ValueError(f"role must be one of: {', '.join(ROLES)}")
    project.lettering[role] = preset
    project.save()
