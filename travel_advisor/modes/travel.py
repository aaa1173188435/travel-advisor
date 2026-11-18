"""旅游模式：人流档期、天气适配、行程节奏与预约装备建议。"""

from __future__ import annotations

from datetime import timedelta

from ..context import AdviceContext
from ..holiday_tips import tips_for
from ..registry import register
from ..weather import display_temp
from .base import Item, Mode, ModeResult, Section, clamp, score_label

# 少数城市的旅游旺季月份（按公开经验整理，用于人流提示）
_PEAK_MONTHS: dict[str, list[int]] = {
    "sanya": [11, 12, 1, 2],
    "haikou": [11, 12, 1, 2],
    "harbin": [12, 1, 2],
    "changchun": [12, 1, 2],
    "shenyang": [12, 1, 2],
    "qingdao": [7, 8],
    "dalian": [7, 8],
    "xiamen": [7, 8],
    "kunming": [3, 4, 5, 9, 10],
    "beijing": [4, 5, 9, 10],
    "hangzhou": [3, 4, 5, 9, 10],
    "suzhou": [3, 4, 5, 9, 10],
    "nanjing": [3, 4, 11],
    "xian": [4, 5, 9, 10],
    "chengdu": [3, 4, 5, 9, 10],
}

_INTEREST_ADVICE = {
    "自然风光": "自然类景点受天气影响最大，出发前确认是否开放，雨后山路注意防滑。",
    "人文历史": "博物馆和古迹多需预约，工作日名额通常更宽松。",
    "美食": "热门餐厅 11:30 和 17:30 排队最久，提前半小时或错到 13:30 后更从容。",
    "亲子": "带娃行程别排太满，上午安排一个主项目，下午留出休息和机动时间。",
    "摄影": "日出后一小时和日落前一小时光线最好，热门机位要提前占位。",
    "购物": "商圈午后到傍晚人流上升，想安静逛街可以上午去。",
    "演出展览": "演出票和展览预约要提前锁定，注意场馆的入场时间要求。",
}


def _temp_text(ctx: AdviceContext) -> str:
    return f"{display_temp(ctx.weather.t_min)}~{display_temp(ctx.weather.t_max)}℃"


