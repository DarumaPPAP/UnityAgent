#!/usr/bin/env python3
"""Repository-local wrapper for the canonical retrieval evaluator."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from Eval.Retrieval.run_retrieval_eval import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
