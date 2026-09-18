# =========================================================================
# MODULE: slots — state
# =========================================================================
"""_resolve_cells: compute the 18-slot cell map for a given page.

Pure function. No classes, no registration. The view/selection globals
live in ctr_racer.state (top-level) because they are shared between
the slots view and the materials view.

On page 0, slots 0-15 are the engine's 16 originals. They are always
reported as kind="original" with the display name and bundled icon
file, regardless of roster.txt (which never has entries there). This
lets the panel grey them out and show the actual racer icons, so the
user can see what's already taken.
"""

# slot -> (display name, icon file in ctr_racer/icons/)
_ORIGINALS = {
    0:  ("Crash Bandicoot",   "crash.png"),
    1:  ("Dr. Neo Cortex",    "cortex.png"),
    2:  ("Tiny Tiger",        "tiny.png"),
    3:  ("Coco Bandicoot",    "coco.png"),
    4:  ("N. Gin",            "ngin.png"),
    5:  ("Dingodile",         "dingo.png"),
    6:  ("Polar",             "polar.png"),
    7:  ("Pura",              "pura.png"),
    8:  ("N. Tropy",          "ntropy.png"),
    9:  ("Pinstripe Potoroo", "pinstripe.png"),
    10: ("Ripper Roo",        "roo.png"),
    11: ("Papu Papu",         "papu.png"),
    12: ("Komodo Joe",        "joe.png"),
    13: ("Penta Penguin",     "penta.png"),
    14: ("Fake Crash",        "fake_crash.png"),
    15: ("Nitros Oxide",      "oxide.png"),
}


def _resolve_cells(page, page_entries, active_racer, active_slug):
    cells = {}
    n = 18
    for slot in range(n):
        # Page 0, slots 0-15: always originals. Short-circuit before the
        # rest of the logic — the engine's meta array for this page is
        # data.MetaDataCharacters[0..15] and roster.txt never has entries
        # in these slots.
        if page == 0 and slot < 16:
            name, icon_file = _ORIGINALS[slot]
            cells[slot] = ("original", {"name": name, "icon_file": icon_file})
            continue

        e = page_entries.get(slot)
        active_here = (active_racer is not None
                       and active_racer.page == page
                       and active_racer.slot == slot)

        if active_here:
            if e is not None and e["folder"] == active_slug:
                cells[slot] = ("entry", e)
            else:
                cells[slot] = ("pending", {
                    "folder": active_slug or "?",
                    "name": active_racer.long_name or active_slug or "?",
                    "engine": active_racer.engine,
                    "mask": active_racer.mask,
                    "wheels": active_racer.wheels,
                    "color": None,
                    "is_pending": True,
                })
            continue

        if e is not None:
            if (active_slug is not None and e["folder"] == active_slug
                    and active_racer is not None
                    and (active_racer.page != page or active_racer.slot != slot)):
                cells[slot] = ("empty", None)
                continue
            cells[slot] = ("entry", e)
            continue

        cells[slot] = ("empty", None)
    return cells