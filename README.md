# MenuBelt — Krita Plugin

Build your own **multi-list action menus** in Krita and reach them from two places at
once: a **cursor popup** and a **Tools → MenuBelt** submenu. Each list is
fully yours to assemble — native Krita actions, layer/blend modes, brushes, brush
values, colour swatches, submenus, headers, separators and checkable toggles — and
every list can open as a **linear List** or a **Blender-style radial Pie**.

Everything is configured in one place, with a **live preview** of the whole menu tree
as you edit. Both entry points share the same configuration.

## Features

- **Native Krita actions** — each command item is a *real* Krita action, so icons,
  enabled/disabled state and shortcut hints are inherited automatically.
- **Layer blend modes** — set the active layer's blend mode via `Node.setBlendingMode`.
- **Brush blend modes** — set the brush stroke blend mode via `View.setCurrentBlendingMode`.
- **Brush values** — quick `Opacity` / `Flow` / `Size` presets.
- **Brush presets** — switch the active Krita brush.
- **Colour swatches** — pick colours from your Krita **palettes**.
- **Submenus** — nest a menu inside a menu, to any depth.
- **Headers / Separators** — visually organise a list.
- **Checkable Toggles** — tick-able items bound to checkable Krita actions.
- **List or Pie form** — each list opens as a linear menu or a radial (Blender-style)
  pie: hold the trigger, drag toward a direction, release to activate. Pie supports up to
  8 items (submenus aren't shown in a pie).
- **Custom names** — rename any item; the menu and Tools submenu show your label with
  the native icon and behaviour.
- **Per-list shortcuts** — bind a hotkey for each list, plus a whole-menu popup trigger,
  all from inside the editor (no need for Krita's Keyboard Shortcuts dialog).
- **Export / Import** — save or load a config file to share or back up your setup.
- **Live preview** — a pane in the editor mirrors the whole menu tree as you edit.
- **Shortcut conflict detection** — warns if a list shortcut collides with another list
  or an existing Krita action.
- **Enable / disable a list** — tick a checkbox to activate a list; untick to hide it
  (skipped in the popup, the Tools submenu and its shortcut; still editable).

## Install

> **Requires Krita 5.x (developed against 5.3).**

1. Download the latest `menubelt.zip` from the
   [Releases page](../../releases).
2. Unzip it and copy the `pykrita/` and `actions/` folders into your Krita resource
   directory (on Windows usually
   `%APPDATA%/krita/`, on Linux `~/.config/krita/`).
   You can also `git clone` the repo and run `deploy.bat` (Windows) to copy the
   files for you.
3. Restart Krita.
4. Enable the plugin: **Settings → Configure Krita → Python Plugin Manager →**
   tick **MenuBelt**, then restart again.

## Quick start

1. Open the editor: **Tools → MenuBelt → Configure MenuBelt**.
2. In the **Menu List**, pick a list (e.g. *Canvas Assist*), or add a new one.
3. In the **Add items** pane choose a source:
   - **Krita Actions** — grouped by Krita's own shortcut-editor categories.
   - **Layer Blend Mode** — set the active layer's blend mode.
   - **Brush Blend Mode** — set the brush stroke blend mode.
   - **Brush Value** — Opacity / Flow / Size presets.
   - **Krita Palettes** — colour swatches from your palettes.
   - **Brushes** — brush presets.
   Select an item and **Add**.
   You can also **Add Submenu**, **Add Header**, **Add Separator**, or **Add Toggle**
   directly from the *Add* menu.
4. **Drag to reorder** lists and items; **double-click** an item to rename it, a
   submenu to enter it (use the breadcrumb to go back).

### Shortcuts

- **Per list:** in the editor, click a list's *Shortcut* field and press a key
  combination (e.g. `Ctrl+Alt+1`) to pop that list at the cursor.
- **Whole menu:** bind it in **Settings → Configure Krita → Keyboard Shortcuts →
  MenuBelt → Pop Up Custom List**.

> **Tip:** prefer modifier+key combos (`Ctrl/Alt/Shift` + a key) and avoid shortcuts
> already used by a Krita action, or they won't fire.

## Repository layout
```
menubelt/
├── pykrita/
│   ├── menubelt.desktop      # plugin manifest
│   └── menubelt/             # plugin source
│       ├── __init__.py
│       ├── menubelt.py       # Extension: Tools menu + cursor popup + trigger
│       ├── config.py                    # config persistence + item types + runner
│       ├── dialog.py                    # multi-menu editor with live preview
│       ├── pie.py                        # Blender-style radial pie widget
│       └── manual.html                  # in-app manual
├── actions/
│   └── menubelt.action       # exposes the trigger to Keyboard Shortcuts
└── deploy.bat                           # Windows: copy files to the resource dir
```

## Technical notes

- Commands reuse Krita's native `Krita.instance().action(id)` QAction.
- Layer blend modes use `Node.setBlendingMode(id)` (ids from `KoCompositeOpRegistry.h`).
- Brush blend modes use `View.setCurrentBlendingMode(id)`.
- Brush values use `View.setPaintingOpacity` / `setFlow` / `setBrushSize`.
- The action catalog is enumerated at runtime via `Krita.instance().actions()`.
- Per-list shortcuts use an app-level key event filter (not `QShortcut`) — reliable
  inside Krita.
- Your list configuration is stored in `config.json` inside the plugin folder
  (not tracked by git).

## License

[GPL-3.0](LICENSE).
