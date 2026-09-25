"""Canon candidate fusion using injected Moirai embedding and reranking providers."""
from __future__ import annotations

import time
from collections import OrderedDict

from ..embedding.remote import RetrievalError
from .vector_index import VectorIndex, read_documents


SPEAKER_VIEW = False
QUERY_INSTRUCTION = ""
RERANK_BLEND = 0.0
ROUTE_SIMILARITY = 0.54
FUSION_K = 10
CHANNEL_WEIGHTS = {"dense": 1.0, "lexical": 0.3, "lines": 0.8, "entities": 0.1}


def fuse(channels: dict[str, dict[str, int]], *, k: int | None = None,
         weights: dict[str, float] | None = None) -> dict[str, float]:
    """Weighted reciprocal-rank fusion shared by the offline and model-backed canon paths."""
    k = FUSION_K if k is None else k
    weights = CHANNEL_WEIGHTS if weights is None else weights
    scores: dict[str, float] = {}
    for name, ranks in channels.items():
        weight = weights.get(name, 1.0)
        for event_id, rank in ranks.items():
            scores[event_id] = scores.get(event_id, 0.0) + weight / (k + rank)
    return scores


def speaker_view(query: str) -> str:
    """The Doctor asks Amiya; name both so embeddings and the reranker see who did what."""
    for pronoun, name in (("我们", "博士和阿米娅"), ("咱们", "博士和阿米娅"), ("你们", "阿米娅她们"),
                          ("我", "博士"), ("你", "阿米娅")):
        query = query.replace(pronoun, name)
    return query


class CanonRetrieval:
    def __init__(self, source, index: VectorIndex, providers, *, mode: str,
                 character: str = "amiya", candidate_limit: int = 40,
                 allow_fallback: bool = False) -> None:
        if mode not in {"hybrid", "hybrid-rerank"} or candidate_limit < 1:
            raise ValueError("Invalid canon retrieval mode or candidate limit")
        documents = read_documents(source, character)
        index.validate(documents)
        self.documents = {d.event_id: d.text for d in documents}
        self.index, self.providers = index, providers
        self.mode, self.candidate_limit = mode, min(candidate_limit, providers.max_candidates)
        self.allow_fallback = allow_fallback
        self._cache = OrderedDict()
        self._dense: OrderedDict[str, list[tuple[str, float]]] = OrderedDict()
        self.last_trace: dict = {}

    def dense(self, query: str) -> list[tuple[str, float]]:
        """Nearest events, cached so routing and ranking share one embedding request."""
        if query in self._dense:
            self._dense.move_to_end(query)
            return self._dense[query]
        found = self.index.search(self.providers.embed_query(QUERY_INSTRUCTION + query), self.candidate_limit)
        self._dense[query] = found
        if len(self._dense) > 128:
            self._dense.popitem(last=False)
        return found

    def confident(self, query: str) -> bool:
        """Whether the closest event is similar enough to treat a nameless question as a story question."""
        try:
            found = self.dense(query)
        except (RetrievalError, RuntimeError):
            return False
        return bool(found) and found[0][1] >= ROUTE_SIMILARITY

    def rank(self, query: str, lexical: dict[str, int], entities: dict[str, int],
             lines: dict[str, int] | None = None) -> dict[str, float]:
        lines = lines or {}
        key = (query, tuple(lexical.items()), tuple(entities.items()), tuple(lines.items()))
        if key in self._cache:
            self._cache.move_to_end(key)
            result, trace = self._cache[key]
            self.last_trace = {**trace, "cache_hit": True, "seconds": 0.0}
            return dict(result)
        started = time.perf_counter()
        trace = {"mode": self.mode, "cache_hit": False, "degraded": False,
                 "lexical": lexical, "entities": entities}
        dense = []
        try:
            dense = self.dense(query)
        except (RetrievalError, RuntimeError) as exc:
            if not self.allow_fallback:
                raise
            trace.update(degraded=True, embedding_error=str(exc))
        fused = fuse({"lexical": lexical, "entities": entities, "lines": lines,
                      "dense": {eid: i for i, (eid, _) in enumerate(dense, 1)}})
        scores = {eid: score for eid, score in fused.items() if eid in self.documents}
        pool = sorted(scores, key=lambda eid: (-scores[eid], eid))[:self.candidate_limit]
        trace.update(dense=dense, candidates=[{"event_id": eid, "rrf": scores[eid]} for eid in pool])
        if self.mode == "hybrid-rerank" and pool:
            try:
                reranked = self.providers.rerank(query, [self.documents[eid] for eid in pool])
                scores = {pool[i]: score for i, score in reranked}
                if RERANK_BLEND:
                    scores = fuse({"rerank": {pool[i]: r for r, (i, _) in enumerate(reranked, 1)},
                                   "pool": {eid: r for r, eid in enumerate(pool, 1)}},
                                  weights={"rerank": 1.0, "pool": RERANK_BLEND})
                trace["reranked"] = [{"event_id": pool[i], "score": score} for i, score in reranked]
            except (RetrievalError, RuntimeError) as exc:
                if not self.allow_fallback:
                    raise
                trace.update(degraded=True, rerank_error=str(exc))
                scores = {eid: scores[eid] for eid in pool}
        else:
            scores = {eid: scores[eid] for eid in pool}
        trace["seconds"] = time.perf_counter() - started
        self.last_trace = trace
        if not trace["degraded"]:
            self._cache[key] = (scores, trace)
            if len(self._cache) > 128:
                self._cache.popitem(last=False)
        return scores
