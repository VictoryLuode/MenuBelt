# Custom Modular Menu (CMM) — Krita 5.3 Python Plugin

Three synchronised multi-list action menus in Krita: a **cursor popup**, a
**Tools > Custom Modular Menu** submenu, and a **Docker panel** (dockable /
floatable like a toolbar). All three read the same configuration.

## Repository layout (= deployable package)
```
custom_modular_menu/
├── pykrita/
│   ├── custom_modular_menu.desktop      # plugin manifest
│   └── custom_modular_menu/             # plugin source
│       ├── __init__.py
│       ├── custom_modular_menu.py       # Extension: Tools menu + cursor popup + trigger
│       ├── config.py                    # multi-list JSON persistence + action enumeration
│       ├── dialog.py                    # multi-list editor dialog
│       └── docker.py                    # Docker panel
└── actions/
    └── custom_modular_menu.action       # exposes the trigger to Keyboard Shortcuts
```

## Deploy
Copy the `pykrita/` and `actions/` folders into the Krita resource directory
`D:/home/Documents/Krita/KritaResource/`, restart Krita, then enable it in
**Settings → Configure Krita → Python Plugin Manager → Custom Modular Menu**.
Or, from the repo root, run `deploy.bat`.

## Usage
- Edit lists: **Tools → Custom Modular Menu → Edit Custom List**, or the Docker
  panel's **"Edit…"** button.
- **Shortcuts (set inside the edit dialog):** each list has a *Popup shortcut*
  field — press a key combination to pop that list at the cursor. The top
  *Menu popup shortcut* field binds the whole-menu cursor popup. These are
  dynamic `QShortcut`s (stored in your config), so you don't need Krita's
  Keyboard Shortcuts editor.
- Cursor popup fallback: **Settings → Configure Krita → Keyboard Shortcuts →
  Custom Modular Menu → Pop Up Custom List** (optional; the action also exists).
- Docker panel: **Settings → Dockers → Custom Modular Menu**.

> Tip: avoid binding a shortcut that already belongs to a Krita action (Qt will
> warn about ambiguous shortcuts).

## Technical notes
- Every item reuses Krita's native `Krita.instance().action(id)` QAction, so
  icons, enable/disable state and shortcut tooltips are inherited.
- The action catalog is enumerated at runtime via `Krita.instance().actions()`.
- The trigger appears in Keyboard Shortcuts thanks to `actions/*.action`
  (the `.action` file is static — action ids must be pre-declared).
