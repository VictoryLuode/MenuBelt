"""Custom Modular Menu (CMM) - multi-list editor dialog:
manage list names, actions/order inside each list, per-list popup shortcuts,
and per-item custom names."""

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


class ListMenuDialog(QDialog):
    """Multi-list editor. Left = list management, right = actions/order + shortcut."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Custom Modular Menu")
        self.setMinimumSize(820, 540)
        self._apply_default_size()

        self._catalog = dict(catalog_actions())
        self.popup_shortcut, self.lists = load_config()  # (str, [{name, shortcut, items}])
        self.current = 0
        self._loading_sc = False

        self._build_ui()
        self._reload_sidebar()
        self._render_items()

    # ---------- Dialog size (remembered across sessions) ----------
    def _apply_default_size(self):
        """Open big enough by default; restore the last-used size if any."""
        try:
            w = Krita.instance().readSetting("custom_modular_menu", "dialog_width", "")
            h = Krita.instance().readSetting("custom_modular_menu", "dialog_height", "")
            if w and h:
                self.resize(int(w), int(h))
                return
        except Exception:
            pass
        # Sensible default based on the available screen
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
        """Save the dialog size on any close (OK / Cancel / Esc / X)."""
        self._persist_size()
        super().done(result)

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        # Whole-menu popup shortcut
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

        # Left: list management
        left_box = QGroupBox("Lists")
        left = QVBoxLayout(left_box)
        self.sidebar = QListWidget()
        self.sidebar.currentRowChanged.connect(self._on_switch_list)
        # Drag-and-drop reorder
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
        left_box.setMinimumWidth(180)
        body.addWidget(left_box, 1)

        # Right: selected list
        right_box = QGroupBox()
        right = QVBoxLayout(right_box)
        self.list_title = QLabel()
        right.addWidget(self.list_title)

        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel("Popup shortcut:"))
        self.list_sc_edit = QKeySequenceEdit()
        self.list_sc_edit.setToolTip("Press a key combination to pop this list at the cursor.")
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
        add_btn.setToolTip("Add the selected action to the current list (or double-click it)")
        add_btn.clicked.connect(self._add_selected)
        avail_col.addWidget(add_btn)
        editor.addLayout(avail_col, 1)

        items_col = QVBoxLayout()
        items_col.addWidget(QLabel(
            "Current items (drag to reorder, double-click to rename):"))
        self.items_list = QListWidget()
        self.items_list.itemDoubleClicked.connect(lambda _i: self._rename_item())
        # Drag-and-drop reorder
        self.items_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.items_list.setDefaultDropAction(Qt.MoveAction)
        self.items_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.items_list.model().rowsMoved.connect(self._sync_items_order)
        items_col.addWidget(self.items_list)
        btn_row = QHBoxLayout()
        for label, slot in (("Rename", self._rename_item),
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

    # ---------- List management ----------
    def _reload_sidebar(self):
        self.sidebar.blockSignals(True)
        self.sidebar.clear()
        for lst in self.lists:
            item = QListWidgetItem(lst["name"])
            item.setData(Qt.UserRole, lst["name"])
            self.sidebar.addItem(item)
        if 0 <= self.current < self.sidebar.count():
            self.sidebar.setCurrentRow(self.current)
        self.sidebar.blockSignals(False)
        self._update_labels()

    def _on_switch_list(self, row):
        if 0 <= row < len(self.lists):
            self.current = row
            self._render_items()
            self._update_labels()

    def _sync_lists_order(self, *_):
        """After a drag reorder of the sidebar, reorder the lists to match."""
        by_name = {lst["name"]: lst for lst in self.lists}
        new_order = []
        for i in range(self.sidebar.count()):
            name = self.sidebar.item(i).data(Qt.UserRole)
            if name in by_name:
                new_order.append(by_name[name])
        if len(new_order) == len(self.lists):
            self.lists[:] = new_order
        self.current = max(0, self.sidebar.currentRow())
        if 0 <= self.current < len(self.lists):
            self._render_items()
            self._update_labels()

    def _update_labels(self):
        self.list_title.setText(f"Current list: {self._name()}")
        # reflect the selected list's shortcut into the key editor (guarded)
        self._loading_sc = True
        self.list_sc_edit.setKeySequence(self._cur_shortcut())
        self._loading_sc = False

    def _name(self):
        return self.lists[self.current]["name"] if self.lists else ""

    def _cur_shortcut(self):
        return self.lists[self.current].get("shortcut", "") if self.lists else ""

    def _new_list(self):
        name, ok = QInputDialog.getText(self, "New List", "List name:")
        if not ok or not name.strip():
            return
        self.lists.append({"name": name.strip(), "shortcut": "", "items": []})
        self.current = len(self.lists) - 1
        self._reload_sidebar()
        self._render_items()

    def _rename_list(self):
        if not self.lists:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename List", "New name:", text=self._name())
        if ok and new_name.strip():
            self.lists[self.current]["name"] = new_name.strip()
            self._reload_sidebar()

    def _delete_list(self):
        if not self.lists:
            return
        if QMessageBox.question(
                self, "Delete List", f"Delete the list \u201c{self._name()}\u201d?") == QMessageBox.Yes:
            self.lists.pop(self.current)
            self.current = max(0, min(self.current, len(self.lists) - 1))
            self._reload_sidebar()
            self._render_items()

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

    # ---------- Selected list items ----------
    def _cur_items(self):
        return self.lists[self.current]["items"] if self.lists else []

    def _sync_items_order(self, *_):
        """After a drag reorder, sync the config list order to the widget order."""
        items = self._cur_items()
        by_id = {it["id"]: it for it in items}
        new_order = []
        for i in range(self.items_list.count()):
            entry = self.items_list.item(i)
            aid = entry.data(Qt.UserRole + 1)
            if aid in by_id:
                new_order.append(by_id[aid])
        if new_order != items:
            items[:] = new_order

    def _render_items(self):
        self.items_list.clear()
        items = self._cur_items()
        for idx, it in enumerate(items):
            aid = it["id"]
            label = it.get("label", "")
            text = label or self._catalog.get(aid, aid)
            entry = QListWidgetItem(text)
            entry.setData(Qt.UserRole, idx)
            entry.setData(Qt.UserRole + 1, aid)
            entry.setToolTip(f"{text}  [{aid}]")
            font = QFont()
            font.setItalic(bool(label))  # custom-named items shown italic
            entry.setFont(font)
            self.items_list.addItem(entry)
        self._reload_available()

    def _reload_available(self):
        self.avail_list.clear()
        needle = self.search_box.text().strip().lower()
        existing = {it["id"] for it in self._cur_items()}
        for action_id, text in self._catalog.items():
            if needle and needle not in text.lower() and needle not in action_id.lower():
                continue
            if action_id in existing:
                continue  # hide already-added actions to avoid duplicates
            entry = QListWidgetItem(f"{text}   [{action_id}]")
            entry.setData(Qt.UserRole, action_id)
            self.avail_list.addItem(entry)

    def _add_selected(self):
        entry = self.avail_list.currentItem()
        if entry is None or not self.lists:
            return
        action_id = entry.data(Qt.UserRole)
        existing = {it["id"] for it in self._cur_items()}
        if action_id not in existing:
            self.lists[self.current]["items"].append({"id": action_id, "label": ""})
            self._render_items()

    def _remove_selected(self):
        row = self.items_list.currentRow()
        if row < 0 or not self.lists:
            return
        self._cur_items().pop(row)
        self._render_items()

    def _move_up(self):
        row = self.items_list.currentRow()
        items = self._cur_items()
        if row <= 0 or not self.lists:
            return
        items[row], items[row - 1] = items[row - 1], items[row]
        self._render_items()
        self.items_list.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.items_list.currentRow()
        items = self._cur_items()
        if row < 0 or row >= len(items) - 1 or not self.lists:
            return
        items[row], items[row + 1] = items[row + 1], items[row]
        self._render_items()
        self.items_list.setCurrentRow(row + 1)

    def _rename_item(self):
        row = self.items_list.currentRow()
        if row < 0 or not self.lists:
            return
        items = self._cur_items()
        cur = items[row]
        default = cur.get("label", "") or self._catalog.get(cur["id"], cur["id"])
        new_label, ok = QInputDialog.getText(
            self, "Rename Item",
            "Custom name (leave empty to use Krita's default):",
            text=default)
        if ok:
            items[row]["label"] = new_label.strip()
            self._render_items()

    # ---------- Save ----------
    def accept(self):
        popup = self.popup_edit.keySequence().toString(QKeySequence.PortableText)
        save_config(popup, self.lists)
        notify_refresh()
        super().accept()
