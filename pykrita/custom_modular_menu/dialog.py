"""Custom Modular Menu (CMM) - multi-list editor dialog.

Supports nested menus, custom-named commands. Provides
a live Current Menu list, shortcut conflict detection, and config export/import.
"""

import json
import os
import sqlite3

from krita import Krita, Palette
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QIcon, QKeySequence, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .config import (
    BRUSH_BLEND_MODES,
    BRUSH_VALUES,
    LAYER_BLEND_MODES,
    build_config_dict,
    catalog_actions,
    load_action_categories,
    load_config,
    notify_refresh,
    parse_config_dict,
    save_config,
)

ROLE_INDEX = Qt.UserRole
ROLE_TOKEN = Qt.UserRole + 1
ROLE_TYPE = Qt.UserRole + 2
TYPE_CMD = "cmd"
TYPE_MENU = "menu"
TYPE_BLEND = "blend"
TYPE_CAT = "category"
TYPE_BRUSH = "brush"
TYPE_BBLEND = "bblend"
TYPE_BVAL = "bval"
TYPE_COLOR = "color"
TYPE_SEP = "sep"
TYPE_HEADER = "header"
TYPE_TOGGLE = "toggle"


def _load_preset_tags():
    """Return (sorted_tag_names, {preset_name: frozenset(tag_names)}) for Krita
    brush presets, read from Krita's resourcecache.sqlite.

    The libkis library API exposes no Resource.tags(), so we read Krita's own
    resource DB (the cache the app maintains) to map preset names to tags.
    resource_type_id 5 == 'paintoppresets'. Returns ([], {}) on any error.
    """
    try:
        root = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", ".."))
        db = os.path.join(root, "resourcecache.sqlite")
        if not os.path.exists(db):
            return [], {}
        con = sqlite3.connect("file:%s?mode=ro" % db.replace("\\", "/"), uri=True)
        try:
            tags = set()
            mapping = {}
            cur = con.execute(
                "select r.name, t.name from resources r "
                "join resource_tags rt on rt.resource_id = r.id and rt.active = 1 "
                "join tags t on t.id = rt.tag_id and t.active = 1 "
                "where r.resource_type_id = 5")
            for name, tag in cur:
                if not name:
                    continue
                tags.add(tag)
                mapping.setdefault(name, set()).add(tag)
        finally:
            con.close()
        return sorted(tags, key=lambda s: s.lower()), \
               {k: frozenset(v) for k, v in mapping.items()}
    except Exception:
        return [], {}


class AddSource:
    """A pluggable source of items for the 'Add items' pane.

    To add a future source (colour swatches, submenu templates, placeholders, ...),
    append an AddSource(...) to ADD_SOURCES with its own item_type, enum_fn, add_fn.
    Nothing else in the dialog needs to change.
    """

    def __init__(self, key, label, item_type, enum_fn, add_fn):
        self.key = key
        self.label = label
        self.item_type = item_type
        self.enum_fn = enum_fn     # (dlg, needle) -> iterable of (payload, display_text)
        self.add_fn = add_fn       # (dlg, payload) -> None  (appends to current menu)


def _enum_actions(dlg, needle):
    existing = dlg._existing_cmd_ids()
    for action_id, text in dlg._catalog.items():
        if needle and needle not in text.lower() and needle not in action_id.lower():
            continue
        if action_id in existing:
            continue
        yield (action_id, text)


def _add_action(dlg, payload):
    action_id = payload
    if action_id not in dlg._existing_cmd_ids():
        dlg._cur_items().append({"id": action_id, "label": ""})
        dlg._render_items()


def _enum_blend(dlg, needle):
    existing = {it.get("blend") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("blend")}
    for oid, label in LAYER_BLEND_MODES:
        if needle and needle not in label.lower() and needle not in oid.lower():
            continue
        if oid in existing:
            continue
        yield (oid, label)


def _add_blend(dlg, payload):
    oid = payload
    existing = {it.get("blend") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("blend")}
    if oid not in existing:
        dlg._cur_items().append({"blend": oid, "label": dict(LAYER_BLEND_MODES).get(oid, oid)})
        dlg._render_items()


def _enum_brush_blend(dlg, needle):
    existing = {it.get("bblend") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("bblend")}
    for oid, label in BRUSH_BLEND_MODES:
        if needle and needle not in label.lower() and needle not in oid.lower():
            continue
        if oid in existing:
            continue
        yield (oid, label)


def _add_brush_blend(dlg, payload):
    oid = payload
    existing = {it.get("bblend") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("bblend")}
    if oid not in existing:
        dlg._cur_items().append({"bblend": oid,
                                 "label": dict(BRUSH_BLEND_MODES).get(oid, oid)})
        dlg._render_items()


def _enum_brush_values(dlg, needle):
    existing = {it.get("bval") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("bval")}
    for spec, label in BRUSH_VALUES:
        if needle and needle not in label.lower() and needle not in spec.lower():
            continue
        if spec in existing:
            continue
        yield (spec, label)


def _add_brush_value(dlg, payload):
    spec = payload
    existing = {it.get("bval") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("bval")}
    if spec in existing:
        return
    dlg._cur_items().append({"bval": spec,
                             "label": dict(BRUSH_VALUES).get(spec, spec)})
    dlg._render_items()


