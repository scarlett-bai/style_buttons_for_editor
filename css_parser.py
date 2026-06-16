"""
CSS 解析模块 (F1)

从 Note Type 的 Styling (CSS) 文本中解析出所有自定义 class，并提取每个 class 的
关键声明(用于按钮样式预览与 tooltip)。

设计目标:
- 纯标准库实现，无外部依赖，保证在各版本 Anki 中可用
- 健壮:遇到语法异常时不抛出，graceful 降级(返回已解析到的内容)
- 性能:单遍字符扫描，满足 PRD 对 50ms 的要求

解析规则(对应 PRD 3.2.2 / 8.1):
- 基础 class:`.name { ... }`
- 逗号分隔:`.a, .b { ... }` 分别提取
- 组合/嵌套选择器:`.card .highlight { ... }` 仅取最后一个简单选择器中的 class
- 复合选择器:`.btn.primary { ... }` 同时提取 btn 与 primary(作用于同一元素)
- 伪类/伪元素:`.tip:hover`、`.x::before` 自动在 `.` 处截断,只取 class 名
- 注释 `/* ... */`:整体剔除
- @media / @supports:解析其内部规则中的 class
- @keyframes / @font-face / @page 等:整块忽略(不含页面 class)
- :root 中的 CSS 变量:作为普通选择器(无 class)自然被忽略
- 去重:同名 class 只保留一次,声明以最后一次定义为准(E10)
"""

from __future__ import annotations

import re

# class 名 token:首字符不能是数字(CSS 规范),允许字母/下划线/连字符/非 ASCII(中文等)
_CLASS_TOKEN_RE = re.compile("\\.(-?[_a-zA-Z\\u00a0-\\uffff][\\w\\-\\u00a0-\\uffff]*)")

# 组合器:空白、>、+、~
_COMBINATOR_RE = re.compile(r"[\s>+~]+")

# 整块忽略的 at-rule(其内部不包含可用于内容标记的 class)
_SKIP_AT_RULES = {
    "@keyframes",
    "@-webkit-keyframes",
    "@-moz-keyframes",
    "@-o-keyframes",
    "@font-face",
    "@page",
    "@counter-style",
    "@font-feature-values",
    "@property",
}

# “透明”at-rule:本身不是选择器,但其内部的规则需要继续解析
_TRANSPARENT_AT_RULES = {
    "@media",
    "@supports",
    "@document",
    "@-moz-document",
    "@layer",
    "@container",
}


def strip_comments(css: str) -> str:
    """移除 CSS 注释 /* ... */(包含跨行)。未闭合的注释按到结尾处理。"""
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _extract_classes_from_selector(selector: str) -> list[str]:
    """
    从单条选择器(逗号分隔后的一段)中按规则提取 class 名。
    仅取最后一个复合选择器中的 class。
    """
    selector = selector.strip()
    if not selector or selector.startswith("@"):
        return []
    parts = _COMBINATOR_RE.split(selector)
    if not parts:
        return []
    last = parts[-1]
    return _CLASS_TOKEN_RE.findall(last)


def _split_declarations(body: str) -> list[tuple[str, str]]:
    """将规则体解析为 (property, value) 列表。容错:忽略不含冒号的片段。"""
    decls: list[tuple[str, str]] = []
    for chunk in body.split(";"):
        chunk = chunk.strip()
        if not chunk or ":" not in chunk:
            continue
        prop, _, value = chunk.partition(":")
        prop = prop.strip().lower()
        value = value.strip()
        if prop and value:
            decls.append((prop, value))
    return decls


class ParsedClass:
    """单个解析出的 class 及其合并后的声明(后定义覆盖先定义)。"""

    __slots__ = ("name", "declarations")

    def __init__(self, name: str) -> None:
        self.name = name
        # 保持插入顺序的属性 -> 值映射
        self.declarations: dict[str, str] = {}

    def update(self, decls: list[tuple[str, str]]) -> None:
        for prop, value in decls:
            self.declarations[prop] = value

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ParsedClass({self.name!r}, {self.declarations!r})"


