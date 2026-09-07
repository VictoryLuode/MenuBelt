"""Custom Modular Menu (CMM) - config layer: multi-list JSON persistence,
full action catalog enumeration, per-list shortcuts, and refresh notification."""

import json
import os

from krita import Krita

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# Default lists on first run (action ids verified against Krita 5.3 krita.action)
DEFAULT_LISTS = [
    {"name": "Canvas Assist", "shortcut": "", "items": [
        "mirror_canvas",
        "wrap_around_mode",
        "toggle_brush_outline",
        "toggle_fg_bg",
    ]},
    {"name": "Layers", "shortcut": "", "items": [
        "duplicatelayer",
        "merge_layer",
        "flatten_layer",
        "copy_selection_to_new_layer",
    ]},
    {"name": "View", "shortcut": "", "items": [
        "zoom_to_fit",
        "zoom_to_100pct",
        "select_all",
        "deselect",
    ]},
]

DEFAULT_POPUP_SHORTCUT = ""  # whole-menu popup trigger key


def _clean_lists(lists):
    """Normalise raw json lists into [{name, shortcut, items}]."""
    clean = []
    for lst in lists if isinstance(lists, list) else []:
        if not isinstance(lst, dict) or not lst.get("name"):
            continue
        items = lst.get("items", [])
        clean.append({
            "name": lst["name"],
            "shortcut": lst.get("shortcut", "") or "",
            "items": list(items) if isinstance(items, list) else [],
        })
    return clean


def load_config():
    """Return (popup_shortcut, lists). Falls back to defaults on missing/empty."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        lists = _clean_lists(data.get("lists", []))
        if lists:
            popup = data.get("popup_shortcut", "") or ""
            return popup, lists
    except (OSError, ValueError):
        pass
    return DEFAULT_POPUP_SHORTCUT, [dict(lst) for lst in DEFAULT_LISTS]


def load_lists():
    """Return [{name, shortcut, items}, ...] only."""
    return load_config()[1]


def load_popup_shortcut():
    """Return the whole-menu popup shortcut string (may be empty)."""
    return load_config()[0]


def save_config(popup_shortcut, lists):
    """Write popup_shortcut + multi-list model to JSON."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "popup_shortcut": popup_shortcut or "",
                "lists": lists,
            }, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[CMM] failed to save config: {e}")


def save_lists(lists):
    """Compatibility wrapper: save lists, preserving current popup_shortcut."""
    popup, _ = load_config()
    save_config(popup, lists)


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


# ---------- Refresh notification (reload Tools menu / Docker / shortcuts after editing) ----------
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
