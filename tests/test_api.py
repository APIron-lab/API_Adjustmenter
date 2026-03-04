from __future__ import annotations

from fastapi.testclient import TestClient
from api_adjustmenter.main import app

client = TestClient(app)


def _assert_meta(meta: dict):
    assert "execution_ms" in meta
    assert "input_length" in meta
    assert "request_id" in meta


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    j = r.json()
    assert "result" in j
    assert "meta" in j
    _assert_meta(j["meta"])


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
    _assert_meta(j["meta"])
    out = j["result"]["output"]
    assert out["user_id"] == 12
    assert out["name"] is None
    assert "T" in out["created_at"]


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
    _assert_meta(j["meta"])
    out = j["result"]["output"]
    assert out["user_id"] == 12
    assert out["profile_zip"] == "1000001"
    assert out["profile_country"] == "JP"


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
    _assert_meta(j["meta"])
    assert j["result"]["diff"]["breaking"] is True
    assert len(j["result"]["diff"]["diff"]["type_changes"]) >= 1
