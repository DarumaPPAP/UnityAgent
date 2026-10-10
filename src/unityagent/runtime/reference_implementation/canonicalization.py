"""RFC 8785 style canonical JSON helpers for the reference contracts.

The existing persistence store intentionally keeps its historical JSON hash
format.  Reference contracts use this separate utility so changing an old
format cannot silently invalidate existing state or evidence.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any


class CanonicalizationError(ValueError):
    """Raised when a value cannot be represented by canonical JSON."""


_EXPONENT_RE = re.compile(r"^(?P<mantissa>-?(?:\d+)(?:\.\d+)?)[eE](?P<sign>[+-]?)(?P<exponent>\d+)$")


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _number(value: int | float) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if not math.isfinite(value):
        raise CanonicalizationError("NaN and Infinity are not valid canonical JSON numbers")
    if value == 0.0:
        return "0"

    # RFC 8785 adopts ECMAScript's Number::toString representation.  Python's
    # repr() is also shortest-round-trip, so we only have to normalize the
    # notation thresholds and exponent spelling.  Do not use a fixed decimal
    # precision here: doing so changes the digest of values such as
    # 1.234567890123456e-05.
    absolute = abs(value)
    if value.is_integer() and absolute < 1e21:
        return str(int(value))
    raw = repr(value).lower()
    if "e" not in raw:
        return raw

    match = _EXPONENT_RE.match(raw)
    if not match:
        return raw
    exponent = int(match.group("exponent"))
    sign = "-" if match.group("sign") == "-" else "+" if match.group("sign") == "+" else ""
    signed_exponent = -exponent if sign == "-" else exponent
    mantissa = match.group("mantissa")
    # ECMAScript uses fixed notation for 1e-6 <= |n| < 1e21.
    if 1e-6 <= absolute < 1e21:
        negative = mantissa.startswith("-")
        digits = mantissa.lstrip("-").replace(".", "")
        decimal_index = (mantissa.lstrip("-").find(".") if "." in mantissa else len(mantissa.lstrip("-"))) + signed_exponent
        if decimal_index <= 0:
            fixed = "0." + ("0" * (-decimal_index)) + digits
        elif decimal_index >= len(digits):
            fixed = digits + ("0" * (decimal_index - len(digits)))
        else:
            fixed = digits[:decimal_index] + "." + digits[decimal_index:]
        fixed = fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
        if fixed in {"", "0"}:
            return "0"
        return ("-" if negative else "") + fixed
    mantissa = mantissa.rstrip("0").rstrip(".") if "." in mantissa else mantissa
    return f"{mantissa}e{sign}{exponent}"


def _canonical(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _number(value)
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_canonical(item) for item in value) + "]"
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise CanonicalizationError("canonical JSON object keys must be strings")
        ordered = sorted(value.items(), key=lambda item: item[0].encode("utf-16-be"))
        return "{" + ",".join(_string(key) + ":" + _canonical(item) for key, item in ordered) + "}"
    raise CanonicalizationError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonicalize(value: Any) -> str:
    """Return a deterministic UTF-8 JSON representation without whitespace."""

    return _canonical(value)


def canonical_bytes(value: Any) -> bytes:
    return canonicalize(value).encode("utf-8")


def sha256_jcs(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest_for(value: dict[str, Any], field: str) -> str:
    """Hash a contract after removing its self-referential digest field."""

    payload = {key: item for key, item in value.items() if key != field}
    return sha256_jcs(payload)
