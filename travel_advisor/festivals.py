"""非公休节庆：不影响放假，但会影响商圈、餐厅和景区人流。

法定节假日由 holidays.py 负责；这里只收录「不放假但人多」的日子。
农历节日（元宵、七夕、重阳）需要农历换算，当前版本暂未覆盖。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class Festival:
    name: str
    kind: str
    crowd_note: str
    commute_note: str | None = None


_FIXED: dict[tuple[int, int], Festival] = {
    (2, 14): Festival(
        "情人节",
        "商业节庆",
        "餐厅、影院和酒店晚间爆满，建议提前预订",
        "晚高峰餐厅和商圈周边更堵",
    ),
    (3, 8): Festival("妇女节", "节日", "部分景区和商场有女性优惠，午后客流增加", None),
    (3, 14): Festival("白色情人节", "商业节庆", "餐厅和商场有促销活动，晚间人流增加", None),
    (5, 20): Festival("520", "商业节庆", "餐厅和婚姻登记处人多，热门餐厅建议提前订", None),
    (5, 21): Festival("521", "商业节庆", "表白日餐厅和商圈人气高，晚间建议提前订位", None),
    (6, 1): Festival("儿童节", "家庭节日", "亲子场所和乐园人多，建议早场入园", None),
    (6, 7): Festival("高考", "校园节点", "考点周边交通管制、酒店紧张，出行避开考点路段", "早高峰考点周边拥堵，提前出门"),
    (6, 8): Festival("高考", "校园节点", "考点周边交通管制、酒店紧张，出行避开考点路段", "早高峰考点周边拥堵，提前出门"),
    (6, 18): Festival("618", "购物节", "电商大促，线下商场同步促销，快递和商圈人流增加", None),
    (9, 1): Festival("开学日", "校园节点", "中小学开学，学校周边和文具店人多", "早高峰提前，学校周边道路拥堵"),
    (9, 10): Festival("教师节", "节日", "部分景区对教师有优惠，相关场馆人流增加", None),
    (10, 31): Festival("万圣节", "商业节庆", "主题乐园和酒吧活动多，夜间人流大", None),
    (11, 11): Festival("双十一", "购物节", "线上大促，线下商场同步活动，快递和商圈人流增加", None),
    (12, 12): Festival("双十二", "购物节", "电商和线下商场年末促销，商圈人流增加", None),
    (12, 24): Festival(
        "平安夜",
        "商业节庆",
        "商圈、餐厅和酒吧晚间人流明显增加，热门餐厅建议提前订位",
        "晚高峰会延长，商圈周边道路和地铁更挤",
    ),
    (12, 25): Festival(
        "圣诞节",
        "商业节庆",
        "商场、餐厅和酒店晚间人多，热门餐厅建议提前预订",
        "商场周边晚高峰延长，打车更难",
    ),
    (12, 31): Festival(
        "跨年夜",
        "商业节庆",
        "跨年活动周边可能交通管制，返程要提前规划",
        "跨年活动多，夜间公共交通可能延长运营",
    ),
}


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """某月第 n 个星期 weekday（weekday: 0=周一）。"""
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (n - 1))


def for_date(day: date) -> Festival | None:
    fixed = _FIXED.get((day.month, day.day))
    if fixed:
        return fixed
    if day == _nth_weekday(day.year, 5, 6, 2):  # 5 月第二个周日
        return Festival("母亲节", "家庭节日", "家庭聚餐和亲子场所人多，餐厅建议提前订位", None)
    if day == _nth_weekday(day.year, 6, 6, 3):  # 6 月第三个周日
        return Festival("父亲节", "家庭节日", "家庭聚餐多，餐厅建议提前订位", None)
    if day == _nth_weekday(day.year, 11, 3, 4):  # 11 月第四个周四
        return Festival("感恩节", "家庭节日", "餐厅和商圈有主题活动，晚间人流增加", None)
    return None
