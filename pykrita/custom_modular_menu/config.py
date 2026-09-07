"""Custom Modular Menu (CMM) - config layer: multi-list JSON persistence,
full action catalog enumeration, and refresh notification."""

import json
import os

from krita import Krita

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Default lists on first run (action ids verified against Krita 5.3 krita.action)
DEFAULT_LISTS = [
    {"name": "Canvas Assist", "items": [
        "mirror_canvas",
        "wrap_around_mode",
        "toggle_brush_outline",
        "toggle_fg_bg",
    ]},
    {"name": "Layers", "items": [
        "duplicatelayer",
        "merge_layer",
        "flatten_layer",
        "copy_selection_to_new_layer",
    ]},
    {"name": "View", "items": [
        "zoom_to_fit",
        "zoom_to_100pct",
        "select_all",
        "deselect",
    ]},
]


def load_lists():
    """Return [{name, items:[action_id]}, ...]. Fell back to defaults on missing/empty."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        lists = data.get("lists", [])
        if isinstance(lists, list) and lists:
            clean = []
            for lst in lists:
                if isinstance(lst, dict) and lst.get("name"):
                    items = lst.get("items", [])
                    clean.append({"name": lst["name"],
                                  "items": list(items) if isinstance(items, list) else []})
            if clean:
                return clean
    except (OSError, ValueError):
        pass
    return [dict(lst) for lst in DEFAULT_LISTS]


def save_lists(lists):
    """Write the multi-list model to JSON."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"lists": lists}, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[CMM] failed to save config: {e}")


def catalog_actions():
    """Enumerate every Krita action. Returns [(action_id, label), ...], sorted by label."""
    out = []
    try:
        for a in Krita.instance().actions():
            try:
                oid = a.objectName()
                text = a.text().replace("&", "").strip()
            except RuntimeError:
                continue
            if oid:
                out.append((oid, text or oid))
    except Exception as e:
        print(f"[CMM] failed to enumerate actions: {e}")
    out.sort(key=lambda x: x[1].lower())
    return out


# ---------- Refresh notification (reload Tools menu / Docker after editing) ----------
_refresh_callbacks = []


def register_refresh(callback):
    """Register a callback to run after any config edit is saved."""
    if callback not in _refresh_callbacks:
        _refresh_callbacks.append(callback)


def notify_refresh():
    for cb in list(_refresh_callbacks):
        try:
            cb()
        except Exception as e:
            print(f"[CMM] refresh callback failed: {e}")
