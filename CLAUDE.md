# Notes for Claude

This repo is Antares's (Ivón's) solo comic pipeline. It started as a Krita
plugin (Comic Page Builder 0.13, in `comicpagebuilder/`) and is being rebuilt
as a pure-Python core + a pink Windows-7-style hub app + importers for
Photoshop, Illustrator and Krita. The plan and every decision live in
`docs/DESIGN.md`. Read its section 1 (decisions D1–D9) and section 14
(milestones) before changing anything.

## Where things stand (2026-11-19)

- **M0 done:** `core/cpb_core/`: units, page geometry, layouts (gutter-free
  cells, seeded BSP, presets, grid).
- **M1 done:** `core/cpb_core/svg/` writes and reads `page.svg`; CLI is
  `python -m cpb_core build | batch | info | papers | borders`.
- **M2 done 2026-11-18** in the local session: PS and AI import work (two
  PS fixes). CSP keeps the PSD's groups and clipping but rasterizes borders,
  so `python -m cpb_core borders page.svg` now writes a borders-only SVG for
  CSP's File → Import → Vector (tested, rounded corners too). Details are in
  `importers/M2_RESULTS.md`.
  The original brief for that test follows. The import scripts were written but
  had never run in the real apps:
  - `importers/photoshop/import_page.psjs` (UXP script, Photoshop 27.4)
  - `importers/illustrator/import_page.jsx` (ExtendScript, Illustrator 30.2)
  - Clip Studio Paint EX 4.0.3 only gets tested by opening the saved PSD.
- **Photoshop re-import done 2026-11-18.** Running `import_page.psjs` with a
  PSD it made as the active document updates the frames in place:
  - the hub's layers are found by XMP tags;
  - art layers are never touched;
  - one history step.

  The test results are in `importers/M2_RESULTS.md`, under "After M2".
- **Illustrator re-import done 2026-11-18**, the same idea:
  - hub items carry a `Comic Page Builder: …` note;
  - updates leave lettering and the user's own items alone.

  Illustrator can't undo a script in one step, so File → Revert is the way
  back (the script asks before updating unsaved work).

