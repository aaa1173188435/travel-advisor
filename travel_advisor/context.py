"""把一次请求的输入整理成规则引擎与模型都能消费的上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import cities, festivals, weather
from .cities import CityProfile
from .festivals import Festival
from .holidays import HolidayStatus, get_calendar, resolve
from .solar import SolarTerm, nearest_term, season_of, term_on
from .weather import WeatherProfile


@dataclass
class AdviceContext:
    day: date
    requested_city: str
    city: CityProfile
    holiday: HolidayStatus
    festival: Festival | None
    weather: WeatherProfile
    season: str
    solar_term: SolarTerm | None
    upcoming_term: SolarTerm
    term_offset: int
    next_holiday_name: str | None
    next_holiday_days: int | None
    options: dict[str, Any] = field(default_factory=dict)

    def option(self, key: str, default: Any = None) -> Any:
        return self.options.get(key, default)

    def facts(self) -> dict[str, Any]:
        """给规则引擎之外（大模型、前端、日志）使用的结构化事实。"""
        return {
            "date": self.day.isoformat(),
            "weekday": self.holiday.weekday_name,
            "city": {
                "name": self.city.name,
                "province": self.city.province,
                "matched": self.city.matched,
                "climate_note": self.city.climate_note,
                "tags": self.city.tags,
                "has_subway": self.city.has_subway,
                "restriction": self.city.restriction,
            },
            "calendar": self.holiday.to_dict(),
            "festival": (
                {
                    "name": self.festival.name,
                    "kind": self.festival.kind,
                    "crowd_note": self.festival.crowd_note,
                }
                if self.festival
                else None
            ),
            "weather": self.weather.to_dict(),
            "season": self.season,
            "solar_term": {
                "current": self.solar_term.name if self.solar_term else None,
                "upcoming": self.upcoming_term.name,
                "upcoming_date": self.upcoming_term.date.isoformat(),
                "days_until": self.term_offset,
            },
            "next_holiday": {
                "name": self.next_holiday_name,
                "days_until": self.next_holiday_days,
            },
            "options": self.options,
        }


def build_context(day: date, city_query: str, options: dict[str, Any] | None = None) -> AdviceContext:
    profile = cities.resolve(city_query)
    status = resolve(day)
    profile_weather = weather.estimate(profile, day)

    upcoming_term, offset = nearest_term(day)
    today_term = term_on(day)

    block, days_until = get_calendar().next_holiday(day)

    return AdviceContext(
        day=day,
        requested_city=city_query,
        city=profile,
        holiday=status,
        festival=festivals.for_date(day),
        weather=profile_weather,
        season=season_of(day),
        solar_term=today_term,
        upcoming_term=upcoming_term,
        term_offset=offset,
        next_holiday_name=block.name if block else None,
        next_holiday_days=days_until,
        options=dict(options or {}),
    )
