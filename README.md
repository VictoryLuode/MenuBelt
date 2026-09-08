# Custom Modular Menu (CMM) — Krita 5.3 Python Plugin

Synchronised multi-list action menus in Krita: a **cursor popup** and a
**Tools > Custom Modular Menu** submenu. Both read the same configuration.

## Repository layout (= deployable package)
```
custom_modular_menu/
├── pykrita/
│   ├── custom_modular_menu.desktop      # plugin manifest
│   └── custom_modular_menu/             # plugin source
│       ├── __init__.py
│       ├── custom_modular_menu.py       # Extension: Tools menu + cursor popup + trigger
│       ├── config.py                    # config persistence + item types + runner
│       └── dialog.py                    # multi-menu editor with live preview
└── actions/
    └── custom_modular_menu.action       # exposes the trigger to Keyboard Shortcuts
```

## Deploy
Copy the `pykrita/` and `actions/` folders into the Krita resource directory
`D:/home/Documents/Krita/KritaResource/`, restart Krita, then enable it in
**Settings → Configure Krita → Python Plugin Manager → Custom Modular Menu**.
Or, from the repo root, run `deploy.bat`.

## Usage
- **Edit menu:** **Tools → Custom Modular Menu → Configure Custom Modular Menu**.
- **Item types:** commands (Krita actions), nested **submenus**, **Python
  scripts**, and **layer blend modes** (set on the active layer via
  `Node.setBlendingMode`).
- **Shortcuts:** each list has a *Shortcut* field in the editor — press a key
  combination to pop that list at the cursor. The whole-menu popup is bound in
  **Settings → Configure Krita → Keyboard Shortcuts → Custom Modular Menu →
  Pop Up Custom List**.
- **Drag to reorder** lists and items; **double-click** a submenu to enter it,
  a command to rename it.

> Tip: avoid binding a shortcut that already belongs to a Krita action (Qt will
> warn about ambiguous shortcuts).

## Technical notes
- Commands reuse Krita's native `Krita.instance().action(id)` QAction.
- Blend modes use `Krita.instance().activeDocument().activeNode().setBlendingMode(id)`
  (ids from `KoCompositeOpRegistry.h`).
- The action catalog is enumerated at runtime via `Krita.instance().actions()`.
- The trigger appears in Keyboard Shortcuts thanks to `actions/*.action`
  (the `.action` file is static — action ids must be pre-declared).
