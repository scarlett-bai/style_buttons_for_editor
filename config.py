"""
配置管理 (F4)

封装对 Anki 插件配置(config.json / meta.json)的读取、规范化与按 class 合并。

配置结构(对应 PRD 3.5.3):

    {
      "global": {
        "enabled": bool,
        "default_tag": str,
        "button_overflow_mode": "dropdown" | "newline" | "scroll",
        "button_overflow_threshold": int,
        "show_css_preview_tooltip": bool,
        "show_button_style_preview": bool,
        "ignored_classes": [str, ...],
        "language": "auto" | "zh" | "en"
      },
      "note_types": {
        "<笔记类型名>": {
          "<class 名>": {
            "visible": bool,
            "display_name": str,
            "order": int,
            "tag": str,        # 空串表示使用全局 default_tag
            "shortcut": str,
            "color": str
          }
        }
      }
    }

配置文件损坏时回退到内置默认值,保证编辑器正常使用(PRD 8.2)。
"""

from __future__ import annotations

from typing import Any

from aqt import mw

from .log import log

# 内置默认值(与 config.json 保持一致),用于配置缺失/损坏时回退。
DEFAULT_GLOBAL: dict[str, Any] = {
    "enabled": True,
    "default_tag": "span",
    "button_overflow_mode": "dropdown",
    "button_overflow_threshold": 8,
    "show_css_preview_tooltip": True,
    "show_button_style_preview": True,
    "ignored_classes": [
        "card",
        "card1",
        "card2",
        "card3",
        "cloze",
        "nightMode",
        "night_mode",
        "replay-button",
        "typepad",
        "typeBad",
        "typeGood",
        "typeMissed",
    ],
    "language": "auto",
}

_VALID_OVERFLOW_MODES = {"dropdown", "newline", "scroll"}

# 单个 class 的默认配置项
DEFAULT_CLASS_CONFIG: dict[str, Any] = {
    "visible": True,
    "display_name": "",
    "order": None,
    "tag": "",
    "shortcut": "",
    "color": "",
}


def _package() -> str:
    """返回本插件在 addonManager 中的包名(即插件目录名)。"""
    return __name__.split(".")[0]


def get_raw_config() -> dict[str, Any]:
    """读取原始配置;失败时返回空 dict。"""
    try:
        cfg = mw.addonManager.getConfig(_package())
        if isinstance(cfg, dict):
            return cfg
    except Exception as exc:  # pragma: no cover - 防御性
        log(f"读取配置失败: {exc}")
    return {}


def get_global() -> dict[str, Any]:
    """返回规范化后的全局配置(缺失项以默认值补齐,非法值回退)。"""
    raw = get_raw_config().get("global", {})
    if not isinstance(raw, dict):
        raw = {}

    g = dict(DEFAULT_GLOBAL)
    for key, default in DEFAULT_GLOBAL.items():
        if key in raw and isinstance(raw[key], type(default)):
            g[key] = raw[key]

    # 额外校验
    if g["button_overflow_mode"] not in _VALID_OVERFLOW_MODES:
        g["button_overflow_mode"] = DEFAULT_GLOBAL["button_overflow_mode"]
    try:
        g["button_overflow_threshold"] = max(1, int(g["button_overflow_threshold"]))
    except (TypeError, ValueError):
        g["button_overflow_threshold"] = DEFAULT_GLOBAL["button_overflow_threshold"]
    if not isinstance(g["ignored_classes"], list):
        g["ignored_classes"] = list(DEFAULT_GLOBAL["ignored_classes"])

    return g


def get_note_type_config(note_type_name: str) -> dict[str, Any]:
    """返回某笔记类型下所有 class 的用户配置(原始,可能为空)。"""
    note_types = get_raw_config().get("note_types", {})
    if not isinstance(note_types, dict):
        return {}
    nt = note_types.get(note_type_name, {})
    return nt if isinstance(nt, dict) else {}


def get_class_config(note_type_name: str, class_name: str) -> dict[str, Any]:
    """
    返回指定笔记类型下某 class 的完整配置(用户值覆盖默认值)。
    """
    cfg = dict(DEFAULT_CLASS_CONFIG)
    user = get_note_type_config(note_type_name).get(class_name, {})
    if isinstance(user, dict):
        for key in DEFAULT_CLASS_CONFIG:
            if key in user:
                cfg[key] = user[key]
    return cfg
