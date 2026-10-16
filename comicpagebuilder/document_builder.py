"""
document_builder.py — Krita document generation + mask scaffolding

Layer stack (top to bottom):
  [Panels]         — single vector layer, all panel borders as SVG rects
  [Cutting Marks]  — vector layer with crop marks (if bleed > 0)
  [Finished Size]  — vector layer: binding box outline
  [Paper]          — white fill background
"""

from typing import Optional
from .utils import PageSpec, mm_to_pt, mm_to_px


# ---------------------------------------------------------------------------
# SVG helpers
# ---------------------------------------------------------------------------

def _svg_wrap(w: float, h: float, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{w:.4f}pt" height="{h:.4f}pt" '
        f'viewBox="0 0 {w:.4f} {h:.4f}">'
        f'{body}</svg>'
    )

def _rect(x, y, w, h, fill, stroke, sw) -> str:
    return (
        f'<rect x="{x:.4f}" y="{y:.4f}" width="{w:.4f}" height="{h:.4f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{sw:.4f}"/>'
    )

def _line(x1, y1, x2, y2, stroke, sw) -> str:
    return (
        f'<line x1="{x1:.4f}" y1="{y1:.4f}" x2="{x2:.4f}" y2="{y2:.4f}" '
        f'stroke="{stroke}" stroke-width="{sw:.4f}"/>'
    )


# ---------------------------------------------------------------------------
# SVG generators
# ---------------------------------------------------------------------------

def _build_panels_svg(spec: PageSpec, layout: dict) -> str:
    ms_w = mm_to_pt(spec.effective_manuscript_w())
    ms_h = mm_to_pt(spec.effective_manuscript_h())
    bd_w = mm_to_pt(spec.effective_binding_w())
    bd_h = mm_to_pt(spec.effective_binding_h())
    mg   = mm_to_pt(spec.margins)
    lw   = mm_to_pt(spec.line_strength)

    ox     = (ms_w - bd_w) / 2
    oy     = (ms_h - bd_h) / 2
    draw_x = ox + mg
    draw_y = oy + mg
    draw_w = bd_w - mg * 2
    draw_h = bd_h - mg * 2

    shapes = []
    for r in layout.get("rects", []):
        rx = draw_x + r["x"]     * draw_w
        ry = draw_y + r["y"]     * draw_h
        rw = r["width"]  * draw_w
        rh = r["height"] * draw_h
        shapes.append(_rect(rx, ry, rw, rh, fill="white", stroke="black", sw=lw))

    return _svg_wrap(ms_w, ms_h, "".join(shapes))



# Fixed stroke weight for printer guides — always thin regardless of line_strength.
# These are reference lines, not artistic elements.
_GUIDE_STROKE_PT = 0.5   # ~0.18mm, hairline


def _build_finished_size_svg(spec: PageSpec) -> str:
    ms_w = mm_to_pt(spec.effective_manuscript_w())
    ms_h = mm_to_pt(spec.effective_manuscript_h())
    bd_w = mm_to_pt(spec.effective_binding_w())
    bd_h = mm_to_pt(spec.effective_binding_h())
    ox   = (ms_w - bd_w) / 2
    oy   = (ms_h - bd_h) / 2
    shape = _rect(ox, oy, bd_w, bd_h, fill="none", stroke="#444444", sw=_GUIDE_STROKE_PT)
    return _svg_wrap(ms_w, ms_h, shape)


def _build_crop_marks_svg(spec: PageSpec) -> Optional[str]:
    if spec.bleed <= 0:
        return None
    ms_w  = mm_to_pt(spec.effective_manuscript_w())
    ms_h  = mm_to_pt(spec.effective_manuscript_h())
    bd_w  = mm_to_pt(spec.effective_binding_w())
    bd_h  = mm_to_pt(spec.effective_binding_h())
    bleed = mm_to_pt(spec.bleed)
    ox    = (ms_w - bd_w) / 2
    oy    = (ms_h - bd_h) / 2
    left, right = ox, ox + bd_w
    top,  bot   = oy, oy + bd_h
    mark_len = min(bleed * 0.8, mm_to_pt(10))
    gap      = mm_to_pt(1)
    c        = "#222222"
    lw       = _GUIDE_STROKE_PT
    lines = [
        _line(left,  oy - gap,           left,  oy - gap - mark_len,           c, lw),
        _line(ox - gap,           top,   ox - gap - mark_len,           top,   c, lw),
        _line(right, oy - gap,           right, oy - gap - mark_len,           c, lw),
        _line(ox + bd_w + gap,    top,   ox + bd_w + gap + mark_len,    top,   c, lw),
        _line(left,  oy + bd_h + gap,    left,  oy + bd_h + gap + mark_len,    c, lw),
        _line(ox - gap,           bot,   ox - gap - mark_len,           bot,   c, lw),
        _line(right, oy + bd_h + gap,    right, oy + bd_h + gap + mark_len,    c, lw),
        _line(ox + bd_w + gap,    bot,   ox + bd_w + gap + mark_len,    bot,   c, lw),
    ]
    return _svg_wrap(ms_w, ms_h, "".join(lines))


