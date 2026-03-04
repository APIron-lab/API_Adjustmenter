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
