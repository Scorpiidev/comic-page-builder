# Comic Page Builder — Feature Documentation

**Version:** 0.13.0  
**Platform:** Krita 5.3.1+, Python plugin (pykrita)  
**Author:** Antares  

---

## Overview

Comic Page Builder is a Krita plugin that generates structured comic page documents from configurable templates and randomized layouts. It outputs ready-to-draw `.kra` files with a complete layer stack — panel borders, crop marks, safe area guides, and per-frame drawing groups — in a single action.

The plugin lives at **Tools → Scripts → Comic Page Builder** and opens as a persistent dialog that remembers your settings for the duration of the session.

---

## Tab 0 — Page Setup

All size values are stored internally in millimetres regardless of the display unit selected.

### Paper Preset
- **Preset dropdown** — bundled paper sizes (Commercial, ISO A4, A3, B4, B5, JIS sizes, US Comic, Manga Tankobon, Postcard, and more). User-saved presets appear at the top marked with ★.
- **↺ Reset button** — force-reapplies the currently selected preset, restoring all fields to their defaults even if the dropdown hasn't changed.
- **Save… button** — saves the current binding size as a named user preset, persisted to `resources/data/user_presets.json`.
- **Units** — switches all size fields between `mm`, `cm`, and `in`. The internal PageSpec always stores millimetres; the conversion is display-only.
- **Orientation** — Portrait / Landscape toggle buttons (matching Krita's own New Document dialog style). Swaps width and height automatically.

### Manuscript Size
Full canvas size including bleed on all sides. Has a proportion **lock button** (🔓/🔒) — when locked, changing either dimension scales the other to preserve the aspect ratio.

### Binding Size
The finished trimmed page size. Same proportion lock. When a preset is applied this is set to the preset's dimensions; Manuscript is set to Binding + 2× bleed.

### Bleed & Safe Area
- **Bleed** — the extra area outside the trim line, in mm. Quick-picks: 0 / 3mm / 5mm / 10mm.
- **Safe Area** — distance inside the trim line where essential content (dialogue, faces) must stay.
- **🔗 Auto-link** — when enabled (default), safe area updates automatically to `bleed + 2mm` (minimum 3mm) whenever bleed changes. Click to unlock for manual control.
- **⚠️ Margin warning** — if your panel inner margin is set smaller than the safe area, an orange warning appears reminding you that panels may be clipped in print.

### Resolution
Spinbox (72–1200 dpi). Quick-picks: **72 — Screen**, **150**, **300 — Print**, **600 — HQ**.

### Panel Layout
- **Inner margin** — space between the binding edge and the outermost panel borders, in mm. Quick-picks: 0 / 3mm / 5mm / 8mm.
- **Line strength** — panel border stroke width, in mm. Quick-picks: 0.25 — Thin / 0.5 — Standard / 1mm — Bold / 2mm — Heavy. This setting only affects panel borders — guide layers (Cutting Marks, Finished Size, Safe Area) always use a fixed hairline stroke regardless.

### Color Space
Six options:
- RGB/A 8-bit — digital, webtoon, screen
- RGB/A 16-bit — high quality print
- RGB/A 32-bit float — HDR / VFX
- Gray/A 8-bit — B&W manga / ink
- Gray/A 16-bit — B&W high quality
- CMYK/A 8-bit — offset press

---

## Tab 1 — Layout

A scrollable grid of panel layout thumbnails rendered as live SVG previews.

### Filter tabs
**All / 1P / 2P / 3P / 4P / 5P / 6P / Title / ★ Saved** — filters the grid by panel count. The ★ Saved tab shows only user-created layouts saved from the Custom Layout tab.

### Thumbnail interaction
- **Single click** — selects the layout and enables the generate buttons at the bottom.
- **Double-click** — selects and immediately triggers "Create in Krita".

User-saved layouts appear with a ★ prefix on their label.

---

## Tab 2 — Custom Layout

### BSP Randomizer
Generates panel layouts algorithmically using Binary Space Partitioning.

- **Panel count** — 1 to 8 panels. Hard cap at 8; anything above becomes unreadable on a standard page.
- **Cut mode:**
  - **Auto (smart axis)** — always cuts the longer dimension first. Produces the most readable, balanced layouts. Recommended default.
  - **Horizontal strips only** — all cuts are horizontal; produces row-based layouts.
  - **Vertical columns only** — all cuts are vertical; produces column-based layouts.
  - **Pure random** — random axis each split; produces experimental/dynamic compositions.
- **Gutter** — space between panels in mm, separate from line strength. Default 3mm. Adjustable per roll.
- **🎲 Roll Layout** — generates a new layout and shows a live SVG preview.
- **↺ Re-roll** — rolls again with the same settings.
- **✓ Use This Layout** — sends the current rolled layout to the generate buttons.
- **💾 Save Layout…** — saves the rolled layout as a JSON preset in `resources/layouts/user/`. It will appear immediately in the Layout tab under ★ Saved.

### Save from Open Document
**📄 Save Open Document as Preset…** — reads the shape geometry from the active Krita document's Panels group, normalises it to [0,1] coordinates, and saves it as a reusable JSON layout preset. Works with any panel shapes including manually edited or diagonally cut panels.

---

## Tab 3 — Project

### Output Folder
- **Browse…** — select where batch-generated files are saved.
- **📁 Initialize Project Folders** — creates a standard comic project folder structure inside the selected directory: `Pages / Characters / Comic Script / Environment / Reference Images`. Automatically redirects output to the `Pages` subfolder.

### Batch Generation
- **Pages (max 20)** — number of pages to generate per batch. Hard cap at 20 to avoid memory issues. Run multiple batches for longer comics. Batch generation continues numbering from the highest existing `page_XX.kra` file in the output folder — no overwrites, no gaps.
- **Layout mode:**
  - **Same layout for all pages** — pick one layout from the dropdown; every page uses it.
  - **Random Auto (BSP balanced)** — each page gets a fresh BSP auto-mode layout.
  - **Random Pure (BSP chaotic)** — each page gets a fresh BSP random-mode layout.
  - **Custom per page** — a scrollable list appears with one dropdown per page. Each page can be set to Random Auto, Random Pure, or any named preset.
- **⚙ Generate All Pages** — creates and saves all pages to the output folder, each with its drawing layers already set up. Pages are closed after saving to keep memory low; open the ones you want from the folder.

### Setup Drawing Layers (Regenerate Masks)
Drawing groups are created **automatically** when you generate a page. These buttons exist to **regenerate** them — for example after editing your layout with Krita's panel tool, or if you accidentally deleted a frame group.

- **↺ Regenerate — Current Document** — rebuilds frame groups in the active document only.
- **↺↺ Regenerate — All Open Documents** — applies to every open document that has a Panels group layer. Documents without a Panels layer are silently skipped with a count in the summary.

**Duplicate detection:** if a document already has a Comic Frames group, a dialog appears with three options: Reapply to all / Skip already masked / Cancel.

---

## Generated Document Structure

Every generated document has the following layer stack, top to bottom:

```
[Panels ▼]              ← group layer
    [Panel 1]           ← individual vector layer, one shape
    [Panel 2]
    [Panel N...]
[Cutting Marks]         ← vector layer, crop marks at binding corners (only if bleed > 0)
[Finished Size]         ← vector layer, thin outline of the trim box
[Safe Area]             ← vector layer, cyan guide at the configured safe-area distance inside the trim line
[Paper]                 ← vector layer, white background fill
```

After Setup Drawing Layers runs, the following is inserted between Panels and Cutting Marks:

```
[Comic Frames ▼]        ← master group; add adjustment layers here to affect all panels
    [Frame 1 ▼]         ← colored label for easy identification
        [Borders]       ← clone of Panel 1, Multiply blending
                           (white → transparent; black border stays on top of artwork)
                           (auto-updates when Panel 1 is edited)
        [Ink]           ← paint layer, inherit alpha
        [Color]         ← paint layer, inherit alpha
        [Sketch]        ← paint layer, inherit alpha
        [Mask]          ← vector layer, exact panel shape filled white (clipping base)
    [Frame 2 ▼]
        ...
```

### Layer behavior notes
- **Panels group** — edit individual Panel N layers here to reshape borders. Use Krita's panel tool (comic panel editing tool) on these layers for interactive cuts and merges.
- **Borders clone** — clones only its corresponding Panel N layer, not the whole Panels group. Editing Panel 3 updates Frame 3's Borders automatically.
- **Inherit alpha** — Sketch, Color, and Ink all inherit alpha from Mask. Drawing outside the panel shape is non-destructive; it is simply not visible.
- **Cutting Marks, Finished Size, Safe Area** — guide layers only. Always hairline stroke. Never affect print output. Safe to hide during drawing.
- **Comic Frames master group** — place global adjustment layers (halftone, color grade, curves) inside this group to affect all panels simultaneously.

---

## JSON Layout Format

User layouts are saved as JSON files in `resources/layouts/user/`. The format is compatible with the original ComicCreator layout files:

```json
{
    "layout": [
        { "type": "rect", "data": { "x": 0.0, "y": 0.0, "width": 0.5, "height": 1.0 } },
        { "type": "rect", "data": { "x": 0.5, "y": 0.0, "width": 0.5, "height": 1.0 } }
    ]
}
```

All coordinates are normalised to [0, 1] relative to the drawable area (binding size minus margins). The plugin scales them to actual document coordinates at generation time.

---

## Installation

1. Unzip the plugin archive.
2. Place `comicpagebuilder.desktop` and the `comicpagebuilder/` folder into Krita's `pykrita` resource folder.  
   Find it via: **Settings → Manage Resources… → Open Resource Folder**
3. Enable the plugin: **Settings → Configure Krita → Python Plugin Manager → Comic Page Builder** ✓
4. Restart Krita.
5. Access via: **Tools → Scripts → Comic Page Builder**

To update: overwrite the files in `pykrita/comicpagebuilder/` and close/reopen the dialog. A full Krita restart is only required when first enabling the plugin.

---

## Known Limitations

- **Panels group is a group, not a flat vector layer** — Krita's "select all shapes" commands operate per-layer. To move or transform all panels simultaneously, select all child layers inside the Panels group.
- **Diagonal cuts via BSP** — the randomizer only produces rectilinear (90°) cuts. For diagonal panels, use Krita's panel tool on the individual Panel N layers after generation, then regenerate masks.
- **CMYK profile availability** — the CMYK color space option requires `ISO Coated v2 - Eci.icc` to be installed on your system. If it is not found, Krita will fall back to its default CMYK profile.

---

## Pending / Roadmap

- Dockable panel (DockWidget) mode
- Interactive grid layout editor (based on RCPG merge/split approach)
- Per-project settings persistence across sessions
- Plugin icon
