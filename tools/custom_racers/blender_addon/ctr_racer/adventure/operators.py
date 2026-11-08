import bpy, os, subprocess, math
from bpy.types import Operator
from ..prefs import _get_prefs
from ..core.helpers import get_python_exe

def _clean_path(p):
    if not p: return ""
    p = p.strip().strip('"\'')
    return os.path.normpath(bpy.path.abspath(p))

def _root(context):
    try:
        prefs = _get_prefs(context)
        repo = getattr(prefs, "repo_path", "")
        if repo:
            p = _clean_path(repo)
            if os.path.isdir(p): return p
    except Exception as e:
        print(f"[Adventure] Error leyendo prefs: {e}")
    
    print(f"[Adventure] WARNING: No repo path found, using CWD: {os.getcwd()}")
    return os.getcwd()

class NFR_OT_AdventureAddCam(Operator):
    bl_idname = "nfr.adventure_add_cam"
    bl_label = "Add Camera"
    ar: bpy.props.StringProperty()
    def execute(self, context):
        cam_data = bpy.data.cameras.new(name=f"AdvCam_{self.ar}")
        cam_obj = bpy.data.objects.new(f"AdvCam_{self.ar}", cam_data)
        context.collection.objects.link(cam_obj)
        if self.ar == '16:9': cam_data.lens = 32
        elif self.ar == '16:10': cam_data.lens = 34
        elif self.ar == '21:9': cam_data.lens = 26
        else: cam_data.lens = 35
        context.scene.camera = cam_obj
        return {'FINISHED'}

class NFR_OT_AdventureAssignSingle(Operator):
    bl_idname = "nfr.adventure_assign_single"
    bl_label = "Get"
    slot_index: bpy.props.IntProperty()
    def execute(self, context):
        st = context.scene.nfr_adventure
        o = context.active_object
        if not o:
            self.report({'ERROR'}, "Selecciona un objeto en el viewport 3D"); return {'CANCELLED'}
        s = st.scale_mult
        setattr(st, f"x_{self.slot_index}", int(o.location.x * s))
        setattr(st, f"y_{self.slot_index}", int(o.location.z * s))
        setattr(st, f"z_{self.slot_index}", int(-o.location.y * s))
        setattr(st, f"rot_{self.slot_index}", int(math.degrees(o.rotation_euler.z) * 4096 / 360))
        return {'FINISHED'}

class NFR_OT_AdventureAssignCam(Operator):
    bl_idname = "nfr.adventure_assign_cam"
    bl_label = "Get Coords from Active Camera"
    def execute(self, context):
        st = context.scene.nfr_adventure
        cam = context.scene.camera
        if not cam:
            self.report({'ERROR'}, "No hay camara activa en la escena"); return {'CANCELLED'}
        s = st.scale_mult
        st.cam_x = int(cam.location.x * s)
        st.cam_y = int(cam.location.z * s)
        st.cam_z = int(-cam.location.y * s)
        st.cam_rot_x = int(math.degrees(cam.rotation_euler.x) * 4096 / 360)
        st.cam_rot_y = int(math.degrees(cam.rotation_euler.z) * 4096 / 360)
        return {'FINISHED'}

class NFR_OT_AdventureBuild(Operator):
    bl_idname = "nfr.adventure_build"
    bl_label = "BUILD ADVENTURE PACK"
    def execute(self, context):
        st = context.scene.nfr_adventure
        root = _root(context)
        script = os.path.join(root, "tools", "custom_racers", "add_adventure_pack.py")
        
        lev_path = _clean_path(st.lev_file)
        vrm_path = _clean_path(st.vrm_file)
        
        print(f"\n--- ADVENTURE BUILD START ---")
        print(f"Root: {root}")
        print(f"Script: {script}")
        print(f"LEV: {lev_path}")
        print(f"VRM: {vrm_path}")

        if not lev_path or not vrm_path or not os.path.isfile(lev_path) or not os.path.isfile(vrm_path):
            self.report({'ERROR'}, f"Archivos no encontrados. LEV: '{lev_path}' VRM: '{vrm_path}'")
            return {'CANCELLED'}
        if not os.path.isfile(script):
            self.report({'ERROR'}, f"No se encuentra el script en: {script}")
            return {'CANCELLED'}

        py_exe = _clean_path(get_python_exe())
        cmd = [py_exe, script, "--name", st.pack_name, "--slug", st.slug,
               "--lev", lev_path, "--vrm", vrm_path,
               "--cam", f"{st.cam_x},{st.cam_y},{st.cam_z},{st.cam_rot_x},{st.cam_rot_y}"]
               
        if st.music_file: 
            cmd += ["--music", _clean_path(st.music_file)]
            
        for i in range(8):
            cmd += ["--slot", f"{getattr(st, f'char_{i}')},{getattr(st, f'x_{i}')},{getattr(st, f'y_{i}')},{getattr(st, f'z_{i}')},{getattr(st, f'rot_{i}')}"]

        print(f"Executing: {cmd}")
        try:
            p = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            if p.stdout: print(f"STDOUT:\n{p.stdout}")
            if p.stderr: print(f"STDERR:\n{p.stderr}")
            
            if p.returncode != 0:
                self.report({'ERROR'}, f"Fallo el script. Revisa la consola."); return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Excepcion de Windows: {e}"); return {'CANCELLED'}
            
        self.report({'INFO'}, "Adventure Pack built successfully")
        return {'FINISHED'}


class NFR_OT_AdventureAimCam(Operator):
    bl_idname = "nfr.adventure_aim_cam"
    bl_label = "Aim Camera at Slot 0"
    bl_description = "Auto-rotates the active camera to look directly at the first character"
    
    def execute(self, context):
        import math
        st = context.scene.nfr_adventure
        cam = context.scene.camera
        if not cam:
            self.report({'ERROR'}, 'No active camera'); return {'CANCELLED'}
        
        s = st.scale_mult
        cx, cy, cz = cam.location.x * s, cam.location.z * s, -cam.location.y * s
        px, py, pz = st.x_0, st.y_0, st.z_0
        
        dx, dy, dz = px - cx, py - cy, pz - cz
        
        yaw_rad = math.atan2(dx, dz)
        horiz_dist = math.sqrt(dx*dx + dz*dz)
        pitch_rad = math.atan2(dy, horiz_dist)
        
        st.cam_rot_y = int((yaw_rad / (2 * math.pi)) * 4096)
        st.cam_rot_x = int((pitch_rad / (2 * math.pi)) * 4096)
        
        cam.rotation_euler[0] = math.pi/2 - pitch_rad
        cam.rotation_euler[2] = -yaw_rad
        
        self.report({'INFO'}, 'Camera auto-aimed at Slot 0')
        return {'FINISHED'}

def register():
    bpy.utils.register_class(NFR_OT_AdventureAddCam)
    bpy.utils.register_class(NFR_OT_AdventureAssignSingle)
    bpy.utils.register_class(NFR_OT_AdventureAssignCam)
    bpy.utils.register_class(NFR_OT_AdventureAimCam)
    bpy.utils.register_class(NFR_OT_AdventureBuild)

def unregister():
    bpy.utils.unregister_class(NFR_OT_AdventureBuild)
    bpy.utils.unregister_class(NFR_OT_AdventureAimCam)
    bpy.utils.unregister_class(NFR_OT_AdventureAssignCam)
    bpy.utils.unregister_class(NFR_OT_AdventureAssignSingle)
    bpy.utils.unregister_class(NFR_OT_AdventureAddCam)