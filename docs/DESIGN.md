# Comic Pipeline: Design Doc

**Status:** draft, written before the rewrite starts
**Author:** Antares
**Last updated:** 2026-11-10

Comic Page Builder grows into the page-building part of a solo comic
pipeline: one hub app that manages the project and builds pages, plus small
importers that turn those pages into native layers in each app.

---

## 1. Decisions so far

| # | Decision | Why |
|---|----------|-----|
| D1 | **Option A: a standalone hub app with thin importers per app.** | Adobe apps run JavaScript, not Python. The hard problems (lettering size, project management, consistent panels) belong in the hub. |
| D2 | **Panels are strictly SVG.** Painted art stays in each app's native file. | SVG panels stay editable everywhere. Raster art can't meaningfully live in SVG. |
| D3 | **Version 1 targets Photoshop and Illustrator.** Clip Studio Paint comes next. Krita stays as an importer. | These are the apps used most in the workflow. |
| D4 | **The hub looks super cute and pink.** | Non-negotiable. See §11. |
| D5 | **The core is pure Python with the standard library only.** | The Krita importer has to be able to import it inside Krita's bundled Python. |

---

## 2. Scope

**Version 1 includes**
- A hub app: projects, pages, page builder (layouts, bleed and safe area, panel style), lettering-size advisor, balloon generator.
- Page output: `page.svg` and the project manifest.
- Photoshop and Illustrator importers that build native layer stacks.
- The Krita importer: today's plugin, rebuilt on top of the core.

**Not in version 1**
- Painting or inking tools. Every app already has those.
- A native importer for Clip Studio Paint. It has no public scripting API, so the route is through a PSD (§8.4).
- Interactive balloon tools *inside* the Adobe apps. These can come later as small scripts that reuse the same balloon rules.
- Cloud sync and collaboration.

---

## 3. Architecture

```
                 ┌──────────────────────────────┐
                 │  Hub app (PySide6, pink UI)  │
                 │  projects · builder · letters│
                 └──────────────┬───────────────┘
                                │ calls
                 ┌──────────────▼───────────────┐
                 │  core (stdlib-only Python)   │
                 │  model · geometry · layouts  │
                 │  lettering · balloons · svg  │
                 └──────────────┬───────────────┘
                                │ writes / reads
             project folder: project.json + pages/NNN/page.svg
                                │ read by
        ┌───────────────┬───────┴────────┬────────────────┐
        ▼               ▼                ▼                ▼
  Photoshop .jsx  Illustrator .jsx  Krita plugin      (later) CSP
  shape layers,   layers, live text  uses core         via PSD
  clipping masks                     directly
```

- **The core** owns every rule: geometry, layouts, lettering math, balloon
  shapes, and SVG in and out. It doesn't know any app exists.
- **The hub** is the only place with real UI. It is also the only part that
  needs third-party packages: PySide6 (LGPL) and fontTools (MIT), both free.
- **Importers** are dumb translators. They read `page.svg` and `project.json`
  and build layers. They never recompute geometry. Anything they need is
  already in the files, so importers in other languages stay tiny.

### Repo layout (working names, rename freely)

```
core/cpb_core/
    model.py         dataclasses: Project, Page, Panel, Balloon, styles
    geometry.py      PageGeometry: trim / bleed / safe / live rects
    layouts/         presets, BSP, grid builder (no gutters stored)
    lettering/       font discovery, metrics, size advisor
    balloons/        balloon outline generation, text fitting
    svg/             writer.py, reader.py (round trip)
    project.py       folder scaffold, manifest read and write
hub/                 PySide6 app, theme/pink.qss, bundled UI font
importers/
    photoshop/import_page.jsx
    illustrator/import_page.jsx
    shared/json2.js  JSON polyfill: ExtendScript has no JSON object
    krita/           the current plugin, slimmed down to an importer
tests/               pytest, plus "golden" SVG files to compare against
docs/DESIGN.md
```

The Krita plugin needs to be a single folder in `pykrita/`. A small build
script copies `cpb_core` into it when packaging.

---

## 4. Core model

Every length is stored in **mm**. They're converted to pt only when the SVG
is written, and to px only when an importer needs pixels.

