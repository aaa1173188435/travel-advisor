"""天气画像：优先使用和风天气的日预报，缺失时回退到气候常年值。

- 有 `TRAVEL_ADVISOR_WEATHER_KEY` 且日期在预报窗口内 → `source="forecast"`
- 其余情况（未配置、超出窗口、接口失败）→ `source="climate"`，并保留失败原因
"""

from __future__ import annotations

import calendar
import math
from dataclasses import dataclass
from datetime import date
from typing import Any

from .cities import CityProfile

_COMFORT_LABELS = (
    (0, "严寒"),
    (10, "寒冷"),
    (18, "偏凉"),
    (26, "舒适"),
    (32, "偏热"),
    (999, "炎热"),
)


def display_temp(value: float) -> int:
    """与前端 Math.round 保持一致的四舍五入（.5 向上）。"""
    return int(math.floor(value + 0.5))


def _comfort(t_mean: float) -> str:
    for limit, label in _COMFORT_LABELS:
        if t_mean < limit:
            return label
    return "炎热"  # pragma: no cover


def _clothing(t_max: float, t_min: float) -> str:
    if t_max >= 33:
        return "短袖短裤为主，备好防晒与补水"
    if t_max >= 28:
        return "短袖或薄衬衫，室内空调房可备一件薄外套"
    if t_max >= 22:
        return "长袖加薄外套，早晚可以再添一件"
    if t_max >= 16:
        return "薄外套或针织衫，怕冷的人加一件内搭"
    if t_max >= 10:
        return "夹克加毛衣，注意早晚温差"
    if t_max >= 0:
        return "厚外套或羽绒服，围巾手套可以带上"
    return "羽绒服、帽子、手套齐全，尽量减少长时间户外停留"


def _level(rain_prob: float, t_max: float) -> str:
    if t_max >= 35:
        return "hot"
    if t_max <= 0:
        return "cold"
    if rain_prob >= 0.45:
        return "rain"
    return "normal"


def _condition_text(rain_prob: float, t_max: float) -> str:
    if rain_prob >= 0.45:
        condition = "降水概率较高"
    elif rain_prob >= 0.30:
        condition = "可能有阵雨"
    elif rain_prob >= 0.18:
        condition = "局部可能有雨"
    else:
        condition = "以晴到多云为主"
    if t_max >= 35:
        return condition + "，高温"
    if t_max <= 0:
        return condition + "，严寒"
    return condition


@dataclass
class WeatherProfile:
    t_max: float
    t_min: float
    t_mean: float
    rain_prob: float
    condition: str
    level: str
    comfort: str
    clothing: str
    umbrella: bool
    sunscreen: bool
    diurnal_range: float
    source: str = "climate"
    provider: str | None = None
    observed_at: str | None = None
    error: str | None = None
    estimated: bool = True

    def to_dict(self) -> dict[str, Any]:
        # 保留两位小数，避免前端再次取整时出现「后端 2 / 前端 3」的偏差
        return {
            "t_max": round(self.t_max, 2),
            "t_min": round(self.t_min, 2),
            "t_mean": round(self.t_mean, 2),
            "rain_prob": round(self.rain_prob, 2),
            "condition": self.condition,
            "level": self.level,
            "comfort": self.comfort,
            "clothing": self.clothing,
            "umbrella": self.umbrella,
            "sunscreen": self.sunscreen,
            "diurnal_range": round(self.diurnal_range, 2),
            "source": self.source,
            "provider": self.provider,
            "observed_at": self.observed_at,
            "error": self.error,
            "estimated": self.estimated,
        }


def climate_estimate(city: CityProfile, day: date) -> WeatherProfile:
    """用 1991—2020 气候常年值估算「常年同期」画像。"""
    index = day.month - 1
    days_in_month = calendar.monthrange(day.year, day.month)[1]
    fraction = (day.day - 0.5) / days_in_month
    nxt = (index + 1) % 12

    def blend(values: list[float]) -> float:
        return values[index] * (1 - fraction) + values[nxt] * fraction

    t_max = blend(city.high)
    t_min = blend(city.low)
    rainy_days = blend(city.rainy_days)
    rain_prob = max(0.02, min(0.85, rainy_days / days_in_month))

    t_mean = (t_max + t_min) / 2
    return WeatherProfile(
        t_max=t_max,
        t_min=t_min,
        t_mean=t_mean,
        rain_prob=rain_prob,
        condition=_condition_text(rain_prob, t_max),
        level=_level(rain_prob, t_max),
        comfort=_comfort(t_mean),
        clothing=_clothing(t_max, t_min),
        umbrella=rain_prob >= 0.30,
        sunscreen=t_max >= 28 and day.month in (4, 5, 6, 7, 8, 9),
        diurnal_range=t_max - t_min,
        source="climate",
        estimated=True,
    )


def from_forecast(forecast: Any) -> WeatherProfile:
    """把和风的日预报转成统一的 WeatherProfile。"""
    from .weather_api import _rain_probability

    rain_prob = _rain_probability(forecast.text, forecast.precip_mm)
    t_mean = (forecast.t_max + forecast.t_min) / 2
    return WeatherProfile(
        t_max=forecast.t_max,
        t_min=forecast.t_min,
        t_mean=t_mean,
        rain_prob=rain_prob,
        condition=forecast.text,
        level=_level(rain_prob, forecast.t_max),
        comfort=_comfort(t_mean),
        clothing=_clothing(forecast.t_max, forecast.t_min),
        umbrella=rain_prob >= 0.30,
        sunscreen=forecast.uv_index >= 6,
        diurnal_range=forecast.t_max - forecast.t_min,
        source="forecast",
        provider=forecast.provider,
        observed_at=forecast.observed_at,
        estimated=False,
    )


def estimate(city: CityProfile, day: date) -> WeatherProfile:
    """优先取预报；任何问题都静默回退到常年值，并把原因留在 error 字段。"""
    fallback = climate_estimate(city, day)

    try:
        from .weather_api import (
            ForecastOutOfRange,
            WeatherApiError,
            fetch_forecast,
            is_configured,
        )
    except ImportError:  # pragma: no cover
        return fallback

    if not is_configured():
        return fallback

    try:
        forecast = fetch_forecast(city, day)
    except ForecastOutOfRange:
        return fallback
    except WeatherApiError as exc:
        fallback.error = str(exc)
        return fallback
    except Exception as exc:  # noqa: BLE001
        fallback.error = f"{type(exc).__name__}: {exc}"
        return fallback

    return from_forecast(forecast)
