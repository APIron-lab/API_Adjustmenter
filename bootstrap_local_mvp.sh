#!/usr/bin/env bash
set -euo pipefail

echo "=== API Adjustmenter: bootstrap local MVP ==="

mkdir -p src/api_adjustmenter tests

cat > pyproject.toml << 'TOML'
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "api-adjustmenter"
version = "0.1.0"
description = "API Adjustmenter - Adjust messy JSON into a stable contract."
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
  "fastapi>=0.110.0",
  "uvicorn[standard]>=0.27.0",
  "pydantic>=2.6.0",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.0.0",
  "httpx>=0.26.0",
  "ruff>=0.3.0",
]

[tool.setuptools]
package-dir = {"" = "src"}

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
TOML

cat > src/api_adjustmenter/__init__.py << 'PY'
__all__ = ["__version__"]
__version__ = "0.1.0"
PY

cat > src/api_adjustmenter/errors.py << 'PY'
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    http_status: int = 400
PY

cat > src/api_adjustmenter/models.py << 'PY'
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


Json = Any


class ErrorPayload(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class OkResponse(BaseModel):
    ok: Literal[True] = True
    output: Json
    meta: Dict[str, Any] = Field(default_factory=dict)


class ErrResponse(BaseModel):
    ok: Literal[False] = False
    error: ErrorPayload


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


class TransformRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: Json
    rules: TransformRules


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


class DiffResponse(BaseModel):
    ok: Literal[True] = True
    breaking: bool
    diff: DiffResult
    meta: Dict[str, Any] = Field(default_factory=dict)
PY

cat > src/api_adjustmenter/util.py << 'PY'
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def is_dict(x: Any) -> bool:
    return isinstance(x, dict)


def is_list(x: Any) -> bool:
    return isinstance(x, list)


def deep_copy_json(x: Any) -> Any:
    if is_dict(x):
        return {k: deep_copy_json(v) for k, v in x.items()}
    if is_list(x):
        return [deep_copy_json(v) for v in x]
    return x


def snake_case(s: str) -> str:
    s = s.replace("-", "_").replace(" ", "_")
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    s = re.sub(r"__+", "_", s)
    return s.lower()


def camel_case(s: str) -> str:
    s = s.replace("-", "_").replace(" ", "_")
    parts = [p for p in s.split("_") if p]
    if not parts:
        return s
    return parts[0].lower() + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def convert_keys(obj: Any, style: str) -> Any:
    if style == "keep":
        return obj
    if is_dict(obj):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            nk = snake_case(k) if style == "snake" else camel_case(k)
            out[nk] = convert_keys(v, style)
        return out
    if is_list(obj):
        return [convert_keys(v, style) for v in obj]
    return obj


def try_parse_epoch_to_iso(v: Any) -> Tuple[bool, Any]:
    if isinstance(v, int):
        if 1_000_000_000 <= v <= 10_000_000_000:
            dt = datetime.fromtimestamp(v, tz=timezone.utc)
            return True, dt.isoformat().replace("+00:00", "Z")
    return False, v


def try_parse_date_string_to_iso(v: Any) -> Tuple[bool, Any]:
    if not isinstance(v, str):
        return False, v
    s = v.strip()
    if not s:
        return False, v
    if re.match(r"^\d{4}-\d{2}-\d{2}T", s):
        return False, v
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return True, f"{s}T00:00:00Z"
    m = re.match(r"^(\d{4})/(\d{2})/(\d{2})$", s)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        return True, f"{y}-{mo}-{d}T00:00:00Z"
    return False, v


def coerce_number(v: Any) -> Tuple[bool, Any]:
    if not isinstance(v, str):
        return False, v
    s = v.strip()
    if s == "":
        return False, v
    if re.match(r"^[+-]?\d+$", s):
        try:
            return True, int(s)
        except Exception:
            return False, v
    if re.match(r"^[+-]?\d+\.\d+$", s):
        try:
            return True, float(s)
        except Exception:
            return False, v
    return False, v


def empty_to_null(v: Any) -> Tuple[bool, Any]:
    if isinstance(v, str) and v == "":
        return True, None
    return False, v


def walk_and_adjust(
    obj: Any,
    *,
    coerce_numbers: bool,
    empty_to_null_flag: bool,
    date_to_iso: bool,
    change_counter: List[int],
) -> Any:
    if is_dict(obj):
        out: Dict[str, Any] = {}
        for k, v in obj.items():
            out[k] = walk_and_adjust(
                v,
                coerce_numbers=coerce_numbers,
                empty_to_null_flag=empty_to_null_flag,
                date_to_iso=date_to_iso,
                change_counter=change_counter,
            )
        return out

    if is_list(obj):
        return [
            walk_and_adjust(
                v,
                coerce_numbers=coerce_numbers,
                empty_to_null_flag=empty_to_null_flag,
                date_to_iso=date_to_iso,
                change_counter=change_counter,
            )
            for v in obj
        ]

    new_v = obj
    changed = False

    if empty_to_null_flag:
        c, new_v = empty_to_null(new_v)
        changed = changed or c

    if coerce_numbers:
        c, new_v = coerce_number(new_v)
        changed = changed or c

    if date_to_iso:
        c1, new_v2 = try_parse_epoch_to_iso(new_v)
        if c1:
            new_v = new_v2
            changed = True
        else:
            c2, new_v3 = try_parse_date_string_to_iso(new_v)
            if c2:
                new_v = new_v3
                changed = True

    if changed:
        change_counter[0] += 1

    return new_v


def get_json_type(x: Any) -> str:
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "bool"
    if isinstance(x, int):
        return "number"
    if isinstance(x, float):
        return "number"
    if isinstance(x, str):
        return "string"
    if is_list(x):
        return "array"
    if is_dict(x):
        return "object"
    return "unknown"


def flatten_paths(obj: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    t = get_json_type(obj)
    if prefix:
        out[prefix] = ("__node__", t)

    if is_dict(obj):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            out.update(flatten_paths(v, p))
        return out

    if is_list(obj):
        for i, v in enumerate(obj[:10]):
            p = f"{prefix}[{i}]" if prefix else f"[{i}]"
            out.update(flatten_paths(v, p))
        return out

    out[prefix or "$"] = obj
    return out


def get_path(obj: Any, path: str) -> Any:
    cur = obj
    if path == "" or path == "$":
        return cur

    tokens: List[str] = []
    buf = ""
    i = 0
    while i < len(path):
        ch = path[i]
        if ch == ".":
            if buf:
                tokens.append(buf)
                buf = ""
            i += 1
            continue
        if ch == "[":
            if buf:
                tokens.append(buf)
                buf = ""
            j = path.find("]", i)
            idx = path[i + 1 : j]
            tokens.append(f"[{idx}]")
            i = j + 1
            continue
        buf += ch
        i += 1
    if buf:
        tokens.append(buf)

    for tok in tokens:
        if tok.startswith("[") and tok.endswith("]"):
            if not is_list(cur):
                return None
            try:
                idx = int(tok[1:-1])
            except Exception:
                return None
            if idx < 0 or idx >= len(cur):
                return None
            cur = cur[idx]
        else:
            if not is_dict(cur):
                return None
            if tok not in cur:
                return None
            cur = cur[tok]
    return cur


def set_path(obj: Any, path: str, value: Any) -> Any:
    if path == "" or path == "$":
        return value
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        if not is_dict(cur):
            return obj
        if p not in cur or not is_dict(cur[p]):
            cur[p] = {}
        cur = cur[p]
    if is_dict(cur):
        cur[parts[-1]] = value
    return obj


def del_path(obj: Any, path: str) -> Any:
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        if not is_dict(cur) or p not in cur:
            return obj
        cur = cur[p]
    if is_dict(cur):
        cur.pop(parts[-1], None)
    return obj
PY

cat > src/api_adjustmenter/normalize.py << 'PY'
from __future__ import annotations

from typing import Any, Dict, Tuple

from .models import NormalizeOptions
from .util import convert_keys, deep_copy_json, walk_and_adjust


def normalize_payload(input_json: Any, options: NormalizeOptions) -> Tuple[Any, Dict[str, Any]]:
    obj = deep_copy_json(input_json)
    obj2 = convert_keys(obj, options.key_style)

    counter = [0]
    obj3 = walk_and_adjust(
        obj2,
        coerce_numbers=options.coerce_numbers,
        empty_to_null_flag=options.empty_to_null,
        date_to_iso=options.date_to_iso,
        change_counter=counter,
    )

    meta = {
        "key_style": options.key_style,
        "changes": counter[0],
        "options": options.model_dump(),
    }
    return obj3, meta
PY

cat > src/api_adjustmenter/transform.py << 'PY'
from __future__ import annotations

from typing import Any, Dict, Tuple

from .errors import AppError
from .models import TransformRules, CastType
from .util import deep_copy_json, get_path, set_path, del_path, is_dict


def _cast_value(value: Any, cast_type: CastType) -> Any:
    if cast_type == "json":
        return value
    if cast_type == "string":
        if value is None:
            return None
        return str(value)
    if cast_type == "int":
        if value is None or value == "":
            return None
        try:
            return int(value)
        except Exception as e:
            raise AppError(code="CAST_FAILED", message="Failed to cast to int", details={"value": value}) from e
    if cast_type == "float":
        if value is None or value == "":
            return None
        try:
            return float(value)
        except Exception as e:
            raise AppError(code="CAST_FAILED", message="Failed to cast to float", details={"value": value}) from e
    if cast_type == "bool":
        if isinstance(value, bool):
            return value
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "y", "on"):
                return True
            if s in ("false", "0", "no", "n", "off"):
                return False
        raise AppError(code="CAST_FAILED", message="Failed to cast to bool", details={"value": value})
    return value


def _rename_keys(obj: Any, rename_map: Dict[str, str]) -> Any:
    if not rename_map:
        return obj
    out = obj
    for src, dst in rename_map.items():
        val = get_path(out, src)
        if val is None:
            continue
        out = set_path(out, dst, val)
        out = del_path(out, src)
    return out


def _apply_defaults(obj: Any, defaults: Dict[str, Any]) -> Any:
    if not defaults:
        return obj
    out = obj
    for path, dv in defaults.items():
        cur = get_path(out, path)
        if cur is None:
            out = set_path(out, path, dv)
    return out


def _apply_cast(obj: Any, casts: Dict[str, CastType]) -> Any:
    if not casts:
        return obj
    out = obj
    for path, ctype in casts.items():
        val = get_path(out, path)
        if val is None:
            continue
        out = set_path(out, path, _cast_value(val, ctype))
    return out


def _flatten(obj: Any, flatten_rules: Dict[str, str]) -> Any:
    if not flatten_rules:
        return obj
    out = obj

    for path, prefix in flatten_rules.items():
        node = get_path(out, path)
        if node is None:
            continue
        if not is_dict(node):
            continue

        if "." in path:
            parent_path = ".".join(path.split(".")[:-1])
            key_name = path.split(".")[-1]
            parent = get_path(out, parent_path)
            if not is_dict(parent):
                continue
            for k, v in node.items():
                parent[f"{prefix}{k}"] = v
            parent.pop(key_name, None)
        else:
            if not is_dict(out):
                continue
            for k, v in node.items():
                out[f"{prefix}{k}"] = v
            out.pop(path, None)

    return out


def transform_payload(input_json: Any, rules: TransformRules) -> Tuple[Any, Dict[str, Any]]:
    obj = deep_copy_json(input_json)
    applied = []

    if rules.rename:
        obj = _rename_keys(obj, rules.rename)
        applied.append("rename")

    if rules.defaults:
        obj = _apply_defaults(obj, rules.defaults)
        applied.append("defaults")

    if rules.cast:
        obj = _apply_cast(obj, rules.cast)
        applied.append("cast")

    if rules.flatten:
        obj = _flatten(obj, rules.flatten)
        applied.append("flatten")

    meta = {"applied": applied}
    return obj, meta
PY

cat > src/api_adjustmenter/diff.py << 'PY'
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .models import DiffResult, TypeChange
from .util import flatten_paths, get_json_type


def diff_shapes(before: Any, after: Any) -> Tuple[bool, DiffResult, Dict[str, Any]]:
    b = flatten_paths(before)
    a = flatten_paths(after)

    b_keys = set(b.keys())
    a_keys = set(a.keys())

    removed = sorted(list(b_keys - a_keys))
    added = sorted(list(a_keys - b_keys))

    type_changes: List[TypeChange] = []
    common = b_keys & a_keys

    for path in sorted(common):
        bv = b[path]
        av = a[path]

        def _type_of(v: Any) -> str:
            if isinstance(v, tuple) and len(v) == 2 and v[0] == "__node__":
                return str(v[1])
            return get_json_type(v)

        bt = _type_of(bv)
        at = _type_of(av)
        if bt != at:
            type_changes.append(TypeChange(path=path, **{"from": bt, "to": at}))

    diff = DiffResult(
        removed_keys=removed,
        added_keys=added,
        type_changes=type_changes,
    )
    breaking = bool(removed) or bool(type_changes)

    meta = {
        "before_paths": len(b_keys),
        "after_paths": len(a_keys),
        "removed": len(removed),
        "added": len(added),
        "type_changes": len(type_changes),
    }
    return breaking, diff, meta
PY

cat > src/api_adjustmenter/main.py << 'PY'
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .errors import AppError
from .models import NormalizeRequest, TransformRequest, DiffRequest, OkResponse, ErrResponse, DiffResponse
from .normalize import normalize_payload
from .transform import transform_payload
from .diff import diff_shapes

app = FastAPI(
    title="API Adjustmenter",
    version="0.1.0",
    description="Adjust messy JSON into a stable contract. Local MVP.",
)

@app.get("/healthz")
def healthz():
    return {"ok": True, "service": "api-adjustmenter"}

@app.exception_handler(AppError)
def app_error_handler(request: Request, exc: AppError):
    payload = ErrResponse(error={"code": exc.code, "message": exc.message, "details": exc.details})
    return JSONResponse(status_code=exc.http_status, content=payload.model_dump())

@app.exception_handler(Exception)
def unhandled_error_handler(request: Request, exc: Exception):
    payload = ErrResponse(error={"code": "INTERNAL_ERROR", "message": "Unhandled server error", "details": {"type": exc.__class__.__name__}})
    return JSONResponse(status_code=500, content=payload.model_dump())

@app.post("/normalize", response_model=OkResponse)
def normalize(req: NormalizeRequest):
    output, meta = normalize_payload(req.input, req.options)
    return OkResponse(output=output, meta=meta)

@app.post("/transform", response_model=OkResponse)
def transform(req: TransformRequest):
    output, meta = transform_payload(req.input, req.rules)
    return OkResponse(output=output, meta=meta)

@app.post("/diff", response_model=DiffResponse)
def diff(req: DiffRequest):
    breaking, diff_result, meta = diff_shapes(req.before, req.after)
    return DiffResponse(breaking=breaking, diff=diff_result, meta=meta)
PY

cat > tests/test_api.py << 'PY'
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
PY

echo "=== bootstrap done ==="
