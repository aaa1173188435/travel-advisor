"""城市档案：气候常年值、季节性看点、交通提示与模糊匹配。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_FILE = Path(__file__).parent / "data" / "cities.json"

_STRIP_SUFFIXES = ("特别行政区", "自治区", "地区", "省", "市", "县", "区")


@dataclass
class CityProfile:
    id: str
    name: str
    province: str
    lat: float
    lon: float
    tier: int
    high: list[float]
    low: list[float]
    rainy_days: list[float]
    climate_note: str
    season_notes: dict[str, str]
    highlights: list[dict[str, Any]]
    transit: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    matched: bool = True

    @property
    def has_subway(self) -> bool:
        return bool(self.transit.get("subway", False))

    @property
    def restriction(self) -> str:
        return str(self.transit.get("restriction", "") or "")

    def highlight_for_month(self, month: int) -> list[str]:
        out = []
        for item in self.highlights:
            months = item.get("months") or []
            if month in months:
                out.append(str(item.get("text", "")))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "province": self.province,
            "lat": self.lat,
            "lon": self.lon,
            "tier": self.tier,
            "tags": self.tags,
            "matched": self.matched,
            "has_subway": self.has_subway,
        }


def _normalize(text: str) -> str:
    value = text.strip().lower()
    value = re.sub(r"\s+", "", value)
    for suffix in _STRIP_SUFFIXES:
        if value.endswith(suffix) and len(value) > len(suffix):
            value = value[: -len(suffix)]
    return value


def _to_float_list(values: Any, expected: int = 12) -> list[float]:
    if not isinstance(values, list) or len(values) != expected:
        raise ValueError(f"需要 {expected} 个月份数值，实际为 {values!r}")
    return [float(item) for item in values]


def _parse(item: dict[str, Any]) -> CityProfile:
    climate = item.get("climate", {})
    return CityProfile(
        id=str(item["id"]),
        name=str(item["name"]),
        province=str(item.get("province", "")),
        lat=float(item.get("lat", 30.0)),
        lon=float(item.get("lon", 120.0)),
        tier=int(item.get("tier", 2)),
        high=_to_float_list(climate.get("high")),
        low=_to_float_list(climate.get("low")),
        rainy_days=_to_float_list(climate.get("rainy_days")),
        climate_note=str(climate.get("note", "")),
        season_notes={str(k): str(v) for k, v in (item.get("season_notes") or {}).items()},
        highlights=[dict(x) for x in (item.get("highlights") or [])],
        transit=dict(item.get("transit") or {}),
        tags=[str(tag) for tag in (item.get("tags") or [])],
        aliases=[str(alias) for alias in (item.get("aliases") or [])],
    )


@lru_cache(maxsize=1)
def _load_cities() -> tuple[list[CityProfile], dict[str, CityProfile], dict[str, CityProfile]]:
    with DATA_FILE.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    cities = [_parse(item) for item in raw.get("cities", [])]
    by_key: dict[str, CityProfile] = {}
    for city in cities:
        for key in [city.id, city.name, *_normalize_keys(city)]:
            by_key.setdefault(key, city)
    return cities, by_key, {city.id: city for city in cities}


def _normalize_keys(city: CityProfile) -> list[str]:
    keys = []
    for alias in city.aliases:
        keys.append(_normalize(alias))
    keys.append(_normalize(city.name))
    return [key for key in keys if key]


def all_cities() -> list[CityProfile]:
    return list(_load_cities()[0])


def search(query: str, limit: int = 8) -> list[CityProfile]:
    cities, by_key, _ = _load_cities()
    needle = _normalize(query)
    if not needle:
        return cities[:limit]
    exact = by_key.get(needle)
    scored: list[tuple[int, CityProfile]] = []
    for city in cities:
        keys = [city.id, *_normalize_keys(city)]
        if exact is city:
            scored.append((0, city))
            continue
        if any(key.startswith(needle) for key in keys):
            scored.append((1, city))
            continue
        if any(needle in key for key in keys):
            scored.append((2, city))
    scored.sort(key=lambda pair: (pair[0], pair[1].tier, pair[1].name))
    return [city for _, city in scored[:limit]]


def generic_profile(name: str) -> CityProfile:
    """未收录城市：按温带季风气候的常年平均给出兜底档案。"""
    return CityProfile(
        id="__generic__",
        name=name.strip() or "未知城市",
        province="",
        lat=32.0,
        lon=118.0,
        tier=3,
        high=[8, 11, 16, 22, 27, 30, 32, 31, 27, 21, 15, 9],
        low=[-1, 1, 6, 12, 17, 21, 24, 23, 19, 12, 6, 0],
        rainy_days=[5, 6, 8, 9, 10, 12, 13, 11, 8, 6, 5, 4],
        climate_note="未收录城市，按温带季风气候的常年平均估算",
        season_notes={
            "spring": "气温回升但波动较大，早晚偏凉。",
            "summer": "高温多雨，午后易有雷阵雨。",
            "autumn": "天高气爽，昼夜温差逐渐拉大。",
            "winter": "寒冷干燥，注意防风保暖。",
        },
        highlights=[],
        transit={"subway": False, "restriction": "", "note": ""},
        tags=["未收录"],
        aliases=[],
        matched=False,
    )


def resolve(query: str) -> CityProfile:
    needle = _normalize(query)
    if not needle:
        return generic_profile(query)
    _, by_key, _ = _load_cities()
    city = by_key.get(needle)
    if city:
        return city
    results = search(query, limit=1)
    if results and results[0].matched:
        # 只有前缀/包含匹配也接受，但要求匹配度足够高，避免「南」命中「南京」
        matched_key = _normalize(results[0].name)
        if needle == matched_key or len(needle) >= 2 and needle in matched_key:
            return results[0]
    return generic_profile(query)
