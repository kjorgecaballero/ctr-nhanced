# =========================================================================
# MODULE: anim — operators
# =========================================================================
"""Authoring operators for the Anim tab."""
import math
import bpy
from bpy.types import Operator
from mathutils import Matrix, Vector

from ..prefs import _get_prefs, DEFAULT_ANIM_FRAME_RANGES
from ..core.helpers import _redraw_view3d
from .helpers import CLIP_ORDER, parse_frame_ranges
from .state import sync_state_from_prefs


MARKER_COLOR_MAP = {
    "turn":    "GREEN",
    "reverse": "BLUE",
    "bump":    "YELLOW",
    "jump":    "RED",
}


# Name of the vertex group that marks kart vertices. Case-insensitive.
KART_VGROUP_NAME = "kart"

# Material names considered part of the kart (fallback when no vertex
# group is defined). Case-insensitive.
LEGACY_KART_MATERIALS = {
    'front', 'back', 'bridge', 'floor', 'red',
    'exhaust', 'motortop', 'side', 'exhaust_pipe',
}


def _is_kart_material(mat):
    if mat is None:
        return False
    n = mat.name.lower()
    if n.startswith('kart'):
        return True
    if n in LEGACY_KART_MATERIALS:
        return True
    return False


def _kart_verts_from_vgroup(obj):
    """Read the 'kart' vertex group if it exists. Returns a set of
    vertex indices (weight > 0.5) or an empty set."""
    vg = None
    for g in obj.vertex_groups:
        if g.name.lower() == KART_VGROUP_NAME:
            vg = g
            break
    if vg is None:
        return set()

    result = set()
    for v in obj.data.vertices:
        for elem in v.groups:
            if elem.group == vg.index and elem.weight > 0.5:
                result.add(v.index)
                break
    return result


def _kart_verts_from_materials(mesh):
    """Fallback: derive kart vertices from material assignment.
    A vertex shared between a kart polygon and a non-kart polygon is
    treated as non-kart, so seams don't tear when we deform."""
    kart_mi = {i for i, mat in enumerate(mesh.materials)
               if _is_kart_material(mat)}
    if not kart_mi:
        return set()

    total = {}
    kart = {}
    for poly in mesh.polygons:
        is_k = poly.material_index in kart_mi
        for vi in poly.vertices:
            total[vi] = total.get(vi, 0) + 1
            if is_k:
                kart[vi] = kart.get(vi, 0) + 1

    return {vi for vi, n in total.items() if kart.get(vi, 0) == n}


def _collect_kart_verts(obj):
    """Prefer the explicit 'kart' vertex group. Fall back to material
    detection when the group doesn't exist. Returns (set, source) where
    source is 'vertex group' | 'materials' | 'none'."""
    vg = _kart_verts_from_vgroup(obj)
    if vg:
        return vg, 'vertex group'
    mats = _kart_verts_from_materials(obj.data)
    if mats:
        return mats, 'materials'
    return set(), 'none'


class NFR_OT_JumpToClip(Operator):
    bl_idname = "nfr.anim_jump_to_clip"
    bl_label = "Jump to clip"
    bl_description = ("Move the cursor to this clip's start frame and "
                      "set the playback range to [start, end].")

    def execute(self, context):
        sync_state_from_prefs(context.scene)

        st = context.scene.nfr_anim
        clip = st.selected_clip

        prefs = _get_prefs(context)
        ranges = parse_frame_ranges(prefs)
        if not ranges or clip not in ranges:
            self.report({"ERROR"}, f"Clip '{clip}' has no valid range")
            return {"CANCELLED"}

        fmin, fmax = ranges[clip]
        scene = context.scene
        scene.frame_start = fmin
        scene.frame_end = fmax
        scene.frame_set(fmin)

        self.report({"INFO"}, f"Clip '{clip}': frames {fmin}-{fmax}")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_ToggleTimelineMarkers(Operator):
    bl_idname = "nfr.anim_toggle_markers"
    bl_label = "Toggle Timeline Markers"
    bl_description = ("Create the 4 clip markers if missing, remove them "
                      "if they already exist.")

    def execute(self, context):
        sync_state_from_prefs(context.scene)

        scene = context.scene

        existing = [m for m in scene.timeline_markers
                    if m.name in CLIP_ORDER]
        if existing:
            for m in existing:
                scene.timeline_markers.remove(m)
            self.report({"INFO"},
                        f"Markers removed ({len(existing)})")
            _redraw_view3d(context)
            return {"FINISHED"}

        prefs = _get_prefs(context)
        ranges = parse_frame_ranges(prefs)
        if not ranges:
            self.report({"ERROR"},
                        "No clips configured (check Preferences > "
                        "Animation)")
            return {"CANCELLED"}

        made = []
        for clip in CLIP_ORDER:
            if clip not in ranges:
                continue
            fmin, _fmax = ranges[clip]
            mk = scene.timeline_markers.new(name=clip, frame=fmin)
            try:
                mk.color = MARKER_COLOR_MAP.get(clip, "GREEN")
            except Exception:
                pass
            made.append(clip)

        self.report({"INFO"}, f"Markers created: {', '.join(made)}")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_ResetAnimRanges(Operator):
    bl_idname = "nfr.anim_reset_ranges"
    bl_label = "Reset frame ranges"
    bl_description = ("Restore the default clip frame ranges "
                      "(turn 0-22, reverse 23-35, bump 36-53, jump 54-59).")

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        prefs = _get_prefs(context)
        prefs.anim_frame_ranges = DEFAULT_ANIM_FRAME_RANGES
        sync_state_from_prefs(context.scene)
        self.report({"INFO"}, "Animation frame ranges reset to defaults")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_MarkKartVertices(Operator):
    bl_idname = "nfr.anim_mark_kart"
    bl_label = "Mark Kart"
    bl_description = (
        "Assign the currently selected vertices to a 'kart' vertex "
        "group. Select them in Edit Mode first. If a 'kart' group "
        "already exists, its membership is replaced."
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}

        # obj.mode is more reliable than context.mode when invoked
        # from a sidebar button.
        mode = getattr(obj, 'mode', None) or context.mode

        if mode == 'EDIT':
            import bmesh
            bm = bmesh.from_edit_mesh(obj.data)
            sel = [v.index for v in bm.verts if v.select]
        else:
            # Object Mode fallback: mesh.vertices[i].select retains
            # the selection from the last edit session.
            sel = [v.index for v in obj.data.vertices if v.select]

        if not sel:
            self.report({"ERROR"},
                        f"No vertices selected (mode={mode})")
            return {"CANCELLED"}

        # VertexGroup.add() is forbidden in Edit Mode. Toggle to Object
        # Mode around the operation, then restore.
        was_edit = (mode == 'EDIT')
        if was_edit:
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception as ex:
                self.report({"ERROR"},
                            f"Could not leave Edit Mode: {ex}")
                return {"CANCELLED"}

        try:
            vg = None
            for g in obj.vertex_groups:
                if g.name.lower() == KART_VGROUP_NAME:
                    vg = g
                    break
            if vg is None:
                vg = obj.vertex_groups.new(name=KART_VGROUP_NAME)

            try:
                vg.remove([v.index for v in obj.data.vertices])
            except Exception:
                pass
            vg.add(sel, 1.0, 'REPLACE')
        finally:
            if was_edit:
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception:
                    pass

        self.report({"INFO"},
                    f"Marked {len(sel)} vertices as '{KART_VGROUP_NAME}' "
                    f"(was_edit={was_edit})")
        _redraw_view3d(context)
        return {"FINISHED"}


