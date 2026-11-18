"""节庆与法定假日特点测试。"""

from datetime import date

from travel_advisor import festivals


def test_fixed_festivals():
    assert festivals.for_date(date(2026, 5, 20)).name == "520"
    assert festivals.for_date(date(2026, 11, 11)).name == "双十一"
    assert festivals.for_date(date(2026, 12, 25)).name == "圣诞节"
    assert festivals.for_date(date(2026, 6, 7)).name == "高考"


def test_weekday_festivals():
    assert festivals.for_date(date(2026, 5, 10)).name == "母亲节"  # 5 月第二个周日
    assert festivals.for_date(date(2026, 6, 21)).name == "父亲节"  # 6 月第三个周日
    assert festivals.for_date(date(2026, 11, 26)).name == "感恩节"  # 11 月第四个周四


def test_ordinary_day_has_no_festival():
    assert festivals.for_date(date(2026, 11, 18)) is None
