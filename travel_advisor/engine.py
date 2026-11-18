"""把请求、规则引擎与大模型润色串起来。"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import modes as _modes  # noqa: F401 - 导入即完成模式注册
from .context import build_context
from .llm import config_from_env, polish
from .registry import describe_all, get as get_mode

ENGINE_VERSION = "1.1.0"

BASE_DISCLAIMER = "限行、景区预约与交通运营信息请以当地主管部门当日发布为准。"


def _disclaimer(weather: Any) -> str:
    if weather.estimated:
        return "天气为基于 1991—2020 气候常年值的估算，不是实时预报。" + BASE_DISCLAIMER
    return (
        f"天气来自{weather.provider or '天气预报'}（更新于 {weather.observed_at or '未知时间'}），仅覆盖预报窗口。"
        + BASE_DISCLAIMER
    )


class UnknownModeError(ValueError):
    def __init__(self, mode_id: str) -> None:
        self.mode_id = mode_id
        super().__init__(f"未知的出行模式：{mode_id}")


def modes_info() -> list[dict[str, Any]]:
    return describe_all()


def advise(
    *,
    city: str,
    day: date,
    mode_id: str,
    options: dict[str, Any] | None = None,
    use_llm: bool = True,
) -> dict[str, Any]:
    mode = get_mode(mode_id)
    if mode is None:
        raise UnknownModeError(mode_id)

    ctx = build_context(day, city, options)
    result = mode.advise(ctx)
    facts = ctx.facts()

    polish_text: str | None = None
    polish_error: str | None = None
    polish_model: str | None = None
    if use_llm:
        config = config_from_env()
        if config is not None:
            polish_model = config.model
            polish_text, polish_error = polish(facts, result.to_dict(), config)

    warnings: list[str] = []
    if not ctx.city.matched:
        warnings.append(f"未收录「{ctx.requested_city}」，已按温带季风气候的常年平均估算。")
    if ctx.holiday.estimated:
        warnings.append("该年份的放假安排尚未正式公布，假期判断为估算值。")
    if ctx.weather.error:
        warnings.append(f"天气接口不可用（{ctx.weather.error}），已回退到气候常年值。")
        if "Invalid Host" in ctx.weather.error:
            warnings.append("请把和风控制台里的 API Host 填入 TRAVEL_ADVISOR_WEATHER_BASE_URL。")

    return {
        "request": {
            "city": city,
            "date": day.isoformat(),
            "mode": mode_id,
            "options": ctx.options,
        },
        "city": ctx.city.to_dict(),
        "date": facts["calendar"],
        "result": result.to_dict(),
        "facts": facts,
        "polish": {
            "used": polish_text is not None,
            "text": polish_text,
            "model": polish_model,
            "error": polish_error,
        },
        "warnings": warnings,
        "meta": {
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "engine_version": ENGINE_VERSION,
            "disclaimer": _disclaimer(ctx.weather),
            "weather_source": ctx.weather.source,
        },
    }
