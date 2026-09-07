"""Quick List Menu — 配置层：多列表 JSON 持久化 + 全量动作目录枚举 + 刷新通知."""

import json
import os

from krita import Krita

CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

# 首次运行的默认列表（action id 均来自 Krita 5.3 官方 krita.action 核实）
DEFAULT_LISTS = [
    {"name": "画布辅助", "items": [
        "mirror_canvas",
        "wrap_around_mode",
        "toggle_brush_outline",
        "toggle_fg_bg",
    ]},
    {"name": "图层", "items": [
        "duplicatelayer",
        "merge_layer",
        "flatten_layer",
        "copy_selection_to_new_layer",
    ]},
    {"name": "视图", "items": [
        "zoom_to_fit",
        "zoom_to_100pct",
        "select_all",
        "deselect",
    ]},
]


def load_lists():
    """返回 [{name, items:[action_id...]}, ...]。读不到或空则退回默认."""
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
    """把多列表写入 JSON."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({"lists": lists}, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[QuickListMenu] 保存配置失败: {e}")


def catalog_actions():
    """枚举 Krita 中所有 action，返回 [(action_id, 显示文本), ...]，按文本排序."""
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
        print(f"[QuickListMenu] 枚举动作失败: {e}")
    out.sort(key=lambda x: x[1].lower())
    return out


# ---------- 刷新通知（编辑后让 Tools 菜单 / Docker 重载） ----------
_refresh_callbacks = []


def register_refresh(callback):
    """登记一个刷新回调，编辑保存后统一触发."""
    if callback not in _refresh_callbacks:
        _refresh_callbacks.append(callback)


def notify_refresh():
    for cb in list(_refresh_callbacks):
        try:
            cb()
        except Exception as e:
            print(f"[QuickListMenu] 刷新回调失败: {e}")
