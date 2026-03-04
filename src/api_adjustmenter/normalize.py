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
