"""Quick List Menu — 多列表编辑对话框：管理列表名 + 每个列表包含的动作与顺序."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from .config import catalog_actions, load_lists, notify_refresh, save_lists


class ListMenuDialog(QDialog):
    """多列表编辑器。左侧=列表管理，右侧=当前列表的动作顺序."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑快捷列表菜单")
        self.resize(860, 540)

        self._catalog = dict(catalog_actions())
        self.lists = load_lists()          # [{name, items}]
        self.current = 0

        self._build_ui()
        self._reload_sidebar()
        self._render_items()

    # ---------- UI ----------
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)

        body = QHBoxLayout()
        body.setSpacing(12)

        # 左：列表管理
        left = QVBoxLayout()
        left.addWidget(QLabel("列表:"))
        self.sidebar = QListWidget()
        self.sidebar.currentRowChanged.connect(self._on_switch_list)
        left.addWidget(self.sidebar)
        for label, slot in (("新建列表", self._new_list),
                            ("重命名", self._rename_list),
                            ("删除列表", self._delete_list)):
            b = QPushButton(label)
            b.clicked.connect(slot)
            left.addWidget(b)
        body.addLayout(left, 1)

        # 右：当前列表项编辑
        right = QVBoxLayout()
        self.list_title = QLabel()
        right.addWidget(self.list_title)

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("可用动作:"))
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("搜索名称或 id…")
        self.search_box.textChanged.connect(self._reload_available)
        search_row.addWidget(self.search_box)
        right.addLayout(search_row)

        editor = QHBoxLayout()
        editor.setSpacing(8)

        avail_col = QVBoxLayout()
        self.avail_list = QListWidget()
        self.avail_list.itemDoubleClicked.connect(lambda _i: self._add_selected())
        avail_col.addWidget(self.avail_list)
        add_btn = QPushButton("添加 →")
        add_btn.clicked.connect(self._add_selected)
        avail_col.addWidget(add_btn)
        editor.addLayout(avail_col, 1)

        items_col = QVBoxLayout()
        items_col.addWidget(QLabel("当前列表项(顺序=菜单顺序):"))
        self.items_list = QListWidget()
        items_col.addWidget(self.items_list)
        btn_row = QHBoxLayout()
        for label, slot in (("↑", self._move_up), ("↓", self._move_down),
                            ("移除", self._remove_selected)):
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
        ok = QPushButton("确定")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(ok)
        bottom.addWidget(cancel)
        root.addLayout(bottom)

    # ---------- 列表管理 ----------
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
        self.list_title.setText(f"当前列表: {self._name()}")

    def _on_switch_list(self, row):
        if 0 <= row < len(self.lists):
            self.current = row
            self._render_items()
            self.list_title.setText(f"当前列表: {self._name()}")

    def _name(self):
        return self.lists[self.current]["name"] if self.lists else ""

    def _new_list(self):
        name, ok = QInputDialog.getText(self, "新建列表", "列表名称:")
        if not ok or not name.strip():
            return
        self.lists.append({"name": name.strip(), "items": []})
        self.current = len(self.lists) - 1
        self._reload_sidebar()
        self._render_items()

    def _rename_list(self):
        if not self.lists:
            return
        new_name, ok = QInputDialog.getText(
            self, "重命名列表", "新名称:", text=self._name())
        if ok and new_name.strip():
            self.lists[self.current]["name"] = new_name.strip()
            self._reload_sidebar()

    def _delete_list(self):
        if not self.lists:
            return
        if QMessageBox.question(
                self, "删除列表", f"确定删除列表「{self._name()}」?") == QMessageBox.Yes:
            self.lists.pop(self.current)
            self.current = max(0, min(self.current, len(self.lists) - 1))
            self._reload_sidebar()
            self._render_items()

    # ---------- 当前列表项 ----------
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
                continue  # 已添加的从候选里隐藏，避免重复
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

    # ---------- 保存 ----------
    def accept(self):
        save_lists(self.lists)
        notify_refresh()
        super().accept()
