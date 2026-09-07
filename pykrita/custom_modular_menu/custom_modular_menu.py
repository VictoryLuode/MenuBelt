"""Custom Modular Menu (CMM) - core: builds three synchronised multi-list entries.

1. Tools > Custom Modular Menu submenu (lists -> items)
2. Cursor popup menu (reuses the same QMenu, bound to a shortcut)
3. Edit dialog (saving changes refreshes every entry automatically)
"""

from krita import Extension, Krita
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import QMenu

from .config import load_lists, notify_refresh, register_refresh


class ListMenuExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        # One entry per window: {window, root_action, menu}
        self._windows = []
        register_refresh(self._rebuild_all)

    def setup(self):
        pass

    def createActions(self, window):
        # Trigger (keyboard bound, lives in Keyboard Shortcuts, hidden from menus)
        popup_action = window.createAction(
            "custom_modular_menu_popup", "Pop Up Custom List", "")
        popup_action.triggered.connect(self.pop_menu)

        # Editor action (shown as a footer item of the Tools submenu)
        edit_action = window.createAction(
            "custom_modular_menu_edit", "Edit Custom List", "")
        edit_action.triggered.connect(self.open_editor)

        # Tools > Custom Modular Menu root
        root_action = window.createAction(
            "custom_modular_menu", "Custom Modular Menu", "tools")
        menu = QMenu(window.qwindow())
        root_action.setMenu(menu)

        self._windows.append({
            "window": window,
            "root_action": root_action,
            "menu": menu,
            "edit_action": edit_action,
        })
        self._rebuild(window)

    # ---------- Build / refresh ----------
    def _rebuild_all(self):
        for entry in self._windows:
            self._rebuild(entry["window"])

    def _rebuild(self, window):
        """Rebuild the Tools>Custom Modular Menu submenu from current config."""
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

    # ---------- Behaviour ----------
    def pop_menu(self, *_):
        """Open the same multi-list menu under the cursor of the active window."""
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
        from .dialog import ListMenuDialog  # lazy import to avoid circular dependency
        dlg = ListMenuDialog()
        # dialog.accept() already calls notify_refresh()
        dlg.exec_()


# -- Registration (runs when pykrita loads the package) --
Krita.instance().addExtension(ListMenuExtension(Krita.instance()))
