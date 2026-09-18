# =========================================================================
# MODULE: kart — state
# =========================================================================
"""PropertyGroups for the kart editor.

`Scene.kart_state` holds everything: which template, which variant,
the list of editable color zones, and the name of the material that
owns the tagged RGB nodes.

The color picker update callback writes to the bound RGB node's
output socket. The node lives inside the material named by
`scene.kart_state.material_name`. If anything is missing (material
renamed, node deleted), the callback silently no-ops -- the panel
keeps the stored value, it just doesn't push it.

Note on the color property: size=3 (RGB). The RGB node expects a
4-component vector, so the callback pads with alpha=1.0. Using
size=3 instead of size=4 avoids a rendering glitch in the color
picker popup on some Blender builds (the picker would open with a
black canvas that still responded to the mouse).
"""
import bpy


def _zone_color_update(self, context):
    """Push self.color -> RGB node's output socket (padded to RGBA)."""
    scene = getattr(context, "scene", None)
    if scene is None:
        return
    state = getattr(scene, "kart_state", None)
    if state is None or not state.is_imported or not state.material_name:
        return
    mat = bpy.data.materials.get(state.material_name)
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return
    node = mat.node_tree.nodes.get(self.node_name)
    if node is None or node.type != 'RGB':
        return
    c = self.color
    node.outputs[0].default_value = (c[0], c[1], c[2], 1.0)


class NFR_KartZone(bpy.types.PropertyGroup):
    display_name: bpy.props.StringProperty()
    node_name:    bpy.props.StringProperty()
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=3,
        default=(1.0, 1.0, 1.0),
        update=_zone_color_update,
    )


class NFR_KartState(bpy.types.PropertyGroup):
    template_option: bpy.props.EnumProperty(
        name="Template",
        items=[('KART', "Kart", "Standard CTR kart")],
        default='KART',
    )
    variant: bpy.props.EnumProperty(
        name="Variant",
        items=[
            ('DEFAULT',      "Default",      "Default pipes"),
            ('GOLD_PIPES',   "Gold Pipes",   "Gold pipes"),
            ('SILVER_PIPES', "Silver Pipes", "Silver pipes"),
        ],
        default='DEFAULT',
    )
    is_imported:   bpy.props.BoolProperty(default=False)
    material_name: bpy.props.StringProperty(default="")
    zones: bpy.props.CollectionProperty(type=NFR_KartZone)


_classes = (NFR_KartZone, NFR_KartState)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    if not hasattr(bpy.types.Scene, "kart_state"):
        bpy.types.Scene.kart_state = bpy.props.PointerProperty(type=NFR_KartState)


def unregister():
    if hasattr(bpy.types.Scene, "kart_state"):
        del bpy.types.Scene.kart_state
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)