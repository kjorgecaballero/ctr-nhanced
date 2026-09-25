# =========================================================================
# MODULE: core — roster I/O
# =========================================================================
"""roster.txt parsing and writing.

Format:
    page  slot  folder  engine  "Display Name"  [#RRGGBB]
        [mask=good|bad|custom_good|custom_bad]  [wheels=yes|no]

Pure functions. No classes, no registration.
"""
import shlex
from pathlib import Path

from ..constants import _ENGINE_SET


def _parse_roster_line(line):
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    try:
        toks = shlex.split(s)
    except ValueError:
        return None
    if len(toks) < 3:
        return None
    try:
        page = int(toks[0])
        slot = int(toks[1])
    except ValueError:
        return None
    folder = toks[2]
    rest = toks[3:]

    engine = "BALANCED"
    if rest and rest[0] in _ENGINE_SET:
        engine = rest[0]
        rest = rest[1:]

    name = ""
    color = None
    mask = "good"
    wheels = "yes"
    for tok in rest:
        if tok.startswith("mask="):
            v = tok[5:]
            if v in ("good", "bad", "custom_good", "custom_bad"):
                mask = v
        elif tok.startswith("wheels="):
            v = tok[7:]
            if v in ("yes", "no"):
                wheels = v
        elif tok.startswith("#"):
            color = tok
        elif len(tok) == 6 and all(c in "0123456789abcdefABCDEF" for c in tok):
            color = "#" + tok
        elif not name:
            name = tok

    return {
        "page": page, "slot": slot, "folder": folder,
        "engine": engine, "name": name or folder, "color": color,
        "mask": mask, "wheels": wheels,
    }


def _read_roster(prefs):
    path = prefs.racers_dir() / "roster.txt"
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    entries = []
    for line in text.splitlines():
        e = _parse_roster_line(line)
        if e is not None:
            entries.append(e)
    return entries


def _group_by_page(entries):
    pages = {}
    for e in entries:
        pages.setdefault(e["page"], {})[e["slot"]] = e
    return pages


def _remove_roster_entry(prefs, page, slot):
    path = prefs.racers_dir() / "roster.txt"
    if not path.is_file():
        return (False, "roster.txt not found")
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as ex:
        return (False, f"Read failed: {ex}")

    new_lines = []
    removed_slug = None
    for line in text.splitlines():
        e = _parse_roster_line(line)
        if e is not None and e["page"] == page and e["slot"] == slot:
            removed_slug = e["folder"]
            continue
        new_lines.append(line)

    if removed_slug is None:
        return (False, "No entry at that slot")

    try:
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as ex:
        return (False, f"Write failed: {ex}")

    return (True, removed_slug)