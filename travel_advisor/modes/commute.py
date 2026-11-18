"""通勤模式：工作日/假期判断、高峰、天气影响与出行方式建议。"""

from __future__ import annotations

from datetime import time

from ..context import AdviceContext
from ..registry import register
from ..weather import display_temp
from .base import Item, Mode, ModeResult, Section, clamp, score_label

_MORNING_PEAK = (time(7, 0), time(9, 30))
_EVENING_PEAK = (time(17, 0), time(19, 30))


def _temp_text(ctx: AdviceContext) -> str:
    return f"{display_temp(ctx.weather.t_min)}~{display_temp(ctx.weather.t_max)}℃"


def _parse_time(value: object) -> time | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        hour_text, minute_text = value.strip().split(":")[:2]
        return time(int(hour_text), int(minute_text))
    except (ValueError, TypeError):
        return None


def _in_peak(moment: time) -> str | None:
    for label, (start, end) in (("早高峰", _MORNING_PEAK), ("晚高峰", _EVENING_PEAK)):
        if start <= moment <= end:
            return label
    return None


def _peak_window(peak: str) -> str:
    start, end = _MORNING_PEAK if peak == "早高峰" else _EVENING_PEAK
    return f"{start.strftime('%H:%M')}—{end.strftime('%H:%M')}"


