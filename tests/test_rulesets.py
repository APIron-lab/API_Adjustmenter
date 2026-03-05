from __future__ import annotations

from fastapi.testclient import TestClient
from api_adjustmenter.main import app

client = TestClient(app)


def _assert_meta(meta: dict):
    assert "execution_ms" in meta
    assert "input_length" in meta
    assert "request_id" in meta


def test_ruleset_create_get_transform_delete():
    # 1) create ruleset
    r = client.post(
        "/rulesets",
        json={
            "name": "demo",
            "rules": {
                "rename": {"userId": "user_id"},
                "cast": {"user_id": "int"},
                "flatten": {"profile": "profile_"},
                "pick": ["user_id", "profile_zip"],
                "omit": [],
            },
        },
    )
    assert r.status_code == 200
    j = r.json()
    _assert_meta(j["meta"])
    ruleset_id = j["result"]["ruleset_id"]
    assert ruleset_id

    # 2) get ruleset
    r2 = client.get(f"/rulesets/{ruleset_id}")
    assert r2.status_code == 200
    j2 = r2.json()
    _assert_meta(j2["meta"])
    assert j2["result"]["ruleset_id"] == ruleset_id

    # 3) transform using ruleset_id
    r3 = client.post(
        "/transform",
        json={
            "input": {"userId": "12", "profile": {"zip": "1000001"}},
            "ruleset_id": ruleset_id,
        },
    )
    assert r3.status_code == 200
    j3 = r3.json()
    _assert_meta(j3["meta"])
    out = j3["result"]["output"]
    assert out["user_id"] == 12
    assert out["profile_zip"] == "1000001"
    # pick により profile_country 等は無い
    assert "profile_country" not in out

    # 4) delete ruleset
    r4 = client.delete(f"/rulesets/{ruleset_id}")
    assert r4.status_code == 200
    j4 = r4.json()
    _assert_meta(j4["meta"])
    assert j4["result"]["deleted"] is True
