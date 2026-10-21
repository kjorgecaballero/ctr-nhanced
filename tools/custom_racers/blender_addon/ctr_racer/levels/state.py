"""PropertyGroups for the Levels tab."""
import bpy
from bpy.props import EnumProperty, StringProperty, IntProperty
from bpy.types import PropertyGroup

RETAIL_TRACKS = [
    ('crash_cove', 'Crash Cove', ''),
    ('mystery_caves', 'Mystery Caves', ''),
    ('sewer_speedway', 'Sewer Speedway', ''),
    ('roo_tubes', 'Roo Tubes', ''),
    ('slide_coliseum', 'Slide Coliseum', ''),
    ('turbo_track', 'Turbo Track', ''),
    ('coco_park', 'Coco Park', ''),
    ('tiger_temple', 'Tiger Temple', ''),
    ('papu_pyramid', 'Papu Pyramid', ''),
    ('dingo_canyon', 'Dingo Canyon', ''),
    ('polar_pass', 'Polar Pass', ''),
    ('tiny_arena', 'Tiny Arena', ''),
    ('dragon_mines', 'Dragon Mines', ''),
    ('blizzard_bluff', 'Blizzard Bluff', ''),
    ('hot_air_skyway', 'Hot Air Skyway', ''),
    ('cortex_castle', 'Cortex Castle', ''),
    ('n_gin_labs', 'N.Gin Labs', ''),
    ('oxide_station', 'Oxide Station', ''),
]

class NFR_LevelsState(PropertyGroup):
    action_type: EnumProperty(
        name="Action",
        items=[
            ('ADD', 'Add New', 'Add a new track'),
            ('REPLACE', 'Replace Retail', 'Replace an existing track'),
        ],
        default='ADD',
    )
    lev_file: StringProperty(name=".LEV File", subtype='FILE_PATH', default="")
    vrm_file: StringProperty(name=".VRM File", subtype='FILE_PATH', default="")
    level_name: StringProperty(name="Name", default="")
    slug: StringProperty(name="Slug", description="Leave blank to auto-generate from Name", default="")
    
    replace_target: EnumProperty(name="Target", items=RETAIL_TRACKS, default='crash_cove')
    base_track: EnumProperty(name="Base", items=RETAIL_TRACKS, default='crash_cove')
    
    music_file: StringProperty(name="Music WAV", subtype='FILE_PATH', default="")
    prim_mem: IntProperty(name="Prim Mem", default=0x300000)
    last_status: StringProperty(name="Status", default="")
    show_tracks: bpy.props.BoolProperty(name="Show Tracks", default=False)
    list_output: StringProperty(name="Tracks", default="")

def register():
    bpy.utils.register_class(NFR_LevelsState)
    if not hasattr(bpy.types.Scene, "nfr_levels"):
        bpy.types.Scene.nfr_levels = bpy.props.PointerProperty(type=NFR_LevelsState)

def unregister():
    if hasattr(bpy.types.Scene, "nfr_levels"):
        del bpy.types.Scene.nfr_levels
    bpy.utils.unregister_class(NFR_LevelsState)
