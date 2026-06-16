"""
Style Buttons for Editor
========================

根据当前笔记类型(Note Type)模板 CSS 中定义的 class,在 Anki 卡片编辑器工具栏
自动生成快捷样式按钮;选中文本点击即可包裹为对应 HTML 标签。

入口:注册编辑器钩子与工具菜单设置项。
"""

from __future__ import annotations

from aqt import gui_hooks, mw
from aqt.qt import QAction

from . import editor_integration
from .i18n import tr
from .log import log


def _open_settings() -> None:
    """打开配置:复用 Anki 原生的插件 JSON 配置编辑器(GUI 配置为后续迭代)。"""
    package = __name__.split(".")[0]
    # 1) 优先使用插件自身注册的 config 动作(若有)
    try:
        cfg_action = mw.addonManager.configAction(package)
        if cfg_action:
            cfg_action()
            return
    except Exception:
        pass
    # 2) 回退:直接打开标准 JSON 配置编辑器(以隐藏的 AddonsDialog 作为父窗口)
    try:
        from aqt.addons import AddonsDialog, ConfigEditor

        conf = mw.addonManager.getConfig(package) or {}
        parent = AddonsDialog(mw.addonManager)
        ConfigEditor(parent, package, conf).exec()
    except Exception as exc:
        log(f"打开设置失败: {exc}")


def _setup_menu() -> None:
    try:
        action = QAction(tr("menu_settings"), mw)
        action.triggered.connect(_open_settings)
        mw.form.menuTools.addAction(action)
    except Exception as exc:  # pragma: no cover
        log(f"添加菜单项失败: {exc}")


def _on_main_window_did_init() -> None:
    _setup_menu()


# 注册编辑器钩子(模块导入时即生效)
editor_integration.register()

# 主窗口初始化后再挂菜单,避免启动早期 mw.form 尚未就绪
gui_hooks.main_window_did_init.append(_on_main_window_did_init)
