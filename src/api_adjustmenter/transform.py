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