def _build_safe_area_svg(spec: PageSpec) -> str:
    """
    Safe area inside the trim line - essential art must stay inside.
    Rendered as a cyan dashed guide line, never affects print output.
    """
    ms_w        = mm_to_pt(spec.effective_manuscript_w())
    ms_h        = mm_to_pt(spec.effective_manuscript_h())
    bd_w        = mm_to_pt(spec.effective_binding_w())
    bd_h        = mm_to_pt(spec.effective_binding_h())
    
    # Now reads from your UI instead of a hardcoded 5mm
    safe_margin = mm_to_pt(spec.safe_area) 
    
    ox          = (ms_w - bd_w) / 2 + safe_margin
    oy          = (ms_h - bd_h) / 2 + safe_margin
    safe_w      = bd_w - safe_margin * 2
    safe_h      = bd_h - safe_margin * 2

    shape = _rect(ox, oy, safe_w, safe_h,
                  fill="none", stroke="#00ccff", sw=_GUIDE_STROKE_PT)
    return _svg_wrap(ms_w, ms_h, shape)


def _build_paper_svg(spec: PageSpec) -> str:
    ms_w = mm_to_pt(spec.effective_manuscript_w())
    ms_h = mm_to_pt(spec.effective_manuscript_h())
    return _svg_wrap(ms_w, ms_h, _rect(0, 0, ms_w, ms_h, "white", "none", 0))


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------

def build_document(spec: PageSpec, layout: dict):
    try:
        from krita import Krita
    except ImportError as e:
        raise RuntimeError(f"Krita API not available: {e}")

    app = Krita.instance()

    cs_map = {
        "RGBA":    ("RGBA",  "U8",  "sRGB-elle-V2-srgbtrc.icc"),
        "RGBA16":  ("RGBA",  "U16", "sRGB-elle-V2-srgbtrc.icc"),
        "RGBA32":  ("RGBA",  "F32", "sRGB-elle-V2-srgbtrc.icc"),
        "GRAYA":   ("GRAYA", "U8",  "Gray-D50-elle-V4-g22.icc"),
        "GRAYA16": ("GRAYA", "U16", "Gray-D50-elle-V4-g22.icc"),
        "CMYK":    ("CMYKA", "U8",  "ISO Coated v2 - Eci.icc"),
    }
    cs_id = getattr(spec, "colorspace", "RGBA")
    model, depth, profile = cs_map.get(cs_id, cs_map["RGBA"])

    w_px = mm_to_px(spec.effective_manuscript_w(), spec.resolution)
    h_px = mm_to_px(spec.effective_manuscript_h(), spec.resolution)

    doc = app.createDocument(w_px, h_px, "Comic Page", model, depth, profile, spec.resolution)
    if doc is None:
        raise RuntimeError("Krita returned None from createDocument.")

    root = doc.rootNode()

    def add_vector(name: str, svg: str):
        layer = doc.createVectorLayer(name)
        root.addChildNode(layer, None)
        layer.addShapesFromSvg(svg)
        return layer

    paper_layer    = add_vector("Paper",         _build_paper_svg(spec))
    safe_layer     = add_vector("Safe Area",     _build_safe_area_svg(spec))
    fs_layer       = add_vector("Finished Size", _build_finished_size_svg(spec))

    crop_svg   = _build_crop_marks_svg(spec)
    crop_layer = add_vector("Cutting Marks", crop_svg) if crop_svg else None

    # Panels: group layer containing one vector layer per panel.
    # Individual layers allow setup_masks to clone each one independently,
    # so Frame N's Borders clone updates only when Panel N is edited.
    panels_group = None
    if layout and layout.get("rects"):
        ms_w   = mm_to_pt(spec.effective_manuscript_w())
        ms_h   = mm_to_pt(spec.effective_manuscript_h())
        bd_w   = mm_to_pt(spec.effective_binding_w())
        bd_h   = mm_to_pt(spec.effective_binding_h())
        mg     = mm_to_pt(spec.margins)
        lw     = mm_to_pt(spec.line_strength)
        ox     = (ms_w - bd_w) / 2
        oy     = (ms_h - bd_h) / 2
        draw_x = ox + mg
        draw_y = oy + mg
        draw_w = bd_w - mg * 2
        draw_h = bd_h - mg * 2

        panels_group = doc.createGroupLayer("Panels")
        root.addChildNode(panels_group, None)

        for i, r in enumerate(layout["rects"], start=1):
            rx  = draw_x + r["x"]     * draw_w
            ry  = draw_y + r["y"]     * draw_h
            rw  = r["width"]  * draw_w
            rh  = r["height"] * draw_h
            svg = _svg_wrap(ms_w, ms_h,
                            _rect(rx, ry, rw, rh, "white", "black", lw))
            vl  = doc.createVectorLayer(f"Panel {i}")
            vl.addShapesFromSvg(svg)
            panels_group.addChildNode(vl, None)

    # Reorder: Panels > Cutting Marks > Finished Size > Safe Area > Paper
    ordered = [l for l in [panels_group, crop_layer, fs_layer, safe_layer, paper_layer] if l]
    prev = None
    for layer in ordered:
        root.addChildNode(layer, prev)
        prev = layer

    # Remove Krita's auto-created blank layer.
    # Use name-based comparison — Krita Node identity checks are unreliable in Python.
    ordered_names = {l.name() for l in ordered}
    krita_default_names = {
        "Background", "Fondo", "paint layer", "Capa de pintura",
        "paintlayer", "background"
    }
    for child in list(root.childNodes()):
        if child.name() not in ordered_names and child.name() in krita_default_names:
            root.removeChildNode(child)

    doc.setActiveNode(ordered[0])
    doc.refreshProjection()
    return doc


