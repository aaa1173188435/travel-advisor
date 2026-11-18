"""节假日解析测试：以国务院办公厅公布的 2026/2027 安排为准。"""

from datetime import date

import pytest

from travel_advisor.holidays import get_calendar, resolve


def test_2026_spring_festival_block():
    status = resolve(date(2026, 2, 17))
    assert status.is_holiday
    assert status.holiday_name == "春节"
    assert status.day_index == 3
    assert status.block_days == 9
    assert not status.is_working_day


def test_2026_makeup_workday_is_working_day():
    status = resolve(date(2026, 2, 14))  # 周六调休上班
    assert status.is_makeup_workday
    assert status.is_working_day
    assert not status.is_holiday
    assert status.day_type == "makeup_workday"


def test_2027_single_day_holiday():
    status = resolve(date(2027, 6, 9))
    assert status.is_holiday
    assert status.holiday_name == "端午节"
    assert status.block_days == 1
    assert status.day_index == 1


def test_2027_national_day_workday_swap():
    status = resolve(date(2027, 9, 26))
    assert status.is_makeup_workday
    assert status.is_working_day


def test_weekend_is_not_working_day():
    status = resolve(date(2026, 11, 21))
    assert status.is_weekend
    assert not status.is_working_day
    assert status.day_type == "weekend"


def test_estimated_year_marks_estimated():
    status = resolve(date(2030, 10, 2))
    assert status.is_holiday
    assert status.estimated
    assert "尚未公布" in (status.note or "")


def test_next_holiday_distance():
    block, days = get_calendar().next_holiday(date(2026, 12, 24))
    assert block is not None and block.name == "元旦"
    assert days == 8


def test_next_holiday_inside_block_returns_zero():
    block, days = get_calendar().next_holiday(date(2027, 2, 6))
    assert block is not None and block.name == "春节"
    assert days == 0


@pytest.mark.parametrize("year", [2026, 2027])
def test_official_years_have_seven_blocks(year):
    assert len(get_calendar().blocks_for_year(year)) == 7
