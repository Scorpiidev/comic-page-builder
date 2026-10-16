from krita import Krita
from .extension import ComicPageBuilderExtension

# Krita calls this on startup to register the plugin
Krita.instance().addExtension(ComicPageBuilderExtension(Krita.instance()))