def open_document(spec: PageSpec, layout: dict):
    """Build a document, open it in Krita, and auto-scaffold drawing layers."""
    from krita import Krita
    doc = build_document(spec, layout)
    win = Krita.instance().activeWindow()
    if win is None:
        raise RuntimeError("No active Krita window found.")
    win.addView(doc)
    # Auto-create frame groups immediately — artist is ready to draw
    try:
        setup_masks(doc)
    except Exception:
        pass  # layout may be empty; don't block opening
    return doc


def save_document(spec: PageSpec, layout: dict, filepath: str):
    """Build a document and save it to disk. Does NOT open or auto-mask.
    For batch generation — keeps memory usage low by not opening documents.
    """
    from krita import Krita
    doc = build_document(spec, layout)
    if not doc.saveAs(filepath):
        raise RuntimeError(f"Krita could not save to: {filepath}")
    # Don't addView or setup_masks for batch — caller opens manually if needed
    return doc


# ---------------------------------------------------------------------------
# Layout extraction
# ---------------------------------------------------------------------------

def extract_layout_from_document(doc) -> list:
    """
    Read shapes from the 'Panels' layer (vector or group) and return
    normalised [0,1] rect dicts relative to the canvas.
    """
    root        = doc.rootNode()
    panels_node = None
    for node in root.childNodes():
        if node.name() == "Panels":
            panels_node = node
            break
    if panels_node is None:
        return []

    # Collect all shapes — either from a flat vector layer or child vector layers
    shapes = []
    if panels_node.type() == "vectorlayer":
        shapes = panels_node.shapes()
    elif panels_node.type() == "grouplayer":
        for child in panels_node.childNodes():
            if child.type() == "vectorlayer":
                shapes.extend(child.shapes())

    if not shapes:
        return []

    dpi         = doc.resolution()
    scale       = 72.0 / dpi
    canvas_w_pt = doc.width()  * scale
    canvas_h_pt = doc.height() * scale

    return [
        {
            "x":      round(s.boundingBox().x()      / canvas_w_pt, 6),
            "y":      round(s.boundingBox().y()      / canvas_h_pt, 6),
            "width":  round(s.boundingBox().width()  / canvas_w_pt, 6),
            "height": round(s.boundingBox().height() / canvas_h_pt, 6),
        }
        for s in shapes
    ]


# ---------------------------------------------------------------------------
# Mask scaffolding
# ---------------------------------------------------------------------------

# Cycle of bright outline colors per frame
_OUTLINE_COLORS = [
    "#4488ff", "#ff6644", "#44cc88", "#ffaa22",
    "#cc66ff", "#44ccdd", "#ff4488", "#aacc00",
]
_FRAME_COLORS = [1, 2, 3, 4, 5, 6, 7, 8, 9]


def check_has_masks(doc) -> bool:
    """True if doc already has a 'Comic Frames' master group or any 'Frame N' groups."""
    root = doc.rootNode()
    for node in root.childNodes():
        if node.name() == "Comic Frames" and node.type() == "grouplayer":
            return True
        if node.name().startswith("Frame ") and node.type() == "grouplayer":
            return True  # legacy: step-8 format without master group
    return False


