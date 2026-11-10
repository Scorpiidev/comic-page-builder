"""
page.svg: the vector truth of a page.

Layers follow Inkscape's convention (``<g inkscape:groupmode="layer">``), the
closest thing to a shared standard; hub data lives in the ``cpb:`` namespace,
which other apps ignore.

Ownership rule: the hub owns exactly the elements whose ``id`` starts with
``cpb-``. When it rewrites a page it replaces those and leaves everything
else alone, so things you add in Illustrator or Inkscape survive.
"""

from .reader import PageDocument, parse_page, read_page
from .writer import page_to_svg, write_page

__all__ = ["PageDocument", "parse_page", "read_page", "page_to_svg", "write_page"]
