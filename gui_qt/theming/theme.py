import os
from interfaces.gui_qt.theming.theme import (
    Theme,
    SIGNAL,
    SYNTHWAVE,
    NEUTRAL_CONTENT_THEME,
    build_stylesheet,
)

TEMPLATE_PATH: str = os.path.join(os.path.dirname(__file__), "base.qss.tmpl")
