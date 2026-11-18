# M2 results: importers in the real apps

Tested 2026-11-18 on Ivón's Windows 11 PC by the local Claude Code session.
Test page: `python -m cpb_core build test/page_07.svg --panels 6 --seed 48213`
(6 panels, 168 × 260 mm trim, 3 mm bleed, 174 × 266 mm canvas, 600 dpi).

| App | Version | Result |
|---|---|---|
| Photoshop | 27.4.0 (Spanish UI) | **Works after 2 fixes** (below). Every checklist item passes. |
| Illustrator | 30.2.1 (Spanish UI) | **Works as written.** Every checklist item passes. |
| Clip Studio Paint | EX (4.0.3 per CLAUDE.md; not re-checked) | From the PSD, groups, names and clipping survive, but **Border and Mask layers arrive as raster**. File → Import → Vector of `page.svg` gives **editable vector borders** at the exact position, all on one layer and mixed with the guides. |

## How it was run (no MCPs)

The two testing MCPs from CLAUDE.md were **not installed**. Windows COM
automation, which the Adobe apps ship with, plus Claude's desktop screen control
covered everything without a Claude Code restart, without third-party npm
packages, and without the Photoshop MCP's default-on analytics.

- **Photoshop:** a `.psjs` file passed to `Photoshop.exe` on the command line
  runs as a UXP script in the open instance, the same as File → Scripts →
  Browse (also tested once). Results were read back with ExtendScript through
  COM (`Photoshop.Application.DoJavaScriptFile`).
