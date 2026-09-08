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

# The authoritative LAYER blend-mode ids (from KoCompositeOpRegistry.h). These are
# the values Node.setBlendingMode() accepts — NOT brush blend modes.
LAYER_BLEND_MODES = [
    ("normal", "Normal"),
    ("multiply", "Multiply"),
    ("screen", "Screen"),
    ("overlay", "Overlay"),
    ("soft_light", "Soft Light (Photoshop)"),
    ("hard_light", "Hard Light"),
    ("dodge", "Color Dodge"),
    ("linear_dodge", "Linear Dodge"),
    ("burn", "Burn"),
    ("linear_burn", "Linear Burn"),
    ("darken", "Darken"),
    ("lighten", "Lighten"),
    ("diff", "Difference"),
    ("exclusion", "Exclusion"),
    ("vivid_light", "Vivid Light"),
    ("linear light", "Linear Light"),
    ("pin_light", "Pin Light"),
    ("hard_mix_photoshop", "Hard Mix (Photoshop)"),
    ("dissolve", "Dissolve"),
    ("darker color", "Darker Color"),
    ("lighter color", "Lighter Color"),
    ("divide", "Divide"),
    ("subtract", "Subtract"),
    ("hue", "Hue"),
    ("saturation", "Saturation"),
    ("color", "Color"),
    ("luminize", "Luminosity"),
]

# Brush painting blend-mode ids (KoCompositeOpRegistry.h) accepted by
# View.setCurrentBlendingMode() — the modes applied to brush STROKES, distinct
# from the layer modes above.
BRUSH_BLEND_MODES = [
    ("normal", "Normal"),
    ("behind", "Behind"),
    ("erase", "Erase"),
    ("clear", "Clear"),
    ("dissolve", "Dissolve"),
    ("multiply", "Multiply"),
    ("screen", "Screen"),
    ("overlay", "Overlay"),
    ("soft_light", "Soft Light"),
    ("hard_light", "Hard Light"),
    ("vivid_light", "Vivid Light"),
    ("linear light", "Linear Light"),
    ("pin_light", "Pin Light"),
    ("hard_mix", "Hard Mix"),
    ("darken", "Darken"),
    ("lighten", "Lighten"),
    ("burn", "Burn (Color Burn)"),
    ("linear_burn", "Linear Burn"),
    ("dodge", "Color Dodge"),
    ("linear_dodge", "Linear Dodge"),
    ("add", "Addition"),
    ("subtract", "Subtract"),
    ("divide", "Divide"),
    ("diff", "Difference"),
    ("exclusion", "Exclusion"),
    ("hue", "Hue"),
    ("saturation", "Saturation"),
    ("color", "Color"),
    ("luminize", "Luminosity"),
    ("alpha_darken", "Alpha Darken"),
    ("marker", "Marker"),
    ("colorize", "Colorize"),
    ("greater", "Greater"),
    ("darker color", "Darker Color"),
    ("lighter color", "Lighter Color"),
    ("displace", "Displace"),
    ("bumpmap", "Bumpmap"),
    ("tangent_normalmap", "Tangent Normalmap"),
]

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
    {"name": "Blend Mode", "shortcut": "",
     "items": [{"blend": o, "label": l} for o, l in LAYER_BLEND_MODES]},
    {"name": "View", "shortcut": "", "items": [
        "zoom_to_fit",
        "zoom_to_100pct",
        "select_all",
        "deselect",
    ]},
]

DEFAULT_POPUP_SHORTCUT = ""  # whole-menu popup trigger key


def _clean_items(items):
    """Normalise raw items recursively.

    command -> {"id","label"};  script -> {"script","label"};
    blend   -> {"blend","label"};  submenu -> {"name","shortcut","items": [...]}.
    Plain string -> command without custom label.
    """
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str) and it:
            out.append({"id": it, "label": ""})
        elif isinstance(it, dict):
            if it.get("id"):
                out.append({"id": it["id"], "label": it.get("label", "") or ""})
            elif it.get("script") is not None:
                out.append({"script": it.get("script", ""),
                            "label": it.get("label", "") or ""})
            elif it.get("blend") is not None:
                out.append({"blend": it.get("blend", ""),
                            "label": it.get("label", "") or ""})
            elif it.get("bblend") is not None:
                out.append({"bblend": it.get("bblend", ""),
                            "label": it.get("label", "") or ""})
            elif it.get("brush") is not None:
                out.append({"brush": it.get("brush", ""),
                            "label": it.get("label", "") or ""})
            elif it.get("name") is not None:
                out.append({
                    "name": it.get("name", ""),
                    "shortcut": it.get("shortcut", "") or "",
                    "items": _clean_items(it.get("items", [])),
                })
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
            "active": bool(lst.get("active", True)),
            "form": lst.get("form", "list"),
            "show_icons": bool(lst.get("show_icons", True)),
            "items": _clean_items(lst.get("items", [])),
        })
    return clean


def _serialize_items(items):
    """Serialize items (dicts) back to compact form: command or nested submenu."""
    out = []
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        if it.get("id"):
            aid = it["id"]
            label = it.get("label", "") or ""
            out.append({"id": aid, "label": label} if label else aid)
        elif it.get("script") is not None:
            out.append({"script": it.get("script", ""),
                        "label": it.get("label", "") or ""})
        elif it.get("blend") is not None:
            out.append({"blend": it.get("blend", ""),
                        "label": it.get("label", "") or ""})
        elif it.get("bblend") is not None:
            out.append({"bblend": it.get("bblend", ""),
                        "label": it.get("label", "") or ""})
        elif it.get("brush") is not None:
            out.append({"brush": it.get("brush", ""),
                        "label": it.get("label", "") or ""})
        elif it.get("name") is not None:
            out.append({
                "name": it.get("name", ""),
                "shortcut": it.get("shortcut", "") or "",
                "items": _serialize_items(it.get("items", [])),
            })
    return out