def _add_color(dlg, payload):
    if payload.startswith("fg:") or payload.startswith("bg:"):
        target, hexc = payload.split(":", 1)
        _append_color(dlg, hexc, target)


def _append_color(dlg, hexc, target):
    existing = {it.get("color") + ":" + it.get("target", "fg")
                for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("color")}
    key = hexc + ":" + target
    if key in existing:
        return
    label = "%s (%s)" % (hexc, "Fg" if target == "fg" else "Bg")
    dlg._cur_items().append({"color": hexc, "target": target, "label": label})
    dlg._render_items()


def _enum_palettes(dlg, needle):
    # The palette source renders a palette -> colors tree in _reload_available;
    # this enum is a no-op placeholder required by the AddSource signature.
    return iter(())


def _enum_brushes(dlg, needle):
    existing = {it.get("brush") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("brush")}
    try:
        presets = Krita.instance().resources("preset")
    except Exception:
        return
    for name in presets:
        if needle and needle not in name.lower():
            continue
        if name in existing:
            continue
        yield (name, name)


def _add_brush(dlg, payload):
    name = payload
    existing = {it.get("brush") for it in dlg._cur_items()
                if isinstance(it, dict) and it.get("brush")}
    if name in existing:
        return
    dlg._cur_items().append({"brush": name, "label": name})
    dlg._render_items()


# Order = order shown in the "Add items" combo. Append new sources here to extend.
ADD_SOURCES = [
    AddSource("actions", "Krita Actions", TYPE_CMD, _enum_actions, _add_action),
    AddSource("blend", "Layer Blend Mode", TYPE_BLEND, _enum_blend, _add_blend),
    AddSource("bblend", "Brush Blend Mode", TYPE_BBLEND, _enum_brush_blend, _add_brush_blend),
    AddSource("bval", "Brush Value", TYPE_BVAL, _enum_brush_values, _add_brush_value),
    AddSource("palette", "Krita Palettes", TYPE_COLOR, _enum_palettes, _add_color),
    AddSource("brush", "Brushes", TYPE_BRUSH, _enum_brushes, _add_brush),
]


