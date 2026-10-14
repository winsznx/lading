import json

import pytest
from fastapi.testclient import TestClient

from api import app as app_module
from api.ratelimit import RateLimiter
from scenarios.scenario_gen import dump, generate

client = TestClient(app_module.app)


@pytest.fixture(autouse=True)
def generous_limiter(monkeypatch):
    monkeypatch.setattr(app_module, "limiter", RateLimiter(per_minute=1000, burst=1000, trusted_proxies=[]))


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scenarios_list_curated_with_disruptions():
    r = client.get("/scenarios")
    assert r.status_code == 200
    ids = {s["id"]: s for s in r.json()}
    assert ids["heldout-1007"]["kind"] == "held-out"
    assert len(ids["p4-far-market"]["disruptions"]) == 4


def test_plan_runs_lading_fefo_validator_and_sim():
    r = client.post("/plan", json={"scenario_id": "p4-far-market", "draws": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lading"]["validation"]["status"] == "PASS"
    assert body["lading"]["plan"]["arm"] == app_module.HEADLINE_ARM
    assert body["fefo"]["plan"]["arm"] == "fefo"
    assert body["lading"]["outcome"]["draws"] == 5
    assert set(body["reasons"]) == {d["batch_id"] for d in body["decisions"]}
    assert body["effect"]


def test_replan_returns_diff_and_effect():
    r = client.post("/replan", json={"scenario_id": "p4-far-market", "disruption_index": 0, "draws": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["effect"].startswith("Delay on Nashik → Mumbai")
    assert body["scenario"]["markets"][1]["travel_h"] == 11
    assert body["lading"]["validation"]["status"] == "PASS"


def test_veto_through_controls_changes_the_plan():
    base = client.post("/plan", json={"scenario_id": "p4-far-market", "draws": 1}).json()
    first = base["lading"]["plan"]["shipments"][0]
    r = client.post(
        "/plan",
        json={
            "scenario_id": "p4-far-market",
            "draws": 1,
            "controls": {
                "locks": [],
                "vetoes": [{"batch_id": first["batch_id"], "market_id": first["market_id"]}],
            },
        },
    )
    moved = [s for s in r.json()["lading"]["plan"]["shipments"] if s["batch_id"] == first["batch_id"]]
    assert all(s["market_id"] != first["market_id"] for s in moved)


def test_bad_scenario_is_schema_invalid_with_path():
    raw = json.loads(dump(generate(3)))
    raw["batches"][2]["kg"] = -1
    r = client.post("/plan", json={"scenario": raw})
    assert r.status_code == 422
    assert r.json() == {"state": "SCHEMA_INVALID", "message": r.json()["message"], "path": "batches[2].kg"}


def test_bad_request_body_is_named():
    r = client.post("/plan", json={"scenario_id": "p4-far-market", "draws": 500})
    assert r.status_code == 422
    assert r.json()["state"] == "SCHEMA_INVALID"


def test_unknown_scenario_is_not_found():
    r = client.post("/plan", json={"scenario_id": "nope"})
    assert r.status_code == 404
    assert r.json()["state"] == "SCENARIO_NOT_FOUND"


def test_oversize_scenario_is_refused():
    raw = json.loads(dump(generate(3)))
    template = raw["batches"][0]
    raw["batches"] = [{**template, "id": f"x{i:03d}"} for i in range(81)]
    r = client.post("/plan", json={"scenario": raw})
    assert r.status_code == 413
    assert r.json()["state"] == "SCENARIO_TOO_LARGE"


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(app_module, "limiter", RateLimiter(per_minute=1, burst=1, trusted_proxies=[]))
    assert client.post("/plan", json={"scenario_id": "p4-far-market", "draws": 1}).status_code == 200
    r = client.post("/plan", json={"scenario_id": "p4-far-market", "draws": 1})
    assert r.status_code == 429
    assert r.json()["state"] == "RATE_LIMITED"


def test_results_whitelist():
    assert client.get("/results/..%2Fpyproject.toml").status_code == 404
    assert client.get("/results/secret.json").json()["state"] == "SCENARIO_NOT_FOUND"


def test_cors_allows_only_configured_origins():
    ok = client.options(
        "/plan", headers={"origin": "http://localhost:5173", "access-control-request-method": "POST"}
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options(
        "/plan", headers={"origin": "https://evil.example", "access-control-request-method": "POST"}
    )
    assert "access-control-allow-origin" not in bad.headers
