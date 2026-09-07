"""Custom Modular Menu (CMM) - config layer: multi-list JSON persistence,
full action catalog enumeration, per-item custom labels, per-list shortcuts,
and refresh notification.

Item storage format (backward compatible):
- no custom label  -> a plain string action id:  "mirror_canvas"
- custom label     -> a dict: {"id": "mirror_canvas", "label": "Mirror"}
After loading, items are normalised to dicts {"id", "label"} internally.
"""

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
    {"name": "Add Layer", "shortcut": "", "items": [
        "add_new_paint_layer",
        "add_new_group_layer",
        "add_new_shape_layer",
        "add_new_clone_layer",
        "add_new_adjustment_layer",
        "add_new_fill_layer",
        "add_new_file_layer",
        "add_new_selection_mask",
        "add_new_transparency_mask",
        "add_new_filter_mask",
        "add_new_colorize_mask",
        "add_new_transform_mask",
    ]},
    {"name": "Filters", "shortcut": "", "items": [
        "krita_filter_gaussian blur",
        "krita_filter_motion blur",
        "krita_filter_lens blur",
        "krita_filter_unsharp",
        "krita_filter_sharpen",
        "krita_filter_gaussianhighpass",
        "krita_filter_levels",
        "krita_filter_hsvadjustment",
        "krita_filter_colorbalance",
        "krita_filter_desaturate",
        "krita_filter_invert",
        "krita_filter_pixelize",
        "krita_filter_height to normal",
        "krita_filter_normalize",
        "krita_filter_oilpaint",
        "krita_filter_sobel",
    ]},
    {"name": "View", "shortcut": "", "items": [
        "zoom_to_fit",
        "zoom_to_100pct",
        "select_all",
        "deselect",
    ]},
]

DEFAULT_POPUP_SHORTCUT = ""  # whole-menu popup trigger key


def _clean_items(items):
    """Normalise raw items into [{"id", "label"}] (string = no custom label)."""
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str) and it:
            out.append({"id": it, "label": ""})
        elif isinstance(it, dict) and it.get("id"):
            out.append({"id": it["id"], "label": it.get("label", "") or ""})
        elif isinstance(it, (list, tuple)) and len(it) >= 1 and it[0]:
            out.append({"id": it[0], "label": it[1] if len(it) > 1 else ""})
    return out


def _clean_lists(lists):
    """Normalise raw json lists into [{name, shortcut, items}]. Items are dicts."""
    clean = []
    for lst in lists if isinstance(lists, list) else []:
        if not isinstance(lst, dict) or not lst.get("name"):
            continue
        clean.append({
            "name": lst["name"],
            "shortcut": lst.get("shortcut", "") or "",
            "items": _clean_items(lst.get("items", [])),
        })
    return clean


def _serialize_items(items):
    """Serialize items (dicts) back to compact form: plain id or {"id","label"}."""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        label = it.get("label", "") or ""
        if label:
            out.append({"id": it["id"], "label": label})
        else:
            out.append(it["id"])
    return out


def _serialize_lists(lists):
    out = []
    for lst in lists if isinstance(lists, list) else []:
        if not isinstance(lst, dict):
            continue
        out.append({
            "name": lst.get("name", ""),
            "shortcut": lst.get("shortcut", "") or "",
            "items": _serialize_items(lst.get("items", [])),
        })
    return out


def load_config():
    """Return (popup_shortcut, lists). Lists items are [{"id","label"}]. Falls back to defaults."""
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
    """Return [{name, shortcut, items:[{"id","label"}]}, ...] only."""
    return load_config()[1]


def load_popup_shortcut():
    """Return the whole-menu popup shortcut string (may be empty)."""
    return load_config()[0]


def save_config(popup_shortcut, lists):
    """Write popup_shortcut + multi-list model to JSON (compact item form)."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "popup_shortcut": popup_shortcut or "",
                "lists": _serialize_lists(lists),
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
