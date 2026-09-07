"""Custom Modular Menu (CMM) - core: builds three synchronised multi-list entries
plus configurable shortcuts.

Shortcuts are implemented with a keyboard EVENT FILTER (not QShortcut), because
Krita's canvas/shortcut handling consumes key events before Qt's QShortcut system
sees them. The event-filter approach is the proven Krita pattern (used by the
shortcut_composer plugin).

- Tools > Custom Modular Menu submenu (lists -> items)
- Cursor popup menu (reuses the same QMenu; bound to a shortcut)
- A dynamic shortcut per list (each list can pop on its own hotkey)
- Edit dialog (saving changes refreshes every entry + shortcuts automatically)
"""

import time

from krita import Extension, Krita
from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtGui import QCursor, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QKeySequenceEdit,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
)

from .config import load_lists, load_popup_shortcut, notify_refresh, register_refresh

# Keys that on their own are modifiers, not real shortcuts
_MODIFIER_KEYS = (
    Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
    Qt.Key_unknown, Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
)
_TEXT_INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit, QKeySequenceEdit)


class _KeyFilter(QObject):
    """Installed on the Krita main window; dispatches configured shortcuts."""

    def __init__(self, extension, owner=None):
        super().__init__(owner)
        self._ext = extension

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in _MODIFIER_KEYS:
                return False
            # Do not hijack typing in text inputs (e.g. renaming a layer)
            fw = QApplication.focusWidget()
            if isinstance(fw, _TEXT_INPUTS):
                return False
            mods = event.modifiers()
            seq = QKeySequence(int(mods) | key)
            self._ext.dispatch_shortcut(seq.toString(QKeySequence.PortableText))
        return False


class ListMenuExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        # One entry per window: {window, root_action, menu}
        self._windows = []
        self._shortcut_map = {}   # shortcut string -> callable
        self._popup_active = False
        self._popup_menu_ref = None
        self._ignore_until = 0.0  # debounce: swallow re-triggers right after closing
        # App-level key filter (global, sees every key press regardless of focus)
        self._app_filter = _KeyFilter(self)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self._app_filter)
        register_refresh(self._rebuild_all)

    def setup(self):
        pass

    def createActions(self, window):
        # Trigger action (whole-menu popup; also usable via Krita shortcuts editor)
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
                self._build_menu_node(sub, lst)
            menu.addSeparator()
            menu.addAction(entry["edit_action"])
            break

    # ---------- Dynamic shortcuts (event filter based) ----------
    def _register_shortcuts(self):
        # Rebuild the shortcut lookup map from current config.
        # The app-level event filter stays installed; only the map changes.
        self._shortcut_map = {}
        popup = load_popup_shortcut()
        if popup:
            self._shortcut_map[popup] = self.pop_menu
        for i, lst in enumerate(load_lists()):
            key = lst.get("shortcut", "")
            if key:
                self._shortcut_map[key] = (lambda i=i: self.pop_list(i))

    def dispatch_shortcut(self, seq_str):
        """Called by the event filter with the pressed key sequence (PortableText)."""
        cb = self._shortcut_map.get(seq_str)
        if cb is not None:
            cb()

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
        if self._popup_active or time.time() < self._ignore_until:
            return
        menu = self._build_popup_menu(self._active_window_widget())
        self._popup_active = True
        try:
            menu.exec_(QCursor.pos())
        finally:
            self._popup_active = False
            self._popup_menu_ref = None
            self._ignore_until = time.time() + 0.3
            menu.deleteLater()

    def pop_list(self, index):
        """Open only one list (given its index) as a cursor menu."""
        if self._popup_active or time.time() < self._ignore_until:
            return
        try:
            lst = load_lists()[index]
        except (IndexError, TypeError):
            return
        parent = self._active_window_widget()
        menu = QMenu(parent)
        self._build_menu_node(menu, lst)
        if not menu.actions():
            menu.deleteLater()
            return
        self._force_close_on_trigger(menu)
        self._popup_active = True
        try:
            menu.exec_(QCursor.pos())
        finally:
            self._popup_active = False
            self._popup_menu_ref = None
            self._ignore_until = time.time() + 0.3
            menu.deleteLater()

    def _build_popup_menu(self, parent):
        """Build a fresh cursor popup menu (lists -> items + edit footer)."""
        menu = QMenu(parent)
        for lst in load_lists():
            sub = menu.addMenu(lst["name"])
            self._build_menu_node(sub, lst)
        menu.addSeparator()
        edit_act = menu.addAction("Edit Custom List…")
        edit_act.triggered.connect(self.open_editor)
        self._force_close_on_trigger(menu)
        return menu

    def _add_popup_action(self, menu, action_id, label=""):
        act = self._make_item_action(action_id, label, menu)
        if act is not None:
            menu.addAction(act)

    def _make_item_action(self, action_id, label, parent):
        """Return a QAction for a menu item.

        No custom label -> reuse Krita's native QAction (keeps icon + live
        enable/disable state). Custom label -> proxy QAction with the custom
        text + native icon, triggering the native action.
        """
        try:
            native = Krita.instance().action(action_id)
        except RuntimeError:
            native = None
        if native is None:
            return None
        if not label:
            return native
        act = QAction(label, parent)
        icon = native.icon()
        if not icon.isNull():
            act.setIcon(icon)
        try:
            act.setEnabled(native.isEnabled())
        except RuntimeError:
            pass
        act.triggered.connect(native.trigger)
        return act

    def _build_menu_node(self, parent_menu, node):
        """Recursively add a menu node's commands and submenus to a QMenu."""
        for entry in node.get("items", []):
            aid, label = None, ""
            if isinstance(entry, str):
                aid = entry
            elif isinstance(entry, dict):
                if entry.get("id"):
                    aid, label = entry["id"], entry.get("label", "")
                elif entry.get("name") is not None:
                    sub = parent_menu.addMenu(entry["name"])
                    self._build_menu_node(sub, entry)
                    continue
                else:
                    continue
            else:
                continue
            act = self._make_item_action(aid, label, parent_menu)
            if act is not None:
                parent_menu.addAction(act)

    def _force_close_on_trigger(self, menu):
        """Force the menu to close after ANY item is clicked (even checkable).

        Connects to a stable method on the extension (not a closure capturing the
        menu) so that stale connections are safe after the menu is deleted.
        """
        self._popup_menu_ref = menu
        for act in menu.actions():
            if act.isSeparator():
                continue
            sub = act.menu()
            if sub is not None:
                self._force_close_on_trigger(sub)
            else:
                act.triggered.connect(self._close_current_popup)

    def _close_current_popup(self):
        m = self._popup_menu_ref
        if m is not None:
            try:
                m.close()   # end the exec_ event loop
            except RuntimeError:
                pass
            try:
                m.hide()
            except RuntimeError:
                pass

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