```python
@dataclass
class PageSize:            # the source of truth for size
    trim_w: float          # finished page (old "binding")
    trim_h: float
    bleed: float
    safe: float            # measured INSIDE the trim, independent of bleed
    margin: float          # trim edge to the outermost panel
    dpi: int
    # manuscript = trim + 2*bleed, always derived, never typed in

@dataclass
class Stroke:  color: str = "#000000"; width_mm: float = 0.5
@dataclass
class Fill:    color: str | None = None        # None = no fill

@dataclass
class PanelStyle:
    stroke: Stroke; fill: Fill; corner_radius_mm: float = 0.0

@dataclass
class Panel:
    index: int             # reading order, 1-based
    shape: Shape           # Rect, or Polygon for diagonal/L-shaped panels
    style: PanelStyle

@dataclass
class Balloon:
    kind: str              # speech | caption | thought | shout | whisper
    anchor: Point          # centre of the body, mm
    tail: Tail | None      # tip point, width at the base, bend
    text: str
    lettering: LetteringStyle
    style: PanelStyle      # balloons reuse stroke and fill

@dataclass
class Page:
    number: int; size: PageSize; panels: list[Panel]
    balloons: list[Balloon]; status: str
```

`PageGeometry(size)` is the **only** place that computes the trim, bleed,
safe and live rects. Nothing else repeats that math. Today the same
calculation is copied in five places.

### Layouts
- Layouts store **cells without gutters** (a partition, or a split tree).
  The gutter is applied at build time, so changing it affects every layout,
  presets included.
- Panels are numbered in **reading order**: left-to-right, or right-to-left
  for manga, set per project.
- Grid merges that aren't rectangles become a real `Polygon`, by taking the
  union of the cells. No more overlapping bounding boxes.
- The BSP generator keeps its `seed`, so changing the gutter re-flows the
  same layout instead of rolling a new one.

---

## 5. File formats

### 5.1 Project folder

```
MyComic/
    project.json
    script/                 the comic script lives here
    pages/
        001/
            page.svg        panels + guides + balloons/letters (vector truth)
            page.psd        art, made by the Photoshop importer
            thumb.png       written by the hub
        002/ ...
    characters/  environment/  reference/
    exports/
```

### 5.2 `project.json`

```json
{
  "format": "cpb-project",
  "version": 1,
  "title": "My Comic",
  "reading_direction": "ltr",
  "page_size": { "trim_w": 170, "trim_h": 260, "bleed": 3, "safe": 5,
                 "margin": 8, "dpi": 600 },
  "print_target": { "trim_w": 170, "trim_h": 260 },
  "panel_style": { "stroke": "#1b1b1b", "stroke_width_mm": 0.6, "fill": null },
  "fonts": {
    "dialogue": { "family": "Some Comic Font", "ps_name": "SomeComicFont-Regular",
                  "size_pt": 8.0 }
  },
  "pages": [
    { "number": 1, "dir": "pages/001", "status": "pencils", "layout": "6 frames 3 rows 2" }
  ]
}
```

- `ps_name` is there because Illustrator and Photoshop pick fonts by
  PostScript name, while SVG uses the family name. Storing both avoids font
  mix-ups.
- `print_target` can differ from `page_size` when you work bigger than the
  printed page. Lettering sizes are computed against **print_target** (§9).

### 5.3 `page.svg` conventions

- Each layer is a group using Inkscape's convention, which is the closest
  thing to a shared standard:
  `<g inkscape:groupmode="layer" inkscape:label="Panels" id="cpb-panels">`
- Hub metadata goes in a custom namespace, so other apps ignore it:
  `xmlns:cpb="https://github.com/Scorpiidev/comic-page-builder/ns/1"`
- Layer stack, top to bottom:

```
cpb-guides     (cpb:print="false")  safe area, trim, crop marks
cpb-letters    balloons + text, one <g> per balloon
cpb-panels     one <path> per panel, stroke/fill from style
<defs>         one <clipPath id="cpb-clip-N"> per panel
```

- Panels are `<path>` elements, rectangles included, so diagonal panels need
  nothing special.
- Each balloon is
  `<g class="cpb-balloon" cpb:kind=… cpb:tail=… cpb:text-role=…>` containing
  one outline `<path>` and one `<text>`.
  - The parameters are kept on the group, so the hub can regenerate the
    balloon after edits.
  - Text is **pre-broken into `<tspan>` lines with explicit x and y**,
    because SVG 1.1 has no text wrapping. This also stops apps re-wrapping
    the text differently.
- **Round trip:** the reader keeps any elements it doesn't recognise. If
  you edit `page.svg` in Illustrator and the hub reopens it, your edits
  survive.

---

## 6. Layer mapping per app

