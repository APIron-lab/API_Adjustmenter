from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None
    http_status: int = 400
