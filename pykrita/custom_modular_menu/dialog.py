"""Custom Modular Menu (CMM) - multi-list editor dialog:
manage list names, actions/order inside each list, and per-list popup shortcuts."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import (
    QDialog,
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
        self.resize(880, 560)

        self._catalog = dict(catalog_actions())
        self.popup_shortcut, self.lists = load_config()  # (str, [{name, shortcut, items}])
        self.current = 0
        self._loading_sc = False

        self._build_ui()
        self._reload_sidebar()
        self._render_items()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # Top: whole-menu popup shortcut
        popup_row = QHBoxLayout()
        popup_row.addWidget(QLabel("Menu popup shortcut (whole list menu):"))
        self.popup_edit = QKeySequenceEdit(self.popup_shortcut)
        self.popup_edit.setClearButtonEnabled(True)
        self.popup_edit.setToolTip("Press a key combination here to bind the whole menu popup.")
        popup_row.addWidget(self.popup_edit, 1)
        root.addLayout(popup_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        # Left: list management
        left = QVBoxLayout()
        left.addWidget(QLabel("Lists:"))
        self.sidebar = QListWidget()
        self.sidebar.currentRowChanged.connect(self._on_switch_list)
        left.addWidget(self.sidebar)
        for label, slot in (("New List", self._new_list),
                            ("Rename", self._rename_list),
                            ("Delete", self._delete_list)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            left.addWidget(b)
        body.addLayout(left, 1)

        # Right: selected list items
        right = QVBoxLayout()
        self.list_title = QLabel()
        right.addWidget(self.list_title)

        sc_row = QHBoxLayout()
        sc_row.addWidget(QLabel("Popup shortcut:"))
        self.list_sc_edit = QKeySequenceEdit()
        self.list_sc_edit.setClearButtonEnabled(True)
        self.list_sc_edit.setToolTip("Press a key combination to pop this list at the cursor.")
        self.list_sc_edit.keySequenceChanged.connect(self._on_list_shortcut_changed)
        sc_row.addWidget(self.list_sc_edit, 1)
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
        add_btn.clicked.connect(self._add_selected)
        avail_col.addWidget(add_btn)
        editor.addLayout(avail_col, 1)

        items_col = QVBoxLayout()
        items_col.addWidget(QLabel("Current items (order = menu order):"))
        self.items_list = QListWidget()
        items_col.addWidget(self.items_list)
        btn_row = QHBoxLayout()
        for label, slot in (("Up", self._move_up), ("Down", self._move_down),
                            ("Remove", self._remove_selected)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            btn_row.addWidget(b)
        items_col.addLayout(btn_row)
        editor.addLayout(items_col, 1)

        right.addLayout(editor)
        body.addLayout(right, 3)

        root.addLayout(body)

        bottom = QHBoxLayout()
        bottom.addStretch()
        ok = QPushButton("OK")
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

    # ---------- Selected list items ----------
    def _cur_items(self):
        return self.lists[self.current]["items"] if self.lists else []

    def _render_items(self):
        self.items_list.clear()
        for action_id in self._cur_items():
            text = self._catalog.get(action_id, action_id)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, action_id)
            item.setToolTip(f"{text}  [{action_id}]")
            self.items_list.addItem(item)
        self._reload_available()

    def _reload_available(self):
        self.avail_list.clear()
        needle = self.search_box.text().strip().lower()
        existing = self._cur_items()
        for action_id, text in self._catalog.items():
            if needle and needle not in text.lower() and needle not in action_id.lower():
                continue
            if action_id in existing:
                continue  # hide already-added actions to avoid duplicates
            item = QListWidgetItem(f"{text}   [{action_id}]")
            item.setData(Qt.UserRole, action_id)
            self.avail_list.addItem(item)

    def _add_selected(self):
        item = self.avail_list.currentItem()
        if item is None or not self.lists:
            return
        action_id = item.data(Qt.UserRole)
        if action_id not in self._cur_items():
            self.lists[self.current]["items"].append(action_id)
            self._render_items()

    def _remove_selected(self):
        row = self.items_list.currentRow()
        if row < 0 or not self.lists:
            return
        action_id = self.items_list.currentItem().data(Qt.UserRole)
        self.lists[self.current]["items"] = [
            x for x in self._cur_items() if x != action_id]
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

    # ---------- Save ----------
    def accept(self):
        popup = self.popup_edit.keySequence().toString(QKeySequence.PortableText)
        save_config(popup, self.lists)
        notify_refresh()
        super().accept()