class NFR_OT_GenerateTestShapeKeys(Operator):
    bl_idname = "nfr.anim_generate_test_shape_keys"
    bl_label = "Generate test shape keys"
    bl_description = (
        "Create Turn_Left, Turn_Right, Compress, Reverse shape keys with "
        "placeholder deformations. Vertices marked as kart (via the "
        "'kart' vertex group, or auto-detected by material name) are "
        "left untouched. Idempotent: existing keys are left as-is."
    )

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Select a mesh first")
            return {"CANCELLED"}

        if context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        mesh = obj.data

        if mesh.shape_keys is None:
            obj.shape_key_add(name='Basis', from_mix=False)

        existing = {kb.name for kb in mesh.shape_keys.key_blocks}

        kart_verts, kart_source = _collect_kart_verts(obj)
        n_kart = len(kart_verts)
        n_total = len(mesh.vertices)

        # Pivot from the non-kart bounding box so the rotation axis
        # sits on the character, not on the whole mesh.
        char_verts = [v for v in mesh.vertices if v.index not in kart_verts]
        if char_verts:
            xs = [v.co.x for v in char_verts]
            ys = [v.co.y for v in char_verts]
            zs = [v.co.z for v in char_verts]
            pivot = Vector((
                (min(xs) + max(xs)) * 0.5,
                (min(ys) + max(ys)) * 0.5,
                (min(zs) + max(zs)) * 0.5,
            ))
        else:
            pivot = Vector((0.0, 0.0, 0.0))

        created = []

        def _emit(name, transform):
            kb = obj.shape_key_add(name=name, from_mix=False)
            for i, v in enumerate(mesh.vertices):
                if i in kart_verts:
                    kb.data[i].co = v.co
                else:
                    kb.data[i].co = transform(v.co)
            kb.value = 0.0
            created.append(name)

        def _rot_y(deg):
            rot = Matrix.Rotation(math.radians(deg), 4, 'Y')
            def t(co):
                return pivot + (rot @ (co - pivot))
            return t

        def _scale_y(factor):
            def t(co):
                p = co - pivot
                return pivot + Vector((p.x, p.y * factor, p.z))
            return t

        if 'Turn_Left' not in existing:
            _emit('Turn_Left', _rot_y(35.0))
        if 'Turn_Right' not in existing:
            _emit('Turn_Right', _rot_y(-35.0))
        if 'Compress' not in existing:
            _emit('Compress', _scale_y(0.6))
        if 'Reverse' not in existing:
            _emit('Reverse', _rot_y(180.0))

        for kb in mesh.shape_keys.key_blocks:
            kb.value = 0.0

        parts = []
        if created:
            parts.append(f"Created: {', '.join(created)}")
        else:
            parts.append("All test shape keys already exist")
        if n_kart:
            parts.append(f"kart verts ({kart_source}): {n_kart}/{n_total}")
        else:
            parts.append("no kart verts detected (whole mesh deformed)")
        self.report({"INFO"}, "  |  ".join(parts))
        _redraw_view3d(context)
        return {"FINISHED"}


_classes = (
    NFR_OT_JumpToClip,
    NFR_OT_ToggleTimelineMarkers,
    NFR_OT_ResetAnimRanges,
    NFR_OT_MarkKartVertices,
    NFR_OT_GenerateTestShapeKeys,
)


def register():
    for c in _classes:
        bpy.utils.register_class(c)


def unregister():
    for c in reversed(_classes):
        bpy.utils.unregister_class(c)