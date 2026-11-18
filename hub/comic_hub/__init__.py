"""
Comic Hub: the pink Aero desktop app on top of cpb_core.

Run it from the repository root:

    PYTHONPATH=core;hub python -m comic_hub        (Windows: use ; between paths)
    PYTHONPATH=core:hub python -m comic_hub        (macOS / Linux)

The hub only does UI. Every rule about pages, layouts and files lives in
cpb_core, so anything the hub can do, the command line and the importers
agree with.
"""

__version__ = "0.1.0"
