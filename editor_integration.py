"""
编辑器接入 (F1 + F2 + F3 编排)

监听 editor_did_load_note(打开编辑器 / 切换笔记类型 / 重载笔记时触发),
解析当前笔记类型的 CSS,结合用户配置生成按钮数据,注入前端运行时渲染。
"""

from __future__ import annotations

import json
import os
from typing import Any

from aqt import gui_hooks, mw
from aqt.editor import Editor

from . import config as cfg
from .css_parser import css_summary, parse_css, safe_preview_style
from .i18n import js_strings, tr
from .log import log

_SAVE_ORDER_PREFIX = "sbfe_save_order:"

_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
_RUNTIME_PATH = os.path.join(_WEB_DIR, "runtime.js")

# 缓存运行时 JS(文件内容在插件生命周期内不变)
_runtime_cache: str | None = None


def _runtime_js() -> str:
    global _runtime_cache
    if _runtime_cache is None:
        with open(_RUNTIME_PATH, encoding="utf-8") as fp:
            _runtime_cache = fp.read()
    return _runtime_cache


def _build_payload(editor: Editor) -> dict[str, Any]:
    """根据当前编辑器笔记构建前端渲染所需的数据。失败时返回空按钮列表。"""
    empty = {"classes": [], "i18n": js_strings()}

    g = cfg.get_global()
    if not g.get("enabled", True):
        return empty

    note = getattr(editor, "note", None)
    if note is None:
        return empty

    try:
        note_type = editor.note_type()
    except Exception:
        return empty
    if not note_type:
        return empty

    css = note_type.get("css") or ""
    note_type_name = note_type.get("name") or ""

    parsed = parse_css(css)
    if not parsed:
        return empty

    ignored = set(g.get("ignored_classes", []))
    default_tag = g.get("default_tag", "span") or "span"
    show_tooltip_css = g.get("show_css_preview_tooltip", True)

    items = []
    for parse_index, pc in enumerate(parsed):
        if pc.name in ignored:
            continue

        cc = cfg.get_class_config(note_type_name, pc.name)
        if not cc.get("visible", True):
            continue

        order = cc.get("order")
        effective_order = order if isinstance(order, int) else parse_index

        tag = (cc.get("tag") or "").strip() or default_tag
        label = (cc.get("display_name") or "").strip() or pc.name

        # tooltip:class 名 + 快捷键 + CSS 摘要
        tip_lines = [pc.name]
        shortcut = (cc.get("shortcut") or "").strip()
        if shortcut:
            tip_lines.append(f"{tr('tooltip_shortcut')}: {shortcut}")
        if show_tooltip_css and pc.declarations:
            tip_lines.append("─" * 12)
            tip_lines.append(css_summary(pc.declarations))
        tooltip = "\n".join(tip_lines)

        items.append(
            {
                "_order": effective_order,
                "_index": parse_index,
                "name": pc.name,
                "label": label,
                "tag": tag,
                "color": (cc.get("color") or "").strip(),
                "shortcut": shortcut,
                "previewStyle": safe_preview_style(pc.declarations),
                "tooltip": tooltip,
            }
        )

    # 按 order 升序排列(order 相同则保持解析顺序)
    items.sort(key=lambda it: (it["_order"], it["_index"]))
    for it in items:
        it.pop("_order", None)
        it.pop("_index", None)

    return {
        "classes": items,
        "noteType": note_type_name,
        "overflowMode": g.get("button_overflow_mode", "dropdown"),
        "overflowThreshold": g.get("button_overflow_threshold", 8),
        "showPreview": g.get("show_button_style_preview", True),
        "i18n": js_strings(),
    }


def _on_editor_did_load_note(editor: Editor) -> None:
    try:
        payload = _build_payload(editor)
        js = (
            _runtime_js()
            + "\n;try{window.__sbfe&&window.__sbfe.render("
            + json.dumps(payload, ensure_ascii=False)
            + ");}catch(e){console.error('[StyleButtons]',e);}"
        )
        editor.web.eval(js)
    except Exception as exc:  # pragma: no cover - 防御性,绝不影响编辑器
        log(f"渲染样式按钮失败: {exc}")


def _save_order(note_type_name: str, ordered_classes: list[str]) -> None:
    """把新的按钮顺序写回配置:为每个 class 设置 order = 其在列表中的下标。"""
    if not note_type_name or not isinstance(ordered_classes, list):
        return
    pkg = cfg._package()
    raw = mw.addonManager.getConfig(pkg) or {}
    if not isinstance(raw, dict):
        raw = {}

    note_types = raw.get("note_types")
    if not isinstance(note_types, dict):
        note_types = raw["note_types"] = {}
    nt = note_types.get(note_type_name)
    if not isinstance(nt, dict):
        nt = note_types[note_type_name] = {}

    for index, class_name in enumerate(ordered_classes):
        if not isinstance(class_name, str):
            continue
        entry = nt.get(class_name)
        if not isinstance(entry, dict):
            entry = nt[class_name] = {}
        entry["order"] = index

    mw.addonManager.writeConfig(pkg, raw)


def _on_js_message(handled, message: str, context):
    """接收前端拖拽排序后的保存请求(JS -> Python)。"""
    if not isinstance(context, Editor):
        return handled
    if not isinstance(message, str) or not message.startswith(_SAVE_ORDER_PREFIX):
        return handled
    try:
        import json as _json

        data = _json.loads(message[len(_SAVE_ORDER_PREFIX):])
        _save_order(data.get("noteType", ""), data.get("order", []))
    except Exception as exc:
        log(f"保存按钮排序失败: {exc}")
    return (True, None)


def register() -> None:
    gui_hooks.editor_did_load_note.append(_on_editor_did_load_note)
    gui_hooks.webview_did_receive_js_message.append(_on_js_message)
