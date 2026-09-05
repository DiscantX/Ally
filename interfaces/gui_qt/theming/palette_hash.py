"""Deprecated location. color_for_key now lives in theming/ so that
package can be imported without depending on interfaces.gui_qt. This
module is kept as a compatibility re-export.
"""
from theming.color_convert import color_for_key

__all__ = ["color_for_key"]
