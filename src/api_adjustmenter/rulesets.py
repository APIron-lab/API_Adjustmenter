from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import boto3

from .errors import AppError
from .models import TransformRules


@dataclass
class RulesetRecord:
    ruleset_id: str
    name: str
    rules: Dict[str, Any]
    created_at: int
    updated_at: int
    expires_at: Optional[int]


class DynamoRulesetStore:
    """
    DynamoDB numbers must not be float.
    We store epoch seconds as int for created_at/updated_at/expires_at (TTL).
    """

    def __init__(self, *, table_name: str, ttl_seconds: int = 7 * 24 * 3600):
        self.table_name = table_name
        self.ttl_seconds = ttl_seconds
        self.ddb = boto3.resource("dynamodb")
        self.table = self.ddb.Table(table_name)

    def _now(self) -> int:
        return int(time.time())

    def _pk(self, ruleset_id: str) -> str:
        return f"RULESET#{ruleset_id}"

    def create(self, *, name: str, rules: TransformRules, ttl_seconds: Optional[int] = None) -> RulesetRecord:
        rid = str(uuid.uuid4())
        now = self._now()
        ttl = self.ttl_seconds if ttl_seconds is None else int(ttl_seconds)
        expires_at: Optional[int] = None if ttl <= 0 else now + ttl

        item: Dict[str, Any] = {
            "pk": self._pk(rid),
            "ruleset_id": rid,
            "name": name,
            "rules": rules.model_dump(),
            "created_at": now,
            "updated_at": now,
        }
        if expires_at is not None:
            item["expires_at"] = expires_at  # DynamoDB TTL attribute (int)

        self.table.put_item(Item=item)

        return RulesetRecord(
            ruleset_id=rid,
            name=name,
            rules=item["rules"],
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )

    def get(self, ruleset_id: str) -> RulesetRecord:
        resp = self.table.get_item(Key={"pk": self._pk(ruleset_id)})
        item = resp.get("Item")
        if not item:
            raise AppError(
                code="RULESET_NOT_FOUND",
                message="指定された ruleset_id が見つかりません。",
                details={"ruleset_id": ruleset_id},
                http_status=404,
            )
        return RulesetRecord(
            ruleset_id=item["ruleset_id"],
            name=item.get("name", ""),
            rules=item.get("rules", {}),
            created_at=int(item.get("created_at", 0)),
            updated_at=int(item.get("updated_at", 0)),
            expires_at=int(item["expires_at"]) if "expires_at" in item else None,
        )

    def delete(self, ruleset_id: str) -> None:
        _ = self.get(ruleset_id)  # nice 404
        self.table.delete_item(Key={"pk": self._pk(ruleset_id)})

    def list(self, *, limit: int = 50) -> List[RulesetRecord]:
        limit = max(1, min(int(limit), 200))
        resp = self.table.scan(Limit=limit)
        items = resp.get("Items", [])

        out: List[RulesetRecord] = []
        for item in items:
            out.append(
                RulesetRecord(
                    ruleset_id=item.get("ruleset_id", ""),
                    name=item.get("name", ""),
                    rules=item.get("rules", {}),
                    created_at=int(item.get("created_at", 0)),
                    updated_at=int(item.get("updated_at", 0)),
                    expires_at=int(item["expires_at"]) if "expires_at" in item else None,
                )
            )
        out.sort(key=lambda r: r.updated_at, reverse=True)
        return out

    def resolve_rules(self, *, ruleset_id: str, override_rules: Optional[TransformRules]) -> TransformRules:
        rec = self.get(ruleset_id)
        base = TransformRules(**rec.rules)

        if override_rules is None:
            return base

        merged = base.model_dump()
        o = override_rules.model_dump()

        for k in ("rename", "defaults", "cast", "flatten"):
            merged[k] = {**merged.get(k, {}), **o.get(k, {})}

        for k in ("pick", "omit"):
            if o.get(k):
                merged[k] = o[k]

        return TransformRules(**merged)


