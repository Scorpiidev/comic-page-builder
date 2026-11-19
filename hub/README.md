# Comic Hub

The pink Aero desktop app for the comic pipeline. It runs on top of
`core/cpb_core`, so pages it builds are the same `page.svg` files the command
line and the Photoshop / Illustrator importers use.

## Start it

**Windows:** double-click `hub\start_comic_hub.bat`. The first run installs
PySide6 (the hub's only dependency, free and open source) if it's missing.

**By hand,** from the repository root:

```
python -m pip install -r hub/requirements.txt
$env:PYTHONPATH="core;hub"; python -m comic_hub      # Windows PowerShell
PYTHONPATH=core:hub python -m comic_hub              # macOS / Linux
```

## What works (M3)

- **All projects:** your recent projects, **New project…** (a 3-step wizard:
  General, Page setup, Folders & pages), **Open…** a project folder, and
  **Project settings…** (the same tabs, for the open project). The last
  project reopens on start.
- **Pages:** thumbnails grouped by status (Thumbs → Done) with a "+ Add page"
  tile, a details pane where you change a page's status, search, **Add page…**
  and **Batch generate…** (1–50 pages with a live preview; numbering continues
  after your last page).
- **Page builder:** page size, units (mm / cm / in; switching never changes
  the page), stroke colour and width, fill, corner radius, gutter, and
  **Layout options…** (random layouts with a lockable seed, the 36 presets,
  right-to-left numbering). The preview sits on neutral grey with the bleed
  tinted. **Save page** writes `pages/NNN/page_NN.svg` and keeps anything other
  apps added to it; if a panel was reshaped elsewhere, it asks first.
- Balloons (M5), Script and Exports are placeholders for now.

## Lettering (M4)

- **The font list** shows every installed font (system and "for me only"
  installs), each name drawn in its own face, with its cap height and the
  dialogue size it needs. Click the star to make it a favourite; **Favourites
  only** hides the rest. The search box searches fonts on this screen.
- **The preview** is a speech balloon at print size (100%) or zoomed, with
  your own text.
- **The advisor** takes the project's trim and the scale you draw at, and for
  each role (dialogue, caption, whisper, SFX) gives the size to use at print
  and the size to type in your canvas. Pick your own size and it tells you if
  the letters will read too small. **Save as preset** stores the font and
  size in the project.
- **Calibration sheet…** makes a PDF with up to three fonts at six sizes
  each. Print it at 100% ("Actual size"), check that the bar measures
  100 mm, pick the smallest sample that reads well at arm's length and type
  its code (like `A4`). That becomes the project's preset.

On Windows 11 the title bar is tinted pink natively (`winframe.py`), so snap
layouts and the rest of the window behaviour stay normal.

## Files

```
comic_hub/
    __main__.py     starts the app
    main_window.py  address bar, command bar, navigation, screens, status bar
    views.py        All projects, Pages, Page builder, placeholders
    lettering_view.py  Lettering: font list, preview, size advisor, calibration dialog
    calibration_pdf.py draws the calibration sheet to a real-size PDF
    dialogs.py      project wizard / settings, add page, batch, layout options
    widgets.py      UnitSpinBox (stores mm), page preview, thumbnails, toast
    theme.py        the pink Aero stylesheet and colour tokens
    icons.py        SVG icons and Inky the mascot
    winframe.py     pink title bar on Windows 11
    assets/         arrow images the stylesheet needs as files
```

Tests: `python -m pytest tests/test_hub.py` (they run headless and skip
themselves if PySide6 isn't installed).