class CommuteMode(Mode):
    id = "commute"
    name = "通勤"
    icon = "🚇"
    description = "工作日上下班、办事通勤，重点看高峰、天气与交通方式"
    options = [
        {
            "key": "depart_time",
            "label": "出发时间",
            "type": "time",
            "default": "08:00",
        },
        {
            "key": "transport",
            "label": "主要方式",
            "type": "select",
            "default": "subway",
            "choices": [
                {"value": "subway", "label": "地铁"},
                {"value": "bus", "label": "公交"},
                {"value": "drive", "label": "自驾"},
                {"value": "bike", "label": "骑行"},
                {"value": "walk", "label": "步行"},
            ],
        },
    ]

    def normalize_options(self, options: dict) -> dict:
        transport = str(options.get("transport") or "subway")
        if transport not in {"subway", "bus", "drive", "bike", "walk"}:
            transport = "subway"
        return {"depart_time": options.get("depart_time") or "08:00", "transport": transport}

    def advise(self, ctx: AdviceContext) -> ModeResult:
        options = self.normalize_options(ctx.options)
        transport = options["transport"]
        depart_time = _parse_time(options["depart_time"])
        working = ctx.holiday.is_working_day
        weather = ctx.weather
        city = ctx.city

        score = 92.0
        tags: list[str] = []
        if working:
            tags.append(ctx.holiday.type_label)
        else:
            tags.append("非工作日")
            score += 4

        peak = _in_peak(depart_time) if (working and depart_time) else None
        if peak:
            score -= 8
            tags.append(peak)
        if weather.rain_prob >= 0.45:
            score -= 18
            tags.append("有雨")
        elif weather.rain_prob >= 0.30:
            score -= 10
            tags.append("可能下雨")
        elif weather.rain_prob >= 0.18:
            score -= 4
        if weather.t_max >= 35:
            score -= 10
            tags.append("高温")
        elif weather.t_max <= -10:
            score -= 14
            tags.append("严寒")
        elif weather.t_max <= 0:
            score -= 8
            tags.append("寒冷")
        if transport == "drive" and city.restriction:
            score -= 6
            tags.append("限行提示")
        if transport in {"bike", "walk"} and (weather.rain_prob >= 0.45 or weather.t_max >= 35 or weather.t_max <= 2):
            score -= 10
        final_score = clamp(score)

        sections = [
            self._weather_section(ctx),
            self._schedule_section(ctx, working, peak, transport),
            self._transport_section(ctx, transport, peak),
            self._packing_section(ctx),
            self._reminder_section(ctx),
        ]

        if not working:
            lead = f"今天{ctx.holiday.type_label}，不用赶通勤"
            if ctx.holiday.holiday_name:
                lead = f"今天{ctx.holiday.type_label}，不用赶通勤"
            headline = f"{lead}；{city.name}{weather.condition}，{_temp_text(ctx)}，出门办事可按自己的节奏安排。"
        elif peak:
            headline = (
                f"{city.name}{ctx.holiday.weekday_name}{peak}，{weather.condition}，{_temp_text(ctx)}；"
                f"建议提前 20 分钟出门，或错峰到 {_peak_window(peak)} 之后再走。"
            )
        else:
            headline = (
                f"{city.name}{ctx.holiday.weekday_name}，{weather.condition}，{_temp_text(ctx)}；"
                f"当前时段不在高峰，通勤压力不大。"
            )

        return ModeResult(
            mode_id=self.id,
            mode_name=self.name,
            headline=headline,
            score=final_score,
            score_label=score_label(final_score),
            tags=tags,
            sections=sections,
        )

    def _weather_section(self, ctx: AdviceContext) -> Section:
        weather = ctx.weather
        items = [
            Item(
                "气温",
                f"常年同期 {_temp_text(ctx)}，体感{weather.comfort}，昼夜温差约 {round(weather.diurnal_range)}℃。",
                "info",
            ),
            Item(
                "降水",
                f"{weather.condition}，降水概率约 {round(weather.rain_prob * 100)}%。",
                "warn" if weather.rain_prob >= 0.30 else "good",
            ),
            Item("穿衣", weather.clothing, "info"),
        ]
        if weather.diurnal_range >= 9:
            items.append(Item("温差", "早晚温差大，通勤路上多带一件外套更稳妥。", "info"))
        if weather.sunscreen:
            items.append(Item("防晒", "紫外线偏强，通勤路上注意防晒。", "info"))
        return Section("weather", "天气与体感", "🌤️", items)

    def _schedule_section(self, ctx: AdviceContext, working: bool, peak: str | None, transport: str) -> Section:
        items: list[Item] = []
        if working:
            items.append(
                Item(
                    "日期",
                    f"{ctx.day.month} 月 {ctx.day.day} 日 {ctx.holiday.weekday_name}，{ctx.holiday.type_label}。",
                    "info",
                )
            )
            if ctx.holiday.is_makeup_workday:
                items.append(Item("调休提醒", "今天是被调休的上班日，别按周末安排。", "warn"))
        else:
            items.append(
                Item(
                    "日期",
                    f"{ctx.day.month} 月 {ctx.day.day} 日 {ctx.holiday.weekday_name}，{ctx.holiday.type_label}。",
                    "good",
                )
            )
            if ctx.holiday.block_days and ctx.holiday.day_index in (1, ctx.holiday.block_days):
                phase = "出城" if ctx.holiday.day_index == 1 else "返程"
                items.append(
                    Item("假期路况", f"{phase}方向车流集中，高速和车站会比平时堵，尽量避开上午 9—11 点。", "warn")
                )
            elif ctx.holiday.block_days:
                items.append(Item("假期路况", "假期中段市区道路相对好走，热门商圈和景点午后人多。", "info"))
            items.append(Item("节奏", "不用赶点，外出可以安排在上午 10 点后或傍晚。", "good"))

        if working and peak:
            items.append(
                Item(
                    "高峰",
                    f"你选的时间落在{peak}（{_peak_window(peak)}），地铁和主干道都会明显变慢，留出 15—20 分钟缓冲。",
                    "warn",
                )
            )
        elif working:
            items.append(Item("高峰", "当前出发时间错开了早晚高峰，路上会轻松不少。", "good"))

        if working and ctx.weather.rain_prob >= 0.30:
            items.append(
                Item(
                    "雨天缓冲",
                    "下雨天打车成功率下降、路口通行变慢，建议比平时早 15 分钟出门。",
                    "warn",
                )
            )
        if working and ctx.weather.t_max >= 35:
            items.append(Item("高温", "高温天尽量选择有空调的交通方式，随身带水。", "warn"))
        if working and ctx.weather.t_max <= 0:
            items.append(Item("低温", "低温天注意路面结冰，自驾和骑行都要减速。", "warn"))

        if working and transport == "drive" and ctx.city.restriction:
            items.append(Item("限行", ctx.city.restriction, "warn"))

        return Section("schedule", "通勤判断", "⏱️", items)

    def _transport_section(self, ctx: AdviceContext, transport: str, peak: str | None) -> Section:
        weather = ctx.weather
        city = ctx.city
        items: list[Item] = []

        if transport == "subway":
            if city.has_subway:
                items.append(Item("地铁", "受雨雪和拥堵影响最小，通勤优先选它。", "good"))
            else:
                items.append(Item("地铁", f"{city.name}暂无地铁运营，建议改选公交或网约车。", "warn"))
        elif transport == "bus":
            items.append(Item("公交", "地面交通受高峰和降雨影响较大，预留更多时间。", "info"))
        elif transport == "drive":
            if city.restriction:
                items.append(Item("自驾", f"注意限行：{city.restriction}", "warn"))
            if weather.rain_prob >= 0.30:
                items.append(Item("自驾", "雨天路滑、视线差，跟车距离拉大，早点出门。", "warn"))
            else:
                items.append(Item("自驾", "路况正常时自驾较灵活，注意提前找好停车位。", "info"))
        elif transport == "bike":
            if weather.rain_prob >= 0.30 or weather.t_max >= 35 or weather.t_max <= 2:
                items.append(Item("骑行", "天气不适合骑行，建议改乘地铁或公交。", "bad"))
            else:
                items.append(Item("骑行", "天气适合骑行，注意保暖和反光装备。", "good"))
        elif transport == "walk":
            if weather.rain_prob >= 0.30:
                items.append(Item("步行", "雨天步行体验差，带好雨具或改乘交通工具。", "warn"))
            else:
                items.append(Item("步行", "距离允许的话步行是不错的选择，顺便活动一下。", "good"))

        if peak and transport in {"drive", "bus"}:
            items.append(Item("替代方案", "高峰时段可考虑「地铁 + 共享单车」组合，通常比全程地面交通快。", "info"))
        if weather.rain_prob >= 0.30:
            items.append(Item("打车", "雨天网约车排队会变长，能地铁就别等车。", "warn"))
        if not ctx.holiday.is_working_day:
            items.append(Item("外出", "假期去热门商圈自驾找车位费时，地铁加步行通常更省心。", "info"))

        return Section("transport", "出行方式", "🚦", items)

    def _packing_section(self, ctx: AdviceContext) -> Section:
        weather = ctx.weather
        items: list[Item] = []
        if weather.umbrella:
            items.append(Item("雨具", "折叠伞放包里，通勤路上用得上。", "warn"))
        if weather.sunscreen:
            items.append(Item("防晒", "防晒霜、遮阳帽按需带上。", "info"))
        if weather.t_max <= 10:
            items.append(Item("保暖", "围巾、手套可以带上，早晚体感更低。", "info"))
        if weather.t_max >= 28:
            items.append(Item("补水", "带一瓶水，高温天及时补水。", "info"))
        items.append(Item("随身", "工牌/门禁卡、充电宝、耳机，按日常通勤清单检查一遍。", "info"))
        return Section("packing", "随身清单", "🎒", items)

    def _reminder_section(self, ctx: AdviceContext) -> Section:
        items: list[Item] = []
        if ctx.solar_term:
            items.append(Item("节气", f"今天是{ctx.solar_term.name}，节令转换，注意作息和保暖。", "info"))
        elif ctx.term_offset is not None and 0 < ctx.term_offset <= 3:
            items.append(
                Item(
                    "节气",
                    f"{ctx.upcoming_term.name}还有 {ctx.term_offset} 天，天气可能转凉或转雨，留意临近预报。",
                    "info",
                )
            )
        if ctx.next_holiday_name and ctx.next_holiday_days is not None and 0 < ctx.next_holiday_days <= 7:
            items.append(
                Item(
                    "假期临近",
                    f"距{ctx.next_holiday_name}还有 {ctx.next_holiday_days} 天，节前最后一个工作日通常更堵。",
                    "warn",
                )
            )
        if ctx.weather.rain_prob >= 0.25:
            items.append(
                Item(
                    "降水提醒",
                    f"降水概率约 {round(ctx.weather.rain_prob * 100)}%，伞放包里，鞋子选防滑的。",
                    "warn",
                )
            )
        if ctx.festival and ctx.festival.commute_note:
            items.append(Item("节庆", f"{ctx.festival.name}：{ctx.festival.commute_note}", "warn"))
        if ctx.holiday.estimated:
            items.append(
                Item("数据说明", "该年份放假安排尚未正式公布，假期判断为按固定日期估算。", "info")
            )
        if not items:
            items.append(Item("提醒", "今天没有特别的通勤风险，按平时节奏出门即可。", "good"))
        return Section("reminders", "当日提醒", "🔔", items)


register(CommuteMode())
