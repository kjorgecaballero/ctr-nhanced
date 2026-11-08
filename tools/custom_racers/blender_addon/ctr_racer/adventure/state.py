import bpy
from bpy.props import StringProperty, IntProperty, PointerProperty
from bpy.types import PropertyGroup

class NFR_AdventureState(PropertyGroup):
    pack_name: StringProperty(name="Pack Name", default="My Pack")
    slug: StringProperty(name="Slug", default="my_pack")
    lev_file: StringProperty(name="LEV File", subtype='FILE_PATH')
    vrm_file: StringProperty(name="VRM File", subtype='FILE_PATH')
    music_file: StringProperty(name="Music OGG", subtype='FILE_PATH')
    
    scale_mult: IntProperty(name="Scale Multiplier", default=100, description="Coordinate scale. CTR uses 100 (cm). Adjust if your LEV is in meters.")
    
    cam_x: IntProperty(name="Cam X", default=0)
    cam_y: IntProperty(name="Cam Y", default=100)
    cam_z: IntProperty(name="Cam Z", default=500)
    cam_rot_x: IntProperty(name="Cam Rot X", default=0)
    cam_rot_y: IntProperty(name="Cam Rot Y", default=0)
    cam_rot_z: IntProperty(name="Cam Rot Z", default=0)

    # 8 Slots (String for custom slugs like 'spyro')
    char_0: StringProperty(name="Slug", default="crash"); x_0: IntProperty(name="X", default=0); y_0: IntProperty(name="Y", default=0); z_0: IntProperty(name="Z", default=0); rot_0: IntProperty(name="Rot", default=0)
    char_1: StringProperty(name="Slug", default="coco"); x_1: IntProperty(name="X", default=0); y_1: IntProperty(name="Y", default=0); z_1: IntProperty(name="Z", default=0); rot_1: IntProperty(name="Rot", default=0)
    char_2: StringProperty(name="Slug", default="cortex"); x_2: IntProperty(name="X", default=0); y_2: IntProperty(name="Y", default=0); z_2: IntProperty(name="Z", default=0); rot_2: IntProperty(name="Rot", default=0)
    char_3: StringProperty(name="Slug", default="tiny"); x_3: IntProperty(name="X", default=0); y_3: IntProperty(name="Y", default=0); z_3: IntProperty(name="Z", default=0); rot_3: IntProperty(name="Rot", default=0)
    char_4: StringProperty(name="Slug", default="polar"); x_4: IntProperty(name="X", default=0); y_4: IntProperty(name="Y", default=0); z_4: IntProperty(name="Z", default=0); rot_4: IntProperty(name="Rot", default=0)
    char_5: StringProperty(name="Slug", default="pura"); x_5: IntProperty(name="X", default=0); y_5: IntProperty(name="Y", default=0); z_5: IntProperty(name="Z", default=0); rot_5: IntProperty(name="Rot", default=0)
    char_6: StringProperty(name="Slug", default="dingodile"); x_6: IntProperty(name="X", default=0); y_6: IntProperty(name="Y", default=0); z_6: IntProperty(name="Z", default=0); rot_6: IntProperty(name="Rot", default=0)
    char_7: StringProperty(name="Slug", default="ngin"); x_7: IntProperty(name="X", default=0); y_7: IntProperty(name="Y", default=0); z_7: IntProperty(name="Z", default=0); rot_7: IntProperty(name="Rot", default=0)

def register():
    bpy.utils.register_class(NFR_AdventureState)
    if not hasattr(bpy.types.Scene, "nfr_adventure"):
        bpy.types.Scene.nfr_adventure = PointerProperty(type=NFR_AdventureState)

def unregister():
    if hasattr(bpy.types.Scene, "nfr_adventure"):
        del bpy.types.Scene.nfr_adventure
    bpy.utils.unregister_class(NFR_AdventureState)
