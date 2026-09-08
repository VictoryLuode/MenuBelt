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
from PyQt5.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PyQt5.QtGui import (QColor, QCursor, QFont, QIcon, QKeySequence,
                         QPainter, QPalette, QPixmap)
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QKeySequenceEdit,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QTextEdit,
    QWidget,
    QWidgetAction,
)

from .config import (load_last_identity, load_lists, notify_refresh,
                     register_refresh, save_last_identity, run_brush,
                     run_brush_blend, run_composite_op, run_script)
from .pie import PieWidget

# Keys that on their own are modifiers, not real shortcuts
_MODIFIER_KEYS = (
    Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta,
    Qt.Key_unknown, Qt.Key_CapsLock, Qt.Key_NumLock, Qt.Key_ScrollLock,
)
_TEXT_INPUTS = (QLineEdit, QTextEdit, QPlainTextEdit, QKeySequenceEdit)

# Dark Blender-like theme applied via QPalette only. ANY setStyleSheet on a QMenu
# switches it to QStyleSheetStyle, which stops drawing item icons — so the theme
# must use the palette alone (separator = QPalette.Mid) to keep icons.
def _apply_dark_theme(menu):
    pal = menu.palette()
    pal.setColor(QPalette.Window, QColor(33, 33, 33))
    pal.setColor(QPalette.Base, QColor(33, 33, 33))
    pal.setColor(QPalette.Text, QColor(232, 232, 232))
    pal.setColor(QPalette.WindowText, QColor(232, 232, 232))
    pal.setColor(QPalette.ButtonText, QColor(232, 232, 232))
    pal.setColor(QPalette.Highlight, QColor(61, 61, 61))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.Mid, QColor(58, 58, 58))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(154, 154, 154))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(154, 154, 154))
    menu.setPalette(pal)


