from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .errors import AppError
from .models import TransformRules


@dataclass
class RulesetRecord:
    ruleset_id: str
    name: str
    rules: Dict[str, Any]  # TransformRules as dict
    created_at: float
    updated_at: float
    expires_at: Optional[float]  # None means never expire


class RulesetStore:
    """
    Local MVP store:
      - In-memory dictionary
      - Optional persistence to JSON file
      - TTL support (default 7 days)
    """

    def __init__(self, *, ttl_seconds: int = 7 * 24 * 3600, persist_path: Optional[str] = None):
        self.ttl_seconds = ttl_seconds
        self.persist_path = Path(persist_path) if persist_path else None
        self._data: Dict[str, RulesetRecord] = {}
        self._load()

    def _now(self) -> float:
        return time.time()

    def _gc(self) -> None:
        now = self._now()
        expired = [rid for rid, rec in self._data.items() if rec.expires_at is not None and rec.expires_at <= now]
        for rid in expired:
            self._data.pop(rid, None)
        if expired:
            self._save()

    def _load(self) -> None:
        if not self.persist_path:
            return
        if not self.persist_path.exists():
            return
        try:
            raw = json.loads(self.persist_path.read_text(encoding="utf-8"))
            for item in raw.get("rulesets", []):
                rec = RulesetRecord(
                    ruleset_id=item["ruleset_id"],
                    name=item.get("name", ""),
                    rules=item["rules"],
                    created_at=float(item["created_at"]),
                    updated_at=float(item["updated_at"]),
                    expires_at=item.get("expires_at"),
                )
                self._data[rec.ruleset_id] = rec
            self._gc()
        except Exception:
            # If persistence is broken, start clean (local MVP behavior)
            self._data = {}

    def _save(self) -> None:
        if not self.persist_path:
            return
        self.persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "rulesets": [
                {
                    "ruleset_id": rec.ruleset_id,
                    "name": rec.name,
                    "rules": rec.rules,
                    "created_at": rec.created_at,
                    "updated_at": rec.updated_at,
                    "expires_at": rec.expires_at,
                }
                for rec in self._data.values()
            ]
        }
        self.persist_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def create(self, *, name: str, rules: TransformRules, ttl_seconds: Optional[int] = None) -> RulesetRecord:
        self._gc()
        rid = str(uuid.uuid4())
        now = self._now()
        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        expires_at = None if ttl <= 0 else now + ttl

        rec = RulesetRecord(
            ruleset_id=rid,
            name=name,
            rules=rules.model_dump(),
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
        self._data[rid] = rec
        self._save()
        return rec

    def get(self, ruleset_id: str) -> RulesetRecord:
        self._gc()
        rec = self._data.get(ruleset_id)
        if not rec:
            raise AppError(
                code="RULESET_NOT_FOUND",
                message="指定された ruleset_id が見つかりません。",
                details={"ruleset_id": ruleset_id},
                http_status=404,
            )
        return rec

    def delete(self, ruleset_id: str) -> None:
        self._gc()
        if ruleset_id not in self._data:
            raise AppError(
                code="RULESET_NOT_FOUND",
                message="指定された ruleset_id が見つかりません。",
                details={"ruleset_id": ruleset_id},
                http_status=404,
            )
        self._data.pop(ruleset_id, None)
        self._save()

    def list(self, *, limit: int = 50) -> List[RulesetRecord]:
        self._gc()
        items = sorted(self._data.values(), key=lambda r: r.updated_at, reverse=True)
        return items[: max(1, min(limit, 200))]

    def resolve_rules(self, *, ruleset_id: str, override_rules: Optional[TransformRules]) -> TransformRules:
        """
        Base ruleset + override merge.
        Override overwrites fields if provided (dict merge for maps, replace for lists).
        """
        rec = self.get(ruleset_id)
        base = TransformRules(**rec.rules)

        if override_rules is None:
            return base

        merged = base.model_dump()

        o = override_rules.model_dump()
        # dict fields: merge
        for k in ("rename", "defaults", "cast", "flatten"):
            merged[k] = {**merged.get(k, {}), **o.get(k, {})}

        # list fields: replace if override provided non-empty, else keep base
        for k in ("pick", "omit"):
            if o.get(k):
                merged[k] = o[k]

        return TransformRules(**merged)


def default_ruleset_store() -> RulesetStore:
    # Local persistence path (safe, not for production)
    # You can disable persistence by setting API_ADJ_RULESET_PERSIST=0
    persist_flag = os.environ.get("API_ADJ_RULESET_PERSIST", "1").strip()
    persist_path = None
    if persist_flag not in ("0", "false", "False", "no", "NO"):
        persist_path = os.environ.get(
            "API_ADJ_RULESET_PATH",
            str(Path.home() / ".api_adjustmenter" / "rulesets.json"),
        )

    ttl = int(os.environ.get("API_ADJ_RULESET_TTL_SECONDS", str(7 * 24 * 3600)))
    return RulesetStore(ttl_seconds=ttl, persist_path=persist_path)
