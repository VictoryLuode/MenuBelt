"""Custom Modular Menu (CMM) - core: builds three synchronised multi-list entries
plus configurable dynamic shortcuts (QShortcut).

- Tools > Custom Modular Menu submenu (lists -> items)
- Cursor popup menu (reuses the same QMenu; bound to a dynamic shortcut)
- A dynamic shortcut per list (each list can pop on its own hotkey)
- Edit dialog (saving changes refreshes every entry + shortcuts automatically)
"""

from krita import Extension, Krita
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor, QKeySequence
from PyQt5.QtWidgets import QMenu, QShortcut

from .config import load_lists, load_popup_shortcut, notify_refresh, register_refresh


class ListMenuExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        # One entry per window: {window, root_action, menu}
        self._windows = []
        self._shortcuts = []   # QShortcut objects (kept alive to avoid GC)
        register_refresh(self._rebuild_all)

    def setup(self):
        pass

    def createActions(self, window):
        # Trigger action (whole-menu popup; can also be used via Krita shortcuts editor)
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
        self._register_shortcuts()

    # ---------- Build / refresh ----------
    def _rebuild_all(self):
        for entry in self._windows:
            self._rebuild(entry["window"])
        self._register_shortcuts()

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

    # ---------- Dynamic shortcuts ----------
    def _register_shortcuts(self):
        self._unregister_shortcuts()
        if not self._windows:
            return
        anchor = self._windows[-1]["window"]
        try:
            parent = anchor.qwindow()
        except RuntimeError:
            return

        popup = load_popup_shortcut()
        if popup:
            sc = QShortcut(QKeySequence(popup), parent)
            sc.setContext(Qt.ApplicationShortcut)
            sc.activated.connect(self.pop_menu)
            self._shortcuts.append(sc)

        for i, lst in enumerate(load_lists()):
            key = lst.get("shortcut", "")
            if key:
                sc = QShortcut(QKeySequence(key), parent)
                sc.setContext(Qt.ApplicationShortcut)
                sc.activated.connect(lambda i=i: self.pop_list(i))
                self._shortcuts.append(sc)

    def _unregister_shortcuts(self):
        for sc in self._shortcuts:
            try:
                sc.setParent(None)
                sc.deleteLater()
            except RuntimeError:
                pass
        self._shortcuts = []

    # ---------- Behaviour ----------
    def _active_menu(self):
        active = Krita.instance().activeWindow()
        if active is not None:
            try:
                active.qwindow()
            except RuntimeError:
                active = None
        for entry in self._windows:
            if active is not None and entry["window"] is active:
                return entry["menu"]
        return self._windows[0]["menu"] if self._windows else None

    def pop_menu(self, *_):
        """Open the whole multi-list menu under the cursor of the active window."""
        menu = self._active_menu()
        if menu is not None:
            menu.exec_(QCursor.pos())

    def pop_list(self, index):
        """Open only one list (given its index) as a cursor menu."""
        try:
            lst = load_lists()[index]
        except (IndexError, TypeError):
            return
        parent = self._active_window_widget()
        menu = QMenu(parent)
        for action_id in lst["items"]:
            try:
                act = Krita.instance().action(action_id)
            except RuntimeError:
                act = None
            if act is not None:
                menu.addAction(act)
        if menu.actions():
            menu.exec_(QCursor.pos())

    def _active_window_widget(self):
        active = Krita.instance().activeWindow()
        if active is not None:
            try:
                return active.qwindow()
            except RuntimeError:
                pass
        try:
            return self._windows[-1]["window"].qwindow()
        except (IndexError, RuntimeError):
            return None

    def open_editor(self, *_):
        from .dialog import ListMenuDialog  # lazy import to avoid circular dependency
        dlg = ListMenuDialog()
        # dialog.accept() already calls notify_refresh()
        dlg.exec_()


# -- Registration (runs when pykrita loads the package) --
Krita.instance().addExtension(ListMenuExtension(Krita.instance()))
