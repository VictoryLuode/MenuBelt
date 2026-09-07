"""Custom Modular Menu (CMM) - multi-list editor dialog.

Supports nested menus: a menu holds commands and/or submenus (arbitrary depth).
Left = top-level lists (drag to reorder), right = current menu's items with a
breadcrumb to navigate into submenus.
"""

from krita import Krita
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
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
    QVBoxLayout,
)

from .config import catalog_actions, load_config, notify_refresh, save_config

ROLE_INDEX = Qt.UserRole
ROLE_TOKEN = Qt.UserRole + 1
ROLE_TYPE = Qt.UserRole + 2
TYPE_CMD = "cmd"
TYPE_MENU = "menu"


class ListMenuDialog(QDialog):
    """Multi-menu editor with nested submenu navigation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Modular Menu")
        self.setMinimumSize(820, 540)
        self._apply_default_size()

        self._catalog = dict(catalog_actions())
        self.popup_shortcut, self.lists = load_config()
        # path = reference chain to the current menu node; path[0] is a top-level list
        self.current = 0
        self.path = [self.lists[self.current]] if self.lists else []
        self._loading_sc = False

        self._build_ui()
        self._reload_sidebar()
        self._render_current()

    # ---------- Dialog size (remembered across sessions) ----------
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
            self.resize(max(880, int(geo.width() * 0.55)), max(540, int(geo.height() * 0.60)))
        except Exception:
            self.resize(920, 580)

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

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        popup_box = QGroupBox("Menu popup shortcut (whole list menu)")
        popup_row = QHBoxLayout(popup_box)
        self.popup_edit = QKeySequenceEdit(self.popup_shortcut)
        self.popup_edit.setToolTip("Press a key combination here to bind the whole menu popup.")
        popup_row.addWidget(self.popup_edit, 1)
        popup_clear = QPushButton("Clear")
        popup_clear.clicked.connect(lambda: self.popup_edit.setKeySequence(QKeySequence("")))
        popup_row.addWidget(popup_clear)
        root.addWidget(popup_box)

        body = QHBoxLayout()
        body.setSpacing(12)

        # Left: top-level lists
        left_box = QGroupBox("Lists")
        left = QVBoxLayout(left_box)
        self.sidebar = QListWidget()
        self.sidebar.currentRowChanged.connect(self._on_switch_list)
        self.sidebar.setDragDropMode(QAbstractItemView.InternalMove)
        self.sidebar.setDefaultDropAction(Qt.MoveAction)
        self.sidebar.setSelectionMode(QAbstractItemView.SingleSelection)
        self.sidebar.model().rowsMoved.connect(self._sync_lists_order)
        left.addWidget(self.sidebar)
        for label, slot in (("New List", self._new_list),
                            ("Rename", self._rename_list),
                            ("Delete", self._delete_list)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            left.addWidget(b)
        left_box.setMinimumWidth(190)
        body.addWidget(left_box, 1)

        # Right: current menu
        right_box = QGroupBox()
        right = QVBoxLayout(right_box)

        # Breadcrumb
        self.crumb_row = QHBoxLayout()
        right.addLayout(self.crumb_row)

        self.list_title = QLabel()
        right.addWidget(self.list_title)

        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel("Popup shortcut:"))
        self.list_sc_edit = QKeySequenceEdit()
        self.list_sc_edit.setToolTip("Press a key combination to pop this menu at the cursor.")
        self.list_sc_edit.keySequenceChanged.connect(self._on_list_shortcut_changed)
        sc_row.addWidget(self.list_sc_edit, 1)
        sc_clear = QPushButton("Clear")
        sc_clear.clicked.connect(self._clear_list_shortcut)
        sc_row.addWidget(sc_clear)
        right.addLayout(sc_row)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Available actions:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search name or id…")
        self.search_box.textChanged.connect(self._reload_available)
        search_row.addWidget(self.search_box)
        right.addLayout(search_row)

        editor = QHBoxLayout()
        editor.setSpacing(8)

        avail_col = QVBoxLayout()
        self.avail_list = QListWidget()
        self.avail_list.itemDoubleClicked.connect(lambda _i: self._add_selected())
        avail_col.addWidget(self.avail_list)
        add_btn = QPushButton("Add →")
        add_btn.setToolTip("Add the selected action to the current menu (or double-click it)")
        add_btn.clicked.connect(self._add_selected)
        avail_col.addWidget(add_btn)
        editor.addLayout(avail_col, 1)

        items_col = QVBoxLayout()
        items_col.addWidget(QLabel(
            "Current items (drag to reorder, double-click a submenu to enter, cmd to rename):"))
        self.items_list = QListWidget()
        self.items_list.itemDoubleClicked.connect(self._on_item_double_click)
        self.items_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.items_list.setDefaultDropAction(Qt.MoveAction)
        self.items_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_list.model().rowsMoved.connect(self._sync_items_order)
        items_col.addWidget(self.items_list)
        btn_row = QHBoxLayout()
        for label, slot in (("Add Submenu", self._add_submenu),
                            ("Rename", self._rename_item),
                            ("Up", self._move_up),
                            ("Down", self._move_down),
                            ("Remove", self._remove_selected)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        items_col.addLayout(btn_row)
        editor.addLayout(items_col, 1)

        right.addLayout(editor)
        body.addWidget(right_box, 3)

        root.addLayout(body)

        bottom = QHBoxLayout()
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

    def _cur_shortcut(self):
        return self._cur_menu().get("shortcut", "")

    def _render_path_bar(self):
        while self.crumb_row.count():
            it = self.crumb_row.takeAt(0).widget()
            if it is not None:
                it.deleteLater()
        for i, node in enumerate(self.path):
            if i > 0:
                sep = QLabel("▸")
                self.crumb_row.addWidget(sep)
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

    def _new_list(self):
        name, ok = QInputDialog.getText(self, "New List", "List name:")
        if not ok or not name.strip():
            return
        self.lists.append({"name": name.strip(), "shortcut": "", "items": []})
        self.current = len(self.lists) - 1
        self.path = [self.lists[self.current]]
        self._reload_sidebar()
        self._render_current()

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

    # ---------- Shortcut ----------
    def _on_list_shortcut_changed(self, seq):
        if self._loading_sc or not self.path:
            return
        self._cur_menu()["shortcut"] = seq.toString(QKeySequence.PortableText)

    def _clear_list_shortcut(self):
        if not self.path:
            return
        self._cur_menu()["shortcut"] = ""
        self._loading_sc = True
        self.list_sc_edit.setKeySequence(QKeySequence(""))
        self._loading_sc = False

    # ---------- Current menu items ----------
    def _render_current(self):
        self.list_title.setText(f"Current list: {self._name()}")
        self._loading_sc = True
        self.list_sc_edit.setKeySequence(self._cur_shortcut())
        self._loading_sc = False
        self._render_path_bar()
        self._render_items()

    def _render_items(self):
        items = self._cur_items()
        self.items_list.clear()
        for idx, it in enumerate(items):
            if isinstance(it, str):
                # bare command
                text = self._catalog.get(it, it)
                token, typ = it, TYPE_CMD
            elif isinstance(it, dict) and it.get("id"):
                aid = it["id"]
                label = it.get("label", "")
                text = label or self._catalog.get(aid, aid)
                token, typ = aid, TYPE_CMD
            elif isinstance(it, dict) and it.get("name") is not None:
                text = f"\u25b8 {it['name']}"   # ▸ submenu marker
                token, typ = it["name"], TYPE_MENU
            else:
                continue
            entry = QListWidgetItem(text)
            entry.setData(ROLE_INDEX, idx)
            entry.setData(ROLE_TOKEN, token)
            entry.setData(ROLE_TYPE, typ)
            entry.setToolTip(f"{text}  [{token}]")
            font = QFont()
            font.setItalic(typ == TYPE_CMD and isinstance(it, dict) and bool(it.get("label")))
            entry.setFont(font)
            self.items_list.addItem(entry)
        self._reload_available()

    def _reload_available(self):
        self.avail_list.clear()
        needle = self.search_box.text().strip().lower()
        existing = {it["id"] if isinstance(it, dict) and it.get("id") else it
                    for it in self._cur_items() if isinstance(it, (str, dict))}
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

        def token_of(it):
            if isinstance(it, str):
                return it
            if isinstance(it, dict):
                if it.get("id"):
                    return it["id"]
                if it.get("name") is not None:
                    return it["name"]
            return None

        by_token = {}
        for it in items:
            t = token_of(it)
            if t is not None and t not in by_token:
                by_token[t] = it
        new_order = []
        for i in range(self.items_list.count()):
            entry = self.items_list.item(i)
            t = entry.data(ROLE_TOKEN)
            if t in by_token:
                new_order.append(by_token[t])
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
        entry = self.avail_list.currentItem()
        if entry is None or not self.path:
            return
        action_id = entry.data(ROLE_TOKEN)
        existing = {it["id"] if isinstance(it, dict) and it.get("id") else it
                    for it in self._cur_items() if isinstance(it, (str, dict))}
        if action_id not in existing:
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

    def _remove_selected(self):
        row = self.items_list.currentRow()
        if row < 0 or not self._cur_items():
            return
        self._cur_items().pop(row)
        self._render_items()

    def _move_up(self):
        row = self.items_list.currentRow()
        items = self._cur_items()
        if row <= 0 or not items:
            return
        items[row], items[row - 1] = items[row - 1], items[row]
        self._render_items()
        self.items_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.items_list.currentRow()
        items = self._cur_items()
        if row < 0 or row >= len(items) - 1 or not items:
            return
        items[row], items[row + 1] = items[row + 1], items[row]
        self._render_items()
        self.items_list.setCurrentRow(row + 1)

    def _rename_item(self):
        row = self.items_list.currentRow()
        items = self._cur_items()
        if row < 0 or not items:
            return
        cur = items[row]
        if isinstance(cur, dict) and cur.get("name") is not None:
            # submenu: rename the submenu
            new_name, ok = QInputDialog.getText(
                self, "Rename Submenu", "Submenu name:", text=cur["name"])
            if ok and new_name.strip():
                cur["name"] = new_name.strip()
                self._render_items()
                self._render_path_bar()
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

    # ---------- Save ----------
    def accept(self):
        popup = self.popup_edit.keySequence().toString(QKeySequence.PortableText)
        save_config(popup, self.lists)
        notify_refresh()
        super().accept()
