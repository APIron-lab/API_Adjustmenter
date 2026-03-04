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
