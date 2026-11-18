"""HTTP 接口测试。"""

from fastapi.testclient import TestClient

from travel_advisor.app import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "commute" in data["modes"]
    assert data["city_count"] >= 20


def test_modes_endpoint():
    data = client.get("/api/modes").json()
    ids = [item["id"] for item in data["modes"]]
    assert ids == ["commute", "travel"]
    for item in data["modes"]:
        assert item["name"] and item["options"] is not None


def test_city_search():
    data = client.get("/api/cities", params={"q": "shang"}).json()
    assert data["cities"]
    assert data["cities"][0]["name"] == "上海"


def test_advice_ok():
    response = client.post(
        "/api/advice",
        json={"city": "上海", "date": "2026-12-24", "mode": "commute", "options": {"depart_time": "08:30"}},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["result"]["sections"]
    assert data["result"]["headline"]
    assert data["meta"]["engine_version"]


def test_advice_unknown_mode_returns_422_with_options():
    response = client.post("/api/advice", json={"city": "上海", "date": "2026-12-24", "mode": "drive"})
    assert response.status_code == 422
    body = response.json()
    assert "available_modes" in body


def test_advice_invalid_date_returns_422():
    response = client.post("/api/advice", json={"city": "上海", "date": "1800-01-01", "mode": "commute"})
    assert response.status_code == 422


def test_root_serves_page():
    response = client.get("/")
    assert response.status_code == 200
    assert "出行建议官" in response.text


def test_rate_limit_blocks_excess_requests(monkeypatch):
    monkeypatch.setenv("TRAVEL_ADVISOR_RATE_LIMIT", "2")
    payload = {"city": "上海", "date": "2026-12-24", "mode": "commute", "use_llm": False}
    assert client.post("/api/advice", json=payload).status_code == 200
    assert client.post("/api/advice", json=payload).status_code == 200
    blocked = client.post("/api/advice", json=payload)
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"
