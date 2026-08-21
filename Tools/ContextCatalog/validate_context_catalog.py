#!/usr/bin/env python3
"""Validate that the committed Context Metadata Index is current."""

from __future__ import annotations

import sys
from pathlib import Path

from build_context_catalog import INDEX_PATH, build_index, serialize


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    path = root / INDEX_PATH
    if not path.is_file():
        print(f"Missing Context Metadata Index: {INDEX_PATH}")
        return 1
    if path.read_text(encoding="utf-8") != serialize(build_index(root)):
        print("Context Metadata Index is stale.")
        return 1
    print("Context Metadata Index validation passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
