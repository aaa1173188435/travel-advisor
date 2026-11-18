FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY travel_advisor ./travel_advisor
COPY web ./web

EXPOSE 8010

# 托管平台会注入 PORT（Render/Railway/Fly 都是），本地缺省 8010
CMD ["sh", "-c", "uvicorn travel_advisor.app:app --host 0.0.0.0 --port ${PORT:-8010}"]
