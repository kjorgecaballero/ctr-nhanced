# =========================================================================
# MODULE: ui subpackage
# =========================================================================
"""User interface: the unified CTR Racer panel."""
from . import panel


def register():
    panel.register()


def unregister():
    panel.unregister()