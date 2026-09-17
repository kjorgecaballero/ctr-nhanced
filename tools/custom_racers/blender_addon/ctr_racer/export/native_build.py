# =========================================================================
# MODULE: export — build & run
# =========================================================================
"""Native exe build/run helpers.

Owns _kill_running_exe, _build_exe, _run_game.
"""
import subprocess
import time
from pathlib import Path

from ..prefs import _get_prefs


def _kill_running_exe(prefs):
    try:
        res = subprocess.run(
            ["taskkill", "/F", "/IM", prefs.exe_name],
            capture_output=True, text=True, timeout=5)
        return res.returncode == 0
    except Exception:
        return False


def _build_exe(context):
    prefs = _get_prefs(context)
    repo = Path(prefs.repo_path)
    build_dir = prefs.build_path()

    if not repo.is_dir():
        return (False, f"Repo not found: {repo}")
    if not build_dir.is_dir():
        return (False, f"Build dir not found: {build_dir}")

    if _kill_running_exe(prefs):
        time.sleep(2)

    log_path = repo / "build_addon.log"
    try:
        with open(log_path, "w", encoding="utf-8") as log:
            res = subprocess.run(
                ["cmake", "--build", str(build_dir), "--config", "Release"],
                cwd=str(repo), stdout=log, stderr=subprocess.STDOUT,
                timeout=900)
    except FileNotFoundError:
        return (False, "cmake not found in PATH")
    except subprocess.TimeoutExpired:
        return (False, "Build timed out (>15 min)")

    if res.returncode != 0:
        return (False, f"Build failed (rc={res.returncode}); see {log_path.name}")
    return (True, "Build OK")


def _run_game(context):
    prefs = _get_prefs(context)
    repo = Path(prefs.repo_path)
    exe = prefs.exe_path()

    if not exe.is_file():
        return (False, f"Exe not found: {exe} (build first?)")

    _kill_running_exe(prefs)
    time.sleep(0.5)

    try:
        subprocess.Popen([str(exe)], cwd=str(repo))
    except Exception as ex:
        return (False, f"Launch failed: {ex}")
    return (True, f"Launched {exe.name}")