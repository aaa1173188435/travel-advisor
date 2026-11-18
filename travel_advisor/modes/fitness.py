"""健身模式：按运动项目、时长、强度和开始时间，结合天气给出训练安排。"""

from __future__ import annotations

from datetime import time

from ..context import AdviceContext
from ..registry import register
from ..weather import display_temp
from .base import Item, Mode, ModeResult, Section, clamp, score_label

# (label, indoor)
_ACTIVITIES: dict[str, tuple[str, bool]] = {
    "run": ("跑步", False),
    "ride": ("骑行", False),
    "outdoor": ("户外训练", False),
    "ball": ("球类", False),
    "gym": ("健身房", True),
    "swim": ("游泳", True),
}

_INTENSITY = {
    "light": ("轻松", "能正常聊天，以活动身体为主"),
    "moderate": ("中等", "呼吸加快、微微出汗，能说短句"),
    "hard": ("高强度", "心率明显上升，难以说完整句子"),
}


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


class FitnessMode(Mode):
    id = "fitness"
    name = "健身"
    icon = "💪"
    description = "跑步、骑行、健身、游泳等运动安排，重点看天气、时段与强度"
    options = [
        {
            "key": "activity",
            "label": "运动项目",
            "type": "select",
            "default": "run",
            "choices": [
                {"value": "run", "label": "跑步"},
                {"value": "ride", "label": "骑行"},
                {"value": "outdoor", "label": "户外训练"},
                {"value": "ball", "label": "球类"},
                {"value": "gym", "label": "健身房"},
                {"value": "swim", "label": "游泳"},
            ],
        },
        {
            "key": "duration",
            "label": "计划时长（分钟）",
            "type": "number",
            "default": 45,
            "min": 15,
            "max": 180,
        },
        {
            "key": "intensity",
            "label": "目标强度",
            "type": "select",
            "default": "moderate",
            "choices": [
                {"value": "light", "label": "轻松"},
                {"value": "moderate", "label": "中等"},
                {"value": "hard", "label": "高强度"},
            ],
        },
        {
            "key": "start_time",
            "label": "计划开始时间",
            "type": "time",
            "default": "07:00",
        },
    ]

    def normalize_options(self, options: dict) -> dict:
        activity = str(options.get("activity") or "run")
        if activity not in _ACTIVITIES:
            activity = "run"
        try:
            duration = int(options.get("duration") or 45)
        except (TypeError, ValueError):
            duration = 45
        duration = max(15, min(180, duration))
        intensity = str(options.get("intensity") or "moderate")
        if intensity not in _INTENSITY:
            intensity = "moderate"
        return {
            "activity": activity,
            "duration": duration,
            "intensity": intensity,
            "start_time": options.get("start_time") or "07:00",
        }

    def advise(self, ctx: AdviceContext) -> ModeResult:
        options = self.normalize_options(ctx.options)
        activity = options["activity"]
        label, indoor = _ACTIVITIES[activity]
        duration = options["duration"]
        intensity = options["intensity"]
        start = _parse_time(options["start_time"])

        weather = ctx.weather
        score = 90.0
        tags: list[str] = ["室内" if indoor else "户外", label]

        if indoor:
            if ctx.holiday.is_working_day and start and 18 <= start.hour < 20:
                score -= 5
                tags.append("器械高峰")
            if ctx.holiday.is_holiday:
                score -= 3
                tags.append("假期人多")
        else:
            if weather.rain_prob >= 0.45:
                score -= 25
                tags.append("有降水")
            elif weather.rain_prob >= 0.30:
                score -= 15
                tags.append("可能降水")
            elif weather.rain_prob >= 0.18:
                score -= 6
            if weather.t_max >= 35:
                score -= 18
                tags.append("高温")
            elif weather.t_max >= 32:
                score -= 10
                tags.append("偏热")
            if weather.t_max <= -10:
                score -= 18
                tags.append("严寒")
            elif weather.t_max <= 0:
                score -= 12
                tags.append("寒冷")
            if intensity == "hard" and (weather.t_max >= 32 or weather.t_max <= 0):
                score -= 4
            if activity == "ride" and weather.rain_prob >= 0.30:
                score -= 5
                tags.append("路面湿滑")

        final_score = clamp(score)
        sections = [
            self._weather_section(ctx),
            self._window_section(ctx, indoor, start),
            self._plan_section(ctx, label, indoor, duration, intensity),
            self._gear_section(ctx, activity, indoor),
            self._safety_section(ctx, activity, indoor, intensity),
        ]
        headline = self._headline(ctx, label, indoor, duration, intensity)
        return ModeResult(
            mode_id=self.id,
            mode_name=self.name,
            headline=headline,
            score=final_score,
            score_label=score_label(final_score),
            tags=tags,
            sections=sections,
        )

    def _headline(self, ctx: AdviceContext, label: str, indoor: bool, duration: int, intensity: str) -> str:
        weather = ctx.weather
        intensity_label = _INTENSITY[intensity][0]
        if indoor:
            advice = f"{label}不受天气影响，按计划进行即可"
        elif weather.rain_prob >= 0.45:
            advice = f"降水概率高，{label}建议改到室内或改天"
        elif weather.rain_prob >= 0.30:
            advice = f"可能有降水，{label}记得带雨具并留意路面"
        elif weather.t_max >= 35:
            advice = f"高温天，{label}建议清晨或日落后进行"
        elif weather.t_max <= 0:
            advice = f"天气寒冷，{label}务必充分热身、缩短户外停留"
        else:
            advice = f"天气条件适合{label}"

        return (
            f"{ctx.city.name}{ctx.holiday.weekday_name}：{weather.condition}，{_temp_text(ctx)}。"
            f"{advice}；计划 {duration} 分钟，强度目标：{intensity_label}。"
        )

    def _weather_section(self, ctx: AdviceContext) -> Section:
        weather = ctx.weather
        items = [
            Item("气温", f"常年同期 {_temp_text(ctx)}，体感{weather.comfort}。", "info"),
            Item(
                "降水",
                f"{weather.condition}，降水概率约 {round(weather.rain_prob * 100)}%。",
                "warn" if weather.rain_prob >= 0.30 else "good",
            ),
            Item("穿衣", weather.clothing, "info"),
        ]
        if weather.diurnal_range >= 10:
            items.append(Item("温差", f"昼夜温差约 {round(weather.diurnal_range)}℃，运动前后注意加减衣。", "info"))
        return Section("weather", "天气与体感", "🌤️", items)

    def _window_section(self, ctx: AdviceContext, indoor: bool, start: time | None) -> Section:
        weather = ctx.weather
        items: list[Item] = []
        if indoor:
            items.append(Item("时段", "室内运动不受天气限制，按自己的作息安排。", "good"))
            if ctx.holiday.is_working_day:
                items.append(Item("避开高峰", "工作日 18:00—20:00 器械和更衣室最挤，可提前到 17:00 或推迟到 20:30。", "info"))
            if ctx.holiday.is_holiday:
                items.append(Item("假期", "假期下午健身房人较多，上午通常更空。", "info"))
        else:
            if weather.rain_prob >= 0.45:
                items.append(Item("时段", "降雨概率高，优先改室内训练；必须户外的话选雨停间歇。", "warn"))
            elif weather.t_max >= 32:
                items.append(Item("时段", "避开 11:00—16:00，选清晨 6:00—8:00 或日落后 19:00 以后。", "warn"))
            elif weather.t_max <= 5:
                items.append(Item("时段", "选 10:00—15:00 气温最高的时段，避免清晨和夜间户外。", "warn"))
            else:
                items.append(Item("时段", "上午 9:00—11:00 或傍晚 17:00—19:00 都比较合适。", "good"))
        if start:
            items.append(Item("你的计划", f"计划 {start.strftime('%H:%M')} 开始，出门前再看一眼实时天气。", "info"))
        return Section("window", "运动时机", "⏰", items)

    def _plan_section(self, ctx: AdviceContext, label: str, indoor: bool, duration: int, intensity: str) -> Section:
        intensity_label, intensity_text = _INTENSITY[intensity]
        warmup = min(10, max(5, duration // 6))
        main = max(10, duration - warmup - 5)
        items = [
            Item("热身", f"先做 {warmup} 分钟动态热身，天冷时延长到 10 分钟。", "info"),
            Item("主训练", f"{label}约 {main} 分钟，强度保持「{intensity_label}」：{intensity_text}。", "good"),
            Item("放松", "留 5 分钟拉伸和慢走，别突然停下。", "info"),
        ]
        if duration >= 60:
            items.append(Item("补水", f"{duration} 分钟的训练，每 20 分钟补水 100—150ml。", "info"))
        if intensity == "hard":
            items.append(Item("强度", "高强度训练后安排 24 小时恢复，别连续两天练同一肌群。", "warn"))
        return Section("plan", "训练安排", "🏃", items)

    def _gear_section(self, ctx: AdviceContext, activity: str, indoor: bool) -> Section:
        weather = ctx.weather
        items: list[Item] = []
        if activity == "run":
            items.append(Item("跑鞋", "选缓震好的跑鞋，鞋底磨损明显就换一双。", "info"))
        elif activity == "ride":
            items.append(Item("骑行", "头盔必戴，检查胎压和刹车，夜间加尾灯。", "warn"))
        elif activity == "gym":
            items.append(Item("健身", "训练鞋、毛巾、水杯，力量训练记得护腕护腰。", "info"))
        elif activity == "swim":
            items.append(Item("游泳", "泳镜、泳帽、拖鞋，下水前确认泳池水质和救生员在位。", "info"))
        else:
            items.append(Item("装备", "合脚的运动鞋和透气衣物，按项目带好护具。", "info"))

        if not indoor:
            if weather.umbrella:
                items.append(Item("雨具", "带一件轻便雨衣，比伞更适合运动。", "warn"))
            if weather.sunscreen:
                items.append(Item("防晒", "防晒霜和遮阳帽，长时间户外每 2 小时补涂。", "info"))
            if weather.t_max <= 5:
                items.append(Item("保暖", "分层穿衣，外层防风，热了可以脱一层。", "info"))
            if weather.t_max >= 30:
                items.append(Item("补水", "带水或电解质饮料，别等口渴才喝。", "info"))
        return Section("gear", "装备清单", "🎒", items)

    def _safety_section(self, ctx: AdviceContext, activity: str, indoor: bool, intensity: str) -> Section:
        weather = ctx.weather
        items: list[Item] = []
        if not indoor and weather.t_max >= 32:
            items.append(Item("防中暑", "出现头晕、恶心、停止出汗要立刻阴凉处休息并补水。", "warn"))
        if not indoor and weather.t_max <= 0:
            items.append(Item("防失温", "手脚发麻、发抖要及时回室内，别硬撑。", "warn"))
        if not indoor and weather.rain_prob >= 0.30:
            items.append(Item("路面", "雨天路滑，跑步和骑行都减速，避开井盖和标线。", "warn"))
        if activity == "swim":
            items.append(Item("游泳安全", "不熟悉的水域不下水，量力而行，别单独野泳。", "warn"))
        if intensity == "hard":
            items.append(Item("身体信号", "胸闷、心悸、异常气短立即停止，必要时就医。", "warn"))
        if not items:
            items.append(Item("安全", "按计划训练，注意补水和热身，身体不适就停。", "good"))
        return Section("safety", "安全提醒", "🛡️", items)


register(FitnessMode())
