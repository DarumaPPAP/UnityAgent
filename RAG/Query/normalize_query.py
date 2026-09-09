"""Deterministic query normalization for technical and Japanese queries."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import unicodedata
from typing import Iterable


# API / shader identifiers are kept as one token. A second set of split tokens is
# emitted so ``RenderGraph`` and ``render_graph`` can still share useful overlap.
TOKEN_RE = re.compile(
    r"[A-Za-z0-9]+(?:[_./:+-][A-Za-z0-9]+)*|[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]+",
    re.UNICODE,
)
SEPARATOR_RE = re.compile(r"[_./:+-]+")
TECHNICAL_RE = re.compile(r"(?:[_./:+-]|\d|[A-Z]{2,}|[A-Z][a-z]+[A-Z])")


def _tokens(value: str) -> list[str]:
    result: list[str] = []
    for match in TOKEN_RE.finditer(value):
        token = match.group(0).casefold()
        if token and token not in result:
            result.append(token)
        for piece in SEPARATOR_RE.split(token):
            if len(piece) >= 2 and piece not in result:
                result.append(piece)
    return result


def _technical_tokens(raw: str, normalized_tokens: Iterable[str]) -> list[str]:
    result: list[str] = []
    for match in TOKEN_RE.finditer(raw):
        token = match.group(0)
        normalized_token = token.casefold()
        if TECHNICAL_RE.search(token) and normalized_token not in result:
            result.append(normalized_token)
    # Keep identifier-shaped fragments from the original query even after NFKC /
    # casefold, which makes exact-token diagnostics useful for symbols such as
    # ``URP_COMPATIBILITY_MODE``.
    for match in TOKEN_RE.finditer(raw):
        token = match.group(0).casefold()
        if ("_" in token or "." in token or "/" in token or ":" in token or any(ch.isdigit() for ch in token)) and token not in result:
            result.append(token)
    return result


@dataclass(frozen=True)
class NormalizedQuery:
    raw: str
    normalized: str
    tokens: tuple[str, ...]
    technical_tokens: tuple[str, ...]
    query_hash: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "raw": self.raw,
            "normalized": self.normalized,
            "tokens": list(self.tokens),
            "technical_tokens": list(self.technical_tokens),
            "query_hash": self.query_hash,
        }


def normalize_query(raw: str) -> NormalizedQuery:
    """Normalize only syntax; do not infer Unity/project metadata."""

    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("query must not be empty")
    normalized_raw = unicodedata.normalize("NFKC", raw).strip()
    tokens = _tokens(normalized_raw)
    if not tokens:
        raise ValueError("query must contain at least one searchable token")
    normalized = " ".join(tokens)
    technical = _technical_tokens(normalized_raw, tokens)
    query_hash = "sha256:" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return NormalizedQuery(
        raw=raw,
        normalized=normalized,
        tokens=tuple(tokens),
        technical_tokens=tuple(technical),
        query_hash=query_hash,
    )
