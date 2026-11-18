"""天气数据层测试：预报解析、回退逻辑与来源标记。"""

import json
import threading
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from travel_advisor import engine, weather, weather_api
from travel_advisor.cities import resolve

SAMPLE = {
    "code": "200",
    "updateTime": "2026-11-18T10:00+08:00",
    "daily": [
        {
            "fxDate": "2026-11-20",
            "tempMax": "20",
            "tempMin": "12",
            "textDay": "小雨",
            "precip": "3.2",
            "uvIndex": "7",
            "humidity": "80",
            "windScaleDay": "3-4",
        }
    ],
}


@pytest.fixture(autouse=True)
def _clear_cache():
    weather_api._CACHE.clear()
    weather_api._FAIL_CACHE.clear()


def test_parse_daily_maps_fields():
    forecast = weather_api.parse_daily(SAMPLE, date(2026, 11, 20))
    assert forecast.t_max == 20
    assert forecast.t_min == 12
    assert forecast.text == "小雨"
    assert forecast.uv_index == 7
    assert forecast.observed_at == "2026-11-18T10:00+08:00"


def test_parse_out_of_window_raises():
    with pytest.raises(weather_api.ForecastOutOfRange):
        weather_api.parse_daily(SAMPLE, date(2026, 12, 20))


def test_rain_probability_heuristics():
    assert weather_api._rain_probability("小雨", 2) == 0.55
    assert weather_api._rain_probability("大雨", 30) == 0.85
    assert weather_api._rain_probability("晴", 0) == 0.05
    assert weather_api._rain_probability("多云", 0) == 0.15


def test_from_forecast_marks_source():
    forecast = weather_api.parse_daily(SAMPLE, date(2026, 11, 20))
    profile = weather.from_forecast(forecast)
    assert profile.source == "forecast"
    assert profile.estimated is False
    assert profile.provider == "和风天气"
    assert profile.umbrella is True
    assert profile.sunscreen is True
    data = profile.to_dict()
    assert data["estimated"] is False
    assert data["source"] == "forecast"


def test_estimate_without_key_uses_climate():
    profile = weather.estimate(resolve("上海"), date(2026, 11, 20))
    assert profile.source == "climate"
    assert profile.estimated is True
    assert profile.error is None


def test_estimate_bad_host_falls_back(monkeypatch):
    monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_KEY", "dummy")
    monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_TIMEOUT", "0.5")
    profile = weather.estimate(resolve("上海"), date(2026, 11, 20))
    assert profile.source == "climate"
    assert profile.estimated is True
    assert profile.error


def test_normalize_base_url():
    assert weather_api._normalize_base_url("kw3h2ucx82.re.qweatherapi.com") == "https://kw3h2ucx82.re.qweatherapi.com"
    assert weather_api._normalize_base_url("https://a.re.qweatherapi.com/") == "https://a.re.qweatherapi.com"
    assert weather_api._normalize_base_url("http://127.0.0.1:8000/v7/weather/7d") == "http://127.0.0.1:8000"
    assert weather_api._normalize_base_url("  \"https://a.re.qweatherapi.com\"  ") == "https://a.re.qweatherapi.com"
    assert weather_api._normalize_base_url("") == ""
    assert weather_api._normalize_base_url("ftp://example.com") == ""


def test_engine_adds_weather_warning(monkeypatch):
    monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_KEY", "dummy")
    monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_BASE_URL", "http://127.0.0.1:9")
    monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_TIMEOUT", "0.5")
    payload = engine.advise(city="上海", day=date(2026, 11, 20), mode_id="commute", use_llm=False)
    assert any("天气接口不可用" in item for item in payload["warnings"])
    assert payload["meta"]["weather_source"] == "climate"


class _FakeQWeather(BaseHTTPRequestHandler):
    requests: list[str] = []

    def do_GET(self):  # noqa: N802
        type(self).requests.append(self.path)
        body = json.dumps(SAMPLE).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # noqa: D401
        pass


def test_fetch_forecast_happy_path(monkeypatch):
    _FakeQWeather.requests = []
    server = HTTPServer(("127.0.0.1", 0), _FakeQWeather)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_KEY", "dummy")
        monkeypatch.setenv("TRAVEL_ADVISOR_WEATHER_BASE_URL", f"http://127.0.0.1:{port}")
        profile = weather.estimate(resolve("上海"), date(2026, 11, 20))
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert profile.source == "forecast"
    assert profile.estimated is False
    assert profile.t_max == 20
    assert profile.condition == "小雨"
    assert any("/v7/weather/7d" in item and "location=" in item for item in _FakeQWeather.requests)
