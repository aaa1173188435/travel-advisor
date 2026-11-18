"""中国法定节假日与调休解析。

带官方通知的年份以 `data/holidays_cn.json` 为准；未覆盖的年份按固定日期
规则估算，并在结果里标记 ``estimated``，提醒用户以官方通知为准。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from .solar import qingming_date

DATA_FILE = Path(__file__).parent / "data" / "holidays_cn.json"

WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


@dataclass(frozen=True)
class HolidayBlock:
    name: str
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


@dataclass
class HolidayStatus:
    day: date
    is_holiday: bool = False
    holiday_name: str | None = None
    is_makeup_workday: bool = False
    is_weekend: bool = False
    is_working_day: bool = False
    estimated: bool = False
    day_index: int | None = None
    block_days: int | None = None
    block_start: date | None = None
    block_end: date | None = None
    source: str | None = None
    note: str | None = None

    @property
    def weekday_name(self) -> str:
        return WEEKDAY_NAMES[self.day.weekday()]

    @property
    def day_type(self) -> str:
        """holiday / makeup_workday / weekend / workday"""
        if self.is_holiday:
            return "holiday"
        if self.is_makeup_workday:
            return "makeup_workday"
        if self.is_weekend:
            return "weekend"
        return "workday"

    @property
    def type_label(self) -> str:
        if self.is_holiday:
            label = f"{self.holiday_name}假期" if self.holiday_name else "法定假期"
            if self.day_index and self.block_days:
                label += f"第 {self.day_index}/{self.block_days} 天"
            return label
        if self.is_makeup_workday:
            return "调休上班日"
        if self.is_weekend:
            return "周末"
        return "工作日"

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.day.isoformat(),
            "weekday": self.weekday_name,
            "day_type": self.day_type,
            "type_label": self.type_label,
            "is_holiday": self.is_holiday,
            "holiday_name": self.holiday_name,
            "is_makeup_workday": self.is_makeup_workday,
            "is_weekend": self.is_weekend,
            "is_working_day": self.is_working_day,
            "estimated": self.estimated,
            "day_index": self.day_index,
            "block_days": self.block_days,
            "block_start": self.block_start.isoformat() if self.block_start else None,
            "block_end": self.block_end.isoformat() if self.block_end else None,
            "source": self.source,
            "note": self.note,
        }


def _fallback_blocks(year: int) -> list[HolidayBlock]:
    """官方安排未公布时的估算：只覆盖日期固定的节日。"""
    blocks = [
        HolidayBlock("元旦", date(year, 1, 1), date(year, 1, 1)),
        HolidayBlock("国庆节", date(year, 10, 1), date(year, 10, 7)),
        HolidayBlock("劳动节", date(year, 5, 1), date(year, 5, 5)),
    ]
    qm = qingming_date(year)
    blocks.append(HolidayBlock("清明节", qm, qm + timedelta(days=2)))
    return blocks


@lru_cache(maxsize=1)
def _load_raw() -> dict[str, Any]:
    with DATA_FILE.open(encoding="utf-8") as handle:
        return json.load(handle)


class HolidayCalendar:
    def __init__(self) -> None:
        self._years: dict[int, dict[str, Any]] = {}
        raw = _load_raw()
        for year_text, payload in raw.get("years", {}).items():
            blocks = [
                HolidayBlock(item["name"], date.fromisoformat(item["start"]), date.fromisoformat(item["end"]))
                for item in payload.get("blocks", [])
            ]
            workdays = {date.fromisoformat(item) for item in payload.get("workdays", [])}
            self._years[int(year_text)] = {
                "blocks": blocks,
                "workdays": workdays,
                "source": payload.get("source"),
            }

    def _year_data(self, year: int) -> tuple[list[HolidayBlock], set[date], str | None, bool]:
        if year in self._years:
            payload = self._years[year]
            return payload["blocks"], payload["workdays"], payload["source"], False
        return _fallback_blocks(year), set(), None, True

    def status(self, day: date) -> HolidayStatus:
        blocks, workdays, source, estimated = self._year_data(day.year)
        status = HolidayStatus(day=day, source=source, estimated=estimated)
        status.is_weekend = day.weekday() >= 5

        if day in workdays:
            status.is_makeup_workday = True
            status.is_working_day = True
            status.note = "调休上班，按工作日安排"
            return status

        for block in blocks:
            if block.start <= day <= block.end:
                status.is_holiday = True
                status.holiday_name = block.name
                status.is_working_day = False
                status.block_start = block.start
                status.block_end = block.end
                status.block_days = block.days
                status.day_index = (day - block.start).days + 1
                if estimated:
                    status.note = "该年份放假安排尚未公布，按固定日期规则估算"
                return status

        status.is_working_day = not status.is_weekend
        if estimated:
            status.note = "该年份放假安排尚未公布，按固定日期规则估算"
        return status

    def next_holiday(self, day: date, within_days: int = 400) -> tuple[HolidayBlock | None, int | None]:
        """返回下一个假期区间及距离天数（当天为假期时返回当前区间）。"""
        cursor = day
        limit = day + timedelta(days=within_days)
        current: HolidayBlock | None = None
        while cursor <= limit:
            status = self.status(cursor)
            if status.is_holiday and status.block_start and status.block_end:
                block = HolidayBlock(status.holiday_name or "假期", status.block_start, status.block_end)
                if not current:
                    current = block
                if block.start > day:
                    return block, (block.start - day).days
                if block.start <= day <= block.end:
                    return block, 0
            cursor += timedelta(days=1)
        return None, None

    def blocks_for_year(self, year: int) -> list[HolidayBlock]:
        blocks, _, _, _ = self._year_data(year)
        return blocks


_calendar: HolidayCalendar | None = None


def get_calendar() -> HolidayCalendar:
    global _calendar
    if _calendar is None:
        _calendar = HolidayCalendar()
    return _calendar


def resolve(day: date) -> HolidayStatus:
    return get_calendar().status(day)
