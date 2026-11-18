# Importers

Scripts that turn a hub `page.svg` into native layers in each app. They only
read the file; they never compute geometry (every panel carries its final
rectangle in `cpb:rect`).

Make a test page first, from the repository root:

```
PYTHONPATH=core python -m cpb_core build test/page_07.svg --panels 6 --seed 48213
```

(On Windows PowerShell: `$env:PYTHONPATH="core"; python -m cpb_core build test/page_07.svg --panels 6 --seed 48213`.)

## Photoshop (2023 or newer, written for 27.4)

1. **File → Scripts → Browse…** and choose `photoshop/import_page.psjs`.
2. Pick `page_07.svg`.

You get a new document at the page's real size and resolution: a
**Comic Frames** group with one **Frame N** group per panel, guides at the
trim and safe area, and a white Background.

Inside each frame: **Border N** (shape layer, editable stroke), **Ink**,
**Color** and **Sketch** (clipped to the mask), and **Mask N** (white panel
shape).

## Illustrator (written for 30.2)

1. **File → Scripts → Other Script…** and choose `illustrator/import_page.jsx`.
2. Pick `page_07.svg`.

The page opens with layers **Guides** (locked, non-printing), **Letters**,
**Panels** (named Panel 1, Panel 2…) and **Paper** (locked).

## M2 test: what to check and report back

This milestone exists to find out what actually works. For each app, note:

**Photoshop**
- [ ] The script ran. If not, copy the error message.
- [ ] Document size and resolution match what the alert says.
- [ ] Border layers are real **shape layers**: double-click the stroke, can you change its width and colour?
- [ ] Painting on Sketch / Ink / Color stays inside the panel.
- [ ] Frame 1 is at the top, and the frames are in reading order.
- [ ] Guides sit on the trim and safe area.
- [ ] Save as PSD.

**Illustrator**
- [ ] The script ran. Any "Couldn't find…" lines in the alert?
- [ ] Four layers, in the order Guides, Letters, Panels, Paper.
- [ ] Panels are editable paths with the right stroke.
- [ ] Guides don't print (File → Print preview).

**Clip Studio Paint (4.0.3)**: open the PSD you saved from Photoshop.
- [ ] Are the groups and the Frame N names kept?
- [ ] Do Border layers come in as **vector** layers or as raster?
- [ ] Is the clipping (Sketch / Ink / Color clipped to the mask) kept?

Screenshots of the Layers panel in each app are the most useful thing to send.
