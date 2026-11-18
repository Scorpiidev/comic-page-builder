# Notes for Claude

This repo is Antares's (Ivón's) solo comic pipeline. It started as a Krita
plugin (Comic Page Builder 0.13, in `comicpagebuilder/`) and is being rebuilt
as a pure-Python core + a pink Windows-7-style hub app + importers for
Photoshop, Illustrator and Krita. The plan and every decision live in
`docs/DESIGN.md`. Read its section 1 (decisions D1–D9) and section 14
(milestones) before changing anything.

## Where things stand (2026-11-18)

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
- Run `python -m pytest` before every commit (105 tests at last count; the hub tests need PySide6).
  Golden files regenerate only on purpose: `CPB_UPDATE_GOLDEN=1`.
- Don't touch `comicpagebuilder/` (the 0.13 plugin) until M6.
- Commit messages explain the why. Ivón is learning Python, so code comments
  should explain reasons, not restate the code.

## Working with Ivón

Peer-level, playful, direct; she likes pushback with reasons. Keep chat
messages short. She prefers free or open-source tools.
