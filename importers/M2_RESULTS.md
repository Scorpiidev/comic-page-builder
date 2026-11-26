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
raster Border layers.

### Built and tested: `python -m cpb_core borders page.svg`

Ivón said to keep going, so the core now writes that file: `page_07.svg` gives
`page_07_borders.svg`. It keeps the same canvas and viewBox, holds one `<path>`
per panel with the same path data as `page.svg`, uses `fill="none"`, and has no
paper, guides, clip defs or letters. It is marked `cpb:format="cpb-borders"`,
and the page reader refuses it with a clear message. Code is in
`core/cpb_core/svg/borders.py`, with tests in `tests/test_borders.py` (79
tests now).

Tested end to end with a **rounded** page, because rounded corners hadn't been
tried in either app:
`build test/page_08.svg --panels 5 --seed 777 --radius 3`.

- **Photoshop** imports rounded frames fine. All 5 frames have the usual stack,
  and the clipping follows the curve: after filling Frame 1 › Color edge to
  edge, a sample just outside the 3 mm curve reads 255,255,255 and one just
  inside reads the fill.
- **CSP**, with `page_08.psd` open and Comic Frames selected, then
  Import → Vector of `page_08_borders.svg`:
  - you get one vector layer, `page_08_borders`, at the top **inside** Comic
    Frames, above Frame 1;
  - there are **no guide lines and no paper outline** this time; the brush size
    reads 14.2 px;
  - at 100% the rounded corner is a single clean stroke. A crop with only the
    vector showing matches a crop with only the PSD's raster Border showing,
    in both place and thickness;
  - each 3 mm arc arrives as about 6 control points rather than one curve.
    It's smooth, just a little fiddlier to reshape.
- Not done automatically: deleting the raster Border layers in CSP. That stays
  a manual step (it's in `importers/README.md`).

## After M2: Photoshop re-import (built and tested 2026-11-18)

Running `import_page.psjs` with a PSD that it made as the active document now
**updates** that PSD instead of making a new one (DESIGN §8.1, §8.2).

**How it finds its own layers:** each hub layer carries a tag in its own XMP
metadata: `cpb:id` = `cpb-frames`, `cpb-frame-N`, `cpb-mask-N` or
`cpb-border-N`. The script sets and reads the tag with batchPlay on the layer's
`metadata` property. A probe confirmed three things first:
- the tag survives renaming the layer and a save and reopen as PSD;
- layer ids persist;
- a duplicated layer copies the tag, so the script keeps the topmost copy.

**What an update does:**
- **Update or new document?** It updates only if the active document's Comic
  Frames tag has the same page number. Anything else gets a new document and
  the active one isn't changed. That includes PSDs made before this change,
  which have no tags.
- **Changed panels:** a key stored on each frame covers rect, stroke, fill and
  radius. If the key changed, Mask and Border are redrawn: a new shape is made
  above the old one, then the old one is deleted. Names you gave them are kept.
  Frames whose key matches are left alone.
- **New panel:** gets a new frame, slotted into reading order.
- **Panel gone:** its frame is hidden, never deleted. It's shown again if the
  panel comes back.
- **Border or Mask deleted by hand:** made again.
- **Guides:** only the hub's own are moved (their positions are stored in the
  tag), and only when the trim or safe area moved.
- **Page size or dpi changed:** the update is refused and nothing changes,
  because resizing the canvas would shift or rescale the art.
- **Undo:** the whole update is one history step, "Update comic frames". If
  anything fails partway, it rolls back.

**Test.** A harness ran the real script with the file picker and the alert
swapped for a fixed path and a log file. Results were read back by
ExtendScript over COM.

Test page `page_09`, 6 panels, seed 48213:
1. **Fresh import** with the untagged `page_07.psd` active made a new document,
   `page_09`, and left `page_07` alone.
