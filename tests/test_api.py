import pytest
from fastapi.testclient import TestClient

from solarsight import api, simulator


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("solarsight.db.DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("SOLARSIGHT_API_KEY", raising=False)
    return TestClient(api.app)


def seed(client, days=4):
    client.post("/api/sites", json=simulator.make_sites())
    batch = [{"site_id": s["site_id"], "ts": ts.isoformat(), "power_kw": kw}
             for s, ts, kw in simulator.generate(days=days)]
    for i in range(0, len(batch), 1000):
        assert client.post("/api/readings", json=batch[i:i + 1000]).status_code == 200
    return len(batch)


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_ingest_counts_and_is_idempotent(client):
    client.post("/api/sites", json=[{"site_id": "A", "district": "Kandy", "capacity_kw": 10}])
    r = [{"site_id": "A", "ts": "2026-10-25T06:00:00+00:00", "power_kw": 4.2}]
    assert client.post("/api/readings", json=r).json()["inserted"] == 1
    assert client.post("/api/readings", json=r).json()["inserted"] == 0  # same reading again


def test_unknown_site_is_rejected(client):
    r = [{"site_id": "NOPE", "ts": "2026-10-25T06:00:00+00:00", "power_kw": 1.0}]
    out = client.post("/api/readings", json=r).json()
    assert out == {"inserted": 0, "rejected_unknown_site": 1}


def test_negative_power_and_naive_timestamp_are_invalid(client):
    client.post("/api/sites", json=[{"site_id": "A", "district": "Kandy", "capacity_kw": 10}])
    bad_power = [{"site_id": "A", "ts": "2026-10-25T06:00:00+00:00", "power_kw": -1}]
    bad_ts = [{"site_id": "A", "ts": "2026-10-25T06:00:00", "power_kw": 1}]
    assert client.post("/api/readings", json=bad_power).status_code == 422
    assert client.post("/api/readings", json=bad_ts).status_code == 422


def test_api_key_required_when_configured(client, monkeypatch):
    monkeypatch.setenv("SOLARSIGHT_API_KEY", "secret")
    sites = [{"site_id": "A", "district": "Kandy", "capacity_kw": 10}]
    assert client.post("/api/sites", json=sites).status_code == 401
    assert client.post("/api/sites", json=sites, headers={"X-API-Key": "secret"}).status_code == 200
    assert client.get("/api/sites").status_code == 200  # reads stay open in this prototype


def test_overview_districts_and_forecast(client):
    seed(client, days=4)
    ov = client.get("/api/overview").json()
    assert ov["points"] and ov["installed_kw"] > 0
    ds = client.get("/api/districts").json()["districts"]
    assert {d["district"] for d in ds} == {"Colombo", "Kandy", "Trincomalee", "Jaffna", "Hambantota"}
    fc = client.get("/api/forecast").json()
    assert len(fc["points"]) == 48
    assert fc["evaluation_last_day"]["mae_kw"] >= 0


def test_forecast_needs_history(client):
    assert client.get("/api/forecast").status_code == 409
