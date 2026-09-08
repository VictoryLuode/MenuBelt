**[Plugin] MenuBelt — build your own multi-list action menus (List & Pie)**

---

Hey everyone 👋

I built **MenuBelt**, a Krita plugin that lets you assemble your own
**multi-list action menus** and reach them from two places at once: a **cursor popup**
and a **Tools → MenuBelt** submenu. Both share the same configuration, so
you build a list once and use it anywhere.

Everything is configured in one place with a **live preview** of the whole menu tree
as you edit. Each list can open as a **linear List** or a **Blender-style radial Pie**.

*(Insert screenshots / GIF here — editor, a list popup, a Pie)*

## What it does

- **Native Krita actions** — every command item is a *real* Krita action, so icons,
  enabled/disabled state and shortcut hints are inherited automatically.
- **Six "Add" sources**:
  - **Krita Actions** (grouped by Krita's own shortcut-editor categories)
  - **Layer Blend Mode** (`Node.setBlendingMode`)
  - **Brush Blend Mode** (`View.setCurrentBlendingMode`)
  - **Brush Value** (Opacity / Flow / Size presets)
  - **Krita Palettes** (colour swatches from your palettes)
  - **Brushes** (presets, via `setCurrentPreset`)
- **List or Pie** — linear menus, or Blender-style radial pies (up to 8 items).
- **Submenus, Headers, Separators, checkable Toggles** — organise any list to any depth.
- **Per-list shortcuts** plus a whole-menu popup trigger, set right inside the editor
  (no need for Krita's Keyboard Shortcuts dialog).
- **Export / Import** — save or load a config file to share or back up your setup.
- **Shortcut conflict detection** and **enable/disable** per list.

## Install

> Requires **Krita 5.x** (developed against 5.3).

1. Download `menubelt_v1.0.0.zip` from the release below.
2. Unzip it, then copy the `pykrita/` and `actions/` folders into your Krita resource
   directory — Windows: `%APPDATA%/krita/`, Linux: `~/.config/krita/`.
3. Restart Krita.
4. **Settings → Configure Krita → Python Plugin Manager →** tick **MenuBelt**,
   restart again.

Then open the editor from **Tools → MenuBelt → Configure MenuBelt**.

## Links

- **GitHub:** https://github.com/VictoryLuode/Custom-Modular-Menu
- **Download:** <release link>
- **License:** GPL-3.0

I'd love to hear how you use it and any feature requests. Feedback & bug reports are
very welcome!
