"""Custom Modular Menu (CMM) - multi-list editor dialog.

Supports nested menus, custom-named commands, and Python script items. Provides
a live preview pane, shortcut conflict detection, and config export/import.
"""

import json

from krita import Krita
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
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
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from .config import (
    build_config_dict,
    catalog_actions,
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
TYPE_SCRIPT = "script"


class ListMenuDialog(QDialog):
    """Multi-menu editor with nested submenu navigation + live preview."""

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

        self._build_ui()
        self._reload_sidebar()
        self._render_current()
        self._update_left_shortcut()
        self._render_preview()

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
        cm = QVBoxLayout(current_box)
        header_row = QHBoxLayout()
        self.crumb_row = QHBoxLayout()
        header_row.addLayout(self.crumb_row)
        header_row.addStretch()
        header_row.addWidget(QLabel("Popup shortcut:"))
        self.list_sc_edit = QKeySequenceEdit()
        self.list_sc_edit.setToolTip("Press a key combination to pop this menu at the cursor.")
        self.list_sc_edit.keySequenceChanged.connect(self._on_list_shortcut_changed)
        header_row.addWidget(self.list_sc_edit, 1)
        sc_clear = QPushButton("Clear")
        sc_clear.clicked.connect(self._clear_list_shortcut)
        header_row.addWidget(sc_clear)
        cm.addLayout(header_row)
        self.items_list = QListWidget()
        self.items_list.itemDoubleClicked.connect(self._on_item_double_click)
        self.items_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.items_list.setDefaultDropAction(Qt.MoveAction)
        self.items_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_list.model().rowsMoved.connect(self._sync_items_order)
        cm.addWidget(self.items_list)
        btn_row = QHBoxLayout()
        for label, slot in (("Add Submenu", self._add_submenu),
                            ("Add Script", self._add_script),
                            ("Rename", self._rename_item),
                            ("Remove", self._remove_selected)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        cm.addLayout(btn_row)
        body.addWidget(current_box, 2)

        # Available actions (pick commands to add)
        avail_box = QGroupBox("Available actions")
        av = QVBoxLayout(avail_box)
        search_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search name or id…")
        self.search_box.textChanged.connect(self._reload_available)
        search_row.addWidget(self.search_box)
        av.addLayout(search_row)
        self.avail_list = QListWidget()
        self.avail_list.itemDoubleClicked.connect(lambda _i: self._add_selected())
        av.addWidget(self.avail_list)
        add_btn = QPushButton("Add")
        add_btn.setToolTip("Add the selected action (or double-click it)")
        add_btn.clicked.connect(self._add_selected)
        av.addWidget(add_btn)
        body.addWidget(avail_box, 2)

        # Preview (right): only the current menu
        preview_box = QGroupBox("Preview")
        pv = QVBoxLayout(preview_box)
        self.preview_tree = QTreeWidget()
        self.preview_tree.setHeaderHidden(True)
        self.preview_tree.setMinimumWidth(180)
        pv.addWidget(self.preview_tree)
        body.addWidget(preview_box, 1)

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

    def _render_path_bar(self):
        while self.crumb_row.count():
            it = self.crumb_row.takeAt(0).widget()
            if it is not None:
                it.deleteLater()
        for i, node in enumerate(self.path):
            if i > 0:
                self.crumb_row.addWidget(QLabel("▸"))
            btn = QPushButton(node.get("name", "?"))
            btn.setFlat(True)
            btn.clicked.connect(lambda _=False, d=i: self._go_to_depth(d))
            self.crumb_row.addWidget(btn)
        self.crumb_row.addStretch()

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
            self.sidebar.addItem(item)
        if 0 <= self.current < self.sidebar.count():
            self.sidebar.setCurrentRow(self.current)
        self.sidebar.blockSignals(False)

    def _on_switch_list(self, row):
        if 0 <= row < len(self.lists):
            self.current = row
            self.path = [self.lists[row]]
            self._update_left_shortcut()
            self._render_current()

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
        self._render_preview()

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
        self._render_preview()

    def _rename_list(self):
        if not self.lists:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename List", "New name:", text=self.lists[self.current]["name"])
        if ok and new_name.strip():
            self.lists[self.current]["name"] = new_name.strip()
            self._reload_sidebar()
            self._render_path_bar()
            self._render_preview()

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
            self._render_preview()

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
            if it.get("script") is not None:
                return "script:" + (it.get("label", "") or "")
            if it.get("name") is not None:
                return it["name"]
        return None

    def _render_current(self):
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
                elif it.get("script") is not None:
                    typ, text = TYPE_SCRIPT, f"[script] {it.get('label', 'Script')}"
                elif it.get("name") is not None:
                    typ, text = TYPE_MENU, f"\u25b8 {it['name']}"
            entry = QListWidgetItem(text)
            entry.setData(ROLE_INDEX, idx)
            entry.setData(ROLE_TOKEN, token)
            entry.setData(ROLE_TYPE, typ)
            entry.setToolTip(f"{text}  [{token}]")
            font = QFont()
            font.setItalic(typ != TYPE_MENU)
            entry.setFont(font)
            self.items_list.addItem(entry)
        self._reload_available()
        self._render_preview()

    def _existing_cmd_ids(self):
        out = set()
        for it in self._cur_items():
            if isinstance(it, str):
                out.add(it)
            elif isinstance(it, dict) and it.get("id"):
                out.add(it["id"])
        return out

    def _reload_available(self):
        self.avail_list.clear()
        needle = self.search_box.text().strip().lower()
        existing = self._existing_cmd_ids()
        for action_id, text in self._catalog.items():
            if needle and needle not in text.lower() and needle not in action_id.lower():
                continue
            if action_id in existing:
                continue
            entry = QListWidgetItem(f"{text}   [{action_id}]")
            entry.setData(ROLE_TOKEN, action_id)
            self.avail_list.addItem(entry)

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
        self._render_preview()

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
        entry = self.avail_list.currentItem()
        if entry is None or not self.path:
            return
        action_id = entry.data(ROLE_TOKEN)
        if action_id not in self._existing_cmd_ids():
            self._cur_items().append({"id": action_id, "label": ""})
            self._render_items()

    def _add_submenu(self):
        if not self.path:
            return
        name, ok = QInputDialog.getText(self, "Add Submenu", "Submenu name:")
        if not ok or not name.strip():
            return
        self._cur_items().append({"name": name.strip(), "shortcut": "", "items": []})
        self._render_items()

    def _add_script(self):
        if not self.path:
            return
        name, ok = QInputDialog.getText(self, "Add Script", "Script name:")
        if not ok or not name.strip():
            return
        code, ok2 = QInputDialog.getMultiLineText(
            self, "Add Script", "Python code (runs when clicked; Krita available as 'krita'/'app'):")
        if ok2 and code.strip():
            self._cur_items().append({"script": code, "label": name.strip()})
            self._render_items()

    def _remove_selected(self):
        row = self.items_list.currentRow()
        if row < 0 or not self._cur_items():
            return
        self._cur_items().pop(row)
        self._render_items()

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
        if isinstance(cur, dict) and cur.get("script") is not None:
            new_label, ok = QInputDialog.getText(
                self, "Rename Script", "Script name:", text=cur.get("label", ""))
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

    # ---------- Live preview ----------
    def _render_preview(self):
        """Preview only the currently selected menu (with its nested submenus)."""
        self.preview_tree.clear()
        node = self._cur_menu()
        if node.get("name"):
            top = QTreeWidgetItem([node["name"]])
            self.preview_tree.addTopLevelItem(top)
            self._preview_fill(top, node)
        self.preview_tree.expandAll()

    def _preview_fill(self, parent_item, node):
        for entry in node.get("items", []):
            if isinstance(entry, str):
                parent_item.addChild(QTreeWidgetItem([self._catalog.get(entry, entry)]))
            elif isinstance(entry, dict):
                if entry.get("id"):
                    text = entry.get("label", "") or self._catalog.get(entry["id"], entry["id"])
                    parent_item.addChild(QTreeWidgetItem([text]))
                elif entry.get("script") is not None:
                    parent_item.addChild(QTreeWidgetItem(
                        ["⚙ " + (entry.get("label", "Script") or "Script")]))
                elif entry.get("name") is not None:
                    child = QTreeWidgetItem([entry["name"]])
                    parent_item.addChild(child)
                    self._preview_fill(child, entry)

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
        self._render_preview()

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