class ListMenuDialog(QDialog):
    """Multi-menu editor with nested submenu navigation + a live Current Menu list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Modular Menu")
        self.setMinimumSize(920, 560)
        self._apply_default_size()

        self._catalog = dict(catalog_actions())
        self._krita_shortcuts = self._collect_krita_shortcuts()
        self.popup_shortcut, self.lists = load_config()
        self.current = 0
        self.path = [self.lists[self.current]] if self.lists else []
        self._loading_sc = False
        self._brush_icons = {}      # preset name -> QIcon (or None)
        self._presets = None        # cached resources("preset") dict
        self._tags_loaded = False   # lazy: brush tag filter data
        self._brush_tags = []       # sorted tag names for brush presets
        self._preset_tags = {}      # preset name -> frozenset(tag names)
        self._palette_cache = None  # lazy: {palette_name -> [(hex, name), ...]}
        self._checkable_actions = None  # lazy: [(action_id, label)] for toggle picker
        self._sources = sorted(ADD_SOURCES, key=lambda s: s.label.lower())
        self._action_categories = load_action_categories()
        catalog_ids = set(self._catalog.keys())
        self._categories = sorted({v for k, v in self._action_categories.items()
                                   if k in catalog_ids})

        self._build_ui()
        self._reload_sidebar()
        self._update_form_combo()
        self._update_show_icons_check()
        self._render_current()
        self._update_left_shortcut()
        self._update_tag_widget()
        self._reload_available()

    # ---------- Size (remembered) ----------
    def _apply_default_size(self):
        try:
            w = Krita.instance().readSetting("custom_modular_menu", "dialog_width", "")
            h = Krita.instance().readSetting("custom_modular_menu", "dialog_height", "")
            if w and h:
                self.resize(int(w), int(h))
                return
        except Exception:
            pass
        try:
            geo = QApplication.primaryScreen().availableGeometry()
            self.resize(max(920, int(geo.width() * 0.6)), max(560, int(geo.height() * 0.65)))
        except Exception:
            self.resize(980, 620)

    def _persist_size(self):
        try:
            app = Krita.instance()
            app.writeSetting("custom_modular_menu", "dialog_width", str(self.width()))
            app.writeSetting("custom_modular_menu", "dialog_height", str(self.height()))
        except Exception:
            pass

    def done(self, result):
        self._persist_size()
        super().done(result)

    @staticmethod
    def _collect_krita_shortcuts():
        out = set()
        try:
            for a in Krita.instance().actions():
                try:
                    s = a.shortcut().toString(QKeySequence.PortableText)
                    if s:
                        out.add(s)
                except Exception:
                    pass
        except Exception:
            pass
        return out

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(12)

        # Left: top-level menus + per-menu popup shortcut
        left_box = QGroupBox("Menu List")
        left = QVBoxLayout(left_box)
        self.sidebar = QListWidget()
        self.sidebar.currentRowChanged.connect(self._on_switch_list)
        self.sidebar.itemChanged.connect(self._on_sidebar_item_changed)
        self.sidebar.setDragDropMode(QAbstractItemView.InternalMove)
        self.sidebar.setDefaultDropAction(Qt.MoveAction)
        self.sidebar.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sidebar.model().rowsMoved.connect(self._sync_lists_order)
        left.addWidget(self.sidebar)
        for label, slot in (("Add", self._new_list),
                            ("Rename", self._rename_list),
                            ("Delete", self._delete_list)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            left.addWidget(b)
        left_box.setMinimumWidth(200)
        body.addWidget(left_box, 1)

        # Current Menu (its own panel, right of Menu List)
        current_box = QGroupBox("Current Menu")
        self.current_box = current_box
        cm = QVBoxLayout(current_box)
        header_row = QHBoxLayout()
        self.crumb_row = QHBoxLayout()
        header_row.addLayout(self.crumb_row)
        header_row.addStretch()
        cm.addLayout(header_row)
        self.items_list = QListWidget()
        self.items_list.itemDoubleClicked.connect(self._on_item_double_click)
        self.items_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.items_list.setDefaultDropAction(Qt.MoveAction)
        self.items_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_list.model().rowsMoved.connect(self._sync_items_order)
        cm.addWidget(self.items_list)

        # Menu settings (per-list popup behaviour)
        settings_box = QGroupBox("Menu Settings")
        st = QVBoxLayout(settings_box)
        st.setContentsMargins(8, 6, 8, 6)

        # Menu form (list / pie)
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel("Form:"))
        self.form_combo = QComboBox()
        self.form_combo.addItem("List", "list")
        self.form_combo.addItem("Pie", "pie")
        self.form_combo.setToolTip(
            "List: linear cursor menu.\n"
            "Pie: Blender-style radial menu (up to 8 items, submenus not shown).")
        self.form_combo.currentIndexChanged.connect(self._on_form_changed)
        form_row.addWidget(self.form_combo)
        form_row.addStretch()
        st.addLayout(form_row)

        # Show icons (Krita action icons + brush thumbnails)
        self.show_icons_check = QCheckBox("Show icons")
        self.show_icons_check.setToolTip("Display Krita action icons and brush thumbnails in this menu.")
        self.show_icons_check.toggled.connect(self._on_show_icons_changed)
        st.addWidget(self.show_icons_check)

        # Per-list popup shortcut (inside Menu Settings)
        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel("Shortcut:"))
        self.list_sc_edit = QKeySequenceEdit()
        self.list_sc_edit.setMinimumWidth(90)
        self.list_sc_edit.setToolTip("Press a key combination to pop this menu at the cursor.")
        self.list_sc_edit.keySequenceChanged.connect(self._on_list_shortcut_changed)
        sc_row.addWidget(self.list_sc_edit)
        sc_clear = QPushButton("Clear")
        sc_clear.clicked.connect(self._clear_list_shortcut)
        sc_row.addWidget(sc_clear)
        sc_row.addStretch()
        st.addLayout(sc_row)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_menu = QMenu(add_btn)
        add_menu.addAction("Add Submenu", self._add_submenu)
        add_menu.addAction("Add Header", self._add_header)
        add_menu.addAction("Add Separator", self._add_separator)
        add_menu.addAction("Add Toggle", self._add_toggle)
        add_btn.setMenu(add_menu)
        btn_row.addWidget(add_btn)
        for label, slot in (("Rename", self._rename_item),
                            ("Remove", self._remove_selected)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        btn_row.addStretch()
        cm.addLayout(btn_row)
        cm.addWidget(settings_box)
        body.addWidget(current_box, 2)

        # Add items (pick a Krita action or a layer blend mode to add)
        avail_box = QGroupBox("Add items")
        av = QVBoxLayout(avail_box)
        self.add_type = QComboBox()
        self.add_type.addItems([s.label for s in self._sources])
        self.add_type.currentIndexChanged.connect(lambda _i: self._on_add_type_changed())
        av.addWidget(self.add_type)
        # Tag filter row: shown only when the brush source is active.
        self.tag_widget = QWidget()
        tag_row = QHBoxLayout(self.tag_widget)
        tag_row.setContentsMargins(0, 0, 0, 0)
        tag_row.addWidget(QLabel("Tag:"))
        self.tag_filter = QComboBox()
        self.tag_filter.currentIndexChanged.connect(lambda _i: self._reload_available())
        tag_row.addWidget(self.tag_filter, 1)
        av.addWidget(self.tag_widget)
        self.tag_widget.setVisible(False)
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search…")
        self.search_box.textChanged.connect(self._reload_available)
        search_row.addWidget(self.search_box)
        av.addLayout(search_row)
        self.add_tree = QTreeWidget()
        self.add_tree.setHeaderHidden(True)
        self.add_tree.setIndentation(14)
        self.add_tree.itemDoubleClicked.connect(self._on_tree_double_click)
        av.addWidget(self.add_tree, 1)  # tree takes the remaining space
        add_btn = QPushButton("Add")
        add_btn.setToolTip("Add the selected item (or double-click it)")
        add_btn.clicked.connect(self._add_selected)
        av.addWidget(add_btn)
        self.detail_box = QLabel()
        self.detail_box.setWordWrap(True)
        self.detail_box.setFixedHeight(104)
        self.detail_box.setTextInteractionFlags(Qt.TextSelectableByMouse)
        av.addWidget(self.detail_box)
        self.add_tree.itemSelectionChanged.connect(self._on_avail_selection_changed)
        body.addWidget(avail_box, 2)

        root.addLayout(body)

        # Bottom: export/import + OK/Cancel
        bottom = QHBoxLayout()
        im = QPushButton("Import…")
        im.clicked.connect(self._import_config)
        bottom.addWidget(im)
        ex = QPushButton("Export…")
        ex.clicked.connect(self._export_config)
        bottom.addWidget(ex)
        bottom.addStretch()
        ok = QPushButton("OK")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        cancel = QPushButton("Cancel")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(ok)
        bottom.addWidget(cancel)
        root.addLayout(bottom)

    # ---------- Current menu / path ----------
    def _cur_menu(self):
        return self.path[-1] if self.path else {"name": "", "shortcut": "", "items": []}

    def _cur_items(self):
        return self._cur_menu().get("items", [])

    def _name(self):
        return self._cur_menu().get("name", "")

    def _update_current_title(self):
        name = self._name()
        self.current_box.setTitle(("Current Menu : %s" % name) if name else "Current Menu")

    def _render_path_bar(self):
        while self.crumb_row.count():
            it = self.crumb_row.takeAt(0).widget()
            if it is not None:
                it.deleteLater()
        # Submenu navigation crumbs — only shown while inside a submenu (i>0).
        if len(self.path) > 1:
            for i, node in enumerate(self.path):
                if i > 0:
                    self.crumb_row.addWidget(QLabel("\u25b8"))
                btn = QPushButton(node.get("name", "?"))
                btn.setFlat(True)
                btn.clicked.connect(lambda _=False, d=i: self._go_to_depth(d))
                self.crumb_row.addWidget(btn)

    def _go_to_depth(self, depth):
        if 0 <= depth < len(self.path):
            self.path = self.path[: depth + 1]
            self._render_current()

    # ---------- Sidebar / list management ----------
    def _reload_sidebar(self):
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for lst in self.lists:
            item = QListWidgetItem(lst["name"])
            item.setData(ROLE_INDEX, lst["name"])
            active = bool(lst.get("active", True))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if active else Qt.Unchecked)
            self.sidebar.addItem(item)
            self._style_sidebar_item(item, active)
        if 0 <= self.current < self.sidebar.count():
            self.sidebar.setCurrentRow(self.current)
        self.sidebar.blockSignals(False)

    def _style_sidebar_item(self, item, active):
        font = QFont()
        font.setItalic(not active)
        item.setFont(font)
        item.setForeground(QBrush(QColor(150, 150, 150)) if not active else QBrush())

    def _on_sidebar_item_changed(self, item):
        name = item.data(ROLE_INDEX)
        if not name:
            return
        active = (item.checkState() == Qt.Checked)
        lst = next((l for l in self.lists if l.get("name") == name), None)
        if lst is None:
            return
        if bool(lst.get("active", True)) == active:
            return  # not a check-state change (e.g. reorder also fires itemChanged)
        lst["active"] = active
        self._style_sidebar_item(item, active)
        save_config(self.popup_shortcut, self.lists)
        notify_refresh()

    def _on_switch_list(self, row):
        if 0 <= row < len(self.lists):
            self.current = row
            self.path = [self.lists[row]]
            self._update_left_shortcut()
            self._update_form_combo()
            self._update_show_icons_check()
            self._render_current()

    def _cur_top_list(self):
        if 0 <= self.current < len(self.lists):
            return self.lists[self.current]
        return None

    def _on_form_changed(self):
        lst = self._cur_top_list()
        if lst is None:
            return
        lst["form"] = self.form_combo.currentData()
        save_config(self.popup_shortcut, self.lists)
        notify_refresh()

    def _update_form_combo(self):
        lst = self._cur_top_list()
        self.form_combo.blockSignals(True)
        if lst is None:
            self.form_combo.setEnabled(False)
            self.form_combo.blockSignals(False)
            return
        self.form_combo.setEnabled(True)
        idx = self.form_combo.findData(lst.get("form", "list"))
        self.form_combo.setCurrentIndex(max(0, idx))
        self.form_combo.blockSignals(False)

    def _on_show_icons_changed(self):
        lst = self._cur_top_list()
        if lst is None:
            return
        lst["show_icons"] = self.show_icons_check.isChecked()
        save_config(self.popup_shortcut, self.lists)
        notify_refresh()

    def _update_show_icons_check(self):
        lst = self._cur_top_list()
        self.show_icons_check.blockSignals(True)
        if lst is None:
            self.show_icons_check.setEnabled(False)
            self.show_icons_check.blockSignals(False)
            return
        self.show_icons_check.setEnabled(True)
        self.show_icons_check.setChecked(bool(lst.get("show_icons", True)))
        self.show_icons_check.blockSignals(False)

    def _sync_lists_order(self, *_):
        by_name = {lst["name"]: lst for lst in self.lists}
        new_order = []
        for i in range(self.sidebar.count()):
            name = self.sidebar.item(i).data(ROLE_INDEX)
            if name in by_name:
                new_order.append(by_name[name])
        if len(new_order) == len(self.lists):
            self.lists[:] = new_order
        self.current = max(0, self.sidebar.currentRow())
        self._update_left_shortcut()

    def _new_list(self):
        name, ok = QInputDialog.getText(self, "Add", "List name:")
        if not ok or not name.strip():
            return
        self.lists.append({"name": name.strip(), "shortcut": "", "items": []})
        self.current = len(self.lists) - 1
        self.path = [self.lists[self.current]]
        self._reload_sidebar()
        self._render_current()
        self._update_left_shortcut()

    def _rename_list(self):
        if not self.lists:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename List", "New name:", text=self.lists[self.current]["name"])
        if ok and new_name.strip():
            self.lists[self.current]["name"] = new_name.strip()
            self._reload_sidebar()
            self._render_path_bar()

    def _delete_list(self):
        if not self.lists:
            return
        if QMessageBox.question(
                self, "Delete List",
                f"Delete the list \u201c{self.lists[self.current]['name']}\u201d?") == QMessageBox.Yes:
            self.lists.pop(self.current)
            self.current = max(0, min(self.current, len(self.lists) - 1))
            self.path = [self.lists[self.current]] if self.lists else []
            self._reload_sidebar()
            self._render_current()
            self._update_left_shortcut()

    # ---------- Shortcut ----------
    def _on_list_shortcut_changed(self, seq):
        if self._loading_sc or not self.lists:
            return
        self.lists[self.current]["shortcut"] = seq.toString(QKeySequence.PortableText)

    def _clear_list_shortcut(self):
        if not self.lists:
            return
        self.lists[self.current]["shortcut"] = ""
        self._loading_sc = True
        self.list_sc_edit.setKeySequence(QKeySequence(""))
        self._loading_sc = False

    def _update_left_shortcut(self):
        if not self.lists:
            return
        self._loading_sc = True
        self.list_sc_edit.setKeySequence(
            self.lists[self.current].get("shortcut", ""))
        self._loading_sc = False

    # ---------- Current menu items ----------
    @staticmethod
    def _token_of(it):
        if isinstance(it, str):
            return it
        if isinstance(it, dict):
            if it.get("id"):
                return it["id"]
            if it.get("blend") is not None:
                return "blend:" + (it.get("blend", "") or "")
            if it.get("bblend") is not None:
                return "bblend:" + (it.get("bblend", "") or "")
            if it.get("bval") is not None:
                return "bval:" + (it.get("bval", "") or "")
            if it.get("color") is not None:
                return "color:" + (it.get("color", "") or "") + ":" + (it.get("target", "fg") or "fg")
            if it.get("sep"):
                return "sep"
            if it.get("header") is not None:
                return "header:" + (it.get("header", "") or "")
            if it.get("toggle") is not None:
                return "toggle:" + (it.get("toggle", "") or "")
            if it.get("brush") is not None:
                return "brush:" + (it.get("brush", "") or "")
            if it.get("name") is not None:
                return it["name"]
        return None

    def _item_icon(self, it):
        """Return a QIcon for an item (action icon / brush thumb / colour swatch)."""
        if isinstance(it, str):
            aid = it
        elif isinstance(it, dict):
            if it.get("color") is not None:
                return self._color_swatch_icon(it.get("color", ""))
            if it.get("toggle") is not None:
                aid = it["toggle"]
            elif it.get("id"):
                aid = it["id"]
            elif it.get("brush") is not None:
                return self._brush_pixmap_icon(it["brush"])
            else:
                return None
        else:
            return None
        try:
            act = Krita.instance().action(aid)
            if act is not None:
                icon = act.icon()
                if not icon.isNull():
                    return icon
        except Exception:
            pass
        return None

    @staticmethod
    def _color_swatch_icon(hexc):
        try:
            pix = QPixmap(20, 20)
            pix.fill(QColor(hexc))
            return QIcon(pix)
        except Exception:
            return None

    @staticmethod
    def _swatch_to_hex(sw):
        """Convert a palette Swatch to a #rrggbb hex string (from display-ordered
        RGB components). Returns None on any error / non-RGB model."""
        try:
            mc = sw.color()
            if mc is None:
                return None
            comps = mc.componentsOrdered()
            if len(comps) < 3:
                return None
            r = int(round(max(0.0, min(1.0, comps[0])) * 255))
            g = int(round(max(0.0, min(1.0, comps[1])) * 255))
            b = int(round(max(0.0, min(1.0, comps[2])) * 255))
            return "#%02x%02x%02x" % (r, g, b)
        except Exception:
            return None

    def _ensure_palette_cache(self):
        """Build the palette -> colours cache once (avoids re-parsing every
        palette on every visit to the Krita Palettes source)."""
        if self._palette_cache is not None:
            return
        cache = {}
        try:
            pals = Krita.instance().resources("palette")
        except Exception:
            pals = {}
        for name, res in pals.items():
            try:
                pal = Palette(res)
                n = pal.numberOfEntries()
                items = []
                for i in range(n):
                    try:
                        sw = pal.entryByIndex(i)
                        if sw is None or not sw.isValid():
                            continue
                        hexc = self._swatch_to_hex(sw)
                        if not hexc:
                            continue
                        cname = (sw.name() or "").strip()
                        items.append((hexc, cname if cname else hexc))
                    except Exception:
                        continue
                if items:
                    cache[name] = items
            except Exception:
                continue
        self._palette_cache = cache

    def _populate_palette_tree(self, needle):
        """Fill the Add pane with Krita palettes -> their colours as addable
        swatches (colour items reuse the Color source's add path)."""
        self._ensure_palette_cache()
        for name, items in self._palette_cache.items():
            if needle and needle not in name.lower():
                continue
            parent = QTreeWidgetItem([name])
            parent.setData(0, ROLE_TYPE, TYPE_CAT)
            parent.setIcon(0, self._color_swatch_icon("#808080"))
            self.add_tree.addTopLevelItem(parent)
            for hexc, label in items:
                child = QTreeWidgetItem([label])
                child.setData(0, ROLE_TOKEN, "fg:" + hexc)
                child.setData(0, ROLE_TYPE, TYPE_COLOR)
                icon = self._color_swatch_icon(hexc)
                if icon is not None:
                    child.setIcon(0, icon)
                parent.addChild(child)
        self.add_tree.expandAll()

    def _get_presets(self):
        """Cached dict of all Krita brush presets (name -> Resource)."""
        if self._presets is None:
            self._presets = Krita.instance().resources("preset")
        return self._presets

    def _brush_pixmap_icon(self, name):
        if name in self._brush_icons:
            return self._brush_icons[name]
        icon = None
        try:
            presets = self._get_presets()
            resource = presets.get(name)
            if resource is None:
                for p in presets.values():
                    try:
                        if p.filename() == name:
                            resource = p
                            break
                    except Exception:
                        continue
            if resource is not None:
                img = resource.image()
                if not img.isNull():
                    icon = QIcon(QPixmap.fromImage(
                        img.scaled(64, 64, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)))
        except Exception:
            icon = None
        self._brush_icons[name] = icon
        return icon

    def _render_current(self):
        self._update_current_title()
        self._render_path_bar()
        self._render_items()

    def _render_items(self):
        items = self._cur_items()
        self.items_list.clear()
        for idx, it in enumerate(items):
            token = self._token_of(it)
            typ, text = TYPE_CMD, token or "?"
            if isinstance(it, str):
                text = self._catalog.get(it, it)
            elif isinstance(it, dict):
                if it.get("id"):
                    text = it.get("label", "") or self._catalog.get(it["id"], it["id"])
                elif it.get("blend") is not None:
                    typ, text = TYPE_BLEND, f"\u25c6 {it.get('label', it['blend'])}"
                elif it.get("bblend") is not None:
                    typ, text = TYPE_BBLEND, f"\u25c6 {it.get('label', it['bblend'])}"
                elif it.get("brush") is not None:
                    typ, text = TYPE_BRUSH, it.get("label", it["brush"])
                elif it.get("bval") is not None:
                    typ, text = TYPE_BVAL, it.get("label", it["bval"])
                elif it.get("color") is not None:
                    typ, text = TYPE_COLOR, "\U0001f3a8 " + (it.get("label", it["color"]) or it["color"])
                elif it.get("sep"):
                    typ, text = TYPE_SEP, "— — — — —"
                elif it.get("header") is not None:
                    typ, text = TYPE_HEADER, it.get("label", it["header"]) or it["header"]
                elif it.get("toggle") is not None:
                    typ, text = TYPE_TOGGLE, "\u2611 " + (it.get("label", it["toggle"]) or it["toggle"])
                elif it.get("name") is not None:
                    typ, text = TYPE_MENU, f"\u25b8 {it['name']}"
            entry = QListWidgetItem(text)
            icon = self._item_icon(it)
            if icon is not None:
                entry.setIcon(icon)
            entry.setData(ROLE_INDEX, idx)
            entry.setData(ROLE_TOKEN, token)
            entry.setData(ROLE_TYPE, typ)
            entry.setToolTip(f"{text}  [{token}]")
            font = QFont()
            font.setItalic(typ not in (TYPE_MENU, TYPE_SEP, TYPE_HEADER))
            entry.setFont(font)
            self.items_list.addItem(entry)

    def _existing_cmd_ids(self):
        out = set()
        for it in self._cur_items():
            if isinstance(it, str):
                out.add(it)
            elif isinstance(it, dict) and it.get("id"):
                out.add(it["id"])
        return out

    def _on_avail_selection_changed(self):
        self._show_item_details(self.add_tree.currentItem())

    def _show_item_details(self, item):
        """Fill the bottom detail box with API info for the selected add item."""
        if item is None or item.data(0, ROLE_TYPE) == TYPE_CAT:
            self.detail_box.setText("")
            return
        src = self._current_source()
        payload = item.data(0, ROLE_TOKEN)
        if src and src.key == "actions" and payload:
            name = item.text(0)
            cat = self._action_categories.get(payload, "other")
            shortcut = ""
            try:
                act = Krita.instance().action(payload)
                if act is not None:
                    shortcut = act.shortcut().toString() or ""
            except Exception:
                pass
            lines = [
                "Krita action: %s" % name,
                "id: %s" % payload,
                "category: %s" % cat,
            ]
            if shortcut:
                lines.append("shortcut: %s" % shortcut)
            lines.append("API: Krita.instance().action('%s').trigger()" % payload)
            self.detail_box.setText("\n".join(lines))
        elif item.data(0, ROLE_TYPE) == TYPE_BLEND and payload:
            label = dict(LAYER_BLEND_MODES).get(payload, payload)
            self.detail_box.setText(
                "Layer blend mode: %s\n"
                "id: %s\n"
                "API: Krita.instance().activeDocument().activeNode()\n"
                "     .setBlendingMode('%s')" % (label, payload, payload))
        elif item.data(0, ROLE_TYPE) == TYPE_BBLEND and payload:
            label = dict(BRUSH_BLEND_MODES).get(payload, payload)
            self.detail_box.setText(
                "Brush blend mode: %s\n"
                "id: %s\n"
                "API: Krita.instance().activeWindow().activeView()\n"
                "     .setCurrentBlendingMode('%s')" % (label, payload, payload))
        else:
            self.detail_box.setText("")

    def _current_source(self):
        idx = self.add_type.currentIndex()
        if 0 <= idx < len(self._sources):
            return self._sources[idx]
        return None

    def _ensure_tags_loaded(self):
        if not self._tags_loaded:
            self._brush_tags, self._preset_tags = _load_preset_tags()
            self._tags_loaded = True

    def _update_tag_widget(self):
        src = self._current_source()
        is_brush = src is not None and src.key == "brush"
        self.tag_widget.setVisible(is_brush)
        if not is_brush:
            return
        self._ensure_tags_loaded()
        items = ["All tags"] + self._brush_tags
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        self.tag_filter.addItems(items)
        self.tag_filter.blockSignals(False)

    def _on_add_type_changed(self):
        self._update_tag_widget()
        self._reload_available()

    def _reload_available(self):
        self.add_tree.clear()
        src = self._current_source()
        if src is None:
            return
        needle = self.search_box.text().strip().lower()
        if src.key == "actions":
            # Group by Krita's ready-made categories -> tree of category > action.
            groups = {}
            for action_id, text in src.enum_fn(self, needle):
                cat = self._action_categories.get(action_id) or "Other"
                groups.setdefault(cat, []).append((action_id, text))
            for cat in sorted(groups):
                parent = QTreeWidgetItem([cat])
                parent.setData(0, ROLE_TYPE, TYPE_CAT)
                self.add_tree.addTopLevelItem(parent)
                for action_id, text in groups[cat]:
                    leaf = QTreeWidgetItem([text])
                    leaf.setData(0, ROLE_TOKEN, action_id)
                    leaf.setData(0, ROLE_TYPE, TYPE_CMD)
                    parent.addChild(leaf)
        elif src.key == "palette":
            self._populate_palette_tree(needle)
        else:
            current_tag = None
            if src.key == "brush":
                t = self.tag_filter.currentText()
                current_tag = t if (t and t != "All tags") else None
                if current_tag is not None:
                    self._ensure_tags_loaded()
            for payload, text in src.enum_fn(self, needle):
                if src.key == "brush" and current_tag is not None:
                    tags = self._preset_tags.get(payload)
                    if not tags or current_tag not in tags:
                        continue
                leaf = QTreeWidgetItem([text])
                leaf.setData(0, ROLE_TOKEN, payload)
                leaf.setData(0, ROLE_TYPE, src.item_type)
                if src.key == "brush":
                    icon = self._brush_pixmap_icon(payload)
                    if icon is not None:
                        leaf.setIcon(0, icon)
                self.add_tree.addTopLevelItem(leaf)
        self.add_tree.expandAll()

    def _sync_items_order(self, *_):
        items = self._cur_items()
        by_tok = {}
        for it in items:
            t = self._token_of(it)
            if t is not None and t not in by_tok:
                by_tok[t] = it
        new_order = []
        for i in range(self.items_list.count()):
            t = self.items_list.item(i).data(ROLE_TOKEN)
            if t in by_tok:
                new_order.append(by_tok[t])
        if len(new_order) == len(items):
            items[:] = new_order

    def _on_item_double_click(self, *_):
        entry = self.items_list.currentItem()
        if entry is None:
            return
        if entry.data(ROLE_TYPE) == TYPE_MENU:
            self._enter_submenu()
        else:
            self._rename_item()

    def _enter_submenu(self):
        idx = self.items_list.currentRow()
        if idx < 0 or not self._cur_items():
            return
        it = self._cur_items()[idx]
        if isinstance(it, dict) and it.get("name") is not None:
            self.path.append(it)
            self._render_current()

    def _add_selected(self):
        entry = self.add_tree.currentItem()
        if entry is None or not self.path:
            return
        # Category headers are not addable.
        if entry.data(0, ROLE_TYPE) == TYPE_CAT:
            return
        src = self._current_source()
        if src is None:
            return
        src.add_fn(self, entry.data(0, ROLE_TOKEN))
        self._reload_available()  # refresh dedup after adding

    def _on_tree_double_click(self, item, _column):
        # Double-click a leaf to add it; a category header just expands/collapses.
        if item is not None and item.data(0, ROLE_TYPE) != TYPE_CAT:
            self._add_selected()

    def _add_submenu(self):
        if not self.path:
            return
        name, ok = QInputDialog.getText(self, "Add Submenu", "Submenu name:")
        if not ok or not name.strip():
            return
        self._cur_items().append({"name": name.strip(), "shortcut": "", "items": []})
        self._render_items()

    def _add_separator(self):
        if not self.path:
            return
        self._cur_items().append({"sep": True, "label": ""})
        self._render_items()

    def _add_header(self):
        if not self.path:
            return
        title, ok = QInputDialog.getText(self, "Add Header", "Header text:")
        if ok and title.strip():
            t = title.strip()
            self._cur_items().append({"header": t, "label": t})
            self._render_items()

    def _add_toggle(self):
        if not self.path:
            return
        if self._checkable_actions is None:
            checkable = []
            try:
                for a in Krita.instance().actions():
                    try:
                        if a.isCheckable() and a.objectName():
                            label = a.text().replace("&", "").strip() or a.objectName()
                            checkable.append((a.objectName(), label))
                    except Exception:
                        continue
            except Exception:
                checkable = []
            checkable.sort(key=lambda x: x[1].lower())
            self._checkable_actions = checkable
        checkable = self._checkable_actions
        if not checkable:
            QMessageBox.information(self, "Add Toggle", "No checkable Krita actions found.")
            return
        items = ["%s  (%s)" % (label, name) for name, label in checkable]
        sel, ok = QInputDialog.getItem(self, "Add Toggle",
                                       "Pick a checkable action (✓ shows its state):",
                                       items, 0, False)
        if ok and sel:
            name = sel.rsplit("  (", 1)[-1].rstrip(")")
            self._cur_items().append({"toggle": name,
                                      "label": dict(checkable).get(name, name)})
            self._render_items()

    def _remove_selected(self):
        row = self.items_list.currentRow()
        if row < 0 or not self._cur_items():
            return
        self._cur_items().pop(row)
        self._render_items()
        self._reload_available()

    def _rename_item(self):
        row = self.items_list.currentRow()
        items = self._cur_items()
        if row < 0 or not items:
            return
        cur = items[row]
        if isinstance(cur, dict) and cur.get("name") is not None:
            new_name, ok = QInputDialog.getText(
                self, "Rename Submenu", "Submenu name:", text=cur["name"])
            if ok and new_name.strip():
                cur["name"] = new_name.strip()
                self._render_items()
                self._render_path_bar()
            return
        if isinstance(cur, dict) and cur.get("blend") is not None:
            new_label, ok = QInputDialog.getText(
                self, "Rename Blend Mode", "Display name:", text=cur.get("label", ""))
            if ok:
                cur["label"] = new_label.strip()
                self._render_items()
            return
        if isinstance(cur, dict) and cur.get("brush") is not None:
            new_label, ok = QInputDialog.getText(
                self, "Rename Brush", "Display name:", text=cur.get("label", ""))
            if ok:
                cur["label"] = new_label.strip()
                self._render_items()
            return
        # command: set custom label
        default = (cur.get("label", "") if isinstance(cur, dict) else "") \
            or self._catalog.get(cur["id"] if isinstance(cur, dict) else cur,
                                 cur["id"] if isinstance(cur, dict) else cur)
        new_label, ok = QInputDialog.getText(
            self, "Rename Item",
            "Custom name (leave empty to use Krita's default):",
            text=default)
        if ok:
            if isinstance(cur, str):
                items[row] = {"id": cur, "label": new_label.strip()}
            else:
                cur["label"] = new_label.strip()
            self._render_items()

    # ---------- Export / import ----------
    def _export_config(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Config", "", "CMM Config (*.json)")
        if not path:
            return
        data = build_config_dict(self.popup_shortcut, self.lists)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "Exported", f"Config exported to\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))

    def _import_config(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "CMM Config (*.json)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.popup_shortcut, self.lists = parse_config_dict(data)
        except Exception as e:
            QMessageBox.warning(self, "Import failed", str(e))
            return
        self.current = 0
        self.path = [self.lists[self.current]] if self.lists else []
        self._reload_sidebar()
        self._render_current()
        self._update_left_shortcut()

    # ---------- Conflict check ----------
    def _check_conflicts(self):
        used = {}
        for lst in self.lists:
            key = lst.get("shortcut", "")
            if not key:
                continue
            if key in used:
                return (f"Lists \u201c{used[key]}\u201d and \u201c{lst['name']}\u201d both "
                        f"use shortcut \u201c{key}\u201d.")
            used[key] = lst["name"]
            if key in self._krita_shortcuts:
                return (f"Shortcut \u201c{key}\u201d for list \u201c{lst['name']}\u201d "
                        f"is already used by a Krita action.")
        return None

    # ---------- Save ----------
    def accept(self):
        conflict = self._check_conflicts()
        if conflict:
            QMessageBox.warning(self, "Shortcut conflict", conflict)
        save_config(self.popup_shortcut, self.lists)
        notify_refresh()
        super().accept()
