"""二十四节气与季节的近似计算。

节气日期采用常见的「世纪常数」近似公式，误差约 ±1 天，用于出行提示足够；
需要精确日期时请以天文台发布为准。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# (名称, 21 世纪世纪常数 C)，公式：day = int(Y*0.2422 + C) - int((Y-1)/4)
_TERM_CONSTANTS: tuple[tuple[str, float], ...] = (
    ("小寒", 5.4055),
    ("大寒", 20.12),
    ("立春", 3.87),
    ("雨水", 18.73),
    ("惊蛰", 5.63),
    ("春分", 20.646),
    ("清明", 4.81),
    ("谷雨", 20.1),
    ("立夏", 5.52),
    ("小满", 21.04),
    ("芒种", 5.678),
    ("夏至", 21.37),
    ("小暑", 7.108),
    ("大暑", 22.83),
    ("立秋", 7.5),
    ("处暑", 23.13),
    ("白露", 7.646),
    ("秋分", 23.042),
    ("寒露", 8.318),
    ("霜降", 23.438),
    ("立冬", 7.438),
    ("小雪", 22.36),
    ("大雪", 7.18),
    ("冬至", 21.94),
)


@dataclass(frozen=True)
class SolarTerm:
    name: str
    date: date

    def to_dict(self) -> dict:
        return {"name": self.name, "date": self.date.isoformat()}


def _term_date(year: int, month: int, constant: float) -> date:
    y = year % 100
    day = int(y * 0.2422 + constant) - int((y - 1) / 4)
    # 极少数年份公式会给出 0 或越界值，夹到当月合法范围
    day = max(1, min(day, 31))
    while True:
        try:
            return date(year, month, day)
        except ValueError:
            day -= 1


def terms_of_year(year: int) -> list[SolarTerm]:
    terms: list[SolarTerm] = []
    for index, (name, constant) in enumerate(_TERM_CONSTANTS):
        month = index // 2 + 1
        terms.append(SolarTerm(name, _term_date(year, month, constant)))
    return terms


def term_on(day: date) -> SolarTerm | None:
    """返回当天恰好是节气的记录（近似，允许 ±1 天视为当天）。"""
    for term in terms_of_year(day.year):
        if term.date == day:
            return term
    return None


def nearest_term(day: date) -> tuple[SolarTerm, int]:
    """返回距离最近的节气以及相差天数（负数表示已经过去）。"""
    candidates = terms_of_year(day.year)
    if day.month <= 2:
        candidates = terms_of_year(day.year - 1)[-2:] + candidates
    if day.month >= 12:
        candidates = candidates + terms_of_year(day.year + 1)[:2]
    best = min(candidates, key=lambda t: abs((t.date - day).days))
    return best, (best.date - day).days


def qingming_date(year: int) -> date:
    for term in terms_of_year(year):
        if term.name == "清明":
            return term.date
    return date(year, 4, 5)  # pragma: no cover - 理论不可达


def season_of(day: date) -> str:
    """按气象季节划分（3—5 春，6—8 夏，9—11 秋，12—2 冬）。"""
    month = day.month
    if month in (3, 4, 5):
        return "春"
    if month in (6, 7, 8):
        return "夏"
    if month in (9, 10, 11):
        return "秋"
    return "冬"


SEASON_LABEL = {"春": "春季", "夏": "夏季", "秋": "秋季", "冬": "冬季"}