class _MenuRow(QWidget):
    """Self-painted menu row (icon + text + optional shortcut).

    Krita applies a global stylesheet, which turns every QMenu into a
    QStyleSheetStyle — and that style drops QMenu action icons. A plain QAction
    therefore can never show an icon in a Krita QMenu. Using a QWidgetAction and
    painting the row ourselves (icon + text) bypasses the stylesheet and
    guarantees the icon renders. Hover highlight is painted from the palette.
    """

    def __init__(self, text, parent=None, icon=None, shortcut=""):
        super().__init__(parent)
        self._text = text
        self._icon = icon
        self._shortcut = shortcut
        self._hover = False
        self.setMouseTracking(True)

    def sizeHint(self):
        fm = self.fontMetrics()
        # 40 = left pad 10 + icon column 20 + gap 10, ALWAYS reserved so no-icon
        # rows align their text with icon rows.
        w = 40 + fm.horizontalAdvance(self._text) + 12   # + right pad
        if self._shortcut:
            w += fm.horizontalAdvance(self._shortcut) + 28
        return QSize(w, 30)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        p = QPainter(self)
        pal = self.palette()
        if self._hover and self.isEnabled():
            p.fillRect(self.rect(), pal.highlight())
        if not self.isEnabled():
            p.setPen(QColor(154, 154, 154))
        elif self._hover:
            p.setPen(pal.highlightedText().color())
        else:
            p.setPen(pal.text().color())
        fm = self.fontMetrics()
        x_icon = 10           # icon column left edge
        x_text = 40           # text always starts here (icon column reserved)
        y = (self.height() - fm.height()) // 2
        if self._icon is not None and not self._icon.isNull():
            size = 20
            p.drawPixmap(x_icon, (self.height() - size) // 2,
                         self._icon.pixmap(QSize(size, size)))
        p.drawText(x_text, y + fm.ascent(), self._text)
        if self._shortcut:
            p.setPen(QColor("#808080"))
            sw = fm.horizontalAdvance(self._shortcut)
            p.drawText(self.width() - sw - 12, y + fm.ascent(), self._shortcut)
        p.end()


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
        self._last_identity = load_last_identity()  # persisted last-triggered item
        self._pie = None            # active PieWidget (None when no pie is open)
        self._ignore_until = 0.0  # debounce: swallow re-triggers right after closing
        # Brush icon + preset caches (build once, not per menu item)
        self._brush_icons = {}      # preset name -> QIcon (or None)
        self._presets = None        # cached resources("preset") dict
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
                    save_last_identity(ident)
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
        _apply_dark_theme(menu)
        self._build_menu_node(menu, lst, ident_map, lst.get("show_icons", True))
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
        pos, at = self._popup_anchor(menu, ident_map)
        self._popup_active = True
        try:
            triggered = menu.exec_(pos, at)
            if triggered is not None:
                ident = ident_map.get(triggered)
                if ident is not None:
                    self._last_identity = ident
                    save_last_identity(ident)
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
                elif entry.get("bblend") is not None:
                    oid = entry.get("bblend", "")
                    slices.append((entry.get("label", oid), None,
                                   lambda o=oid: run_brush_blend(o)))
                    continue
                elif entry.get("brush") is not None:
                    bfile = entry.get("brush", "")
                    slices.append((entry.get("label", bfile), self._brush_icon(bfile),
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
        _apply_dark_theme(menu)
        for lst in load_lists():
            if not lst.get("active", True):
                continue
            sub = menu.addMenu(lst["name"])
            _apply_dark_theme(sub)
            self._build_menu_node(sub, lst, ident_map, lst.get("show_icons", True))
        menu.addSeparator()
        edit_act = menu.addAction("Configure Custom Modular Menu…")
        edit_act.triggered.connect(self.open_editor)
        self._force_close_on_trigger(menu)
        return menu

    def _add_row(self, menu, text, icon, callback, shortcut="", enabled=True):
        """Add a QWidgetAction row that paints its own icon+text, so icons render
        even under Krita's global stylesheet (which makes QMenu drop action icons).
        Returns the QWidgetAction."""
        act = QWidgetAction(menu)
        row = _MenuRow(text, icon=icon, shortcut=shortcut)
        row.setPalette(menu.palette())
        row.setEnabled(enabled)
        act.setDefaultWidget(row)
        act.setEnabled(enabled)
        if callback is not None:
            act.triggered.connect(lambda _=False: callback())
        menu.addAction(act)
        return act

    def _add_cmd(self, menu, action_id, label, show_icons, ident_map):
        """Add a command (Krita action) row; trigger() runs the native action."""
        try:
            native = Krita.instance().action(action_id)
        except RuntimeError:
            native = None
        if native is None:
            return
        text = label or native.text().replace("&", "").strip()
        icon = None
        if show_icons:
            try:
                icon = native.icon()
                if icon.isNull():
                    icon = None
            except RuntimeError:
                icon = None
        try:
            sc = native.shortcut().toString(QKeySequence.NativeText)
        except Exception:
            sc = ""
        act = self._add_row(menu, text, icon, native.trigger, shortcut=sc,
                            enabled=native.isEnabled())
        if ident_map is not None:
            ident_map[act] = ("cmd", action_id)

    def _get_presets(self):
        """Cached dict of all Krita brush presets (name -> Resource).

        Calling resources("preset") enumerates every preset; building a menu with
        N brush items called it N times (O(N^2) -> seconds of lag). Cache it once.
        """
        if self._presets is None:
            self._presets = Krita.instance().resources("preset")
        return self._presets

    def _brush_icon(self, name):
        """Return a QIcon built from a brush preset's thumbnail image (or None).

        Icons are cached per preset name so each brush only loads its image once.
        """
        if name in self._brush_icons:
            return self._brush_icons[name]
        icon = None
        try:
            presets = self._get_presets()
            resource = presets.get(name)
            if resource is None:
                # fallback: legacy configs stored the preset filename
                for p in presets.values():
                    try:
                        if p.filename() == name:
                            resource = p
                            break
                    except Exception:
                        continue
            if resource is not None:
                img = resource.image()
                if not img.isNull():
                    # downscale once to a small pixmap; avoids a full-size copy
                    icon = QIcon(QPixmap.fromImage(
                        img.scaled(64, 64, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)))
        except Exception:
            icon = None
        self._brush_icons[name] = icon
        return icon

    def _build_menu_node(self, parent_menu, node, ident_map=None, show_icons=True):
        """Recursively add a menu node's commands, scripts and submenus.

        ident_map (optional) maps each added leaf QWidgetAction -> an identity
        tuple, so the popup can remember/relocate the last-triggered item.
        """
        for entry in node.get("items", []):
            if isinstance(entry, str):
                self._add_cmd(parent_menu, entry, "", show_icons, ident_map)
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("id"):
                self._add_cmd(parent_menu, entry["id"], entry.get("label", ""),
                              show_icons, ident_map)
            elif entry.get("script") is not None:
                label = entry.get("label", "Script")
                act = self._add_row(parent_menu, label, None,
                                    lambda c=entry.get("script", ""): run_script(c))
                if ident_map is not None:
                    ident_map[act] = ("script", label)
            elif entry.get("blend") is not None:
                label = entry.get("label", entry["blend"])
                act = self._add_row(parent_menu, label, None,
                                    lambda o=entry.get("blend", ""): run_composite_op(o))
                if ident_map is not None:
                    ident_map[act] = ("blend", entry.get("blend", ""))
            elif entry.get("bblend") is not None:
                label = entry.get("label", entry["bblend"])
                act = self._add_row(parent_menu, label, None,
                                    lambda o=entry.get("bblend", ""): run_brush_blend(o))
                if ident_map is not None:
                    ident_map[act] = ("bblend", entry.get("bblend", ""))
            elif entry.get("brush") is not None:
                label = entry.get("label", entry["brush"])
                icon = self._brush_icon(entry.get("brush", "")) if show_icons else None
                act = self._add_row(parent_menu, label, icon,
                                    lambda f=entry.get("brush", ""): run_brush(f))
                if ident_map is not None:
                    ident_map[act] = ("brush", entry.get("brush", ""))
            elif entry.get("name") is not None:
                sub = parent_menu.addMenu(entry["name"])
                self._build_menu_node(sub, entry, ident_map, show_icons)

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
