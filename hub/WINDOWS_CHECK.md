# M3 on Windows: what the hub does on a real PC

Checked 2026-11-18 on Ivón's PC by the local Claude Code session, against the
four points in CLAUDE.md. Commit 0813e10 as pushed, plus the fixes below.

| | |
|---|---|
| OS | Windows 11 Pro 24H2 (10.0.26100), **dark mode on** |
| Screens | two 1920 × 1080 monitors, both at **100 %**; taskbar on the **left** |
| Python | 3.13.16 (`python` on PATH), PySide6-Essentials 6.12.0 |
| Apps | Photoshop 27.4.0 and Illustrator 30.2.1, both with a Spanish UI |
| Locale | es-ES (decimal comma) |

## Summary

| Check | Result |
|---|---|
| `start_comic_hub.bat` installs PySide6 and starts | **Works.** |
| Pink title bar on Windows 11 | **Main window: works. Dialogs: fixed** (they had dark title bars). |
| Segoe UI, nothing clipped at 125 % / 150 % | **Segoe UI: yes. Clipping: no text is clipped anywhere. Fixed:** the main window was bigger than the screen at 125 % and 150 %. |
| A page saved in the hub imports into PS and AI | **Works**, both fresh imports and re-imports that update in place. |

Found along the way and fixed: Qt followed Windows' dark mode into a half-dark
theme; typing `3.5` in a mm box did nothing under a Spanish locale; the `×` in
the wizard's trim row took the spare width.

## 1. `start_comic_hub.bat`

- **First run:** no PySide6 yet, so the bat ran `pip install -r hub\requirements.txt`.
  That installed PySide6-Essentials 6.12.0 and shiboken6, then started the hub
  with `pythonw` (no console window).
- **Second run:** skipped the install and started straight away.
- **Note:** it installs into whatever `python` is on PATH, globally (here
  `D:\tools\Python-3.13`), not into a venv. That's fine for a one-person
  machine. A `.venv` next to the repo would keep the hub's packages apart from
  other Python tools, if that ever matters.

## 2. Title bar and theme

- **Main window:** the title bar is pink (`#f7ccdb`) with dark text, through
  `DwmSetWindowAttribute`. Snap, shadow and dragging all stay native.
- **Dialogs: fixed.** Only `MainWindow.showEvent` tinted its own title bar,
  so the wizard, Add page, Batch, Layout options, message boxes and the colour
  picker kept the default title bar, which is *black* in dark mode.
  `winframe.tint_new_windows(app)` now tints every window as it takes focus,
  through `focusWindowChanged`. That signal is cheaper than an event filter,
  which would run Python for every event. Every dialog above was checked: all
  pink.
- **Dark mode: fixed.** Qt 6.12 follows Windows' dark setting
  (`styleHints().colorScheme()` was `Dark`). So Fusion started from a black
  palette (window `#1e1e1e`, text white). Everything the stylesheet paints
  looked right, but everything else came out dark: radio-button dots, message
  boxes, the colour picker, the dialogs' title bars. `theme.apply` now sets
  `Qt.ColorScheme.Light` before choosing Fusion, because the hub's theme is
  light by design.
- **Font:** the stylesheet's font resolves to **Segoe UI 9 pt**
  (`QFontInfo`), and Segoe UI is installed.

## 3. Display scaling (125 % and 150 %)

Both monitors run at 100 %, and changing Windows' display settings was off
limits. So the scaling was emulated with `QT_SCALE_FACTOR=1.25` and `1.5`.
Qt 6 lays out and draws text the same way under real per-monitor scaling. The
only difference: the title bar's height comes from the real DPI, so it stays
100 %-sized in the emulation. **Worth one look at real 150 % some day**
(Settings → Display → Scale), but nothing here suggests a surprise.

A probe script opened every screen and dialog at 100, 125 and 150 % and saved a
picture of each:

- All projects, Pages, Page builder;
- the wizard's three tabs, Project settings, Add page, Batch, Layout options;
- a message box and the colour picker.

It also listed every label, button, combo box and spin box smaller than its
size hint, every elided tab, and any toolbar overflow.

**No text is clipped anywhere, at any scale.** The pictures agree.

What it found:

