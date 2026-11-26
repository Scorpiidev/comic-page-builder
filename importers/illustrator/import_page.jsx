// Comic Page Builder: bring a page.svg into Illustrator, or update a page it made.
//
// Run it from File > Scripts > Other Script… and pick this file (written
// against Illustrator 30.2). It asks for a page.svg made by the hub.
//
// * If the active document was made by this script for the same page, it is
//   UPDATED: the panels, guides and paper that changed in the new page.svg
//   are redrawn in place, new panels are added, and panels that left the
//   layout are hidden (never deleted). Your lettering and your own layers
//   and items are left alone.
// * Otherwise it opens the page as a new document, sorted into layers:
//
//   Guides    trim, safe area, crop marks (locked, doesn't print)
//   Letters   balloons and text (where lettering goes)
//   Panels    one path per panel, named "Panel 1", "Panel 2"...
//   Paper     white canvas (locked)
//
// The hub's items carry a note (Window > Attributes shows it), such as
// "Comic Page Builder: cpb-panel-3 | page 9 | key 1f2e3d4c". Updates find
// them by that note, not by name or layer, so renaming or moving them by
// hand doesn't break anything.
//
// ExtendScript is old JavaScript (ES3): no let/const, arrow functions or JSON.

#target illustrator

(function () {
    var LAYERS = [ // top to bottom
        ["cpb-guides", "Guides"],
        ["cpb-letters", "Letters"],
        ["cpb-panels", "Panels"],
        ["cpb-paper", "Paper"]
    ];
    var NOTE = "Comic Page Builder: ";
    var MM = 25.4 / 72; // Illustrator measures in points

    // Illustrator may encode "-" in ids as "_x2D_" and add "_1_" suffixes.
    function norm(name) {
        return String(name || "").replace(/_x2D_/g, "-").replace(/_\d+_$/, "");
    }

    function findByName(doc, wanted) {
        for (var i = 0; i < doc.pageItems.length; i++) {
            if (norm(doc.pageItems[i].name) === wanted) return doc.pageItems[i];
        }
        return null;
    }

    // Name -> item, in one pass. Call it while doc is the active document:
    // reading the items of a document in the background takes about 0.3 s per
    // item, which made an update take 40 seconds.
    function itemsByName(doc) {
        var map = {}, items = doc.pageItems, n = items.length;
        for (var i = 0; i < n; i++) {
            var key = norm(items[i].name);
            if (!map.hasOwnProperty(key)) map[key] = items[i];
        }
        return map;
    }

    function moveContents(item, layer) {
        // Keep the stacking order: take the bottom item first, put it on top.
        if (item.typename === "GroupItem") {
            while (item.pageItems.length) {
                item.pageItems[item.pageItems.length - 1].move(layer, ElementPlacement.PLACEATBEGINNING);
            }
            item.remove();
        } else {
            item.move(layer, ElementPlacement.PLACEATBEGINNING);
        }
    }

    // ---------- reading page.svg ----------
    function attr(tag, name) {
        var m = tag.match(new RegExp("\\s" + name + "=\"([^\"]*)\""));
        return m ? m[1] : null;
    }

    // A short fingerprint of an element's tag (FNV-1a hash). The hub writes the
    // same text for the same panel, so a new fingerprint means the panel
    // changed, without this script having to understand any geometry.
    function fingerprint(s) {
        var h = 0x811c9dc5;
        for (var i = 0; i < s.length; i++) {
            h ^= s.charCodeAt(i);
            h = (h + (h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24)) >>> 0;
        }
        return h.toString(16);
    }

    // Every element the hub drew (its id starts with "cpb-"), in file order,
    // with the layer group it sits in. The layer groups themselves and the
    // clip paths in <defs> are skipped.
    function hubElements(text) {
        var out = [], groups = [], inDefs = 0, m;
        var re = /<(\/?)([\w:-]+)([^>]*?)(\/?)>/g;
        while ((m = re.exec(text))) {
            var closing = m[1] === "/", name = m[2], empty = m[4] === "/";
            if (name === "defs") { if (!empty) inDefs += closing ? -1 : 1; continue; }
            if (name === "g") {
                if (closing) groups.pop();
                else if (!empty) groups.push({ id: attr(m[0], "id") || "", label: attr(m[0], "inkscape:label") || "" });
                continue;
            }
            if (closing || inDefs) continue;
            var id = attr(m[0], "id");
            if (!id || id.indexOf("cpb-") !== 0) continue;
            var g = groups.length ? groups[groups.length - 1] : { id: "", label: "" };
            var whole = m[0];
            // A text's words and line positions live inside it, not in its
            // tag, so they go into the fingerprint too.
            if (name === "text" && !empty) {
                var end = text.indexOf("</text>", re.lastIndex);
                if (end > 0) { whole = text.slice(m.index, end); re.lastIndex = end; }
            }
            out.push({ id: id, group: g.id, label: g.label, key: fingerprint(whole) });
        }
        return out;
    }

    function unescapeXml(s) {
        return s.replace(/&#10;/g, "\n").replace(/&quot;/g, '"').replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&amp;/g, "&");
    }

    // What each balloon's text should be, read from page.svg: its lines,
    // where the first baseline sits (mm), and the font by PostScript name.
    // Keyed by the text's id, "cpb-balloon-3-text".
    function balloonTexts(text) {
        var out = {}, re = /<g\b[^>]*id="cpb-balloon-\d+"[^>]*>[\s\S]*?<\/g>/g, m;
        while ((m = re.exec(text))) {
            var gtag = m[0].match(/<g\b[^>]*>/)[0];
            var font = unescapeXml(attr(gtag, "cpb:font") || "");
            var t = m[0].match(/<text\b([^>]*)>([\s\S]*?)<\/text>/);
            if (!t) continue;
            var id = attr(t[0], "id"), spans = [], s, sre = /<tspan\b([^>]*)>([\s\S]*?)<\/tspan>/g;
            while ((s = sre.exec(t[2]))) {
                spans.push({ x: parseFloat(attr(s[0], "x")), y: parseFloat(attr(s[0], "y")), text: unescapeXml(s[2]) });
            }
            if (!id || !spans.length) continue;
            var num = function (k, dflt) { var v = font.match(new RegExp('"' + k + '":([\\d.]+)')); return v ? parseFloat(v[1]) : dflt; };
            var ps = font.match(/"ps_name":"([^"]*)"/);
            var size = num("size_pt", 8);
            var lines = [];
            for (var i = 0; i < spans.length; i++) lines.push(spans[i].text);
            out[id] = {
                lines: lines, x: spans[0].x, y: spans[0].y, size: size, psName: ps ? ps[1] : "",
                // Baseline to baseline as the hub laid it out, in points.
                leading: spans.length > 1 ? (spans[1].y - spans[0].y) / MM : size * num("leading", 1.2)
            };
        }
        return out;
    }

    // Illustrator opens each line (tspan) as its own left-aligned point text
    // and picks the font by family name only, so "Comic Sans MS" Bold comes in
    // Regular. Swap each balloon's text for one centred point text in the
    // preset's exact face. Returns the fonts that aren't installed.
    function rebuildTexts(doc, info) {
        var r = doc.artboards[0].artboardRect, named = itemsByName(doc), missing = [];
        for (var id in info) {
            var old = named[id], b = info[id];
            if (!old) continue;
            var sample = old.typename === "TextFrame" ? old : (old.textFrames && old.textFrames.length ? old.textFrames[0] : null);
            var tf = doc.textFrames.pointText([r[0] + b.x / MM, r[1] - b.y / MM]);
            tf.contents = b.lines.join("\r");
            var ca = tf.textRange.characterAttributes;
            if (sample) {
                ca.textFont = sample.textRange.characterAttributes.textFont;
                ca.fillColor = sample.textRange.characterAttributes.fillColor;
            }
            if (b.psName) {
                try { ca.textFont = app.textFonts.getByName(b.psName); }
                catch (e) { if (("," + missing.join(",") + ",").indexOf("," + b.psName + ",") < 0) missing.push(b.psName); }
            }
            ca.size = b.size;
            ca.autoLeading = false;
            ca.leading = b.leading;
            tf.textRange.paragraphAttributes.justification = Justification.CENTER;
            tf.move(old, ElementPlacement.PLACEBEFORE);
            tf.name = old.name;
            old.remove();
        }
        return missing;
    }

    function fontReport(missing) {
        return missing.length ? "\nNot installed, so the balloons use a stand-in: " + missing.join(", ") + "." : "";
    }

    // "cpb-panel-3" -> "panel 3", "cpb-crop-marks" -> "crop marks", for messages.
    function said(id) {
        return id.replace(/^cpb-/, "").replace(/-/g, " ");
    }

    // ---------- notes: how the script recognises its own items ----------
    // Text items also note a fingerprint of their words as the hub wrote
    // them, so an update can tell when you've edited them here.
    function noteFor(id, page, key, hidden, words) {
        return NOTE + id + " | page " + page + " | key " + key + (hidden ? " | hidden" : "") + (words ? " | words " + words : "");
    }

    function wordsOf(item) {
        return item.typename === "TextFrame" ? fingerprint(String(item.contents)) : "";
    }

    function readNote(item) {
        var note = "";
        try { note = String(item.note || ""); } catch (e) {}
        var m = note.match(/^Comic Page Builder: (cpb-[\w-]+) \| page (\d+) \| key (\w+)( \| hidden)?( \| words (\w+))?/);
        return m ? { id: m[1], page: m[2], key: m[3], hidden: !!m[4], words: m[6] || "", item: item } : null;
    }

    // The hub's items in doc, by id. A duplicated item copies its note, so
    // the first (topmost) copy wins.
    function findTagged(doc) {
        var byId = {}, page = null, items = doc.pageItems, n = items.length;
        for (var i = 0; i < n; i++) {
            var t = readNote(items[i]);
            if (t && !byId[t.id]) { byId[t.id] = t; if (page === null) page = t.page; }
        }
        return { byId: byId, page: page };
    }

    // Illustrator undoes a script one step at a time (it has nothing like
    // Photoshop's single history step), so File > Revert is the real way back.
    // Returns a warning when Revert wouldn't bring back the work as it is now.
    function undoRisk(doc) {
        var path = "";
        try { path = doc.fullName.fsName; } catch (e) {}
        if (/\.svg$/i.test(path)) {
            return doc.name + " is still the SVG the hub wrote. Save it as an .ai file first " +
                "(File > Save As): then File > Revert can take you back, and " + doc.name + " stays the hub's.";
        }
        if (!doc.saved) {
            return doc.name + " has unsaved changes. Illustrator undoes this update one step at a time, " +
                "so save first if you want File > Revert as a one-step way back.";
        }
        return null;
    }

    // Resizing would move or crop the lettering, so a page whose size changed
    // is refused and left to you. Sizes in mm; returns the reason or null.
    function sizeProblem(doc, page, w, h) {
        var r = doc.artboards[0].artboardRect; // left, top, right, bottom in points
        var dw = (r[2] - r[0]) * MM, dh = (r[1] - r[3]) * MM;
        if (Math.abs(dw - w) < 0.01 && Math.abs(dh - h) < 0.01) return null;
        return "Nothing changed. " + doc.name + " is " + dw.toFixed(1) + " × " + dh.toFixed(1) + " mm, but page " +
            page + " is now " + w.toFixed(1) + " × " + h.toFixed(1) + " mm.\n\n" +
            "To get it as a new document instead, switch to another document (or close this one) and run the script again.";
    }

    // Would an update change anything? Answered from the notes alone, so a run
    // with nothing to do doesn't open the page or ask about saving.
    function hasChanges(elements, tagged) {
        var wanted = {};
        for (var i = 0; i < elements.length; i++) {
            var t = tagged[elements[i].id];
            if (!t || t.key !== elements[i].key || t.hidden) return true;
            wanted[elements[i].id] = true;
        }
        for (var id in tagged) if (!wanted[id] && !tagged[id].hidden) return true;
        return false;
    }

    function openDocumentFor(file) {
        for (var i = 0; i < app.documents.length; i++) {
            try { if (app.documents[i].fullName.fsName === file.fsName) return app.documents[i]; } catch (e) {}
        }
        return null;
    }

    // ---------- new document ----------
    function importFresh(file, page, elements, texts) {
        var doc = app.open(file);
        var report = [];
        var missing = rebuildTexts(doc, texts);
        var created = {};

        // Tag the hub's items first, while they still have their SVG ids as names.
        var named = itemsByName(doc);
        for (var e = 0; e < elements.length; e++) {
            var hub = named[elements[e].id] || null;
            if (hub) hub.note = noteFor(elements[e].id, page, elements[e].key, false, wordsOf(hub));
            else report.push("Couldn't find " + elements[e].id + " (Illustrator may not have kept the id).");
        }

        // Make the layers. Each new layer goes on top, so add them bottom first.
        for (var i = LAYERS.length - 1; i >= 0; i--) {
            var layer = doc.layers.add();
            layer.name = LAYERS[i][1];
            created[LAYERS[i][0]] = layer;
        }

        for (var j = 0; j < LAYERS.length; j++) {
            var id = LAYERS[j][0];
            var src = findByName(doc, id);
            if (src) {
                moveContents(src, created[id]);
            } else if (id !== "cpb-letters") {
                report.push("Couldn't find " + id + " (Illustrator may not have kept the id).");
            }
        }

        // Friendly panel names.
        var panels = created["cpb-panels"];
        var count = 0;
        for (var k = 0; k < panels.pageItems.length; k++) {
            var m = norm(panels.pageItems[k].name).match(/^cpb-panel-(\d+)$/);
            if (m) { panels.pageItems[k].name = "Panel " + m[1]; count++; }
            var g = norm(panels.pageItems[k].name).match(/^cpb-inset-gap-(\d+)$/);
            if (g) panels.pageItems[k].name = "Inset gap " + g[1];
        }

        // Remove layers that are now empty (Illustrator's own "Layer 1").
        for (var n = doc.layers.length - 1; n >= 0; n--) {
            var L = doc.layers[n];
            var ours = false;
            for (var key in created) if (created[key] === L) ours = true;
            if (!ours && L.pageItems.length === 0 && L.layers.length === 0) L.remove();
        }

        created["cpb-guides"].printable = false;
        created["cpb-guides"].locked = true;
        created["cpb-paper"].locked = true;
        created["cpb-letters"].hasSelectedArtwork = false;
        doc.activeLayer = created["cpb-letters"];

        // Illustrator would save this document back over the hub's SVG as its own SVG.
        return "Imported " + file.name + ": " + count + " panels.\n" +
            (report.length ? "\n" + report.join("\n") : "Layers: Guides, Letters, Panels, Paper.") + fontReport(missing) +
            "\n\nSave it as an .ai file (File > Save As) before you letter, so " + file.name + " stays the hub's.";
    }

    // ---------- update an existing document ----------
    function update(doc, file, page, elements, tagged, texts) {
        // Open the new page from a temporary copy. If this document IS that
        // page.svg (never saved as .ai), opening the file again would just hand
        // back this document, and closing it afterwards would close your work.
        var tmp = new File(Folder.temp + "/cpb-update-" + new Date().getTime() + ".svg");
        if (!file.copy(tmp)) throw new Error("Couldn't copy " + file.name + " to a temporary file.");
        var src = app.open(tmp);
        var missing = rebuildTexts(src, texts);
        var fresh = itemsByName(src); // while src is the active document (see itemsByName)
        var touched = []; // layers unlocked or shown for the update, with their old state

        // Illustrator won't change items on a locked or hidden layer, so unlock
        // and show each layer the update works in, and put it back afterwards.
        function prep(layer) {
            for (var L = layer; L && L.typename === "Layer"; L = L.parent) {
                var k = 0;
                while (k < touched.length && touched[k].layer !== L) k++;
                if (k === touched.length) touched.push({ layer: L, locked: L.locked, visible: L.visible });
                L.locked = false;
                L.visible = true;
            }
        }

        // Change an item even if you locked it, then lock it again.
        function edit(item, change) {
            prep(item.layer);
            var locked = item.locked;
            if (locked) item.locked = false;
            change(item);
            if (locked) item.locked = true;
        }

        function copyIn(f, layer) {
            prep(layer);
            var copy = f.duplicate(layer, ElementPlacement.PLACEATBEGINNING);
            if (dx || dy) copy.translate(dx, dy);
            return copy;
        }

        // The new item goes right above the old one, takes over its name, its
        // place in a clipping group you made, and its locked or hidden state.
        function replace(old, f, e) {
            var copy = copyIn(f, old.item.layer);
            copy.move(old.item, ElementPlacement.PLACEBEFORE);
            var was = old.item;
            var clip = was.typename === "PathItem" && was.clipping;
            var hidden = old.hidden ? false : was.hidden; // shown again if the hub had hidden it
            var locked = was.locked;
            copy.name = was.name;
            if (locked) was.locked = false;
            was.remove();
            if (clip) copy.clipping = true;
            copy.note = noteFor(e.id, page, e.key, false, wordsOf(copy));
            copy.hidden = hidden;
            copy.locked = locked;
            return copy;
        }

        // A new panel goes next to its neighbour from the same layer of
        // page.svg (the one before it, else the one after), so it lands with
        // the other panels wherever you keep them.
        function add(f, e) {
            var before = null, after = null, seen = false;
            for (var i = 0; i < elements.length; i++) {
                var o = elements[i];
                if (o.id === e.id) { seen = true; continue; }
                if (o.group !== e.group || !tagged[o.id]) continue;
                if (!seen) before = tagged[o.id].item;
                else if (!after) after = tagged[o.id].item;
            }
            var near = before || after, layer;
            if (near) layer = near.layer;
            else {
                try { layer = doc.layers.getByName(e.label); }
                catch (err) { layer = doc.layers.add(); layer.name = e.label || "Comic Page Builder"; }
            }
            var copy = copyIn(f, layer);
            if (before) copy.move(before, ElementPlacement.PLACEBEFORE);
            else if (after) copy.move(after, ElementPlacement.PLACEAFTER);
            var m = e.id.match(/^cpb-panel-(\d+)$/);
            if (m) copy.name = "Panel " + m[1];
            var g = e.id.match(/^cpb-inset-gap-(\d+)$/);
            if (g) copy.name = "Inset gap " + g[1];
            copy.note = noteFor(e.id, page, e.key, false, wordsOf(copy));
            return copy;
        }

        try {
            // main checked the size from page.svg's width and height; check
            // again with the page as Illustrator read it, before changing anything.
            var a = doc.artboards[0].artboardRect, b = src.artboards[0].artboardRect; // left, top, right, bottom
            var problem = sizeProblem(doc, page, (b[2] - b[0]) * MM, (b[1] - b[3]) * MM);
            if (problem) return problem;
            // In case the artboard sits somewhere else in this document.
            var dx = a[0] - b[0], dy = a[1] - b[1];
            app.activeDocument = doc;

            var done = { redrawn: [], added: [], shown: [], hidden: [], missing: [], kept: [] }, wanted = {};
            for (var i = 0; i < elements.length; i++) {
                var e = elements[i], old = tagged[e.id];
                wanted[e.id] = true;
                if (old && old.key === e.key) {
                    if (old.hidden) {
                        edit(old.item, function (it) { it.hidden = false; it.note = noteFor(e.id, page, e.key, false, old.words); });
                        done.shown.push(said(e.id));
                    }
                    continue;
                }
                var f = fresh[e.id] || null;
                if (!f) { done.missing.push(e.id); continue; }
                if (old && old.words && old.item.typename === "TextFrame" && wordsOf(old.item) !== old.words) {
                    // You edited this text here and the hub changed it too:
                    // keep yours (hidden, and no longer the hub's) under the new one.
                    var mine = old.item, itsName = mine.name;
                    edit(mine, function (it) { it.hidden = true; it.note = ""; it.name = "Your edit of " + said(e.id); });
                    var put = copyIn(f, mine.layer);
                    put.move(mine, ElementPlacement.PLACEBEFORE);
                    put.name = itsName;
                    put.note = noteFor(e.id, page, e.key, false, wordsOf(put));
                    tagged[e.id] = { id: e.id, key: e.key, hidden: false, item: put };
                    done.kept.push(said(e.id));
                } else if (old) {
                    tagged[e.id] = { id: e.id, key: e.key, hidden: false, item: replace(old, f, e) };
                    done.redrawn.push(said(e.id));
                } else {
                    tagged[e.id] = { id: e.id, key: e.key, hidden: false, item: add(f, e) };
                    done.added.push(said(e.id));
                }
            }

            // Items whose panel left the layout: hidden, never deleted.
            for (var id in tagged) {
                var t = tagged[id];
                if (wanted[id] || t.hidden) continue;
                edit(t.item, function (it) { it.hidden = true; it.note = noteFor(t.id, page, t.key, true, t.words); });
                done.hidden.push(said(id));
            }
        } finally {
            src.close(SaveOptions.DONOTSAVECHANGES);
            tmp.remove();
            for (var r = touched.length - 1; r >= 0; r--) {
                touched[r].layer.visible = touched[r].visible;
                touched[r].layer.locked = touched[r].locked;
            }
            app.activeDocument = doc;
        }

        var lines = [];
        if (done.redrawn.length) lines.push("Redrawn: " + done.redrawn.join(", ") + ".");
        if (done.added.length) lines.push("New: " + done.added.join(", ") + ".");
        if (done.shown.length) lines.push("Shown again: " + done.shown.join(", ") + ".");
        if (done.hidden.length) lines.push("Hidden (gone from the layout, kept): " + done.hidden.join(", ") + ".");
        if (done.kept.length) lines.push("Edited here and changed in the hub: " + done.kept.join(", ") +
            ". Your version is kept, hidden, right under the new one (named \"Your edit of …\").");
        if (missing.length) lines.push(fontReport(missing).slice(1));
        if (done.missing.length) lines.push("Couldn't find in the new page: " + done.missing.join(", ") + ".");
        if (!lines.length) return doc.name + " already matches " + file.name + ". Nothing changed.";
        doc.selection = null;
        return "Updated " + doc.name + " from " + file.name + ".\n" + lines.join("\n") +
            "\n\nYour lettering and your own items weren't touched. Ctrl+Z goes back one step at a time; " +
            "File > Revert goes back to your last save.";
    }

    // ---------- main ----------
    var file = File.openDialog("Choose a Comic Page Builder page.svg", "SVG:*.svg");
    if (!file) return;

    file.encoding = "UTF-8";
    file.open("r");
    var text = file.read();
    file.close();
    if (text.indexOf('cpb:format="cpb-borders"') >= 0) {
        alert("This is the borders-only file for Clip Studio Paint. Pick the page.svg instead.");
        return;
    }
    if (text.indexOf('cpb:format="cpb-page"') < 0) {
        alert("This SVG wasn't made by Comic Page Builder.");
        return;
    }
    var root = text.match(/<svg\b[^>]*>/);
    var page = root ? attr(root[0], "cpb:page") : null;
    if (!page) {
        alert("The page is missing its cpb:page value. Rebuild it with a newer hub.");
        return;
    }
    var elements = hubElements(text);
    var texts = balloonTexts(text);

    try {
        var doc = app.documents.length ? app.activeDocument : null;
        var tags = doc ? findTagged(doc) : { byId: {}, page: null };
        if (doc && tags.page === page) {
            if (!hasChanges(elements, tags.byId)) {
                alert(doc.name + " already matches " + file.name + ". Nothing changed.");
                return;
            }
            var w = attr(root[0], "width"), h = attr(root[0], "height");
            var problem = /mm$/.test(w || "") && /mm$/.test(h || "") ? sizeProblem(doc, page, parseFloat(w), parseFloat(h)) : null;
            if (problem) { alert(problem); return; }
            var risk = undoRisk(doc);
            if (risk && !confirm(risk + "\n\nUpdate anyway?")) return;
            alert(update(doc, file, page, elements, tags.byId, texts));
        } else if (doc && openDocumentFor(file) === doc) {
            // Opening it again would hand back this document and re-sort its layers.
            alert(doc.name + " has no Comic Page Builder notes (it was imported before updates existed), " +
                  "so it can't be updated. Close it to import the page fresh.");
        } else if (openDocumentFor(file)) {
            alert(file.name + " is already open in Illustrator.\n\n" +
                  "To update it, switch to it and run the script again. To import it fresh, close it first.");
        } else {
            alert(importFresh(file, page, elements, texts));
        }
    } catch (err) {
        alert("Comic Page Builder import failed:\n" + err.message + (err.line ? " (line " + err.line + ")" : ""));
    }
})();
