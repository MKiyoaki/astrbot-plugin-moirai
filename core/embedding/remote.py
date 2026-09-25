"""Validated HTTP transport shared by Moirai embedding and reranking providers."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx


class RetrievalError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True)
class RemoteSettings:
    base_url: str
    api_key: str = field(repr=False)
    embedding_model: str = "arc:embedvl"
    rerank_model: str = "arc:rerankvl"
    rerank_path: str = "/rerank"
    query_instruction: str = ""
    timeout: float = 60.0
    retries: int = 1

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if (parsed.scheme not in {"http", "https"} or not parsed.netloc
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Retrieval base URL must be an HTTP(S) endpoint without credentials")
        if not self.rerank_path.startswith("/") or "?" in self.rerank_path:
            raise ValueError("Rerank path must be an absolute API path suffix")
        if not self.embedding_model or not self.rerank_model or not self.api_key:
            raise ValueError("KCL retrieval models and API key must be configured")
        if not math.isfinite(self.timeout) or self.timeout <= 0 or not 0 <= self.retries <= 3:
            raise ValueError("Retrieval timeout must be positive; retries must be between 0 and 3")

    @property
    def identity(self) -> dict:
        return {"endpoint": self.base_url.rstrip("/"), "model": self.embedding_model,
                "query_instruction": self.query_instruction}


def normalized_vector(value, dimension: int | None = None) -> list[float]:
    if not isinstance(value, list) or not value or (dimension and len(value) != dimension):
        raise RetrievalError("Embedding vector has an invalid dimension")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) for v in value):
        raise RetrievalError("Embedding vector must contain numbers")
    try:
        vector = [float(v) for v in value]
        norm = math.hypot(*vector)
    except (OverflowError, ValueError):
        raise RetrievalError("Embedding vector contains invalid numbers") from None
    if not math.isfinite(norm) or norm == 0:
        raise RetrievalError("Embedding vector must be finite and nonzero")
    return [v / norm for v in vector]


class RemoteRetrievalClient:
    def __init__(self, settings: RemoteSettings, *, transport=None, sleep=time.sleep) -> None:
        self.settings = settings
        self._http = httpx.Client(
            timeout=httpx.Timeout(settings.timeout, connect=min(10, settings.timeout)),
            transport=transport, follow_redirects=False,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
        self._sleep = sleep
        self._lock = threading.Lock()
        self._metrics = {"embedding_requests": 0, "rerank_requests": 0,
                         "retries": 0, "request_seconds": 0.0}

    def close(self) -> None:
        self._http.close()

    def metrics(self) -> dict:
        with self._lock:
            return dict(self._metrics)

    def _post(self, path: str, payload: dict, kind: str) -> dict:
        for attempt in range(self.settings.retries + 1):
            started = time.perf_counter()
            delay = min(2 ** attempt, 5)
            retryable = False
            reason = "transport failure"
            with self._lock:
                self._metrics[f"{kind}_requests"] += 1
                self._metrics["retries"] += bool(attempt)
            try:
                response = self._http.post(self.settings.base_url.rstrip("/") + path, json=payload)
                if response.is_success:
                    try:
                        body = response.json()
                    except ValueError:
                        raise RetrievalError(f"{kind}: invalid JSON response") from None
                    if not isinstance(body, dict):
                        raise RetrievalError(f"{kind}: response must be an object")
                    return body
                reason = f"HTTP {response.status_code}"
                retryable = response.status_code == 429 or response.status_code >= 500
                try:
                    delay = min(max(float(response.headers.get("retry-after", delay)), 0), 5)
                except ValueError:
                    pass
            except httpx.HTTPError:
                retryable = True
            finally:
                with self._lock:
                    self._metrics["request_seconds"] += time.perf_counter() - started
            if not retryable or attempt == self.settings.retries:
                raise RetrievalError(f"{kind}: {reason}", retryable=retryable) from None
            self._sleep(delay)
        raise RetrievalError(f"{kind}: request failed")

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        body = self._post("/embeddings", {"model": self.settings.embedding_model,
                                         "input": texts}, "embedding")
        rows = body.get("data")
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise RetrievalError("embedding: response count does not match inputs")
        if any(not isinstance(row, dict) for row in rows):
            raise RetrievalError("embedding: malformed response row")
        positional = all("index" not in row for row in rows)
        ordered = {}
        dimension = None
        for position, row in enumerate(rows):
            idx = position if positional else row.get("index")
            if type(idx) is not int or not 0 <= idx < len(texts) or idx in ordered:
                raise RetrievalError("embedding: invalid or duplicate response index")
            vector = normalized_vector(row.get("embedding"), dimension)
            dimension = len(vector)
            ordered[idx] = vector
        return [ordered[i] for i in range(len(texts))]

    def embed_query(self, query: str) -> list[float]:
        instruction = self.settings.query_instruction
        text = f"Instruct: {instruction}\nQuery: {query}" if instruction else query
        return self.embed([text])[0]

    def rerank(self, query: str, documents: list[str]) -> list[tuple[int, float]]:
        if not documents:
            return []
        body = self._post(self.settings.rerank_path,
                          {"model": self.settings.rerank_model, "query": query,
                           "documents": documents, "top_n": len(documents)}, "rerank")
        rows = body.get("results", body.get("data"))
        if not isinstance(rows, list) or len(rows) != len(documents):
            raise RetrievalError("rerank: response count does not match candidates")
        scores = {}
        for row in rows:
            if not isinstance(row, dict):
                raise RetrievalError("rerank: malformed response row")
            idx, score = row.get("index"), row.get("relevance_score", row.get("score"))
            if type(idx) is not int or not 0 <= idx < len(documents) or idx in scores:
                raise RetrievalError("rerank: invalid or duplicate candidate index")
            if (isinstance(score, bool) or not isinstance(score, (int, float))
                    or not math.isfinite(score)):
                raise RetrievalError("rerank: score must be finite")
            scores[idx] = float(score)
        return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
