from __future__ import annotations

from fastapi.testclient import TestClient
from api_adjustmenter.main import app

client = TestClient(app)


def test_ruleset_timestamps_are_int():
    r = client.post(
        "/rulesets",
        json={
            "name": "type-test",
            "rules": {"rename": {"userId": "user_id"}},
        },
    )
    assert r.status_code == 200
    rid = r.json()["result"]["ruleset_id"]

    r2 = client.get(f"/rulesets/{rid}")
    assert r2.status_code == 200
    res = r2.json()["result"]

    assert isinstance(res["created_at"], int)
    assert isinstance(res["updated_at"], int)
    assert (res["expires_at"] is None) or isinstance(res["expires_at"], int)
