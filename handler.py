from __future__ import annotations

import os
import sys

# Ensure src/ is importable on AWS Lambda
HERE = os.path.dirname(__file__)
SRC = os.path.join(HERE, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from mangum import Mangum
from api_adjustmenter.main import app

handler = Mangum(app)
