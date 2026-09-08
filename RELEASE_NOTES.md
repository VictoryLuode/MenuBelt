# Custom Modular Menu v1.0.0

**Build your own multi-list action menus in Krita, reachable from a cursor popup and
a Tools → Custom Modular Menu submenu. Each list opens as a linear menu or a
Blender-style radial pie.**

This is the first public release of **Custom Modular Menu**.

## Highlights

- **Native Krita actions** — each command is a *real* Krita action (icons, enable/disable
  state and shortcut hints inherited automatically).
- **Six "Add" sources** — Krita Actions, Layer Blend Mode, Brush Blend Mode, Brush
  Value (Opacity/Flow/Size), Krita Palettes (colour swatches), and Brushes (presets).
- **List or Pie** — linear menus, or Blender-style radial pies (up to 8 items).
- **Submenus, Headers, Separators, checkable Toggles** — organise any list.
- **Per-list shortcuts** plus a whole-menu popup trigger, set from inside the editor.
- **Live preview** of the whole menu tree while editing.
- **Export / Import** config to share or back up your setup.

## Install

> Requires **Krita 5.x** (developed against 5.3).

1. Download this `custom_modular_menu_v1.0.0.zip`.
2. Unzip it and copy the `pykrita/` and `actions/` folders into your Krita resource
   directory (Windows: `%APPDATA%/krita/`; Linux: `~/.config/krita/`).
3. Restart Krita.
4. **Settings → Configure Krita → Python Plugin Manager →** tick **Custom Modular Menu**,
   then restart again.

Then open the editor from **Tools → Custom Modular Menu → Configure Custom Modular Menu**.

## License

GPL-3.0 · [Full license](LICENSE)
