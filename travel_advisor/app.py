"""FastAPI 应用：静态页面 + 出行建议 API。"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import cities, engine, llm, weather_api
from .schema import AdviceRequest

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="出行建议官",
    description="输入日期、城市与出行模式，返回可解释的出行建议。",
    version=engine.ENGINE_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 公网部署时保护后端额度：按 IP 限制生成请求频率（滑动窗口）
_RATE_BUCKETS: dict[str, deque[float]] = {}
_RATE_LOCK = threading.Lock()
_RATE_WINDOW_SECONDS = 60


def _rate_limit() -> int:
    try:
        return int(os.getenv("TRAVEL_ADVISOR_RATE_LIMIT", "30"))
    except ValueError:
        return 30


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    limit = _rate_limit()
    if request.method == "POST" and request.url.path == "/api/advice" and limit > 0:
        ip = _client_ip(request)
        now = time.time()
        with _RATE_LOCK:
            bucket = _RATE_BUCKETS.setdefault(ip, deque())
            while bucket and bucket[0] <= now - _RATE_WINDOW_SECONDS:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "请求过于频繁，请稍后再试"},
                    headers={"Retry-After": str(_RATE_WINDOW_SECONDS)},
                )
            bucket.append(now)
    return await call_next(request)


@app.exception_handler(engine.UnknownModeError)
async def _unknown_mode_handler(request: Request, exc: engine.UnknownModeError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "detail": str(exc),
            "available_modes": [item["id"] for item in engine.modes_info()],
        },
    )


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "engine_version": engine.ENGINE_VERSION,
        "modes": [item["id"] for item in engine.modes_info()],
        "city_count": len(cities.all_cities()),
        "llm": llm.status(),
        "weather": weather_api.status(),
    }


@app.get("/api/modes")
def list_modes() -> dict[str, Any]:
    return {"modes": engine.modes_info()}


@app.get("/api/cities")
def search_cities(q: str = Query("", max_length=40), limit: int = Query(8, ge=1, le=30)) -> dict[str, Any]:
    results = cities.search(q, limit=limit)
    return {"query": q, "cities": [city.to_dict() for city in results]}


@app.post("/api/advice")
def create_advice(payload: AdviceRequest) -> dict[str, Any]:
    return engine.advise(
        city=payload.city,
        day=payload.date,
        mode_id=payload.mode,
        options=payload.options,
        use_llm=payload.use_llm,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
