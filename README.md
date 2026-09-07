# Quick List Menu（Krita 5.3 Python 插件）

在光标处 / Tools 菜单 / Docker 面板三处同步呈现**可自定义的多列表** Krita 动作菜单。

## 结构（仓库 = 可部署包）
```
quick_list_menu/
├── pykrita/
│   ├── quick_list_menu.desktop      # 插件声明
│   └── quick_list_menu/             # 插件源码
│       ├── __init__.py
│       ├── quick_list_menu.py       # Extension：Tools 菜单 + 光标弹菜单 + 触发器
│       ├── config.py                # 多列表 JSON 持久化 + 动作目录枚举
│       ├── dialog.py                # 多列表编辑对话框
│       └── docker.py                # Docker 面板
└── actions/
    └── quick_list_menu.action       # 让触发器出现在快捷键编辑器
```

## 部署
把 `pykrita/` 和 `actions/` 两个目录复制到 Krita 资源目录 `D:/home/Documents/Krita/KritaResource/`，重启 Krita，在
**Settings → Configure Krita → Python Plugin Manager** 勾选 **Quick List Menu** 启用。

## 使用
- 编辑列表：**Tools → Quick List Menu → 编辑快捷列表菜单…** 或 Docker 面板的“编辑列表…”按钮
- 光标弹菜单：**Settings → Configure Krita → Keyboard Shortcuts → Quick List Menu → 弹出快捷列表菜单** 绑定触发键
- Docker 面板：**Settings → Dockers → Quick List Menu** 开启，可停靠/浮动当工具栏

## 技术要点
- 每个列表项直接复用 `Krita.instance().action(id)` 的原生 QAction（图标/置灰/快捷键提示全继承）
- 动作目录用 `Krita.instance().actions()` 动态枚举
- 触发器进键盘快捷键编辑器，靠 `actions/*.action` 文件（`.action` 是静态的，须预声明同 id）
