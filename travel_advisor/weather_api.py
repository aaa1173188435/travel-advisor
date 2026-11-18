"""和风天气（QWeather）日预报接入。

注意：2024 年起和风为每个账号分配专属 API Host（形如 ``abc123.re.qweatherapi.com``），
公共的 devapi.qweather.com / api.qweather.com 会返回 403 Invalid Host。
把控制台里的 API Host 填到 ``TRAVEL_ADVISOR_WEATHER_BASE_URL`` 即可。

未配置 Key / Host、日期超出预报窗口或接口失败时，调用方会回退到气候常年值。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .env import load_env_files

load_env_files()

DEFAULT_BASE_URL = ""
CACHE_TTL_SECONDS = 600
FAIL_TTL_SECONDS = 60

_CACHE: dict[str, tuple[float, "DailyForecast"]] = {}
_FAIL_CACHE: dict[str, tuple[float, str]] = {}


class WeatherApiError(RuntimeError):
    """接口不可用（配置错误、鉴权失败、网络异常等）。"""


class ForecastOutOfRange(WeatherApiError):
    """日期不在接口返回的预报窗口内，属于正常情况，不应作为告警。"""


@dataclass
class DailyForecast:
    day: date
    t_max: float
    t_min: float
    text: str
    precip_mm: float
    uv_index: int
    humidity: int
    wind_scale: str
    observed_at: str
    provider: str = "和风天气"


def _normalize_base_url(raw: str) -> str:
    """把 `abc.re.qweatherapi.com`、带路径的地址统一成 `https://abc.re.qweatherapi.com`。"""
    value = (raw or "").strip().strip('"').strip("'")
    if not value:
        return ""
    if "://" not in value:
        value = "https://" + value
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def config() -> tuple[str, str, float]:
    """返回 (base_url, api_key, timeout)；未配置时 base_url/key 为空串。"""
    base_url = _normalize_base_url(os.getenv("TRAVEL_ADVISOR_WEATHER_BASE_URL") or DEFAULT_BASE_URL)
    api_key = (os.getenv("TRAVEL_ADVISOR_WEATHER_KEY") or os.getenv("QWEATHER_KEY") or "").strip()
    try:
        timeout = float(os.getenv("TRAVEL_ADVISOR_WEATHER_TIMEOUT", "6"))
    except ValueError:
        timeout = 6.0
    return base_url, api_key, timeout


def is_configured() -> bool:
    _, api_key, _ = config()
    return bool(api_key)


def status() -> dict[str, Any]:
    base_url, api_key, _ = config()
    if not api_key:
        return {"enabled": False, "reason": "未配置 TRAVEL_ADVISOR_WEATHER_KEY，天气使用气候常年值"}
    if not base_url:
        return {
            "enabled": False,
            "reason": "已配置 Key 但缺少 API Host：把和风控制台的 API Host 填入 TRAVEL_ADVISOR_WEATHER_BASE_URL",
        }
    return {"enabled": True, "provider": "和风天气", "base_url": base_url, "forecast_days": 7}


def _endpoint(base_url: str, days: str) -> str:
    return f"{base_url}/v7/weather/{days}"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _rain_probability(text: str, precip_mm: float) -> float:
    """和风日预报不直接给降水概率，按天气现象与降水量估算。"""
    if any(word in text for word in ("暴雨", "大暴雨", "特大暴雨")):
        return 0.9
    if "大雨" in text:
        return 0.85
    if "中雨" in text or "中雪" in text:
        return 0.7
    if any(word in text for word in ("小雨", "阵雨", "雷阵雨", "雨夹雪")):
        return 0.55
    if "雪" in text:
        return 0.6
    if precip_mm > 0:
        return 0.45
    if "阴" in text:
        return 0.25
    if "多云" in text:
        return 0.15
    return 0.05


def parse_daily(payload: dict[str, Any], day: date) -> DailyForecast:
    daily = payload.get("daily") or []
    for item in daily:
        if item.get("fxDate") == day.isoformat():
            text = str(item.get("textDay") or "未知")
            precip = _float(item.get("precip"))
            return DailyForecast(
                day=day,
                t_max=_float(item.get("tempMax")),
                t_min=_float(item.get("tempMin")),
                text=text,
                precip_mm=precip,
                uv_index=int(_float(item.get("uvIndex"))),
                humidity=int(_float(item.get("humidity"))),
                wind_scale=str(item.get("windScaleDay") or ""),
                observed_at=str(payload.get("updateTime") or ""),
            )
    raise ForecastOutOfRange(f"{day.isoformat()} 不在和风预报窗口内（最多 7 天）")


def _error_message(response: Any, body: Any) -> str:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and error.get("title"):
            return f"{error.get('title')}（HTTP {response.status_code}）"
        code = body.get("code")
        if code and str(code) != "200":
            return f"和风返回错误码 {code}（HTTP {response.status_code}）"
    return f"和风接口异常（HTTP {response.status_code}）"


def _request_days(base_url: str, api_key: str, timeout: float, days: str, location: str) -> dict[str, Any]:
    import httpx

    try:
        response = httpx.get(
            _endpoint(base_url, days),
            params={"location": location, "key": api_key, "lang": "zh"},
            timeout=timeout,
        )
    except Exception as exc:  # noqa: BLE001
        hint = "（请检查 TRAVEL_ADVISOR_WEATHER_BASE_URL 是否为完整地址，例如 https://xxx.re.qweatherapi.com）" if type(exc).__name__ == "UnsupportedProtocol" else ""
        raise WeatherApiError(f"请求和风超时或失败：{type(exc).__name__}{hint}") from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise WeatherApiError(f"和风返回了非 JSON 内容（HTTP {response.status_code}）") from exc

    if response.status_code != 200 or str(body.get("code")) != "200":
        raise WeatherApiError(_error_message(response, body))
    return body


def fetch_forecast(city: Any, day: date) -> DailyForecast:
    """按城市经纬度取指定日期的预报；失败抛 WeatherApiError。"""
    base_url, api_key, timeout = config()
    if not api_key:
        raise WeatherApiError("未配置 TRAVEL_ADVISOR_WEATHER_KEY")
    if not base_url:
        raise WeatherApiError("未配置 TRAVEL_ADVISOR_WEATHER_BASE_URL（和风控制台里的 API Host）")

    cache_key = f"{city.id}:{day.isoformat()}:{base_url}"
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > time.time():
        return cached[1]
    failed = _FAIL_CACHE.get(cache_key)
    if failed and failed[0] > time.time():
        raise WeatherApiError(failed[1])

    location = f"{city.lon:.2f},{city.lat:.2f}"
    try:
        forecast = _fetch_from_api(base_url, api_key, timeout, location, day)
    except WeatherApiError as exc:
        _FAIL_CACHE[cache_key] = (time.time() + FAIL_TTL_SECONDS, str(exc))
        raise
    _CACHE[cache_key] = (time.time() + CACHE_TTL_SECONDS, forecast)
    return forecast


def _fetch_from_api(base_url: str, api_key: str, timeout: float, location: str, day: date) -> DailyForecast:
    last_error: WeatherApiError | None = None
    for days in ("7d", "3d"):
        try:
            payload = _request_days(base_url, api_key, timeout, days, location)
        except WeatherApiError as exc:
            last_error = exc
            # 主机或鉴权问题不必换个预报窗口重试
            if "Invalid Host" in str(exc) or "401" in str(exc) or "403" in str(exc):
                raise
            continue
        return parse_daily(payload, day)

    raise last_error or WeatherApiError("和风接口不可用")