class TravelMode(Mode):
    id = "travel"
    name = "旅游"
    icon = "🧳"
    description = "休闲出游、短途旅行，重点看人流档期、天气与行程节奏"
    options = [
        {
            "key": "days",
            "label": "计划天数",
            "type": "number",
            "default": 2,
            "min": 1,
            "max": 10,
        },
        {
            "key": "interests",
            "label": "兴趣偏好",
            "type": "multi",
            "default": [],
            "choices": [
                {"value": "自然风光", "label": "自然风光"},
                {"value": "人文历史", "label": "人文历史"},
                {"value": "美食", "label": "美食"},
                {"value": "亲子", "label": "亲子"},
                {"value": "摄影", "label": "摄影"},
                {"value": "购物", "label": "购物"},
                {"value": "演出展览", "label": "演出展览"},
            ],
        },
    ]

    def normalize_options(self, options: dict) -> dict:
        try:
            days = int(options.get("days") or 2)
        except (TypeError, ValueError):
            days = 2
        days = max(1, min(10, days))
        raw_interests = options.get("interests") or []
        if isinstance(raw_interests, str):
            raw_interests = [raw_interests]
        interests = [str(item) for item in raw_interests if str(item) in _INTEREST_ADVICE]
        return {"days": days, "interests": interests[:3]}

    def advise(self, ctx: AdviceContext) -> ModeResult:
        options = self.normalize_options(ctx.options)
        days = options["days"]
        interests = options["interests"]
        weather = ctx.weather
        holiday = ctx.holiday
        city = ctx.city

        score = 88.0
        tags: list[str] = []
        peak_season = ctx.day.month in _PEAK_MONTHS.get(city.id, [])

        if holiday.is_holiday:
            score -= 12
            tags.append("假期人流")
        elif holiday.is_weekend:
            score -= 4
            tags.append("周末")
        else:
            score += 4
            tags.append("错峰")

        if peak_season:
            score -= 5
            tags.append("旺季")
        if ctx.festival:
            score -= 4
            tags.append(ctx.festival.name)
        if weather.rain_prob >= 0.35:
            score -= 12
            tags.append("多雨")
        elif weather.rain_prob >= 0.25:
            score -= 6
            tags.append("可能下雨")
        if weather.t_max >= 35:
            score -= 6
            tags.append("高温")
        elif weather.t_max <= 0:
            score -= 6
            tags.append("寒冷")
        final_score = clamp(score)

        sections = [
            self._weather_section(ctx),
            self._crowd_section(ctx, peak_season),
            self._rhythm_section(ctx, days, interests),
            self._highlight_section(ctx),
            self._booking_section(ctx, days),
            self._packing_section(ctx, days),
        ]
        tips = tips_for(ctx.holiday.holiday_name) if ctx.holiday.is_holiday else None
        if tips:
            sections.insert(2, self._holiday_section(tips))

        headline = self._headline(ctx, days, peak_season)

        return ModeResult(
            mode_id=self.id,
            mode_name=self.name,
            headline=headline,
            score=final_score,
            score_label=score_label(final_score),
            tags=tags,
            sections=sections,
        )

    def _headline(self, ctx: AdviceContext, days: int, peak_season: bool) -> str:
        city = ctx.city
        weather = ctx.weather
        holiday = ctx.holiday
        temperature = _temp_text(ctx)

        if holiday.is_holiday and holiday.block_days and holiday.block_days >= 3:
            crowd = f"正值{holiday.holiday_name}假期第 {holiday.day_index}/{holiday.block_days} 天，热门景点人流大"
        elif holiday.is_weekend:
            crowd = "周末出游，热门景点午后会明显变挤"
        else:
            crowd = "工作日出行，景区排队和交通压力都小很多"
        if peak_season:
            crowd += "，且处于当地旅游旺季"
        if ctx.festival and not holiday.is_holiday:
            crowd += f"，当天是{ctx.festival.name}，商圈和餐厅会更热闹"

        if weather.rain_prob >= 0.35:
            plan = "雨水偏多，行程以室内场馆和商圈为主，户外项目留好备选"
        elif weather.rain_prob >= 0.25:
            plan = "可能有阵雨，雨具随身带，户外行程留一个室内备选"
        elif weather.t_max >= 35:
            plan = "高温天建议早出晚归，中午安排室内休息"
        elif weather.t_max <= 0:
            plan = "天气寒冷，优先安排室内展馆，户外注意防寒"
        else:
            plan = "天气条件不错，适合把主要景点放在户外"

        return (
            f"{ctx.day.month} 月 {ctx.day.day} 日（{holiday.weekday_name}）{city.name}："
            f"{weather.condition}，{temperature}。{crowd}；{plan}。计划 {days} 天可以按这个节奏排。"
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
        if ctx.city.climate_note:
            items.append(Item("城市气候", ctx.city.climate_note, "info"))
        return Section("weather", "天气与体感", "🌤️", items)

    def _crowd_section(self, ctx: AdviceContext, peak_season: bool) -> Section:
        holiday = ctx.holiday
        items: list[Item] = []
        if holiday.is_holiday:
            if holiday.day_index == 1:
                items.append(Item("出城高峰", "假期第一天是出城高峰，高速和车站都会很挤，尽量早走或改到下午。", "warn"))
            elif holiday.block_days and holiday.day_index == holiday.block_days:
                items.append(Item("返程高峰", "假期最后一天返程集中，车票和高速都要提前安排。", "warn"))
            else:
                items.append(
                    Item(
                        "景区人流",
                        f"假期第 {holiday.day_index}/{holiday.block_days} 天，热门景点 10:00—15:00 最挤，把大景点放在开园或闭园前。",
                        "warn",
                    )
                )
        elif holiday.is_weekend:
            items.append(Item("周末节奏", "周六上午和周日傍晚是人流高峰，周五晚出发也容易堵。", "info"))
        else:
            items.append(Item("错峰优势", "工作日出行，博物馆和热门景点的预约名额通常更宽松。", "good"))

        if peak_season:
            items.append(Item("旺季", f"{ctx.city.name}当前处于旅游旺季，住宿和热门项目建议提前预订。", "warn"))
        if ctx.festival:
            items.append(Item("节庆", f"{ctx.festival.name}：{ctx.festival.crowd_note}", "warn"))
        if ctx.city.highlight_for_month(ctx.day.month):
            items.append(Item("当季看点", "；".join(ctx.city.highlight_for_month(ctx.day.month)[:2]), "good"))
        return Section("crowd", "人流与档期", "👥", items)

    def _holiday_section(self, tips: dict[str, str]) -> Section:
        return Section(
            "holiday",
            "假期特点",
            "🎊",
            [
                Item("人流", tips["crowd"], "warn"),
                Item("行程", tips["travel"], "info"),
                Item("预订", tips["booking"], "warn"),
                Item("当季玩法", tips["special"], "good"),
            ],
        )

    def _rhythm_section(self, ctx: AdviceContext, days: int, interests: list[str]) -> Section:
        weather = ctx.weather
        items: list[Item] = []
        if weather.rain_prob >= 0.35:
            items.append(Item("上午", "把室内展馆、博物馆放在上午，避开午后降雨高峰。", "info"))
            items.append(Item("午后", "留出商场、咖啡馆或书店作备选，随时可以躲雨。", "info"))
        elif weather.rain_prob >= 0.25:
            items.append(Item("上午", "核心景点尽量上午走完，午后阵雨概率更高。", "info"))
            items.append(Item("午后", "带好雨具，同时留一个室内备选，遇到阵雨直接切换。", "warn"))
        elif weather.t_max >= 35:
            items.append(Item("上午", "8:30 前出发，把户外主景点放在 11:00 前完成。", "info"))
            items.append(Item("午后", "13:00—15:30 安排室内休息，16:00 之后再出门。", "warn"))
        else:
            items.append(Item("上午", "8:30—11:30 安排最想去的核心景点，人少、光线也好。", "good"))
            items.append(Item("午后", "14:00 后再去第二个点，避开午餐和午后人流。", "info"))
        items.append(Item("傍晚", "17:00 后适合城市漫步、夜景和拍照，也方便顺路吃饭。", "info"))

        if days <= 1:
            items.append(Item("一日节奏", "只留一天的话，集中玩一个片区，别在城市两头来回跑。", "warn"))
        elif days <= 3:
            items.append(Item("行程密度", f"{days} 天建议一天一个大片区，预留半天机动时间应对天气变化。", "info"))
        else:
            items.append(Item("行程密度", f"{days} 天可以安排一个近郊日，中间留一天缓冲，避免全程赶路。", "info"))

        for interest in interests:
            items.append(Item(interest, _INTEREST_ADVICE[interest], "info"))
        return Section("rhythm", "行程节奏", "🗓️", items)

    def _highlight_section(self, ctx: AdviceContext) -> Section:
        city = ctx.city
        spots = city.highlight_for_month(ctx.day.month)
        items: list[Item] = []
        if spots:
            for text in spots[:3]:
                items.append(Item("当季", text, "good"))
        else:
            items.append(Item("当季", f"{city.name}这个月份没有特别集中的季节性看点，按常规景点安排即可。", "info"))

        month_names = {1: "1 月", 2: "2 月", 3: "3 月", 4: "4 月", 5: "5 月", 6: "6 月",
                       7: "7 月", 8: "8 月", 9: "9 月", 10: "10 月", 11: "11 月", 12: "12 月"}
        others = [item for item in city.highlights if ctx.day.month not in (item.get("months") or [])]
        if others:
            texts = []
            for item in others[:2]:
                months = item.get("months") or []
                span = "、".join(month_names[m] for m in months if m in month_names)
                texts.append(f"{span}：{item.get('text', '')}")
            items.append(Item("其他季节", "；".join(texts), "info"))

        note = city.season_notes.get(
            {"春": "spring", "夏": "summer", "秋": "autumn", "冬": "winter"}[ctx.season]
        )
        if note:
            items.append(Item("季节提示", note, "info"))
        return Section("highlights", "本季看点", "⭐", items)

    def _booking_section(self, ctx: AdviceContext, days: int) -> Section:
        holiday = ctx.holiday
        items: list[Item] = []
        if holiday.is_holiday:
            items.append(Item("预约", "假期热门景点和博物馆通常提前 3—7 天约满，先锁门票再订酒店。", "warn"))
            items.append(Item("住宿", "假期房价上浮明显，尽量订可免费取消的房型。", "warn"))
        elif holiday.is_weekend:
            items.append(Item("预约", "周末热门场馆建议提前 1—3 天预约，演出类更早。", "info"))
        else:
            items.append(Item("预约", "工作日多数场馆当天可约，仍建议出发前确认开放时间。", "good"))

        if days >= 3:
            items.append(Item("交通", "跨城或长途建议提前看返程票，节假日票源更紧张。", "info"))

        next_days = ctx.next_holiday_days
        if holiday.is_holiday:
            if holiday.block_end:
                after = holiday.block_end + timedelta(days=1)
                items.append(
                    Item(
                        "错峰窗口",
                        f"假期到 {holiday.block_end.month} 月 {holiday.block_end.day} 日结束，"
                        f"{after.month} 月 {after.day} 日起人流和价格通常回落。",
                        "info",
                    )
                )
        elif ctx.festival:
            after = ctx.day + timedelta(days=1)
            items.append(
                Item(
                    "错峰窗口",
                    f"{ctx.festival.name}当天商圈和餐厅偏忙，{after.month} 月 {after.day} 日起人流回落，可把主要行程放到之后。",
                    "info",
                )
            )
        elif ctx.next_holiday_name and next_days is not None and 0 < next_days <= 10 and holiday.is_working_day:
            items.append(
                Item(
                    "错峰窗口",
                    f"距{ctx.next_holiday_name}还有 {next_days} 天，节前的工作日通常是价格和人流的相对低谷。",
                    "good",
                )
            )
        return Section("booking", "预约与预算", "🎫", items)

    def _packing_section(self, ctx: AdviceContext, days: int) -> Section:
        weather = ctx.weather
        items: list[Item] = [Item("鞋", "舒适好走的鞋是第一位，行程里步行量通常远超预期。", "info")]
        if weather.umbrella:
            items.append(Item("雨具", "折叠伞或轻便雨衣，户外行程必备。", "warn"))
        if weather.sunscreen:
            items.append(Item("防晒", "防晒霜、墨镜、遮阳帽，户外时间长的话都带上。", "info"))
        if weather.t_max <= 10:
            items.append(Item("保暖", "保暖内衣、围巾手套，北方室内外温差大。", "info"))
        if weather.t_max >= 30:
            items.append(Item("补水", "随身水杯和电解质饮料，高温天别等口渴才喝。", "info"))
        if days >= 3:
            items.append(Item("行李", f"{days} 天建议一个登机箱加一个双肩包，别带太多换洗衣物。", "info"))
        items.append(Item("证件", "身份证、优惠证件、充电宝和常用药，出发前过一遍清单。", "info"))
        return Section("packing", "装备清单", "🎒", items)


register(TravelMode())