def default_ruleset_store():
    store = os.environ.get("API_ADJ_RULESET_STORE", "local").strip().lower()
    ttl = int(os.environ.get("API_ADJ_RULESET_TTL_SECONDS", str(7 * 24 * 3600)))

    if store == "dynamodb":
        table = os.environ.get("API_ADJ_RULESET_TABLE")
        if not table:
            raise RuntimeError("API_ADJ_RULESET_TABLE is required for DynamoDB store")
        return DynamoRulesetStore(table_name=table, ttl_seconds=ttl)

    # Local fallback (for local dev)
    from pathlib import Path
    import json

    @dataclass
    class _LocalRec:
        ruleset_id: str
        name: str
        rules: Dict[str, Any]
        created_at: int
        updated_at: int
        expires_at: Optional[int]

    class LocalStore:
        def __init__(self, ttl_seconds: int, persist: bool):
            self.ttl_seconds = ttl_seconds
            self.persist = persist
            self.path = Path.home() / ".api_adjustmenter" / "rulesets.json"
            self.data: Dict[str, _LocalRec] = {}
            if self.persist:
                self._load()

        def _now(self) -> int:
            return int(time.time())

        def _gc(self) -> None:
            now = self._now()
            expired = [k for k, v in self.data.items() if v.expires_at is not None and v.expires_at <= now]
            for k in expired:
                self.data.pop(k, None)
            if expired and self.persist:
                self._save()

        def _load(self) -> None:
            if not self.path.exists():
                return
            try:
                obj = json.loads(self.path.read_text(encoding="utf-8"))
                for it in obj.get("rulesets", []):
                    self.data[it["ruleset_id"]] = _LocalRec(
                        ruleset_id=it["ruleset_id"],
                        name=it.get("name", ""),
                        rules=it["rules"],
                        created_at=int(it["created_at"]),
                        updated_at=int(it["updated_at"]),
                        expires_at=int(it["expires_at"]) if it.get("expires_at") is not None else None,
                    )
                self._gc()
            except Exception:
                self.data = {}

        def _save(self) -> None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "rulesets": [
                    {
                        "ruleset_id": r.ruleset_id,
                        "name": r.name,
                        "rules": r.rules,
                        "created_at": r.created_at,
                        "updated_at": r.updated_at,
                        "expires_at": r.expires_at,
                    }
                    for r in self.data.values()
                ]
            }
            self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        def create(self, *, name: str, rules: TransformRules, ttl_seconds: Optional[int] = None) -> RulesetRecord:
            self._gc()
            rid = str(uuid.uuid4())
            now = self._now()
            ttl2 = self.ttl_seconds if ttl_seconds is None else int(ttl_seconds)
            exp = None if ttl2 <= 0 else now + ttl2
            rec = _LocalRec(ruleset_id=rid, name=name, rules=rules.model_dump(), created_at=now, updated_at=now, expires_at=exp)
            self.data[rid] = rec
            if self.persist:
                self._save()
            return RulesetRecord(rid, name, rec.rules, now, now, exp)

        def get(self, ruleset_id: str) -> RulesetRecord:
            self._gc()
            rec = self.data.get(ruleset_id)
            if not rec:
                raise AppError(code="RULESET_NOT_FOUND", message="指定された ruleset_id が見つかりません。", details={"ruleset_id": ruleset_id}, http_status=404)
            return RulesetRecord(rec.ruleset_id, rec.name, rec.rules, rec.created_at, rec.updated_at, rec.expires_at)

        def delete(self, ruleset_id: str) -> None:
            self._gc()
            if ruleset_id not in self.data:
                raise AppError(code="RULESET_NOT_FOUND", message="指定された ruleset_id が見つかりません。", details={"ruleset_id": ruleset_id}, http_status=404)
            self.data.pop(ruleset_id, None)
            if self.persist:
                self._save()

        def list(self, *, limit: int = 50) -> List[RulesetRecord]:
            self._gc()
            items = sorted(self.data.values(), key=lambda r: r.updated_at, reverse=True)
            items = items[: max(1, min(int(limit), 200))]
            return [RulesetRecord(i.ruleset_id, i.name, i.rules, i.created_at, i.updated_at, i.expires_at) for i in items]

        def resolve_rules(self, *, ruleset_id: str, override_rules: Optional[TransformRules]) -> TransformRules:
            rec = self.get(ruleset_id)
            base = TransformRules(**rec.rules)
            if override_rules is None:
                return base
            merged = base.model_dump()
            o = override_rules.model_dump()
            for k in ("rename", "defaults", "cast", "flatten"):
                merged[k] = {**merged.get(k, {}), **o.get(k, {})}
            for k in ("pick", "omit"):
                if o.get(k):
                    merged[k] = o[k]
            return TransformRules(**merged)

    persist_flag = os.environ.get("API_ADJ_RULESET_PERSIST", "1").strip().lower()
    persist = persist_flag not in ("0", "false", "no")
    return LocalStore(ttl_seconds=ttl, persist=persist)
