"""
国际化(i18n)— 中英文文案(对应 PRD 4.4)。

语言来源:config.global.language;为 "auto" 时跟随 Anki 界面语言。
class 名称本身不翻译(保持 CSS 原始名或用户自定义名)。
"""

from __future__ import annotations

from aqt import mw

DEFAULT_LANG = "en"

TRANSLATIONS = {
    "zh": {
        "menu_settings": "Style Buttons 设置…",
        "tooltip_shortcut": "快捷键",
        "more": "更多",
        "config_reset_notice": "Style Buttons 配置无法读取,已临时使用默认配置。",
        "wrap_error": "样式包裹失败,字段内容未改动。",
    },
    "en": {
        "menu_settings": "Style Buttons Settings…",
        "tooltip_shortcut": "Shortcut",
        "more": "More",
        "config_reset_notice": "Style Buttons config could not be read; using defaults for now.",
        "wrap_error": "Failed to apply style; the field was not modified.",
    },
}


def _resolve_lang() -> str:
    from .config import get_global

    lang = get_global().get("language", "auto")
    if lang in TRANSLATIONS:
        return lang
    # auto:跟随 Anki 界面语言
    try:
        anki_lang = (mw.pm.meta.get("defaultLang") or "").lower()
    except Exception:
        anki_lang = ""
    if anki_lang.startswith("zh"):
        return "zh"
    return DEFAULT_LANG


def tr(key: str) -> str:
    lang = _resolve_lang()
    table = TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG])
    return table.get(key, TRANSLATIONS[DEFAULT_LANG].get(key, key))


def js_strings() -> dict[str, str]:
    """供前端 runtime.js 使用的文案集合。"""
    return {
        "more": tr("more"),
        "tooltip_shortcut": tr("tooltip_shortcut"),
        "wrap_error": tr("wrap_error"),
    }
