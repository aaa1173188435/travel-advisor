"""模式（Mode）基类：新增一种出行场景 = 新增一个 Mode 子类并注册。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from ..context import AdviceContext

Level = Literal["good", "info", "warn", "bad"]


@dataclass
class Item:
    label: str
    text: str
    level: Level = "info"

    def to_dict(self) -> dict[str, str]:
        return {"label": self.label, "text": self.text, "level": self.level}


@dataclass
class Section:
    id: str
    title: str
    icon: str
    items: list[Item] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "icon": self.icon,
            "items": [item.to_dict() for item in self.items],
        }


@dataclass
class ModeResult:
    mode_id: str
    mode_name: str
    headline: str
    score: int
    score_label: str
    tags: list[str]
    sections: list[Section]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode_id": self.mode_id,
            "mode_name": self.mode_name,
            "headline": self.headline,
            "score": self.score,
            "score_label": self.score_label,
            "tags": self.tags,
            "sections": [section.to_dict() for section in self.sections],
        }


def clamp(value: float, low: int = 30, high: int = 100) -> int:
    return int(max(low, min(high, round(value))))


def score_label(score: int) -> str:
    if score >= 85:
        return "顺畅"
    if score >= 70:
        return "良好"
    if score >= 55:
        return "一般"
    if score >= 40:
        return "较差"
    return "不宜"


class Mode(ABC):
    """一种出行场景的规则处理器。"""

    id: str = ""
    name: str = ""
    icon: str = "📍"
    description: str = ""
    # 供前端自动渲染的附加选项；格式见 README
    options: list[dict[str, Any]] = []

    @abstractmethod
    def advise(self, ctx: AdviceContext) -> ModeResult:
        """根据上下文产出建议。"""

    def normalize_options(self, options: dict[str, Any]) -> dict[str, Any]:
        """把请求里的原始选项收敛成后端可用的值。"""
        return dict(options)

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "description": self.description,
            "options": self.options,
        }