2. **Test art:** a rectangle painted in Frame 1 › Sketch
   (400,400 → 2400,2000 px, running past the panel's right edge), and one in
   Frame 4 › Color.
3. **New layout, same page** (seed 777): all 6 frames were redrawn.
   - The art layers kept their ids and pixel bounds, and their clipping.
   - Panel 1 grew to the right, so art that used to be hidden under the gutter
     now shows: the sample at 2300,1000 reads the art colour. The new gutter
     reads white.
   - Frame 4's art below the panel's new bottom edge is clipped away.
   - It made one history step. Stepping back one state brought back the old
     shapes (old layer ids).
4. **Same file again:** "already matches … Nothing changed", and no history
   step.
5. **Hand edits, then 7 panels.** Before the run: Frame 2 renamed "Splash",
   Border 3 deleted, art painted in Frame 6 › Ink.
   - "Splash" was found and kept its name.
   - Border 3 was made again on top of Frame 3.
   - Frame 7 is new, placed under Frame 6.
6. **4 panels:** frames 5–7 hidden, and Frame 6's art is still there.
   **Back to 6:** frames 5 and 6 shown and redrawn; 7 stays hidden.
7. **Refusal and new page:**
   - A 170 mm wide trim was refused with the size message, and nothing changed.
   - Page 10 with `page_09` active made a new document.

**Bug found while testing (fixed):** setting `isClippingMask = false` on a
layer that isn't clipped throws "El comando “Soltar máscara de recorte” no
está disponible" ("Release Clipping Mask is not available"). The script now
checks first (`unclip`). The rollback did its job here: the document came back
exactly as it was before the failed run.

**Worth knowing (design, not a bug):** frames follow panel **numbers**. When a
new layout renumbers the panels (say, adding a panel to a BSP layout), the art
in Frame 4 stays in Frame 4, so it moves to wherever panel 4 is now. In the
7-panel test, Frame 4's art (drawn in the right column) ended up behind a
left-column mask.
- That's fine for nudging gutters or tweaking a layout.
- After a big re-layout, expect to move art by hand.
- A "match frames by position" option could come later if this bites.

**Not changed:** a fresh import still leaves many history steps. Only updates
are one step. A new document can just be closed.

## After M2: Illustrator re-import (built and tested 2026-11-18)

Running `import_page.jsx` with a document it made as the active document now
**updates** that document. Tested on Illustrator 30.2.1.

**How it finds its own items:** each hub item carries a **note** (the
Attributes panel shows it), such as
`Comic Page Builder: cpb-panel-3 | page 9 | key 1f2e3d4c`. A probe confirmed
the note survives a save as `.ai` and a reopen.

The key is a short hash of the element's own tag in `page.svg`. The hub writes
the same text for the same panel, so a new key means the panel changed. The
script never has to understand the geometry.

**What an update does:**
- It opens a temporary copy of the new `page.svg`. A copy matters because, if
  the document is still that `page.svg`, opening the file again would just hand
  back the same document.
- For each hub item whose key changed, it duplicates the new item in above the
  old one, then deletes the old one. The new item keeps:
  - the old name;
  - its lock and hidden state;
  - its place as the clipping path of a clip group you made.
- **New panels** go next to their neighbour panel.
- **Panels that left the layout** are hidden, never deleted.
- **Unchanged items** (here, guides and paper) aren't touched.
- **Locked or hidden layers** are unlocked and shown for the update, then put
  back.
- **Refused:** a page whose size changed.
- **New document instead:** another page number, or a document with no notes.

**Test** (a harness swapped the file dialog and alerts; then one real run from
File → Scripts → Other Script).

Fresh import of `page_09.svg`, then the user edits:
- lettering (a text frame and a balloon on Letters);
- Panel 2 used as the clipping path of a clip group over an "SFX art"
  rectangle;
- Panel 3 renamed "Splash", Panel 1 locked;
- saved as `page_09.ai`, closed and reopened.

Results:
1. **New layout (seed 777):** all 6 panels sit on their new rects. The guides
   and paper were left alone, and the edits survived: lettering untouched,
   "Splash" kept, Panel 1 still locked, and the clip group still clipped by
   the new Panel 2.
2. **7 panels** (run from the menu): Panel 7 added.
   **Same file again:** "already matches … Nothing changed".
3. **Panel 4 deleted by hand, then 4 panels:** Panel 4 made again, and
   panels 5–7 hidden. **Back to 6:** 5 and 6 shown and redrawn; 7 stays hidden.
4. **Refusals and new documents:**
   - A 176 mm wide page was refused, and nothing changed.
   - Page 10 made a new document.
   - An old untagged import gets "can't be updated, close it to import
     fresh".
   - A fresh import with no document open works.

**Found while testing (fixed):**
- **Slow:** the first version took **36–40 s** for 7 panels, from COM and from
  the menu alike. Reading the items of a document that isn't active costs about
  0.3 s per item, and the script searched the temporary page once per panel.
  It now collects them all in one pass while that page is active: **3 s**, and
  under 4 s from the menu.
- **Undo can't be one step.** Illustrator undoes a script operation by
  operation: one Ctrl+Z after a menu run only took back Panel 7's name and
  note. ExtendScript has no way to group them, unlike Photoshop's
  `suspendHistory`. So File → Revert is the way back, and the script:
  - asks first when the document has unsaved changes ("save first if you want
    File > Revert as a one-step way back");
  - asks first, more firmly, when the document is still the hub's `page.svg`
    (never saved as `.ai`);
  - doesn't ask when nothing would change (it checks the notes first);
  - says so in the final alert.
- A fresh import now says to save as `.ai` before lettering. Illustrator saves
  a document opened from an SVG back as SVG, which would overwrite the hub's
  `page.svg`.
- With no document open, an early version would have crashed on the
  "already open" check (`null === null`). Fixed before it ran.

**Not covered:** balloons (`cpb-letters`) are still empty until M5. When they
exist, their groups will need the same notes.

## After M5 started: hand-cut panels in Photoshop (2026-11-26)

The layout builder's panels are polygons, but `import_page.psjs` built
rectangle frames from `cpb:rect`, so slanted panels came in as their
bounding boxes.

**Smart objects or native shapes?** Ivón suggested placing the SVG as a smart
object. A probe showed `make contentLayer` also takes a `pathClass` shape (a
list of anchors with curve handles), so frames stay ordinary shape layers:
stroke editable in Properties, editable with Direct Selection, and nothing
hidden inside a .psb for CSP to flatten. Smart objects stay the fallback.

**What changed** (`photoshop/import_page.psjs`):
- A panel with `cpb:points` takes its outline from its `d`, which the hub
  writes with M/L/H/V/C/Z only, so rounded corners arrive as the hub drew
  them. `parsePath` turns it into Photoshop path points; any other command
  stops the import with an error instead of giving a wrong shape.
- Insets: an **Inset N** group above the ordinary frames, holding its frames
  and an **Inset gap** shape (white fill and white stroke, from
  `cpb-inset-gap-N`). Without that, an inset could sit under a neighbour's
  white mask, because frames are stacked by panel number.
- Updates keep inset groups in line: missing groups are made, gaps are
  redrawn, added or removed ("Gap around insets" off), frames move in or out
  of an inset when their number changes sides, and a group is only deleted
  once it's empty.
- The frame key only gains the outline for polygons, so documents imported
  before this change aren't redrawn for nothing.

**Test** (Photoshop 27.4, harness as before; results read back over COM, with
PNG exports):
1. Fresh import of a hand-cut page (3 slanted cuts plus an inset, 2.5 mm
   corners, and the same page with sharp corners). It matches the hub's
   render, gap included. Art painted into Frame 3, 2 and the inset clipped to
   the slanted, rounded outlines.
2. Updates on that document: the inset moved and a cut added (frames 3–5
   redrawn, 6 added, the inset group's frames swapped); same file again:
   "Nothing changed"; gap off: gap removed; inset removed: empty group
   deleted, extra frames hidden; back to the first layout: group, gap and
   frames restored. The art was identical after all five.
3. A BSP page imported with the previous script, then updated with this one:
   "already matches … Nothing changed".

**Bug found while testing (fixed):** the gap rectangle is written with H/V,
which the first parser silently skipped, drawing a wrong gap.

**Not tested yet:** Illustrator with hand-cut pages and insets. Its script
copies every `cpb-` item from the SVG, so it should work.

## M5: balloons in Photoshop and Illustrator (2026-11-26)

Test page: a hand-cut page with an inset and one balloon of each kind
(speech, thought, shout, whisper, caption), dialogue in Comic Sans MS **Bold**
(`ComicSansMS-Bold`) and the caption in Segoe UI **Semibold Italic**. Faces
whose family name alone would give the wrong style, on purpose.

### Illustrator (30.2.1)

Hand-cut panels and the inset gap came in right as they were (open question
2's clip-path half: the panels don't need clip paths). The balloon text didn't:
- **Each tspan became its own left-aligned point text**, so a 4-line balloon
  was 4 loose text objects.
- **Fonts picked by family only:** Bold came in as Comic Sans Regular, the
  caption as plain Segoe UI.
- **Text changes would never have reached an update:** the change key was the
  fingerprint of the `<text>` tag alone, and the words live inside it.

**Fixed** (`illustrator/import_page.jsx`):
- After opening the page (fresh or the update's temporary copy), each balloon's
  text is rebuilt as **one point text**: the hub's lines as paragraphs,
  centred on the first baseline, font by `ps_name`, the preset's size, and
  leading taken from the tspans' spacing.
- A text's key includes its words.
- Text notes carry a fingerprint of the words (`| words …`). If you edited a
  balloon's words in Illustrator and the hub changed that balloon too, yours
  is kept, hidden and no longer the hub's ("Your edit of …"), under the new one.
- A font that isn't installed is named in the final message; the balloon
  keeps the stand-in Illustrator picked.
- Inset gaps are named "Inset gap N".

### Photoshop (27.4)

New in `photoshop/import_page.psjs`: a **Letters** group above Comic Frames,
one **Balloon N** group per balloon, holding a live **text layer** over a
**shape layer** (round joins; whisper dashes). It's built on import and kept
in line on updates, with the same rules as frames: redrawn when the balloon's
group in page.svg changed, added when new, hidden (never deleted) when gone,
shown again when back. The same rule for your text edits as in Illustrator
(kept, hidden, untagged).

**Found while testing:**
- **Type size at 600 dpi:** `createTextLayer({fontSize: 8})` gave text 8 px
  tall (ExtendScript read it back as 0.96 pt). Photoshop's UXP scripting
  takes type sizes as if the document were 72 dpi, so the script asks for
  size × dpi/72. The Character panel then shows 8 pt. Leading the same.
- The anchor is the first baseline, and centring keeps it in place, so the
  hub's tspan position can be used as is.
- A thought balloon's outline has several subpaths (the bubbles), so
  `parsePath` returns a list of subpaths now.
- Hiding the kept "Your edit" layer before tagging and moving it didn't
  stick (it came back visible); it's hidden last now.

### Checks
- Both apps: the page matches the hub's layout. Text centred in the
  balloons, the exact faces, 8 pt / 7 pt, leading 9.6 / 8.4 pt.
- Update with balloon 1 moved and balloon 2's words changed after editing
  them by hand: 1 redrawn, 2's new text on top and the hand edit kept,
  hidden. Same file again: "Nothing changed".
- Photoshop: balloon 3 removed in the hub → hidden; back → shown.
- A preset with a font that isn't installed (`NoSuchFont-Regular`): both
  apps import, name it in the message, and use a stand-in (Photoshop: Myriad
  Pro).
- Regression: a page without balloons imports as before; a PSD made by the
  previous script updates with "Nothing changed".

**Still open:** the art layer of drawn pages (D7) isn't imported by either
script yet. CSP gets balloons only as raster through the PSD.

## D7: drawn pages in Photoshop and Illustrator (2026-11-26)

Test page: a drawn page (2008 × 3071 px PNG at 300 dpi, covering the trim),
no panels, two balloons, as `Project.add_art_page` writes it: the image beside
page.svg, linked from `cpb-art` by a relative `xlink:href`.

**Before:** Photoshop refused it ("The page has no panels."). Illustrator
linked the image, the right size but **3 mm off** in x and y, and left it in
a stray "Layer 1" under the white Paper, so the drawing was hidden.

**Photoshop** (`import_page.psjs`):
- A page with art and no panels is fine.
- The image is placed as an **embedded smart object** (the PSD carries it,
  and CSP can read it), scaled and moved onto the rect in page.svg, named
  **Art**, under Comic Frames and Letters.
- An update with different art places the new one above the old. The old one
  is kept, hidden and untagged ("Old art"), since you may have painted fixes
  into it.
- Found while testing: on a drawn page the empty Comic Frames group was
  selected, so Letters got built **inside** it. Letters is now moved above it.

**Illustrator** (`import_page.jsx`):
- A locked **Art** layer between Panels and Paper (removed when the page has
  no art). The image stays **linked**, so a re-exported drawing updates.
- The image is put exactly at page.svg's x, y, width and height.
- Updates open their temporary copy **beside page.svg** (`.cpb-update-….svg`,
  removed afterwards), not in the temp folder, so the relative link resolves.

**Checks:** art at 3 mm, 170.011 mm wide in both apps (35 px at 300 dpi in
Photoshop); moving the art in page.svg to x = 8 mm redrew it there (Photoshop:
old art kept hidden; Illustrator: still linked, layer still locked); same file
again: "Nothing changed"; generated pages get no Art layer and update as
before; a PSD from the previous script still says "Nothing changed".

**Not covered:** the change key is the `<image>` tag, so redrawing the art
into the *same* file name isn't noticed by Photoshop (its copy is embedded).
Illustrator's link picks it up by itself. The hub doesn't replace art yet, so
this can wait.

## Files changed

- `importers/photoshop/import_page.psjs`: top-level `await`; Border made
  before the art layers, then moved above Ink; clipping set last. After M2:
  XMP tags on the hub's layers, and the update mode described above.
- `importers/illustrator/import_page.jsx`: after M2, notes on the hub's
  items and the update mode described above.
- `core/cpb_core/svg/borders.py`, the `borders` CLI command, and
  `tests/test_borders.py`: the borders-only SVG for CSP.
- `importers/README.md`: how to bring a page into CSP.
- `docs/DESIGN.md`: M2 marked done; §6, §8.4 and §15 updated with what the
  test found.
