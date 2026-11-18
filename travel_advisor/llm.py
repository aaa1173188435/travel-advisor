"""可选的大模型润色层。

规则引擎负责「事实」，大模型只负责把事实组织成更自然的推荐语。
没有配置 API Key 时整层自动跳过，接口行为不受影响。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from .env import load_env_files

load_env_files()

SYSTEM_PROMPT = (
    "你是一位中文出行建议编辑。用户已经拿到一份由规则引擎生成的出行建议，"
    "你的任务是用 2—3 句自然、口语化的中文把结论润色一遍。"
    "必须遵守：只使用给定事实，不得编造天气、限行、票价、人流等数据；"
    "不要逐条复述列表；不要使用 Markdown 标题；总长度不超过 120 个汉字；"
    "如果事实里存在风险（降水、高温、严寒、限行、节假日人流），必须点明；"
    "提供 must_mention 时，每一类事实都必须在润色文本中出现。"
)

# must_mention 标签 → 判定关键词（命中任意一个即视为提到）
_KEYWORDS: dict[str, tuple[str, ...]] = {
    "节假日人流": ("假期", "节假", "人流", "人多", "拥挤", "游客", "客流"),
    "通勤高峰": ("高峰", "拥堵", "挤"),
    "降水": ("雨", "雪", "降水", "伞"),
    "高温": ("高温", "炎热", "热"),
    "严寒": ("严寒", "寒冷", "低温", "冷", "保暖"),
    "城市未收录": ("未收录", "估算", "兜底", "按温带"),
}


def missing_points(text: str, required: list[str] | None) -> list[str]:
    """检查润色文本是否覆盖了规则要求必须提到的事实。"""
    if not required:
        return []
    missing = []
    for point in required:
        keywords = _KEYWORDS.get(point, (point,))
        if not any(keyword in text for keyword in keywords):
            missing.append(point)
    return missing


@dataclass
class LlmConfig:
    api_key: str
    base_url: str
    model: str
    timeout: float

    @property
    def endpoint(self) -> str:
        return self.base_url.rstrip("/") + "/chat/completions"

    def public(self) -> dict[str, Any]:
        return {"enabled": True, "model": self.model, "base_url": self.base_url}


def config_from_env() -> LlmConfig | None:
    api_key = os.getenv("TRAVEL_ADVISOR_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    base_url = os.getenv("TRAVEL_ADVISOR_LLM_BASE_URL", "https://api.deepseek.com/v1")
    model = os.getenv("TRAVEL_ADVISOR_LLM_MODEL", "deepseek-chat")
    try:
        timeout = float(os.getenv("TRAVEL_ADVISOR_LLM_TIMEOUT", "12"))
    except ValueError:
        timeout = 12.0
    return LlmConfig(api_key=api_key, base_url=base_url, model=model, timeout=timeout)


def status() -> dict[str, Any]:
    config = config_from_env()
    if not config:
        return {"enabled": False, "reason": "未设置 TRAVEL_ADVISOR_LLM_API_KEY 或 DEEPSEEK_API_KEY，使用纯规则模式"}
    return config.public()


def _build_messages(facts: dict[str, Any], draft: dict[str, Any], required: list[str] | None = None) -> list[dict[str, str]]:
    payload = {
        "facts": facts,
        "draft": {
            "headline": draft.get("headline"),
            "score": draft.get("score"),
            "score_label": draft.get("score_label"),
            "tags": draft.get("tags"),
            "sections": [
                {
                    "title": section.get("title"),
                    "items": [item.get("text") for item in section.get("items", [])],
                }
                for section in draft.get("sections", [])
            ],
        },
    }
    instruction = "请根据以下事实润色出行建议：\n"
    if required:
        instruction += "必须提到：" + "、".join(required) + "。\n"
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": instruction + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
    ]


def polish(
    facts: dict[str, Any],
    draft: dict[str, Any],
    config: LlmConfig | None = None,
    required: list[str] | None = None,
) -> tuple[str | None, str | None]:
    """返回 (润色文本, 错误信息)。失败时返回 (None, 错误原因)，调用方自行降级。"""
    config = config or config_from_env()
    if not config:
        return None, "未配置大模型 API Key"

    try:
        import httpx
    except ImportError:  # pragma: no cover
        return None, "未安装 httpx，无法调用大模型"

    body = {
        "model": config.model,
        "messages": _build_messages(facts, draft, required),
        "temperature": 0.6,
        "max_tokens": 300,
        "stream": False,
    }
    headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=config.timeout) as client:
            response = client.post(config.endpoint, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        text = " ".join(str(text).split()).strip()
        if not text:
            return None, "大模型返回了空内容"
        return text[:400], None
    except Exception as exc:  # noqa: BLE001 - 任何异常都降级为规则结果
        return None, f"{type(exc).__name__}: {exc}"
