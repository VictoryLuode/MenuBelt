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
from PyQt5.QtCore import QEvent, QObject, QPoint, Qt
from PyQt5.QtGui import QCursor, QFont, QKeySequence
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QKeySequenceEdit,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
)

from .config import (load_lists, notify_refresh, register_refresh,
                     run_brush, run_composite_op, run_script)
from .pie import PieWidget

# Keys that on their own are modifiers, not real shortcuts
_MODIFIER_KEYS = (
    Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
    Qt.Key_unknown, Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
)
_TEXT_INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit, QKeySequenceEdit)

# Blender-style dark menu palette (mimics the Add menu: dark bg, grey/white
# text, grey hover, thin separators, grey disabled header).
_MENU_QSS = """
QMenu {
    background-color: #212121;
    border: 1px solid #2c2c2c;
    color: #e8e8e8;
    padding: 4px;
}
QMenu::item {
    background: transparent;
    color: #e8e8e8;
    padding: 5px 18px 5px 0px;
}
QMenu::item:selected {
    background-color: #3d3d3d;
    color: #ffffff;
}
QMenu::item:disabled {
    color: #9a9a9a;
}
QMenu::separator {
    background-color: #3a3a3a;
    height: 1px;
    margin: 4px 8px;
}
"""


class _KeyFilter(QObject):
    """Installed on the Krita main window; dispatches configured shortcuts."""

    def __init__(self, extension, owner=None):
        super().__init__(owner)
        self._ext = extension

    def eventFilter(self, obj, event):
        if event.type() == QEvent.KeyPress:
            if event.isAutoRepeat():
                return False  # ignore key auto-repeat while held (prevents re-triggering)
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
        elif event.type() == QEvent.KeyRelease:
            if event.isAutoRepeat():
                return False  # ignore auto-release pairs while held
            key = event.key()
            if key in _MODIFIER_KEYS:
                return False
            # A pie is shown while the trigger key is held; release activates it.
            self._ext.pie_release()
        return False


