"""Custom Modular Menu (CMM) - Docker panel: multi-list actions as clickable
buttons, dockable / floatable like a toolbar."""

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
    """Display multi-list action buttons. Clicking one triggers the Krita action."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Custom Modular Menu")
        register_refresh(self.rebuild)
        self.rebuild()

    def canvasChanged(self, _canvas):
        pass

    def rebuild(self):
        """Rebuild the panel content from current config."""
        container = QWidget(self)
        outer = QVBoxLayout(container)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        header = QHBoxLayout()
        edit_btn = QPushButton("Edit…")
        edit_btn.setToolTip("Configure Custom Modular Menu")
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

            for item in lst["items"]:
                body.addWidget(self._make_button(item["id"], item.get("label", "")))

        body.addStretch()
        inner.setLayout(body)
        scroll.setWidget(inner)
        outer.addWidget(scroll)

        container.setLayout(outer)
        self.setWidget(container)

    def _make_button(self, action_id, label=""):
        act = None
        try:
            act = Krita.instance().action(action_id)
        except RuntimeError:
            act = None
        text = label or (act.text().replace("&", "").strip()
                         if act and act.text() else action_id)
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
        from .dialog import ListMenuDialog  # lazy import to avoid circular dependency
        dlg = ListMenuDialog(self)
        dlg.exec_()
        # dialog.accept() already calls notify_refresh(); this is a fallback
        notify_refresh()


# -- Docker factory registration (runs when pykrita loads the package) --
_docker_factory = DockWidgetFactory(
    "custom_modular_menu_docker", DockWidgetFactoryBase.DockRight, ListMenuDocker)
Krita.instance().addDockWidgetFactory(_docker_factory)
