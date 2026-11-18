"""测试默认离线：清掉可能来自 .env 的天气配置，避免测试联网或产生偶发差异。"""

import pytest


@pytest.fixture(autouse=True)
def _offline_weather(monkeypatch):
    for name in (
        "TRAVEL_ADVISOR_WEATHER_KEY",
        "QWEATHER_KEY",
        "TRAVEL_ADVISOR_WEATHER_BASE_URL",
    ):
        monkeypatch.delenv(name, raising=False)
