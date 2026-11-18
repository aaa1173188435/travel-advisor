"""规则引擎与模式注册测试。"""

from datetime import date

import pytest

from travel_advisor import engine
from travel_advisor.cities import resolve
from travel_advisor.engine import UnknownModeError


def test_builtin_modes_registered():
    ids = {item["id"] for item in engine.modes_info()}
    assert {"commute", "travel"} <= ids


def test_mode_describe_has_options():
    commute = next(item for item in engine.modes_info() if item["id"] == "commute")
    keys = {option["key"] for option in commute["options"]}
    assert {"depart_time", "transport"} <= keys


def test_commute_on_public_holiday_is_relaxed():
    payload = engine.advise(city="上海", day=date(2026, 10, 2), mode_id="commute", use_llm=False)
    result = payload["result"]
    assert result["score"] >= 80
    assert "不用赶通勤" in result["headline"]
    assert payload["date"]["day_type"] == "holiday"


def test_commute_peak_lowers_score():
    morning = engine.advise(
        city="北京", day=date(2026, 11, 19), mode_id="commute", options={"depart_time": "08:30"}, use_llm=False
    )
    offpeak = engine.advise(
        city="北京", day=date(2026, 11, 19), mode_id="commute", options={"depart_time": "10:30"}, use_llm=False
    )
    assert morning["result"]["score"] < offpeak["result"]["score"]
    assert "早高峰" in morning["result"]["tags"]


def test_rainy_day_warns():
    # 广州 6 月降水概率高
    payload = engine.advise(city="广州", day=date(2026, 6, 16), mode_id="commute", use_llm=False)
    texts = " ".join(item["text"] for section in payload["result"]["sections"] for item in section["items"])
    assert "雨" in texts


def test_travel_holiday_crowd_section():
    payload = engine.advise(
        city="北京",
        day=date(2027, 2, 6),
        mode_id="travel",
        options={"days": 4, "interests": ["人文历史"]},
        use_llm=False,
    )
    sections = {section["id"]: section for section in payload["result"]["sections"]}
    assert "crowd" in sections
    assert "人流" in sections["crowd"]["title"]
    assert payload["date"]["holiday_name"] == "春节"


def test_unknown_city_falls_back_with_warning():
    payload = engine.advise(city="火星", day=date(2026, 11, 20), mode_id="commute", use_llm=False)
    assert payload["city"]["matched"] is False
    assert payload["warnings"]
    assert payload["result"]["score"] > 0


def test_new_city_baishan_is_available():
    profile = resolve("白山市")
    assert profile.id == "baishan"
    assert profile.matched is True
    payload = engine.advise(city="白山市", day=date(2027, 1, 10), mode_id="travel", use_llm=False)
    assert payload["city"]["name"] == "白山"
    assert payload["result"]["sections"]


def test_fitness_mode_registered():
    ids = {item["id"] for item in engine.modes_info()}
    assert "fitness" in ids


def test_fitness_indoor_beats_outdoor_in_cold():
    day = date(2027, 1, 10)
    outdoor = engine.advise(city="白山", day=day, mode_id="fitness", options={"activity": "run"}, use_llm=False)
    indoor = engine.advise(city="白山", day=day, mode_id="fitness", options={"activity": "gym"}, use_llm=False)
    assert outdoor["result"]["score"] < indoor["result"]["score"]
    assert "寒冷" in outdoor["result"]["tags"] or "严寒" in outdoor["result"]["tags"]
    assert "室内" not in outdoor["result"]["tags"]
    assert "室内" in indoor["result"]["tags"]


def test_fitness_duration_and_intensity_applied():
    payload = engine.advise(
        city="上海",
        day=date(2026, 11, 21),
        mode_id="fitness",
        options={"activity": "gym", "duration": 90, "intensity": "hard"},
        use_llm=False,
    )
    texts = " ".join(item["text"] for section in payload["result"]["sections"] for item in section["items"])
    assert "90 分钟" in texts
    assert "高强度" in texts


def test_missing_points_detects_holiday_omission():
    from travel_advisor.llm import missing_points

    assert missing_points("今天天气不错，适合出门。", ["节假日人流"]) == ["节假日人流"]
    assert missing_points("春节假期人流大，建议错峰。", ["节假日人流"]) == []


def test_llm_polish_is_rejected_when_it_ignores_holiday(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(engine, "polish", lambda *args, **kwargs: ("今天天气不错，适合出门。", None))
    payload = engine.advise(city="北京", day=date(2027, 2, 6), mode_id="travel", use_llm=True)
    assert payload["polish"]["used"] is False
    assert "遗漏" in (payload["polish"]["error"] or "")


def test_festival_affects_travel_advice():
    payload = engine.advise(city="北京", day=date(2026, 12, 25), mode_id="travel", use_llm=False)
    texts = " ".join(item["text"] for section in payload["result"]["sections"] for item in section["items"])
    assert "圣诞节" in texts
    assert "圣诞节" in payload["result"]["tags"]
    assert payload["facts"]["festival"]["name"] == "圣诞节"


def test_spring_festival_has_specific_travel_tips():
    payload = engine.advise(city="北京", day=date(2027, 2, 6), mode_id="travel", use_llm=False)
    sections = {section["id"]: section for section in payload["result"]["sections"]}
    assert "holiday" in sections
    text = " ".join(item["text"] for item in sections["holiday"]["items"])
    assert "返乡" in text and "庙会" in text


def test_llm_polish_rejected_when_festival_ignored(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setattr(engine, "polish", lambda *args, **kwargs: ("今天天气不错，适合出门。", None))
    payload = engine.advise(city="北京", day=date(2026, 12, 25), mode_id="travel", use_llm=True)
    assert payload["polish"]["used"] is False
    assert "遗漏" in (payload["polish"]["error"] or "")


def test_scores_are_bounded():
    for city in ("哈尔滨", "三亚", "拉萨"):
        for mode_id in ("commute", "travel"):
            payload = engine.advise(city=city, day=date(2026, 7, 20), mode_id=mode_id, use_llm=False)
            assert 0 <= payload["result"]["score"] <= 100


def test_unknown_mode_raises():
    with pytest.raises(UnknownModeError):
        engine.advise(city="上海", day=date(2026, 11, 20), mode_id="nope", use_llm=False)


def test_llm_disabled_does_not_call_model(monkeypatch):
    monkeypatch.delenv("TRAVEL_ADVISOR_LLM_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    payload = engine.advise(city="上海", day=date(2026, 11, 20), mode_id="commute", use_llm=True)
    assert payload["polish"]["used"] is False
    assert payload["polish"]["text"] is None


def test_llm_kill_switch_disables_polish(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("TRAVEL_ADVISOR_LLM_ENABLED", "0")
    payload = engine.advise(city="上海", day=date(2026, 11, 20), mode_id="commute", use_llm=True)
    assert payload["polish"]["used"] is False
    assert payload["result"]["sections"]


def test_polish_failure_falls_back(monkeypatch):
    monkeypatch.setenv("TRAVEL_ADVISOR_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("TRAVEL_ADVISOR_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("TRAVEL_ADVISOR_LLM_TIMEOUT", "0.5")
    payload = engine.advise(city="上海", day=date(2026, 11, 20), mode_id="commute", use_llm=True)
    assert payload["polish"]["used"] is False
    assert payload["polish"]["error"]
    assert payload["result"]["sections"]
