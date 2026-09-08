![MenuBelt](assets/menubelt-poster.png)

Build your own **multi-list action menus** in Krita and reach them from a **cursor popup**
or the **Tools → MenuBelt** submenu — as a **linear List** or a **Blender-style radial Pie**.

## Demo

[![MenuBelt demo](https://img.youtube.com/vi/hjSDBv3bs3Q/maxresdefault.jpg)](https://youtu.be/hjSDBv3bs3Q)

## Highlights

- **Native Krita actions** — icons, state and shortcut hints inherited automatically.
- **Six "Add" sources** — Krita Actions, Layer & Brush Blend Modes, Brush Values, Colour swatches, Brushes.
- **List or Pie** — linear menus, or a radial pie (up to 8 items).
- **Nested menus** — submenus, headers, separators and checkable toggles.
- **Per-list shortcuts** — bind hotkeys in-editor, no Krita shortcut dialog needed.
- **Live preview · Export / Import · conflict detection.**

## Install

> **Requires Krita 5.x.** Download the latest `menubelt.zip` from [Releases](../../releases),
> unzip, copy the `pykrita/` and `actions/` folders into your Krita resource dir
> (Windows `%APPDATA%/krita/`, Linux `~/.config/krita/`), restart Krita, then enable it
> in **Settings → Configure Krita → Python Plugin Manager**.

## Quick start

**Tools → MenuBelt → Configure MenuBelt**, pick a list, add items from a source
(Krita Actions, Blend Modes, Brush Values, Palettes, Brushes) or **Add Submenu /
Header / Separator / Toggle**, then **drag to reorder** and **double-click** to rename.

Bind a list shortcut by clicking its *Shortcut* field; the whole-menu trigger lives in
**Keyboard Shortcuts → MenuBelt → Pop Up Custom List**.

## License

[GPL-3.0](LICENSE).
