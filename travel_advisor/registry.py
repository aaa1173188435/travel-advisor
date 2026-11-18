"""模式注册表：运行时按 id 查找，前端从 /api/modes 自动获得列表。

注意：本模块不导入具体的 Mode 实现，避免与 ``travel_advisor.modes`` 循环导入。
具体模式在 ``travel_advisor/modes/__init__.py`` 中导入并注册。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from .modes.base import Mode

_MODES: dict[str, "Mode"] = {}


def register(mode: "Mode") -> "Mode":
    if not mode.id:
        raise ValueError("Mode.id 不能为空")
    if mode.id in _MODES:
        raise ValueError(f"模式 {mode.id!r} 已注册")
    _MODES[mode.id] = mode
    return mode


def get(mode_id: str) -> "Mode | None":
    return _MODES.get(mode_id)


def all_modes() -> list["Mode"]:
    return sorted(_MODES.values(), key=lambda mode: mode.id)


def describe_all() -> list[dict]:
    return [mode.describe() for mode in all_modes()]


def default_mode_id() -> str:
    modes = all_modes()
    return modes[0].id if modes else ""