def _serialize_lists(lists):
    out = []
    for lst in lists if isinstance(lists, list) else []:
        if not isinstance(lst, dict):
            continue
        out.append({
            "name": lst.get("name", ""),
            "shortcut": lst.get("shortcut", "") or "",
            "active": bool(lst.get("active", True)),
            "form": lst.get("form", "list"),
            "show_icons": bool(lst.get("show_icons", True)),
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
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            old = json.load(f)
        last_identity = old.get("last_identity")
    except (OSError, ValueError):
        last_identity = None
    try:
        data = {
            "popup_shortcut": popup_shortcut or "",
            "lists": _serialize_lists(lists),
        }
        if last_identity is not None:
            data["last_identity"] = last_identity
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[CMM] failed to save config: {e}")


def load_last_identity():
    """Return the persisted last-triggered item identity (or None)."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        val = data.get("last_identity")
        if val:
            return tuple(val)
    except (OSError, ValueError):
        pass
    return None


def save_last_identity(identity):
    """Persist the last-triggered item identity for the 'last used' popup position."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    data["last_identity"] = list(identity) if identity else None
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[CMM] failed to save last identity: {e}")


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


def build_config_dict(popup_shortcut, lists):
    """Serialise in-memory lists to a config dict (for export)."""
    return {"popup_shortcut": popup_shortcut or "", "lists": _serialize_lists(lists)}


def parse_config_dict(data):
    """Parse a config dict into (popup_shortcut, lists)."""
    popup = data.get("popup_shortcut", "") or ""
    return popup, _clean_lists(data.get("lists", []))


# ---------- Script items ----------
def _candidate_action_dirs():
    """Candidate dirs holding Krita's .action XML files (ready-made categories)."""
    dirs = []
    try:
        from PyQt5.QtWidgets import QApplication
        appdir = QApplication.applicationDirPath()
        for rel in (os.path.join("..", "share", "krita", "actions"),
                    os.path.join("share", "krita", "actions")):
            dirs.append(os.path.join(appdir, rel))
    except Exception:
        pass
    try:
        import glob
        dirs.extend(glob.glob("D:/Program Files/Scoop/apps/krita/*/share/krita/actions"))
    except Exception:
        pass
    return dirs


def load_action_categories():
    """Parse Krita's .action XML files -> {action_id: category}.

    Reuses the ready-made categories Krita's shortcut editor already groups by
    (File/Edit/View/Select/Layer/Filter/Settings/Help/...). Returns {} on failure.
    """
    mapping = {}
    try:
        import xml.etree.ElementTree as ET
        for d in _candidate_action_dirs():
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if not fn.endswith(".action"):
                    continue
                try:
                    tree = ET.parse(os.path.join(d, fn))
                except Exception:
                    continue
                for actions in tree.getroot().findall("Actions"):
                    cat = actions.get("category")
                    if not cat:
                        continue
                    for a in actions.findall("Action"):
                        aid = a.get("name")
                        if aid:
                            mapping[aid] = cat
    except Exception:
        return {}
    return mapping


def run_script(code):
    """Execute a user-supplied Python snippet in a namespace with Krita access."""
    if not isinstance(code, str) or not code.strip():
        return
    app = Krita.instance()
    try:
        exec(code, {"__builtins__": __builtins__,
                    "Krita": Krita, "krita": app, "app": app})
    except Exception as e:
        print(f"[CMM] script error: {e}")


def run_composite_op(op_id):
    """Set the active layer's blend mode by its Krita id (setBlendingMode)."""
    if not isinstance(op_id, str) or not op_id:
        return
    try:
        doc = Krita.instance().activeDocument()
    except Exception:
        return
    if doc is None:
        return
    node = doc.activeNode()
    if node is not None:
        try:
            node.setBlendingMode(op_id)
        except Exception as e:
            print(f"[CMM] setBlendingMode error: {e}")


def run_brush_blend(op_id):
    """Set the active brush painting blend mode (View.setCurrentBlendingMode)."""
    if not isinstance(op_id, str) or not op_id:
        return
    try:
        win = Krita.instance().activeWindow()
    except Exception:
        return
    if win is None:
        return
    for view in win.views():
        try:
            view.setCurrentBlendingMode(op_id)
            return
        except Exception:
            continue


def run_brush(name):
    """Set the active Krita brush preset by its name (View.activateResource)."""
    if not isinstance(name, str) or not name:
        return
    try:
        presets = Krita.instance().resources("preset")
        resource = presets.get(name)
        if resource is None:
            # fallback: legacy configs stored the preset filename
            for p in presets.values():
                try:
                    if p.filename() == name:
                        resource = p
                        break
                except Exception:
                    continue
        if resource is None:
            return
        window = Krita.instance().activeWindow()
        if window is None:
            return
        for view in window.views():
            try:
                view.activateResource(resource)
                return
            except Exception:
                continue
    except Exception as e:
        print(f"[CMM] run_brush error: {e}")


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
