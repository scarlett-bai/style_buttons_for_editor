"""
日志辅助:统一前缀,写入 Anki 的 debug 日志/标准输出(对应 PRD 4.3)。
"""

from __future__ import annotations

PREFIX = "[StyleButtons]"


def log(message: str) -> None:
    try:
        print(f"{PREFIX} {message}")
    except Exception:
        pass
