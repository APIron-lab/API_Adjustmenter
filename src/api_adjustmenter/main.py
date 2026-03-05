from __future__ import annotations

import time
import uuid
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .errors import AppError
from .models import (
    NormalizeRequest,
    TransformRequest,
    DiffRequest,
    SuccessResponse,
    ErrorResponse,
    Meta,
    DiffPayload,
    RulesetCreateRequest,
    RulesetGetResponse,
    RulesetSummary,
    TransformRules,
)
from .normalize import normalize_payload
from .transform import transform_payload
from .diff import diff_shapes
from .rulesets import default_ruleset_store


app = FastAPI(
    title="API Adjustmenter",
    version="0.3.0",
    description="Adjust messy JSON into a stable contract. Includes ruleset presets (ruleset_id).",
)

RULESETS = default_ruleset_store()


def _make_meta(*, start_ns: int, input_length: int, request_id: str) -> Meta:
    execution_ms = int((time.perf_counter_ns() - start_ns) / 1_000_000)
    return Meta(execution_ms=execution_ms, input_length=input_length, request_id=request_id)


async def _read_body_len(request: Request) -> int:
    b = await request.body()
    return len(b)


def _success(result: Any, meta: Meta) -> JSONResponse:
    payload = SuccessResponse(result=result, meta=meta)
    return JSONResponse(status_code=200, content=payload.model_dump())


def _error(code: str, message: str, hint: Optional[str], meta: Meta, http_status: int) -> JSONResponse:
    payload = ErrorResponse(error={"code": code, "message": message, "hint": hint}, meta=meta)
    return JSONResponse(status_code=http_status, content=payload.model_dump())


@app.get("/healthz")
def healthz():
    start_ns = time.perf_counter_ns()
    request_id = str(uuid.uuid4())
    meta = _make_meta(start_ns=start_ns, input_length=0, request_id=request_id)
    return SuccessResponse(result={"service": "api-adjustmenter"}, meta=meta)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    start_ns = request.state.start_ns if hasattr(request.state, "start_ns") else time.perf_counter_ns()
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    input_length = request.state.input_length if hasattr(request.state, "input_length") else await _read_body_len(request)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)
    # hint は英語（APIron標準）
    return _error(exc.code, exc.message, "Check request fields/types and try again.", meta, exc.http_status)


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    start_ns = request.state.start_ns if hasattr(request.state, "start_ns") else time.perf_counter_ns()
    request_id = request.state.request_id if hasattr(request.state, "request_id") else str(uuid.uuid4())
    input_length = request.state.input_length if hasattr(request.state, "input_length") else await _read_body_len(request)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)
    return _error("INTERNAL_ERROR", "サーバ内部で予期しないエラーが発生しました。", "Retry later or contact support.", meta, 500)


@app.middleware("http")
async def add_request_context(request: Request, call_next):
    request.state.start_ns = time.perf_counter_ns()
    request.state.request_id = str(uuid.uuid4())
    request.state.input_length = await _read_body_len(request)
    return await call_next(request)


@app.post("/normalize")
async def normalize(request: Request, req: NormalizeRequest):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    output, extra_meta = normalize_payload(req.input, req.options)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)
    result = {"output": output, "adjustment": extra_meta}
    return _success(result, meta)


@app.post("/transform")
async def transform(request: Request, req: TransformRequest):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    # Resolve rules
    rules: Optional[TransformRules] = None

    if req.ruleset_id:
        rules = RULESETS.resolve_rules(ruleset_id=req.ruleset_id, override_rules=req.override_rules)
    elif req.rules:
        rules = req.rules
    else:
        raise AppError(
            code="MISSING_FIELD",
            message="rules または ruleset_id のいずれかが必要です。",
            details={"required_one_of": ["rules", "ruleset_id"]},
            http_status=400,
        )

    output, extra_meta = transform_payload(req.input, rules)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)
    result = {"output": output, "adjustment": extra_meta}
    return _success(result, meta)


@app.post("/diff")
async def diff(request: Request, req: DiffRequest):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    breaking, diff_result, extra_meta = diff_shapes(req.before, req.after)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)

    payload = DiffPayload(breaking=breaking, diff=diff_result)
    result = {"diff": payload.model_dump(by_alias=True), "adjustment": extra_meta}
    return _success(result, meta)


# ---- Ruleset endpoints ----

@app.post("/rulesets")
async def create_ruleset(request: Request, req: RulesetCreateRequest):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    rec = RULESETS.create(name=req.name, rules=req.rules, ttl_seconds=req.ttl_seconds)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)
    result = {"ruleset_id": rec.ruleset_id, "name": rec.name, "expires_at": rec.expires_at}
    return _success(result, meta)


@app.get("/rulesets/{ruleset_id}")
async def get_ruleset(request: Request, ruleset_id: str):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    rec = RULESETS.get(ruleset_id)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)

    result = RulesetGetResponse(
        ruleset_id=rec.ruleset_id,
        name=rec.name,
        rules=TransformRules(**rec.rules),
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        expires_at=rec.expires_at,
    ).model_dump()
    return _success(result, meta)


@app.get("/rulesets")
async def list_rulesets(request: Request, limit: int = 50):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    items = RULESETS.list(limit=limit)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)

    result = {
        "items": [
            RulesetSummary(
                ruleset_id=r.ruleset_id,
                name=r.name,
                updated_at=r.updated_at,
                expires_at=r.expires_at,
            ).model_dump()
            for r in items
        ]
    }
    return _success(result, meta)


@app.delete("/rulesets/{ruleset_id}")
async def delete_ruleset(request: Request, ruleset_id: str):
    start_ns = request.state.start_ns
    request_id = request.state.request_id
    input_length = request.state.input_length

    RULESETS.delete(ruleset_id)
    meta = _make_meta(start_ns=start_ns, input_length=input_length, request_id=request_id)
    return _success({"deleted": True, "ruleset_id": ruleset_id}, meta)
