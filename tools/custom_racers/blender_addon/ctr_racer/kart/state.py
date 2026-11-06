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
import colorsys
from .templates import KART_TEMPLATES


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
    # Clampeamos los valores para evitar que el nodo se vaya a NaN o Infinito
    r = min(1.0, max(0.0, self.color[0]))
    g = min(1.0, max(0.0, self.color[1]))
    b = min(1.0, max(0.0, self.color[2]))
    node.outputs[0].default_value = (r, g, b, 1.0)


def _hover_hsv_update(self, context):
    import colorsys
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return
    
    if not obj.data.color_attributes:
        return

    color_layer = obj.data.color_attributes.active_color
    if not color_layer:
        return

    # 1. Save original colors if not saved yet
    if "orig_vcols" not in obj:
        # Guardamos en formato sRGB si es BYTE_COLOR, o Linear si es FLOAT_COLOR
        # .color_srgb devuelve el valor correcto visualmente
        obj["orig_vcols"] = [list(c.color) for c in color_layer.data]

    orig_colors = obj["orig_vcols"]

    # 2. Find the material.
    target_mat_prefix = "969_208_18_248_4_16"
    target_slot_idx = -1
    for i, slot in enumerate(obj.material_slots):
        if slot.material and target_mat_prefix in slot.material.name:
            target_slot_idx = i
            break

    if target_slot_idx == -1:
        target_slot_idx = 0

    # 3. Apply HSV math
    is_byte_color = (color_layer.data_type == 'BYTE_COLOR')
    
    # Evitar bucle si los valores están en su estado neutro
    if self.hover_hue == 0.5 and self.hover_saturation == 1.0 and self.hover_value == 1.0:
        pass # Aún así lo aplicamos para restaurar si el usuario movió el slider
    else:
        for poly in obj.data.polygons:
            if poly.material_index == target_slot_idx:
                for loop_idx in poly.loop_indices:
                    if loop_idx < len(orig_colors):
                        r, g, b = orig_colors[loop_idx][:3]
                        h, s, v = colorsys.rgb_to_hsv(r, g, b)       

                        new_h = (h + (self.hover_hue - 0.5)) % 1.0   
                        new_s = min(1.0, max(0.0, s * self.hover_saturation))
                        new_v = min(1.0, max(0.0, v * self.hover_value))

                        nr, ng, nb = colorsys.hsv_to_rgb(new_h, new_s, new_v)
                        
                        if is_byte_color:
                            # En BYTE_COLOR, .color espera Linear. Pero al leer/escribir usamos .color
                            color_layer.data[loop_idx].color = (nr, ng, nb, 1.0)
                        else:
                            color_layer.data[loop_idx].color = (nr, ng, nb, 1.0)

    obj.data.update()
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def _template_filter_update(self, context):
    self.preset_page = 1
    tpl = KART_TEMPLATES.get(self.template_filter)
    if tpl:
        var_key = self.variant_filter
        if var_key == 'GOLD': var_key = 'GOLD_PIPES'
        elif var_key == 'SILVER': var_key = 'SILVER_PIPES'
        elif var_key == 'DEFAULT': var_key = 'DEFAULT'
        
        # Si la plantilla elegida no soporta la variante actual, forzar DEFAULT
        if var_key not in tpl.get("variant_dirs", {}):
            self.variant_filter = 'DEFAULT'

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
        soft_min=0.0,
        soft_max=1.0,
        update=_zone_color_update,
    )


class NFR_KartState(bpy.types.PropertyGroup):
    template_option: bpy.props.EnumProperty(
        name="Template",
        items=[(k, v["display_name"], "") for k, v in KART_TEMPLATES.items()],
        default='KART',
    )
    template_mode: bpy.props.EnumProperty(
        name="Mode",
        items=[('EDIT', "Edit (Paint)", ""), ('USER', "User (View)", "")],
        default='EDIT'
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
    output_mode: bpy.props.EnumProperty(
        name="Output Mode",
        description="How to save the baked pieces",
        items=[
            ("SENTINEL", "Sentinel (full RGB)",
             "Save the baked piece as-is. The kart loader treats it as "
             "a plain RGB texture, so no color limit applies."),
            ("PALETTED", "Paletted (16 colors, legacy)",
             "Quantize to 16 colors. Only needed for the original PS1 "
             "paletted path."),
        ],
        default="SENTINEL",
    )
    template_filter: bpy.props.EnumProperty(
        name="Template",
        items=[(k, v["display_name"], "") for k, v in KART_TEMPLATES.items()],
        default='KART',
        update=_template_filter_update,
    )
    variant_filter: bpy.props.EnumProperty(
        name="Variant",
        items=[
            ('DEFAULT', "Default", "Default variant"),
            ('GOLD', "Gold", "Gold variant"),
            ('SILVER', "Silver", "Silver variant"),
        ],
        default='DEFAULT',
    )
    preset_page: bpy.props.IntProperty(
        name="Page",
        default=1,
        min=1,
    )
    is_imported:   bpy.props.BoolProperty(default=False)
    material_name: bpy.props.StringProperty(default="")

    hover_hue: bpy.props.FloatProperty(name="Hue", min=0.0, max=1.0, default=0.5, update=_hover_hsv_update)
    hover_saturation: bpy.props.FloatProperty(name="Saturation", min=0.0, max=2.0, default=1.0, update=_hover_hsv_update)
    hover_value: bpy.props.FloatProperty(name="Value", min=0.0, max=2.0, default=1.0, update=_hover_hsv_update)
    hover_color: bpy.props.FloatVectorProperty(name="Color", subtype='COLOR_GAMMA', size=3, default=(1.0, 1.0, 1.0))
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