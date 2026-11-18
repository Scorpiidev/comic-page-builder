// Comic Page Builder: open a page.svg in Illustrator with proper layers.
//
// Run it from File > Scripts > Other Script… and pick this file
// (written against Illustrator 30.2). It asks for a page.svg made by the
// hub, opens it, and sorts the content into named layers:
//
//   Guides    trim, safe area, crop marks (locked, doesn't print)
//   Letters   balloons and text (where lettering goes)
//   Panels    one path per panel, named "Panel 1", "Panel 2"...
//   Paper     white canvas (locked)
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

    var file = File.openDialog("Choose a Comic Page Builder page.svg", "SVG:*.svg");
    if (!file) return;

    file.encoding = "UTF-8";
    file.open("r");
    var text = file.read();
    file.close();
    if (text.indexOf('cpb:format="cpb-page"') < 0) {
        alert("This SVG wasn't made by Comic Page Builder.");
        return;
    }

    var doc = app.open(file);
    var report = [];
    var created = {};

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

    alert("Imported " + file.name + ": " + count + " panels.\n" +
          (report.length ? "\n" + report.join("\n") : "Layers: Guides, Letters, Panels, Paper."));
})();