def parse_css(css: str) -> "list[ParsedClass]":
    """
    解析 CSS 文本,返回按首次出现顺序排列的 ParsedClass 列表(已去重)。

    任何异常都被吞掉并返回当前已解析到的结果,确保不影响编辑器。
    """
    if not css:
        return []

    try:
        return _parse_css_impl(css)
    except Exception as exc:  # pragma: no cover - 防御性
        from .log import log

        log(f"CSS 解析异常,已降级: {exc}")
        return []


def _parse_css_impl(css: str) -> "list[ParsedClass]":
    css = strip_comments(css)

    ordered: list[str] = []
    by_name: dict[str, ParsedClass] = {}

    # 栈中每一帧描述一个 `{` 打开的块:
    #   kind: "selector" | "transparent" | "skip"
    #   selector: 选择器原文(仅 selector 帧有意义)
    #   body_start: 块体在 css 中的起始索引(用于切片提取声明)
    stack: list[dict] = []
    buf: list[str] = []  # 自上一个 { } ; 以来累积的文本(prelude)
    i = 0
    n = len(css)

    def in_skip() -> bool:
        return any(f["kind"] == "skip" for f in stack)

    while i < n:
        c = css[i]
        if c == "{":
            prelude = "".join(buf).strip()
            buf = []
            head = prelude.lstrip()

            if in_skip():
                # 已在被忽略的块内部,所有嵌套块同样忽略
                stack.append({"kind": "skip"})
            elif head.startswith("@"):
                at_name = head.split(None, 1)[0].lower()
                # 去掉可能的尾随内容,仅比对 at 关键字
                at_keyword = re.match(r"@[-\w]+", at_name)
                at_keyword = at_keyword.group(0) if at_keyword else at_name
                if at_keyword in _SKIP_AT_RULES:
                    stack.append({"kind": "skip"})
                elif at_keyword in _TRANSPARENT_AT_RULES:
                    stack.append({"kind": "transparent"})
                else:
                    # 未知 at-rule:保守地当作透明块,继续解析内部
                    stack.append({"kind": "transparent"})
            else:
                stack.append(
                    {"kind": "selector", "selector": prelude, "body_start": i + 1}
                )
        elif c == "}":
            buf = []
            if stack:
                frame = stack.pop()
                if frame["kind"] == "selector":
                    body = css[frame["body_start"] : i]
                    # 仅当本规则体不含嵌套块时才解析声明(避免把嵌套规则当声明)
                    decls = (
                        _split_declarations(body) if "{" not in body else []
                    )
                    for selector in frame["selector"].split(","):
                        for cls in _extract_classes_from_selector(selector):
                            pc = by_name.get(cls)
                            if pc is None:
                                pc = ParsedClass(cls)
                                by_name[cls] = pc
                                ordered.append(cls)
                            pc.update(decls)
        elif c == ";":
            # 声明结束或 @import/@charset 等语句结束,丢弃 prelude
            buf = []
        else:
            buf.append(c)
        i += 1

    return [by_name[name] for name in ordered]


# 用于按钮样式预览的“安全”CSS 属性白名单(对应 PRD Q5 方案 A)。
# 仅这些属性会被应用到按钮本身,避免 display/position/transform 等破坏按钮布局。
SAFE_PREVIEW_PROPS = (
    "color",
    "background-color",
    "background",
    "font-weight",
    "font-style",
    "font-family",
    "font-variant",
    "text-decoration",
    "text-decoration-line",
    "text-decoration-color",
    "text-decoration-style",
    "text-transform",
    "letter-spacing",
)


def safe_preview_style(declarations: dict[str, str]) -> str:
    """从声明中筛出可安全应用于按钮的属性,拼成 inline style 字符串。"""
    parts = []
    for prop in SAFE_PREVIEW_PROPS:
        if prop in declarations:
            value = declarations[prop]
            # 去掉 !important,避免覆盖按钮自身的 hover 等状态
            value = re.sub(r"\s*!\s*important", "", value, flags=re.IGNORECASE).strip()
            if value:
                parts.append(f"{prop}: {value}")
    return "; ".join(parts)


def css_summary(declarations: dict[str, str], max_lines: int = 6) -> str:
    """生成用于 tooltip 的 CSS 属性摘要(最多 max_lines 条)。"""
    items = list(declarations.items())[:max_lines]
    return "\n".join(f"{prop}: {value};" for prop, value in items)
