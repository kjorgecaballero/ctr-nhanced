# =========================================================================
# MODULE: kart — state
# =========================================================================
"""PropertyGroups for the kart editor.

`Scene.kart_state` holds everything: which template, which variant,
the list of editable color zones, the material that owns the tagged
RGB nodes, the preset name, and the preset browser state.

Color uses FloatVectorProperty(subtype='COLOR_GAMMA') with an update
callback that writes directly to the bound RGB node output.

Known limitation: Blender's color picker popup freezes if the user
drags the Value bar to exactly pure black (V=0) or pure white
(V=1, S=0), because the widget's internal HSV conversion is singular
at those points and the depsgraph update triggered by the callback
kills the popup's internal state. Workaround: click Reset Colors to
unstick.
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


def _preset_filter_update(self, context):
    self.preset_page = 1


class NFR_KartZone(bpy.types.PropertyGroup):
    display_name: bpy.props.StringProperty()
    node_name:    bpy.props.StringProperty()
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR_GAMMA',
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
    preset_name: bpy.props.StringProperty(
        name="Preset Name",
        description="Folder name to write the baked PNGs into",
        default="",
    )
    preset_filter: bpy.props.EnumProperty(
        name="Variant",
        description="Which preset variant to show in the browser",
        items=[
            ('KART',   "Kart",   "Standard kart presets"),
            ('GOLD',   "Gold",   "Gold pipe presets"),
            ('SILVER', "Silver", "Silver pipe presets"),
        ],
        default='KART',
        update=_preset_filter_update,
    )
    preset_page: bpy.props.IntProperty(
        name="Page",
        default=1,
        min=1,
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