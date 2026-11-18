"""请求/响应的数据契约（Pydantic v2）。"""

from __future__ import annotations

from datetime import date as DateType
from typing import Any

from pydantic import BaseModel, Field, field_validator

_MIN_DATE = DateType(1970, 1, 1)
_MAX_DATE = DateType(2100, 12, 31)


class AdviceRequest(BaseModel):
    city: str = Field(min_length=1, max_length=40, description="城市名，支持拼音与简称")
    date: DateType = Field(description="出行日期，YYYY-MM-DD")
    mode: str = Field(min_length=1, max_length=30, description="出行模式 id，如 commute / travel")
    options: dict[str, Any] = Field(default_factory=dict, description="模式专属选项")
    use_llm: bool = Field(default=True, description="是否尝试大模型润色（未配置 Key 时自动跳过）")

    @field_validator("date")
    @classmethod
    def _check_range(cls, value: DateType) -> DateType:
        if not (_MIN_DATE <= value <= _MAX_DATE):
            raise ValueError("日期需在 1970-01-01 至 2100-12-31 之间")
        return value

    @field_validator("city")
    @classmethod
    def _strip_city(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("城市不能为空")
        return cleaned