- **M3 done 2026-11-18** in the cloud session: the hub app in `hub/`
  (start with `hub\start_comic_hub.bat`) and `core/cpb_core/project.py`
  (project.json, `pages/NNN/page_NN.svg`). Screens: All projects (wizard +
  settings), Pages (status groups, add, batch), Page builder (save keeps
  other apps' edits). It was only ever run headless on Linux, so **on
  Windows, please check**:
  - the title bar turns pink on Windows 11 (`hub/comic_hub/winframe.py`);
  - Segoe UI is used and nothing is clipped at 125% / 150% display scaling;
  - `start_comic_hub.bat` installs PySide6 on first run and starts the app;
  - a page saved in the hub imports into Photoshop and Illustrator as before.

  Write what you find to `hub/WINDOWS_CHECK.md`, fix small things, commit, push.
- **M3 Windows check done 2026-11-18** in the local session. All four points
  pass after five small fixes: dialogs' title bars, a forced light theme
  under Windows dark mode, the window fitting the screen at 125 % / 150 %,
  typing `3.5` under a comma locale, and the wizard's trim row. Scaling was
  emulated with `QT_SCALE_FACTOR`. Open questions are at the end of
  `hub/WINDOWS_CHECK.md`.
- **Page files renamed 2026-11-18** (Ivón's call): `pages/007/page_07.svg`
  instead of `pages/007/page.svg`, so Photoshop and Illustrator tabs show
  the page number. Old projects are renamed when they open.
- **M4 built 2026-11-19** in the cloud session, not finished yet. It has:
  - `core/cpb_core/lettering/`: a font reader, the size advisor and the
    calibration sheet layout;
  - the hub's Lettering screen (`hub/comic_hub/lettering_view.py`);
  - the calibration PDF (`calibration_pdf.py`);
  - presets in `project.json` under `"lettering"`.

  It only ran headless on Linux, with Linux fonts. **On Windows, please
  check** and write the results to `hub/WINDOWS_CHECK.md` under "M4":
  - The font list has Ivón's indie and Google fonts, including ones installed
    "for me only" (`%LOCALAPPDATA%\Microsoft\Windows\Fonts`). Each name is
    drawn in its own face, with the right style (Light vs Regular, Italic).
    Watch for families with many weights: Qt on Windows may name them
    differently from the font file. `font_for()` in `lettering_view.py`
    handles that.
  - A font marked "(measured)" gets a sensible cap height (about 0.65–0.75
    em for most fonts).
  - **Calibration sheet…** saves a PDF to `exports/`, opens it, and the PDF
    lists the fonts as embedded (in Acrobat: File → Properties → Fonts).
  - **The test print**, which is M4's done-when. Ask Ivón to:
    1. print the dialogue sheet at 100% / "Actual size";
    2. measure the 100 mm bar;
    3. type the code of the best sample.

    Check that `project.json` then has the preset. If the bar isn't 100 mm,
    the print dialog scaled the page. That's a settings issue, not a bug,
    but write it down.
  - Each preset's `ps_name` is the name Photoshop and Illustrator show for
    that font. Check one in each app. M5 balloons will rely on it.

  Then mark M4 ✅ in `docs/DESIGN.md` §14 and here.

- **M5 started 2026-11-25** in the local session, core first:
  - `core/cpb_core/balloons/`: `Balloon` and `Tail` as parameters (D6),
    outlines for all five kinds as one path (M/L/C/Z only, no arcs, so the
    Photoshop importer can map them), and text fitting with a pluggable
    `measure` (the hub should pass Qt's real widths; the core's
    `approx_measure` is a rough guess).
  - `core/cpb_core/svg/letters.py` writes and reads the Letters layer:
    one `cpb-balloon-N` group per balloon, parameters on the group, text
    pre-broken into positioned tspans.
  - `Page.balloons = None` means "leave the Letters layer alone", so the
    page builder's saves never wipe lettering.
  - **Watch out:** Qt's `QSvgRenderer` (SVG Tiny 1.2) ignores tspan x/y and
    runs a balloon's lines together. Previews flatten each tspan into its own
    `<text>` in memory first (the file keeps tspans for Illustrator). Also,
    `QT_QPA_PLATFORM=offscreen` on Windows has no fonts (text draws as
    boxes), so check text rendering with the normal platform.
  - **Balloons screen done 2026-11-25** (`hub/comic_hub/balloons_view.py`):
    canvas that paints balloons itself with Qt's real font widths, body
    handles (pink) and tail handles (blue), inspector, keyboard, size check.
    **Save letters** uses `Project.save_balloons`, which rewrites only the
    Letters layer. Checked on Windows with a real window screenshot.
  - Assumption to confirm with Ivón: page mm are print mm, so a balloon's
    font size is the preset's print size (work_scale isn't applied).
  - Next: image/PDF page import (D7), letters in the PS and AI importers,
    then test in the real apps (open question 2 in DESIGN.md §15). Nice to
    have: zoom on the balloon canvas, undo.

The previous work was done in a cloud session that can't reach this PC's
apps. That's why you're here.

## The M2 test brief (done 2026-11-18, kept for re-testing)

1. Set up the testing MCPs (they're for testing only, not part of the product). Both need Node.js 20+:
   ```
   claude mcp add illustrator-mcp -- npx -y illustrator-mcp-server@latest
   claude mcp add photoshop -- npx -y @alisaitteke/photoshop-mcp
   ```
   - The Photoshop one has a small plugin to load inside Photoshop; follow its README.
   - Turn off its usage analytics, which are on by default.
   - Restart Claude Code afterwards so the tools load.
2. Make a test page (PowerShell, from the repo root):
   ```
   $env:PYTHONPATH="core"; python -m cpb_core build test/page_07.svg --panels 6 --seed 48213
   ```
3. Run each importer on it. Use the MCPs to run them and to inspect the result.
   If an MCP can't run a script file, ask Ivón to run it: Photoshop is
   File → Scripts → Browse, Illustrator is File → Scripts → Other Script.
4. Go through the checklist in `importers/README.md`, then ask Ivón to open the
   saved PSD in Clip Studio Paint and screenshot its Layers panel.
5. Write what you found to `importers/M2_RESULTS.md`:
   - for each app: what worked, what failed, exact error messages;
   - for CSP: whether Border layers arrive as vector or raster, and whether clipping and groups survive.

   Commit it with the fixes you made and push. The cloud session reads that file to plan the next step.

Fix bugs in the importers as you find them. Keep the fixes small and say
what changed in `M2_RESULTS.md`.

## Rules of the codebase

- The core is **standard-library Python only**: no Qt, no Krita, no Adobe imports. Python 3.10 is the minimum.
- Everything is in **millimetres**. page.svg uses mm user units.
- **Ownership rule:** the hub only rewrites SVG elements whose `id` starts
  with `cpb-`. Never delete anything else.
- **Importers never compute geometry.** Each panel carries its final rect
  in `cpb:rect`.
- Run `python -m pytest` before every commit (162 tests at last count; the hub tests need PySide6).
  Golden files regenerate only on purpose: `CPB_UPDATE_GOLDEN=1`.
- Don't touch `comicpagebuilder/` (the 0.13 plugin) until M6.
- Commit messages explain the why. Ivón is learning Python, so code comments
  should explain reasons, not restate the code.

## Working with Ivón

Peer-level, playful, direct; she likes pushback with reasons. Keep chat
messages short. She prefers free or open-source tools.
