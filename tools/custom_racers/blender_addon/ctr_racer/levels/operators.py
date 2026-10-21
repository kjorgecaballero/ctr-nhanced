"""Operators for the Levels tab."""
import os, subprocess, sys, shutil, json, json
import bpy
from bpy.types import Operator
from ..prefs import _get_prefs
from ..constants import DEFAULT_REPO

def _root():
    try:
        prefs = _get_prefs()
        repo = getattr(prefs, "repo_path", "")
        if repo and os.path.isdir(bpy.path.abspath(repo)):
            return bpy.path.abspath(repo)
    except Exception:
        pass
    if os.path.isdir(DEFAULT_REPO):
        return bpy.path.abspath(DEFAULT_REPO)
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

def _script():
    return os.path.join(_root(), "tools", "custom_racers", "add_level.py")

def _python_exe():
    p = shutil.which("python")
    if p: return p
    p = shutil.which("python3")
    if p: return p
    return sys.executable

def _run(args):
    sc = _script()
    if not os.path.isfile(sc):
        return -1, f"add_level.py not found. Revisa la ruta del repo.\nBuscado en: {sc}"
    try:
        p = subprocess.run([_python_exe(), sc] + args, cwd=_root(), capture_output=True, text=True, timeout=600)
    except Exception as e:
        return -1, str(e)
    if p.stdout: print("--- stdout ---\n" + p.stdout)
    if p.stderr: print("--- stderr ---\n" + p.stderr)
    return p.returncode, (p.stderr if p.returncode != 0 and p.stderr else p.stdout)

class NFR_OT_LevelsBuild(Operator):
    bl_idname = "nfr.levels_build"
    bl_label = "Build Track"
    bl_description = "Packages the .LEV and .VRM files and installs the track to the game"
    
    def execute(self, context):
        st = context.scene.nfr_levels
        lev = bpy.path.abspath(st.lev_file) if st.lev_file else ""
        vrm = bpy.path.abspath(st.vrm_file) if st.vrm_file else ""
        
        if not os.path.isfile(lev): return self._err("LEV file not found")
        if not os.path.isfile(vrm): return self._err("VRM file not found")
        if not st.level_name: return self._err("Name is required")

        cmd = ["--lev", lev, "--vrm", vrm, "--name", st.level_name, "--force", "--prim-mem", "4194304"]
        if st.slug: cmd += ["--slug", st.slug]
        if st.music_file: cmd += ["--music", bpy.path.abspath(st.music_file)]
        
        # Siempre usamos el track seleccionado como base de datos (SFX, IA, etc.)
        cmd += ["--base", st.replace_target]
        
        # Si el modo es reemplazo, además ocupamos su lugar en el menú
        if st.action_type == 'REPLACE': 
            cmd += ["--replace", st.replace_target]

        ret, msg = _run(cmd)
        if ret != 0:
            st.last_status = f"FAILED ({ret})"
            self.report({'ERROR'}, msg)
            return {'CANCELLED'}
        
        st.last_status = "Build OK"
        st.list_output = ""
        st.show_tracks = False
        st.list_output = ""
        st.show_tracks = False
        self.report({'INFO'}, "Track built successfully")
        return {'FINISHED'}

    def _err(self, msg):
        self.report({'ERROR'}, msg)
        return {'CANCELLED'}

class NFR_OT_LevelsList(Operator):
    bl_idname = "nfr.levels_list"
    bl_label = "List Tracks"
    bl_description = "Lists all custom tracks currently installed in the game folder"
    
    def execute(self, context):
        st = context.scene.nfr_levels
        levels_root = os.path.join(_root(), "assets", "mods", "levels")
        
        if not os.path.isdir(levels_root):
            st.list_output = "No tracks folder found (assets/mods/levels)."
            st.last_status = "List Failed"
            return {'CANCELLED'}
            
        out = []
        for slug in sorted(os.listdir(levels_root)):
            jpath = os.path.join(levels_root, slug, "level.json")
            if os.path.isfile(jpath):
                try:
                    with open(jpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    name = data.get("name", slug)
                    mode = f"Replace: {data['replace']}" if "replace" in data else "Add New"
                    out.append(f"{name} ({slug}) - {mode}")
                except Exception:
                    out.append(f"{slug} (Error reading JSON)")
                    
        if not out:
            st.list_output = "No custom tracks installed."
        else:
            st.list_output = "\n".join(out)
            
        st.last_status = "List OK"
        st.show_tracks = True
        return {'FINISHED'}

class NFR_OT_LevelsDelete(Operator):
    bl_idname = "nfr.levels_delete"
    bl_label = "Delete Track"
    bl_description = "Deletes a custom track from the game folder using its slug"
    
    slug: bpy.props.StringProperty(name="Track Slug", description="Slug of the track to delete")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        if not self.slug: return {'CANCELLED'}
        ret, msg = _run(["--delete", self.slug])
        if ret == 0:
            context.scene.nfr_levels.last_status = f"Deleted {self.slug}"
            self.report({'INFO'}, f"Deleted {self.slug}")
            return {'FINISHED'}
        self.report({'ERROR'}, msg)
        return {'CANCELLED'}

CLASSES = (NFR_OT_LevelsBuild, NFR_OT_LevelsList, NFR_OT_LevelsDelete)

def register():
    for c in CLASSES: bpy.utils.register_class(c)

def unregister():
    for c in reversed(CLASSES): bpy.utils.unregister_class(c)
