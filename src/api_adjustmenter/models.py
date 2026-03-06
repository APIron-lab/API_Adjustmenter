from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


Json = Any


class Meta(BaseModel):
    execution_ms: int
    input_length: int
    request_id: str


class SuccessResponse(BaseModel):
    result: Json
    meta: Meta


class ErrorBody(BaseModel):
    code: str
    message: str
    hint: Optional[str] = None


class ErrorResponse(BaseModel):
    error: ErrorBody
    meta: Meta


KeyStyle = Literal["keep", "snake", "camel"]


class NormalizeOptions(BaseModel):
    key_style: KeyStyle = "keep"
    coerce_numbers: bool = False
    empty_to_null: bool = False
    date_to_iso: bool = False


class NormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: Json
    options: NormalizeOptions = Field(default_factory=NormalizeOptions)


CastType = Literal["string", "int", "float", "bool", "json"]


class TransformRules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rename: Dict[str, str] = Field(default_factory=dict)
    defaults: Dict[str, Any] = Field(default_factory=dict)
    cast: Dict[str, CastType] = Field(default_factory=dict)
    flatten: Dict[str, str] = Field(default_factory=dict)

    pick: List[str] = Field(default_factory=list)
    omit: List[str] = Field(default_factory=list)


class TransformRequest(BaseModel):
    """
    Either:
      - rules: TransformRules
      - ruleset_id: str (+ optional override_rules)
    """
    model_config = ConfigDict(extra="forbid")
    input: Json
    rules: Optional[TransformRules] = None
    ruleset_id: Optional[str] = None
    override_rules: Optional[TransformRules] = None


class DiffRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: Json
    after: Json


class TypeChange(BaseModel):
    path: str
    from_type: str = Field(alias="from")
    to_type: str = Field(alias="to")


class DiffResult(BaseModel):
    removed_keys: List[str] = Field(default_factory=list)
    added_keys: List[str] = Field(default_factory=list)
    type_changes: List[TypeChange] = Field(default_factory=list)


class DiffPayload(BaseModel):
    breaking: bool
    diff: DiffResult


# ---- Ruleset APIs ----

class RulesetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    rules: TransformRules
    ttl_seconds: Optional[int] = Field(default=None, description="TTL in seconds. null=default. 0 or negative=never expire.")


class RulesetSummary(BaseModel):
    ruleset_id: str
    name: str
    updated_at: int
    expires_at: Optional[int] = None


class RulesetGetResponse(BaseModel):
    ruleset_id: str
    name: str
    rules: TransformRules
    created_at: int
    updated_at: int
    expires_at: Optional[int] = None
