# Comic Page Builder for Krita

A Python plugin for Krita 5.3+ that generates ready-to-draw comic pages: panel layouts, bleed and crop marks, safe area guides, and a per-panel drawing layer structure (Mask / Sketch / Color / Ink) that clips to each panel automatically.

## Features

- Paper presets (Commercial, ISO, JIS, US Comic, Manga and more), user-saved presets, mm / cm / in units
- Bleed, safe area (auto-linked to bleed), margins, line strength and resolution, with quick-pick values
- Color space choice: RGB 8/16/32-bit, Grayscale 8/16-bit, CMYK
- 30+ preset panel layouts, filterable by panel count
- BSP layout randomizer with live preview and adjustable gutters
- Save any generated layout, or the panels of an open document, as a reusable preset
- Batch generation of up to 20 pages per run, numbering continues from existing files
- One-click project folder scaffold (Pages, Characters, Comic Script, Environment, Reference Images)
- Each panel gets its own vector layer, so Krita's comic panel tool works on generated pages; frame groups clone their own panel border

Full details in [DOCUMENTATION.md](DOCUMENTATION.md).

## Installation

1. Download or clone this repository.
2. In Krita: **Settings → Manage Resources… → Open Resource Folder**, then open `pykrita`.
3. Copy `comicpagebuilder.desktop` and the `comicpagebuilder/` folder into `pykrita`.
4. **Settings → Configure Krita → Python Plugin Manager**, enable **Comic Page Builder**, restart Krita.
5. Open it from **Tools → Scripts → Comic Page Builder**.

## Credits

- Built by **Antares**.
- Preset layouts and paper sizes come from [ComicCreator](https://github.com/moritzmolch/ComicCreator) by Moritz Molch (GPL-3.0). This plugin is a Python re-implementation for current Krita versions, not a fork of its code.

## License

GPL-3.0, see [LICENSE.md](LICENSE.md).
