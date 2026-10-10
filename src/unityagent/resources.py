"""Read the canonical resource layout bundled at build time.

This root is package-owned and independent of the caller's cwd and checkout.
Repository tools/tests pass their repository root explicitly when auditing sources.
"""
from pathlib import Path


def resource_root() -> Path:
    return Path(__file__).resolve().parent / '_resources'