| Concept | Photoshop | Illustrator | Krita | CSP (expected) |
|---|---|---|---|---|
| Panel border | **shape layer**, stroke and fill stay editable | path in layer `Panels` | vector layer per panel | via PSD, *probably rasterized* |
| Frame clipping | layer group + **vector mask** from the panel path | clipping mask from `cpb-clip-N` | Mask layer + inherit alpha | via PSD |
| Sketch / Ink / Color | raster layers, **clipping masks** (`layer.grouped = true`) | (not needed, art is in PS) | paint layers, inherit alpha | via PSD |
| Balloon | shape layer + text layer | path + point text | vector layer | via PSD, rasterized |
| Guides | layer group, hidden by default | layer, non-printing | vector layers | via PSD |

---

## 7. Hub app

- PySide6, installed with `pip`. It can be packaged as a desktop app with
  PyInstaller (free).
- Screens:
  1. **Projects:** recent projects, create or open one.
  2. **Pages board:** thumbnails grouped by status
     (thumbs → pencils → inks → colors → letters → done). Drag to change status.
  3. **Page builder:** page size, layout picker, BSP or grid, panel style
     (stroke colour, width, fill, corner radius), live preview.
  4. **Lettering:** font picker, size advisor, calibration sheet (§9).
  5. **Balloons:** place, edit and restyle balloons on the page preview.
  6. **Export / send to app:** writes the files and tells you which
     importer script to run.

---

## 8. Importers

### 8.1 Shared rules
- Importers only read `page.svg` and `project.json`, and never compute
  geometry.
- They're idempotent: running one again updates the vector layers (panels,
  guides, letters) and **never touches the art layers**. This fixes today's
  "Regenerate adds a second Comic Frames" bug by design.
- Layers are matched by stable ids (`cpb-panel-3`), not by name, so
  renaming a layer by hand doesn't break anything.

### 8.2 Photoshop (`import_page.jsx`)
- Version 1 uses ExtendScript, run from **File → Scripts → Browse**. No
  install, no signing. If it ever needs a docked panel, it can move to UXP.
- Shape layers and vector masks are created through Action Manager code
  (`executeAction`). Clipping masks are just `artLayer.grouped = true`.
- Uses a bundled `json2.js`, because ExtendScript is ES3 and has no `JSON`.
- Creates or updates `page.psd` next to `page.svg`.

### 8.3 Illustrator (`import_page.jsx`)
- Opens `page.svg`, moves the groups into named layers, applies the clipping
  paths, and sets text fonts by `ps_name`.
- This is the natural place to finish lettering: live text, real vector
  balloons.

### 8.4 Clip Studio Paint (next)
- There's no public scripting API, so the route is to open `page.psd`.
- **Risk:** vector shapes and balloons will probably arrive rasterized
  rather than as CSP-native balloons. **Test this in M2**, before planning
  around it.

### 8.5 Krita
- The current plugin is reduced to an importer that calls `cpb_core`
  directly. The existing layer structure (Mask, Sketch, Color, Ink, Borders
  clone) is kept.

---

## 9. Lettering-size advisor

**The problem it solves:** the last printed comic had lettering that read as
too tiny. Usually that's because lettering was judged at screen zoom, or the
page was printed smaller than the working canvas.

**Rule:** size lettering by its **cap height at the final printed size**,
never by the working canvas.

1. **Target.** Each text role has a target cap height in mm at print size.
   Starting presets, **to be calibrated with a test print**:
   - dialogue ≈ 1.8–2.2 mm cap height, about 7–9 pt for typical all-caps
     comic fonts
   - captions: the same or slightly smaller
   - whisper and small text: a hard minimum warning below ≈ 1.5 mm
2. **Font metrics.** Read the cap height from the font's OS/2 table
   (`sCapHeight`), or fall back to measuring the `H` glyph. Comic fonts are
   all caps, so cap height matters more than the nominal pt size.
   ```
   size_pt_at_print = target_cap_mm / (cap_height / units_per_em) / 0.3528
   size_pt_working  = size_pt_at_print * (working_trim_w / print_trim_w)
   ```
   The constant 0.3528 is mm per pt.
3. **Digital output.** The same idea, measured in pixels at the target
   display width (for example a webtoon column). Presets get calibrated on a
   real phone.
4. **Calibration sheet.** The hub generates a one-page SVG or PDF with
   sample balloons in the chosen fonts at several sizes. Print it at the
   real print size, pick the one that reads well, and save that as the
   project preset. This step is what actually prevents a repeat of last time.
5. **Font discovery.** Scan the system and user font folders on Windows,
   macOS and Linux with fontTools, and cache the names and metrics. Mark
   favourites to tag your comic fonts. Google Fonts work like any other
   installed font.
6. **Fonts on other machines.** Text stays live in `page.svg`. Export offers
   **convert to outlines**. Check each indie font's licence, since some limit
   embedding, and outlines are usually the safe route for print files.

---

## 10. Balloons