- **Main window too big: fixed.**
  - `resize(1240, 820)` is in logical pixels, so at 125 % it needs 1550 × 1025
    real pixels and at 150 % 1860 × 1230. That's taller than a 1080p screen.
  - At 125 % Windows put the window at (-488, -31): the **title bar was above
    the top edge**, so the window couldn't be dragged.
  - At 150 % its bottom ran off the screen.
  - `MainWindow._fit_to_screen()` now caps the starting size to the screen's
    free area (minus the taskbar) and centres the frame in it.
  - Measured after the fix (visible frame):

    | Scale | Position | Size |
    |---|---|---|
    | 100 % | 363, 114 | 1242 × 852 (unchanged) |
    | 125 % | 208, 12 | 1552 × 1057 |
    | 150 % | 53, 1 | 1862 × 1081 (fills the screen) |

- **Batch dialog at 150 %: left alone.** Qt caps a new dialog's height at
  ¾ of the screen (540 of 720 logical pixels). So the "Panels per page" spin
  boxes get 24 px instead of the 27 they'd like. The digits are still fully
  visible.
- **Page builder at 150 %:** the settings column gets a scroll bar. That's
  expected, because it's a scroll area.
- **Not a problem:** the round Back / Forward buttons are 24 px by the
  stylesheet, against a 27 px size hint, at every scale. They draw as full
  circles.

## 4. Hub → Photoshop / Illustrator round trip

1. **Made a project in the wizard** (General → Page setup → Folders & pages):
   `test/HubTest`, now with 6 folders and 8 pages. `project.json` and
   `pages/NNN/page.svg` look as `core/cpb_core/project.py` says.
2. **Opened page 3 in the Page builder.** Rolled the layout, set the corner
   radius to 2 mm, and saved. The page is `pages/003/page.svg` (seed 60840).
3. **Photoshop:** `import_page.psjs` on that file made the 6 frames, with
   rounded corners.
4. **Illustrator:** `import_page.jsx` made the panels, with
   `Comic Page Builder: … | page 3 | …` notes on the hub items.
5. **Re-imported.** I re-rolled and saved again in the hub, then ran both
   importers on the open documents:
   - Photoshop updated in place: "Moved or redrawn: frames 1–6", one history
     step.
   - Illustrator first asked about updating an svg-backed document, as
     designed, then reported "Redrawn: panel 1–6".

So the hub writes `page.svg` files the M2 importers read unchanged.

## Also fixed

- **Typing a dot in mm boxes** (`widgets.UnitSpinBox`).
  - Under es-ES the boxes show `3,5 mm`, and Qt silently refused a typed `3.5`:
    the box kept its old value. The numpad's decimal key types a dot.
  - The box now reads a dot as the decimal point too. That's safe because the
    boxes never show thousands separators.
  - Covers trim, bleed, safe area, margin, stroke width, corner radius and
    gutter.
  - Test: `test_unit_spin_box_takes_a_dot_under_a_comma_locale`.
- **Wizard trim row:** the `×` label was stretching and squeezing the two
  boxes. Now the boxes take the spare width.
- **Tests:** `test_window_starts_inside_the_screen` was added for the window
  fix. 105 tests pass, the hub ones included (PySide6 6.12.0).

## For the cloud session to decide

- **Done, Ivón's call: page files carry the page number.** Every page file
  was called `page.svg`. So Photoshop opened every page as a document named
  "page", and Illustrator as "page.svg", and Save As suggested `page.psd` for
  all of them. The toast, breadcrumb and title bar also said `page_03.svg`
  for a file that was really `pages/003/page.svg`. Now:
  - the file is `pages/003/page_03.svg`, named by `project.page_file()`;
  - `load_project` renames an old `page.svg` once, and leaves a `page.psd`
    or `.ai` beside it alone;
  - checked on `test/HubTest`: all 8 files were renamed on open, page 3's
    too, while Illustrator had it open;
  - a fresh import names the document `page_03` in Photoshop and
    `page_03.svg` in Illustrator. Documents made before the rename still
    update, because the importers match pages by number, not by file name;
  - Illustrator's messages said "so page.svg stays the hub's". They now
    use the real file name.
- **Decimal commas:** the boxes follow Windows' number format (`168,0 mm`),
  but the status bar and toasts use Python formatting (`gutter 3 mm`,
  `seed 60840`). That's harmless, just mixed.
- **Recent projects** live in `HKCU\Software\Antares\Comic Hub`. `HubTest` is
  in that list now. It drops out by itself if `test/HubTest` is deleted
  (`recent()` skips missing folders). There's no "remove from list" in the UI.
- **Window size isn't remembered** between runs. `saveGeometry()` /
  `restoreGeometry()` in QSettings would do it. `_fit_to_screen` should then
  still run, in case the screen changed since.
