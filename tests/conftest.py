"""测试默认离线：清掉可能来自 .env 的配置，并在每个用例前重置进程内缓存与限流桶。"""

import pytest

from travel_advisor import app as app_module
from travel_advisor import engine


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    engine.clear_cache()
    app_module._RATE_BUCKETS.clear()
    for name in (
        "TRAVEL_ADVISOR_WEATHER_KEY",
        "QWEATHER_KEY",
        "TRAVEL_ADVISOR_WEATHER_BASE_URL",
        "TRAVEL_ADVISOR_RATE_LIMIT",
        "TRAVEL_ADVISOR_CACHE_TTL",
        "TRAVEL_ADVISOR_LLM_ENABLED",
    ):
        monkeypatch.delenv(name, raising=False)