- **Version 1 kinds:** speech (ellipse), caption (rounded box), thought
  (cloud plus trailing bubbles), shout (spiky burst).
- **Later:** whisper (dashed), merged balloons, more than one tail.
- **One outline path:** the body and tail are built as **a single path**.
  Split the ellipse at the two angles where the tail attaches and insert the
  tail curve. The stroke never crosses the joint, and no boolean-operation
  library is needed.
- **Text fitting:**
  1. Break lines greedily using the font metrics. Text can be centred, and
     shaped into a diamond or "bubble" layout later.
  2. Measure the text block, w × h.
  3. Fit the ellipse around it: an ellipse with semi-axes `a = w/√2`,
     `b = h/√2` passes exactly through the block's corners. Add padding.
- **Style:** stroke colour, stroke width and fill, the same controls as
  panels. They default to the project style.

---

## 11. Visual direction: cutie patootie pink

Theme tokens live in `hub/theme/pink.qss`. There's a light theme and a dark
theme.

| Token | Light | Dark |
|---|---|---|
| `bg` | `#FFF4F8` | `#1F141A` |
| `surface` | `#FFFFFF` | `#2B1C24` |
| `surface-2` | `#FFE3EE` | `#3A2430` |
| `primary` | `#FF5FA2` | `#FF7EB8` |
| `primary-press` | `#E8458A` | `#FF9CCA` |
| `accent` (secondary pink) | `#FFB3D1` | `#B84D7F` |
| `text` | `#3D1F2E` | `#FBE9F1` |
| `text-muted` | `#9C7A8A` | `#C9A3B6` |
| `border` | `#F5C6D8` | `#4A2E3C` |
| `danger` | `#E5484D` | `#FF6B70` |

- Rounded everything: 12 px cards, 999 px pill buttons, soft shadows.
- UI font: a rounded open-licensed (OFL) font bundled with the app, such as
  **Nunito** or **Quicksand** from Google Fonts.
- Icons: an open-licensed set (Lucide or Phosphor), tinted pink.
- Small delights: confetti on "page done", and a little mascot on empty
  states.
- **One rule against the pink:** page previews and thumbnails sit on
  **neutral grey**, never pink. Surrounding colour skews how you judge the
  page's own colours. Pink belongs to the UI frame, never the canvas.

---

## 12. Testing

- **Core:** pytest. It runs anywhere, no Krita or Adobe needed.
- **Golden files:** build known pages and compare them with checked-in SVGs.
- **Round trip:** write, read, write again, and the output must be
  identical.
- **Importers:** Adobe apps can't run in CI, so there's a manual checklist
  per release: open, import, re-import, check art layers are untouched,
  check fonts.
- CI uses GitHub Actions, which is free for public repos.

---

## 13. Migration from Comic Page Builder 0.13

| Kept | Changed |
|---|---|
| Paper presets, layout presets (converted to cells without gutters) | `PageSpec` is replaced by `PageSize` and `PageGeometry` |
| BSP generator, grid builder (now makes real polygons) | Manuscript size is derived, not typed in |
| Frame layer structure (Mask / Sketch / Color / Ink / Borders) | Unit handling moves to a spinbox that stores mm |
| Project folder scaffold | User data moves out of the plugin folder |
| Bug fixes from commit `a144769` | The Krita UI is replaced by the hub; the plugin becomes an importer |

---

## 14. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Restructure the repo, set up the core skeleton and pytest | geometry, layouts and BSP are ported with tests |
| M1 | SVG writer and reader, page build from the command line | golden and round-trip tests pass |
| M2 | **Risk spike:** Photoshop and Illustrator importers, test opening the PSD in CSP | one page imports into PS and AI; CSP result written down |
| M3 | Hub app shell in pink: projects + page builder | build a page from the UI |
| M4 | Lettering advisor + calibration sheet | test print done, presets saved |
| M5 | Balloons | four kinds, text fitting, editable again later |
| M6 | Krita importer port | parity with 0.13 |
| M7 | Pages board, statuses, batch build | a whole chapter runs through the hub |

---

## 15. Open questions and risks

1. **CSP and PSD:** what survives the import? (M2)
2. **Illustrator SVG import:** how faithfully do `clipPath` and positioned
   `tspan`s come through? (M2)
3. **Photoshop on the user's version:** do shape layers and vector masks
   work through Action Manager there? (M2)
4. **Krita 5.3's bundled Python version:** sets the minimum Python version
   for the core. 3.10 is assumed; check it.
5. **Font name matching across apps:** PostScript name versus family name.
   Covered by storing both, but needs testing with the indie comic fonts.
6. **Hub name:** still to decide.
