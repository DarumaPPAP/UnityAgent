"""Small stdlib-only Qdrant REST transport.

Keeping the transport injectable makes the adapter testable without a running
Qdrant service and avoids making ``qdrant-client`` a UnityAgent dependency.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from RAG.Adapters.qdrant.config import QdrantConfig


class QdrantError(RuntimeError):
    """Base error for unavailable or invalid Qdrant responses."""

    code = "qdrant_error"


class QdrantTimeoutError(QdrantError):
    code = "qdrant_timeout"


class QdrantHttpError(QdrantError):
    code = "qdrant_http_error"

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class QdrantTransport(Protocol):
    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]: ...


class UrllibQdrantTransport:
    """Authenticated JSON transport using only Python's standard library."""

    def __init__(self, config: QdrantConfig) -> None:
        self.config = config
        self.base_url = config.url.rstrip("/") + "/"

    def request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        timeout_seconds: float = 10.0,
    ) -> dict[str, Any]:
        if not str(path).startswith("/"):
            raise QdrantHttpError("Qdrant REST path must start with '/'")
        body = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {"Accept": "application/json"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if self.config.api_key:
            headers["api-key"] = self.config.api_key
        request = Request(urljoin(self.base_url, path.lstrip("/")), data=body, headers=headers, method=str(method).upper())
        try:
            with urlopen(request, timeout=float(timeout_seconds)) as response:
                raw = response.read()
        except HTTPError as exc:
            # Do not include response bodies: a server may echo sensitive payloads.
            if exc.status == 404:
                raise QdrantHttpError("Qdrant resource was not found", status=exc.status) from exc
            raise QdrantHttpError(f"Qdrant returned HTTP {exc.status}", status=exc.status) from exc
        except TimeoutError as exc:
            raise QdrantTimeoutError("Qdrant request timed out") from exc
        except URLError as exc:
            raise QdrantError("Qdrant request was unavailable") from exc
        except OSError as exc:
            raise QdrantError("Qdrant request failed") from exc
        try:
            value = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise QdrantError("Qdrant returned a non-JSON response") from exc
        if not isinstance(value, dict):
            raise QdrantError("Qdrant response must be a JSON object")
        return value


__all__ = [
    "QdrantError",
    "QdrantHttpError",
    "QdrantTimeoutError",
    "QdrantTransport",
    "UrllibQdrantTransport",
]
