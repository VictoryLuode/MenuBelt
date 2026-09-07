"""Quick List Menu — 核心：打造三处同步的多列表入口。

1. Tools > Quick List Menu 子菜单（列表→项）
2. 光标弹菜单（复用同一个 QMenu，绑定快捷键触发）
3. 编辑对话框（改完多列表配置后所有入口自动刷新）
"""

from krita import Extension, Krita
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QMenu

from .config import load_lists, notify_refresh, register_refresh


class ListMenuExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        # 每个窗口一套 {root_action, menu, edit_action}
        self._windows = []
        register_refresh(self._rebuild_all)

    def setup(self):
        pass

    def createActions(self, window):
        app = Krita.instance()

        # 触发器（键盘绑定，进快捷键编辑器，不在菜单里显示）
        popup_action = window.createAction(
            "quick_list_menu_popup", "弹出快捷列表菜单", "")
        popup_action.triggered.connect(self.pop_menu)

        # 编辑器 action（会作为 Tools>Quick List Menu 底部的一项显示）
        edit_action = window.createAction(
            "quick_list_menu_edit", "编辑快捷列表菜单…", "")
        edit_action.triggered.connect(self.open_editor)

        # Tools > Quick List Menu 根菜单
        root_action = window.createAction(
            "quick_list_menu", "Quick List Menu", "tools")
        menu = QMenu(window.qwindow())
        root_action.setMenu(menu)

        self._windows.append({
            "window": window,
            "root_action": root_action,
            "menu": menu,
            "edit_action": edit_action,
        })
        self._rebuild(window)

    # ---------- 构建 / 刷新 ----------
    def _rebuild_all(self):
        for entry in self._windows:
            self._rebuild(entry["window"])

    def _rebuild(self, window):
        """按当前配置重建某个窗口的 Tools>Quick List Menu 子菜单."""
        for entry in self._windows:
            if entry["window"] is not window:
                continue
            menu = entry["menu"]
            menu.clear()
            for lst in load_lists():
                sub = menu.addMenu(lst["name"])
                for action_id in lst["items"]:
                    try:
                        act = Krita.instance().action(action_id)
                    except RuntimeError:
                        act = None
                    if act is not None:
                        sub.addAction(act)
            menu.addSeparator()
            menu.addAction(entry["edit_action"])
            break

    # ---------- 行为 ----------
    def _parent_widget(self, window):
        try:
            return window.qwindow()
        except RuntimeError:
            return None

    def pop_menu(self, *_):
        """在当前活动窗口的光标处弹出同一个多列表菜单."""
        active = Krita.instance().activeWindow()
        if active is not None:
            try:
                active.qwindow()
            except RuntimeError:
                active = None
        for entry in self._windows:
            if active is not None and entry["window"] is active:
                entry["menu"].exec_(QCursor.pos())
                return
        if self._windows:
            self._windows[0]["menu"].exec_(QCursor.pos())

    def open_editor(self, *_):
        from .dialog import ListMenuDialog  # 延迟导入，避免循环依赖
        dlg = ListMenuDialog()
        # 保存时 dialog 内部会 notify_refresh()；这里仅在无窗口时兜底刷新
        dlg.exec_()


# —— 注册（pykrita 加载即生效）——
Krita.instance().addExtension(ListMenuExtension(Krita.instance()))
