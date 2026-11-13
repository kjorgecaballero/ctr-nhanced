import bpy
from bpy.props import StringProperty, IntProperty, PointerProperty, BoolProperty, CollectionProperty, EnumProperty
from bpy.types import PropertyGroup


# ─────────────────────────────────────────────────────────────────────
# NFR_AdventureSfxEntry — one per-frame SFX for a slot
# Must be defined FIRST (NFR_AdventureSlot references it)
# ─────────────────────────────────────────────────────────────────────
class NFR_AdventureSfxEntry(PropertyGroup):
    frame: IntProperty(name="Frame", min=0, default=0)
    wav_path: StringProperty(name="WAV", subtype='FILE_PATH', default="")


# ─────────────────────────────────────────────────────────────────────
# NFR_AdventureSlot — per-slot config (8 slots in NFR_AdventureState)
# Must be defined BEFORE NFR_AdventureState (which references it)
# ─────────────────────────────────────────────────────────────────────
def _get_char_items():
    from ..constants import RETAIL_CHARACTERS
    items = [('CUSTOM', "Custom", "Custom character")]
    for cid, name, slug in RETAIL_CHARACTERS:
        items.append((str(cid), name, f"Retail: {name}"))
    return items

def _update_slot_kind(self, context):
    from ..constants import RETAIL_CHARACTERS
    if self.slot_kind == 'CUSTOM':
        self.retail_id = 0
        self.char_slug = ""
    else:
        self.retail_id = int(self.slot_kind)
        for cid, name, slug in RETAIL_CHARACTERS:
            if cid == self.retail_id:
                self.char_slug = slug
                break

class NFR_AdventureSlot(PropertyGroup):
    slot_kind: EnumProperty(
        name="Character",
        items=_get_char_items(),
        update=_update_slot_kind
    )
    retail_id: IntProperty(name="Retail ID", default=0)
    char_slug:    StringProperty(name="Character Slug", default="")
    idle_object:  PointerProperty(name="Idle/Char Object", type=bpy.types.Object)
    kart_object:  PointerProperty(name="Kart Object", type=bpy.types.Object)

    # Position (auto-filled on export)
    pos_x: IntProperty(name="X", default=0)
    pos_y: IntProperty(name="Y", default=0)
    pos_z: IntProperty(name="Z", default=0)
    pos_rot: IntProperty(name="Rot", default=0)

    # Camera (per-slot)
    cam_x: IntProperty(name="Cam X", default=0)
    cam_y: IntProperty(name="Cam Y", default=100)
    cam_z: IntProperty(name="Cam Z", default=500)
    cam_rot_x: IntProperty(name="Cam Rot X", default=0)
    cam_rot_y: IntProperty(name="Cam Rot Y", default=0)
    cam_captured: BoolProperty(name="Cam Captured", default=False)

    # UI side for this specific slot
    stats_side: EnumProperty(
        name="Stats Menu Side",
        items=[('RIGHT', "Right", "Right side (default)"),
               ('LEFT', "Left", "Left side (like Tiny/Pura)")],
        default='RIGHT'
    )

    # Animations
    idle_anim: IntProperty(name="Idle Anim", default=0)
    idle_start: IntProperty(name="Idle Start", default=0)
    idle_end: IntProperty(name="Idle End", default=0)
    idle_loop: BoolProperty(name="Idle Loop", default=True)

    select_anim: IntProperty(name="Select Anim", default=0)
    select_start: IntProperty(name="Select Start", default=0)
    select_end: IntProperty(name="Select End", default=0)
    select_loop: BoolProperty(name="Select Loop", default=False)

    # Audio (per character)
    ambient_wav: StringProperty(name="Ambient WAV", subtype='FILE_PATH', default="")
    sfx_entries: CollectionProperty(type=NFR_AdventureSfxEntry)


# ─────────────────────────────────────────────────────────────────────
# NFR_AdventureState — the whole garage pack (Scene.nfr_adventure)
# ─────────────────────────────────────────────────────────────────────
class NFR_AdventureState(PropertyGroup):
    pack_name: StringProperty(name="Pack Name", default="My Pack")
    slug: StringProperty(name="Slug", default="my_pack")
    lev_file: StringProperty(name="LEV File", subtype='FILE_PATH')
    vrm_file: StringProperty(name="VRM File", subtype='FILE_PATH')

    # Camera (one per garage)
    cam_x: IntProperty(name="Cam X", default=0)
    cam_y: IntProperty(name="Cam Y", default=100)
    cam_z: IntProperty(name="Cam Z", default=500)
    cam_rot_x: IntProperty(name="Cam Rot X", default=0)
    cam_rot_y: IntProperty(name="Cam Rot Y", default=0)
    cam_captured: BoolProperty(name="Captured", default=False)

    # 8 slots (each one is a NFR_AdventureSlot)
    slots: CollectionProperty(type=NFR_AdventureSlot)
    active_slot_idx: IntProperty(name="Active Slot", default=0, min=0, max=7)


_classes = (NFR_AdventureSfxEntry, NFR_AdventureSlot, NFR_AdventureState)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)

    if not hasattr(bpy.types.Scene, "nfr_adventure"):
        bpy.types.Scene.nfr_adventure = PointerProperty(type=NFR_AdventureState)

    # Pre-populate 8 slots on first access
    def _init_slots():
        scene = getattr(bpy.context, 'scene', None)
        if scene is None or not hasattr(scene, 'nfr_adventure'):
            return None
        try:
            st = scene.nfr_adventure
            while len(st.slots) < 8:
                st.slots.add()
        except Exception:
            pass
        return None  # don't re-run

    bpy.app.timers.register(_init_slots, first_interval=0.5)


def unregister():
    if hasattr(bpy.types.Scene, "nfr_adventure"):
        del bpy.types.Scene.nfr_adventure
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