def _shape_to_filled_svg(shape, canvas_w_pt: float, canvas_h_pt: float,
                         fill: str = "white", stroke: str = "none",
                         stroke_width: float = 0.0) -> str:
    """
    Build a canvas-sized SVG containing the given shape's geometry.

    Tries shape.toSvg() first (preserves diagonals / polygons).
    Falls back to the axis-aligned bounding box rect if toSvg() is
    unavailable or returns empty.
    """
    path_svg = ""
    try:
        raw = shape.toSvg()
        if raw and raw.strip():
            # toSvg() returns just the shape element(s), not a full SVG document.
            # Inject our fill/stroke attributes by wrapping in a <g>.
            path_svg = (
                f'<g fill="{fill}" stroke="{stroke}" '
                f'stroke-width="{stroke_width:.4f}">'
                f'{raw}'
                f'</g>'
            )
    except Exception:
        pass

    if not path_svg:
        # Fallback: axis-aligned bounding box
        bb = shape.boundingBox()
        path_svg = (
            f'<rect x="{bb.x():.4f}" y="{bb.y():.4f}" '
            f'width="{bb.width():.4f}" height="{bb.height():.4f}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{stroke_width:.4f}"/>'
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{canvas_w_pt:.4f}pt" height="{canvas_h_pt:.4f}pt" '
        f'viewBox="0 0 {canvas_w_pt:.4f} {canvas_h_pt:.4f}">'
        f'{path_svg}'
        f'</svg>'
    )


def setup_masks(doc) -> int:
    """
    Scaffold drawing groups.

    Expects Panels to be a group containing individual Panel N vector layers
    (as built by build_document). Falls back gracefully to flat vector layer.

    Layer structure:
        [Comic Frames ▼]
            [Frame N ▼]  (colored label)
                [Borders]  <- clone of Panel N only, Multiply mode
                              auto-updates when Panel N is edited
                [Ink]      <- inherit alpha
                [Color]    <- inherit alpha
                [Sketch]   <- inherit alpha
                [Mask]     <- vector, exact shape filled white

    Returns frame groups created, or -1 if no Panels layer found.
    """
    root        = doc.rootNode()
    panels_node = None
    for node in root.childNodes():
        if node.name() == "Panels":
            panels_node = node
            break

    if panels_node is None:
        return -1

    dpi      = doc.resolution()
    scale    = 72.0 / dpi
    canvas_w = doc.width()  * scale
    canvas_h = doc.height() * scale

    # Build (source_layer, shape) pairs
    panel_sources = []
    if panels_node.type() == "grouplayer":
        for child in panels_node.childNodes():
            if child.type() == "vectorlayer":
                shapes = child.shapes()
                if shapes:
                    panel_sources.append((child, shapes[0]))
    elif panels_node.type() == "vectorlayer":
        # Legacy flat layer
        for shape in panels_node.shapes():
            panel_sources.append((panels_node, shape))

    if not panel_sources:
        raise RuntimeError("The Panels layer contains no shapes.")

    master_group = doc.createGroupLayer("Comic Frames")
    created      = 0

    for i, (source_layer, shape) in enumerate(panel_sources, start=1):

        # Mask: exact shape, white fill, clipping base
        mask_svg   = _shape_to_filled_svg(shape, canvas_w, canvas_h,
                                          fill="white", stroke="none",
                                          stroke_width=0.0)
        mask_layer = doc.createVectorLayer("Mask")
        mask_layer.addShapesFromSvg(mask_svg)

        # Drawing layers
        sketch_layer = doc.createNode("Sketch", "paintlayer")
        color_layer  = doc.createNode("Color",  "paintlayer")
        ink_layer    = doc.createNode("Ink",    "paintlayer")
        for layer in (sketch_layer, color_layer, ink_layer):
            layer.setInheritAlpha(True)

        # Borders: clone of THIS panel's individual layer only, Multiply.
        # White becomes transparent, black border stays on top of artwork.
        # Editing Panel N updates this clone automatically.
        borders_layer = doc.createCloneLayer("Borders", source_layer)
        borders_layer.setBlendingMode("multiply")

        group = doc.createGroupLayer(f"Frame {i}")
        group.setColorLabel(_FRAME_COLORS[(i - 1) % len(_FRAME_COLORS)])

        group.addChildNode(mask_layer,    None)
        group.addChildNode(sketch_layer,  mask_layer)
        group.addChildNode(color_layer,   sketch_layer)
        group.addChildNode(ink_layer,     color_layer)
        group.addChildNode(borders_layer, ink_layer)

        master_group.addChildNode(group, None)
        created += 1

    root.addChildNode(master_group, panels_node)
    doc.refreshProjection()
    return created