class ListMenuExtension(Extension):
    def __init__(self, parent):
        super().__init__(parent)
        # One entry per window: {window, root_action, menu}
        self._windows = []
        self._shortcut_map = {}   # shortcut string -> callable
        self._popup_active = False
        self._popup_menu_ref = None
        self._last_identity = None  # identity of last-triggered item (reposition marker)
        self._pie = None            # active PieWidget (None when no pie is open)
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
            "custom_modular_menu_edit", "Configure Custom Modular Menu", "")
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
                if not lst.get("active", True):
                    continue
                sub = menu.addMenu(lst["name"])
                self._build_menu_node(sub, lst)
            menu.addSeparator()
            menu.addAction(entry["edit_action"])
            break

    # ---------- Dynamic shortcuts (event filter based) ----------
    def _register_shortcuts(self):
        # Rebuild the shortcut lookup map from current config.
        # Whole-menu popup trigger is bound via Krita's own Keyboard Shortcuts
        # editor (the custom_modular_menu_popup action), so only per-list keys
        # are registered here. The app-level event filter stays installed.
        self._shortcut_map = {}
        for lst in load_lists():
            if not lst.get("active", True):
                continue
            key = lst.get("shortcut", "")
            if key:
                name = lst["name"]
                if lst.get("form", "list") == "pie":
                    self._shortcut_map[key] = (lambda n=name: self.pop_pie(n))
                else:
                    self._shortcut_map[key] = (lambda n=name: self.pop_list(n))

    def _list_index_by_name(self, name):
        for i, lst in enumerate(load_lists()):
            if lst.get("name") == name:
                return i
        return -1

    def dispatch_shortcut(self, seq_str):
        """Called by the event filter with the pressed key sequence (PortableText)."""
        if self._pie is not None or self._popup_active:
            return  # a pie or list popup is already open
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

    def _find_action(self, ident_map, identity):
        """Return the QAction in ident_map whose identity matches (or None)."""
        if identity is None or not ident_map:
            return None
        for act, ident in ident_map.items():
            if ident == identity:
                return act
        return None

    def _popup_anchor(self, menu, ident_map):
        """Return (pos, at_action) so the popup opens with the LAST-triggered item
        under the cursor (both axes), falling back to the raw cursor position."""
        pos = QCursor.pos()
        at = self._find_action(ident_map, self._last_identity)
        if at is not None:
            try:
                rect = menu.actionGeometry(at)
                if rect.isValid():
                    # Qt anchors the menu's left edge at pos.x (that's why X sits at
                    # the leftmost); shift left by the item's centre so the cursor
                    # points at the item's middle instead.
                    pos = QPoint(pos.x() - rect.center().x(), pos.y())
            except Exception:
                pass
        return pos, at

    def pop_menu(self, *_):
        """Open the whole multi-list menu under the cursor of the active window."""
        if self._popup_active or time.time() < self._ignore_until:
            return
        ident_map = {}
        menu = self._build_popup_menu(self._active_window_widget(), ident_map)
        pos, at = self._popup_anchor(menu, ident_map)
        self._popup_active = True
        try:
            triggered = menu.exec_(pos, at)
            if triggered is not None:
                ident = ident_map.get(triggered)
                if ident is not None:
                    self._last_identity = ident
        finally:
            self._popup_active = False
            self._popup_menu_ref = None
            self._ignore_until = time.time() + 0.3
            menu.deleteLater()

    def pop_list(self, target):
        """Open only one list (given its index or name) as a cursor menu."""
        if self._popup_active or time.time() < self._ignore_until:
            return
        index = target if isinstance(target, int) else self._list_index_by_name(target)
        if index < 0:
            return
        try:
            lst = load_lists()[index]
        except (IndexError, TypeError):
            return
        if not lst.get("active", True):
            return
        parent = self._active_window_widget()
        ident_map = {}
        menu = QMenu(parent)
        menu.setStyleSheet(_MENU_QSS)
        self._build_menu_node(menu, lst, ident_map)
        if not menu.actions():
            menu.deleteLater()
            return
        # Prepend a menu-name header (disabled title) above a divider.
        first = menu.actions()[0]
        title = QAction(lst["name"], menu)
        title.setEnabled(False)
        tf = title.font()
        tf.setPointSize(max(6, tf.pointSize() - 1))
        title.setFont(tf)
        menu.insertAction(first, title)
        menu.insertSeparator(first)
        self._force_close_on_trigger(menu)
        pos_mode = lst.get("popup_position", "last")
        if pos_mode == "cursor":
            pos, at = QCursor.pos(), None
        else:
            pos, at = self._popup_anchor(menu, ident_map)
        self._popup_active = True
        try:
            triggered = menu.exec_(pos, at)
            if triggered is not None and pos_mode == "last":
                ident = ident_map.get(triggered)
                if ident is not None:
                    self._last_identity = ident
        finally:
            self._popup_active = False
            self._popup_menu_ref = None
            self._ignore_until = time.time() + 0.3
            menu.deleteLater()

    # ---------- Pie (radial) form ----------
    def _pie_slices(self, lst):
        """Build [(label, icon|None, trigger_callable)] for a list's leaf items."""
        slices = []
        for entry in lst.get("items", []):
            aid, label = None, ""
            if isinstance(entry, str):
                aid = entry
            elif isinstance(entry, dict):
                if entry.get("id"):
                    aid, label = entry["id"], entry.get("label", "")
                elif entry.get("script") is not None:
                    code = entry.get("script", "")
                    slices.append((entry.get("label", "Script"), None,
                                   lambda c=code: run_script(c)))
                    continue
                elif entry.get("blend") is not None:
                    oid = entry.get("blend", "")
                    slices.append((entry.get("label", oid), None,
                                   lambda o=oid: run_composite_op(o)))
                    continue
                elif entry.get("brush") is not None:
                    bfile = entry.get("brush", "")
                    slices.append((entry.get("label", bfile), None,
                                   lambda f=bfile: run_brush(f)))
                    continue
                elif entry.get("name") is not None:
                    continue  # submenu: not representable in a single-level pie (v1)
                else:
                    continue
            else:
                continue
            act = Krita.instance().action(aid)
            if act is None:
                continue
            icon = act.icon()
            slices.append((label or act.text().replace("&", "").strip(),
                           icon if not icon.isNull() else None, act.trigger))
        return slices

    def pop_pie(self, target):
        """Show a Blender-style radial menu for a pie-form list (index or name)."""
        if self._pie is not None:
            return
        index = target if isinstance(target, int) else self._list_index_by_name(target)
        if index < 0:
            return
        try:
            lst = load_lists()[index]
        except (IndexError, TypeError):
            return
        if not lst.get("active", True):
            return
        slices = self._pie_slices(lst)
        if not slices:
            return
        pie = PieWidget(slices, self._active_window_widget())
        self._pie = pie
        pie.show_pie(QCursor.pos())

    def pie_release(self):
        """Activate the currently highlighted pie item and close the pie."""
        pie = self._pie
        if pie is None:
            return
        trig = pie.current_trigger()
        self._pie = None
        pie.close_pie()
        if trig is not None:
            trig()

    def _build_popup_menu(self, parent, ident_map=None):
        """Build a fresh cursor popup menu (lists -> items + edit footer)."""
        menu = QMenu(parent)
        menu.setStyleSheet(_MENU_QSS)
        for lst in load_lists():
            if not lst.get("active", True):
                continue
            sub = menu.addMenu(lst["name"])
            self._build_menu_node(sub, lst, ident_map)
        menu.addSeparator()
        edit_act = menu.addAction("Configure Custom Modular Menu…")
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

    def _build_menu_node(self, parent_menu, node, ident_map=None):
        """Recursively add a menu node's commands, scripts and submenus.

        ident_map (optional) maps each added leaf QAction -> an identity tuple,
        so the popup can remember/relocate the last-triggered item.
        """
        for entry in node.get("items", []):
            aid, label = None, ""
            if isinstance(entry, str):
                aid = entry
            elif isinstance(entry, dict):
                if entry.get("id"):
                    aid, label = entry["id"], entry.get("label", "")
                elif entry.get("script") is not None:
                    sact = QAction(entry.get("label", "Script"), parent_menu)
                    if ident_map is not None:
                        ident_map[sact] = ("script", entry.get("label", "Script"))
                    sact.triggered.connect(
                        lambda _=False, c=entry.get("script", ""): run_script(c))
                    parent_menu.addAction(sact)
                    continue
                elif entry.get("blend") is not None:
                    bact = QAction(entry.get("label", entry["blend"]), parent_menu)
                    if ident_map is not None:
                        ident_map[bact] = ("blend", entry.get("blend", ""))
                    bact.triggered.connect(
                        lambda _=False, o=entry.get("blend", ""): run_composite_op(o))
                    parent_menu.addAction(bact)
                    continue
                elif entry.get("brush") is not None:
                    br_act = QAction(entry.get("label", entry["brush"]), parent_menu)
                    if ident_map is not None:
                        ident_map[br_act] = ("brush", entry.get("brush", ""))
                    br_act.triggered.connect(
                        lambda _=False, f=entry.get("brush", ""): run_brush(f))
                    parent_menu.addAction(br_act)
                    continue
                elif entry.get("name") is not None:
                    sub = parent_menu.addMenu(entry["name"])
                    self._build_menu_node(sub, entry, ident_map)
                    continue
                else:
                    continue
            else:
                continue
            act = self._make_item_action(aid, label, parent_menu)
            if act is not None:
                if ident_map is not None:
                    ident_map[act] = ("cmd", aid)
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
