"""Минимальные проверки, что сервис не сломан. Запуск: pytest -q"""
from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as c:
        assert c.get("/health").json() == {"status": "healthy"}


def test_detect_shape():
    with TestClient(app) as c:
        r = c.post("/detect", json={"text": "Согласно пп. 1 п. 1 ст. 374 НК РФ ..."})
        assert r.status_code == 200
        links = r.json()["links"]
        assert {"law_id": 15, "article": "374", "point_article": "1",
                "subpoint_article": "1"} in links


def test_empty_text():
    with TestClient(app) as c:
        assert c.post("/detect", json={"text": ""}).json() == {"links": []}
