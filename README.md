# MenuBelt — Krita Plugin

Build your own **multi-list action menus** in Krita and reach them from two places at
once: a **cursor popup** and a **Tools → MenuBelt** submenu. Each list is fully yours
to assemble — native Krita actions, blend modes, brushes, colour swatches, submenus and
more — and can open as a **linear List** or a **Blender-style radial Pie**.

Everything is configured in one place, with a **live preview** as you edit.

## Highlights

- **Native Krita actions** — icons, enabled/disabled state and shortcut hints inherited automatically.
- **Six "Add" sources** — Krita Actions, Layer & Brush Blend Modes, Brush Values, Colour swatches, Brushes.
- **List or Pie** — linear menus, or a Blender-style radial pie (up to 8 items).
- **Nested menus** — submenus, headers, separators and checkable toggles, to any depth.
- **Per-list shortcuts** — bind hotkeys (plus a whole-menu trigger) right in the editor, no Krita shortcut dialog needed.
- **Live preview · Export / Import · shortcut conflict detection · enable/disable per list.**

## Install

> **Requires Krita 5.x (developed against 5.3).**

1. Download the latest `menubelt.zip` from the [Releases page](../../releases).
2. Unzip it and copy the `pykrita/` and `actions/` folders into your Krita resource
   directory (Windows: `%APPDATA%/krita/`, Linux: `~/.config/krita/`).
   Or `git clone` the repo and run `deploy.bat` (Windows).
3. Restart Krita.
4. **Settings → Configure Krita → Python Plugin Manager →** tick **MenuBelt**, restart again.

## Quick start

1. **Tools → MenuBelt → Configure MenuBelt**.
2. Pick a list in **Menu List**, or add a new one.
3. In **Add items**, choose a source — Krita Actions, Layer Blend Mode, Brush Blend Mode,
   Brush Value, Krita Palettes, Brushes — then **Add**. Or **Add Submenu / Header /
   Separator / Toggle** directly.
4. **Drag to reorder**; **double-click** to rename an item or enter a submenu.

### Shortcuts

- **Per list:** click a list's *Shortcut* field and press a combo (e.g. `Ctrl+Alt+1`).
- **Whole menu:** **Settings → Configure Krita → Keyboard Shortcuts → MenuBelt → Pop Up Custom List**.

> **Tip:** prefer modifier+key combos and avoid shortcuts already used by a Krita action.

## Repository layout
```
menubelt/
├── pykrita/
│   ├── menubelt.desktop      # plugin manifest
│   └── menubelt/             # plugin source
│       ├── __init__.py
│       ├── menubelt.py       # Extension: Tools menu + cursor popup + trigger
│       ├── config.py         # config persistence + item types + runner
│       ├── dialog.py         # multi-menu editor with live preview
│       ├── pie.py            # Blender-style radial pie widget
│       └── manual.html       # in-app manual
├── actions/
│   └── menubelt.action       # exposes the trigger to Keyboard Shortcuts
└── deploy.bat                # Windows: copy files to the resource dir
```

## License

[GPL-3.0](LICENSE).
