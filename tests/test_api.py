from __future__ import annotations

from fastapi.testclient import TestClient
from api_adjustmenter.main import app

client = TestClient(app)

def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True

def test_normalize_snake_and_coerce():
    r = client.post(
        "/normalize",
        json={
            "input": {"userId": "12", "created_at": 1700000000, "name": ""},
            "options": {"key_style": "snake", "coerce_numbers": True, "empty_to_null": True, "date_to_iso": True},
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["output"]["user_id"] == 12
    assert j["output"]["name"] is None
    assert "T" in j["output"]["created_at"]

def test_transform_rules():
    r = client.post(
        "/transform",
        json={
            "input": {"userId": "12", "profile": {"zip": "1000001"}},
            "rules": {
                "rename": {"userId": "user_id"},
                "defaults": {"profile.country": "JP"},
                "cast": {"user_id": "int", "profile.zip": "string"},
                "flatten": {"profile": "profile_"},
            },
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["output"]["user_id"] == 12
    assert j["output"]["profile_zip"] == "1000001"
    assert j["output"]["profile_country"] == "JP"

def test_diff_breaking():
    r = client.post(
        "/diff",
        json={
            "before": {"id": 1, "name": "a", "tags": ["x"]},
            "after": {"id": "1", "full_name": "a", "tags": "x"},
        },
    )
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["breaking"] is True
    assert len(j["diff"]["type_changes"]) >= 1
