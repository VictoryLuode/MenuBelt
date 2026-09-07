"""Quick List Menu — Docker 面板：把多列表动作做成可点击按钮，可停靠/浮动当工具栏."""

from krita import DockWidget, DockWidgetFactory, DockWidgetFactoryBase, Krita
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .config import load_lists, notify_refresh, register_refresh


class ListMenuDocker(DockWidget):
    """显示多列表动作按钮。点按钮直接触发对应 Krita action."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Quick List Menu")
        register_refresh(self.rebuild)
        self.rebuild()

    def canvasChanged(self, _canvas):
        pass

    def rebuild(self):
        """从当前配置重建面板内容."""
        container = QWidget(self)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        header = QHBoxLayout()
        edit_btn = QPushButton("编辑列表…")
        edit_btn.setToolTip("配置快捷列表菜单")
        edit_btn.clicked.connect(self._open_editor)
        header.addWidget(edit_btn)
        header.addStretch()
        outer.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        body = QVBoxLayout(inner)
        body.setSpacing(6)
        body.setAlignment(Qt.AlignTop)

        for lst in load_lists():
            label = QLabel(lst["name"])
            label.setStyleSheet("font-weight: bold; color: #ddd;")
            body.addWidget(label)

            for action_id in lst["items"]:
                body.addWidget(self._make_button(action_id))

        body.addStretch()
        inner.setLayout(body)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        container.setLayout(outer)
        self.setWidget(container)

    def _make_button(self, action_id):
        act = None
        try:
            act = Krita.instance().action(action_id)
        except RuntimeError:
            act = None
        text = (act.text().replace("&", "").strip() if act and act.text()
                else action_id)
        btn = QPushButton(text)
        btn.setToolTip(f"{text}  [{action_id}]")
        if act is not None:
            icon = act.icon()
            if not icon.isNull():
                btn.setIcon(icon)
            try:
                btn.setEnabled(act.isEnabled())
            except RuntimeError:
                pass
        btn.setStyleSheet("QPushButton { text-align: left; padding: 3px 6px; }")
        btn.clicked.connect(lambda _=False, a=action_id: self._run(a))
        return btn

    def _run(self, action_id):
        try:
            act = Krita.instance().action(action_id)
        except RuntimeError:
            act = None
        if act is not None:
            act.trigger()

    def _open_editor(self):
        from .dialog import ListMenuDialog  # 延迟导入，避免循环依赖
        dlg = ListMenuDialog(self)
        dlg.exec_()
        # dialog.accept() 内已调用 notify_refresh()，这里兜底
        notify_refresh()


# —— 注册 docker（pykrita 加载即生效）——
# 注意：创建 factory 即触发实例化；实例里再 register_refresh(self.rebuild)
_docker_factory = DockWidgetFactory(
    "quick_list_menu_docker", DockWidgetFactoryBase.DockRight, ListMenuDocker)
Krita.instance().addDockWidgetFactory(_docker_factory)