- **Illustrator:** ran `import_page.jsx` through COM `DoJavaScriptFile` (it
  shows the same file dialog as File → Scripts → Other Script). On this PC,
  Illustrator's COM registration points to a stale path
  (`D:\Program Files\Adobe Illustrator 2026\…`, missing `\Adobe\`), so
  `New-Object` only connects once Illustrator is already running, and calls need
  late binding (`[System.__ComObject].InvokeMember`). This is a quirk of this
  PC's install and doesn't affect the importers. A Creative Cloud repair would
  probably fix it.
- **CSP:** opened `test/page_07.psd` (saved by Photoshop after the import) and
  inspected the Layers panel and Layer menu by screen control.

## Photoshop

### Bugs found and fixed (`photoshop/import_page.psjs`)

1. **The import silently did nothing.** After the file picker closed, no
   document appeared and there was no alert or error. Cause: the last line called
   `main()` without `await`. Photoshop ends a UXP script as soon as its
   top-level code returns, so the pending work was dropped. Two probe scripts
   confirmed it: an un-awaited async alert never showed, and the awaited one did.
   **Fix:** `await main().catch(…)` (top-level await works in `.psjs`).
2. **Ink layer vanished, then the import failed.** Error text (Spanish UI):
   `Comic Page Builder import failed: Error: The capa with an id of 5 does not exist.`
   Frame 6 had Border 6, Color, Sketch and Mask 6, but no Ink, and Border 6 was
   clipped. Cause: the Border was made with `make contentLayer` while the
   freshly created, **empty** Ink pixel layer was selected. In that case Photoshop
   replaces the empty layer with the new shape layer, so Ink (id 5) was deleted
   and its clipping passed to the Border. `createLayerGroup` then failed on the
   missing id.
   **Fix:** make the Border right after the Mask (while the Mask is selected),
   then make Sketch/Color/Ink and `border.move(ink, PLACEBEFORE)` to lift the
   Border back on top. Only then set `isClippingMask`.
   - Tried and dropped: selecting the Mask with `batchPlay select` before
     `doc.createLayer`. The new pixel layers still landed **above** the Border, so
     they clipped to the stroke. The explicit `move()` doesn't depend on
     selection.

### Checklist

- [x] **Script ran.** Alert: `Imported page_07.svg: 6 panels on a 174 × 266 mm canvas (4110 × 6283 px at 600 dpi).`
- [x] **Size and resolution match:** document is 4110 × 6283 px, 600 ppi, RGB.
- [x] **Border layers are real shape layers.** The Properties panel shows "Shape
  properties" with Fill none and Stroke 14.17 px, solid line, all editable (14.17 px =
  0.6 mm at 600 dpi). Action Manager: layerKind 4 (vector), `strokeEnabled=true`,
  `fillEnabled=false`.
- [x] **Painting stays inside the panel.** Filled Frame 1 › Sketch and Frame 4 ›
  Color edge to edge, then sampled the composite:
  panel 1 centre = 255,150,150 (the fill); gutter 1|2, left margin, panel 2
  centre and gutter 3|4 = 255,255,255; panel 4 centre = 150,190,255 (the fill).
- [x] **Frame 1 on top, reading order 1→6.** Bounds go top-left, top-right,
  middle-left… as expected.
- [x] **Guides on trim and safe area.** Vertical at 70.87 / 4039.37 px (3 / 171
  mm), horizontal at 70.87 / 6212.60 px (3 / 263 mm), safe area at 188.98 /
  3921.26 / 6094.49 px (8 / 166 / 258 mm).
- [x] **Saved as PSD:** `test/page_07.psd`, 9.5 MB (kept the two test fills on
  purpose so lost clipping would be obvious in CSP).

Final layer stack (DOM dump):

```
Comic Frames (group)
  Frame 1 (group)
    Border 1 (SOLIDFILL = shape layer, stroke only)
    Ink (clipped)
    Color (clipped)
    Sketch (clipped)
    Mask 1 (SOLIDFILL = shape layer, white fill)
  Frame 2 … Frame 6 (same)
Fondo (Background)
```

Panel bounds are exact: Mask 1 = 259,259 → 2020,2146 px; Border 1 is 7 px
bigger on each side (half of the centred 14.17 px stroke).

### Smaller notes (not fixed)

- `app.showAlert` uses a red ✕ "error" icon even for the success message
  (Windows). Cosmetic, but it reads like a failure. A UXP dialog or a gentler
  message would fix it later.
- Error text is half-localized ("The **capa** with an id…"). Worth knowing when
  reading reports from a Spanish Photoshop.

## Illustrator

No changes needed.

- [x] **Script ran.** Alert: `Imported page_07.svg: 6 panels. Layers: Guides, Letters, Panels, Paper.`
  No "Couldn't find…" lines, so Illustrator kept the ids as item names
  (`cpb-paper`, `cpb-panels`, `cpb-guides`). The empty `cpb-letters` group
  ends up the same either way, so whether Illustrator kept it wasn't checked.
- [x] **Four layers, in order:** Guides, Letters, Panels, Paper. Illustrator's own
  "Layer 1" was removed. Letters is the active layer.
- [x] **Panels are editable paths with the right stroke.** `Panel 1` … `Panel 6`,
  each a closed 4-point PathItem, stroke #1b1b1b at 0.6 mm, no fill. Geometry
  matches `cpb:rect` to the micron (e.g. Panel 1 = 11, 11, 74.5 × 79.833 mm;
  Panel 3 height reads 105.445 vs 105.444, which is rounding).
- [x] **Guides don't print.** Guides layer is `locked=true`, `printable=false`,
  and the Layers panel shows its name in italics (Illustrator's non-printing
  marker). The Print dialog's "Print layers" is "Visible & Printable Layers". The
  dialog's preview thumbnail is too small to read the dashes, so this check rests
  on the layer flag.
- Guides content: `cpb-trim` (3, 3, 168 × 260 mm, #8a8a8f 0.25 mm, dash 2/1.4 mm),
  `cpb-safe` (8, 8, 158 × 250 mm, #00a6d6, dash 1.4/1.2 mm), `cpb-crop-marks`
  (compound path). Paper: `cpb-paper-fill`, white, full canvas, locked layer.
- Document came in as RGB with rulers in **millimetres**.

Still open (DESIGN §15 Q2): the test page has no letters and nothing uses
`clip-path` yet, so how Illustrator handles `clipPath` and positioned
`tspan`s is **untested**. The unreferenced `cpb-clip-N` defs were simply
dropped. This needs a page with balloons (M5) to test.

## Clip Studio Paint (opened `test/page_07.psd`)

- **Groups and names survive.** Comic Frames › Frame 1…6 come in as folders with
  blend mode "Through" (pass-through), with every layer name intact.
  Fondo becomes a locked paper layer at the bottom.
- **Clipping survives.** Ink, Color and Sketch each show CSP's red "clip to layer
  below" bar, and the two test fills stay inside panels 1 and 4 on the canvas.
- **Border layers arrive as raster** (and so do Masks). With Border 1 or Mask 4
  selected, Layer → Rasterize is greyed out (it is only enabled for non-raster
  layers), "Convert to lines and tones" is enabled, and Layer Property shows only
  Expression color. The stroke looks right at 600 dpi, but its width and colour
  are no longer editable.

So through the PSD alone, CSP gets the **art layers and structure** but the
**panel borders don't stay editable vectors**.

A screenshot of CSP's Layers panel and canvas was shared with Ivón in the session.

### Follow-up: CSP's File → Import → Vector… with `page.svg`

Ivón asked for this test the same day. Imported `test/page_07.svg` into the
open `page_07.psd` (no options dialog appeared).

- **It arrives as a real vector layer**, one layer named after the file
  (`page_07`), inserted above the selected layer. The thumbnail has CSP's
  vector icon, Layer → Rasterize is *enabled*, and Layer Property offers the
  vector tool navigation.
- **Each panel is its own closed vector line.** The Object tool selects panel 2
  alone, with control points at the corners. Tool Property shows brush size
  **14.2 px** (0.6 mm at 600 dpi) and the dark stroke colour, both editable.
- **The position is exact.** At 100% zoom, a crop of panel 2's corner with only
  the vector showing matches the crop with only the PSD's raster Border 2
  showing, so they agree within about 1 px (0.04 mm).
- **Everything lands on that one layer:** panels, trim, safe area and crop
  marks, plus the paper. The guides would print unless they're deleted by
  hand.
- **Dashes are lost.** Trim and safe come in as solid lines.
- **Fill-only shapes turn into strokes.** CSP vector layers can't hold fills,
  so the white `cpb-paper-fill` rect became a closed **white line 23.5 px
  (≈ 1 mm) wide around the canvas edge**. That's SVG's default `stroke-width`
  of 1 user unit, and our user unit is 1 mm. It sits in the bleed, but it would
  paint over bleed art.
- Not tested: rounded corners (this page has radius 0), and CSP's own
  frame-border folders (an SVG can't create those).

What this means for the plan (DESIGN §8.4): a CSP route that keeps borders
editable looks like **PSD for the frames, art layers and clipping, plus
Import → Vector of a borders-only SVG**. That SVG would hold just the panel
paths, with stroke set and no paper, guides or fills, and would replace the
raster Border layers. All panels share one vector layer, so it belongs above
Comic Frames, not inside a Frame folder. The hub could write that file next
to `page.svg`.

## Files changed

- `importers/photoshop/import_page.psjs`: top-level `await`; Border made
  before the art layers, then moved above Ink; clipping set last.
