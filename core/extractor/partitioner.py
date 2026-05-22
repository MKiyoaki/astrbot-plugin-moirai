from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow
    from ..embedding.encoder import Encoder

logger = logging.getLogger(__name__)


def _has_embedding(vec: object) -> bool:
    try:
        return len(vec) > 0  # type: ignore[arg-type]
    except Exception:
        return False


def _to_embedding_list(vec: object) -> list[float]:
    if hasattr(vec, "tolist"):
        vec = vec.tolist()
    return [float(v) for v in vec]  # type: ignore[union-attr]

class Partition:
    """A logical cluster of messages identified as a potential event."""
    def __init__(self, indices: List[int], metadata: Dict[str, Any] = None):
        self.indices = indices
        self.metadata = metadata or {}

class BasePartitioner(ABC):
    @abstractmethod
    async def partition(self, window: MessageWindow) -> List[Partition]:
        """Split a MessageWindow into one or more Partitions."""
        pass

class LlmPartitioner(BasePartitioner):
    """Placeholder for the 'Pure LLM' approach where the LLM does the splitting.
    
    In this strategy, the partitioner actually returns a single 'catch-all' 
    partition, and the Extractor will let the LLM handle the splitting 
    internally via the JSON Array output.
    """
    async def partition(self, window: MessageWindow) -> List[Partition]:
        return [Partition(indices=list(range(len(window.messages))))]

try:
    import numpy as np
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_distances
    _SKLEARN_AVAILABLE = True
except ImportError:
    _SKLEARN_AVAILABLE = False


class SemanticPartitioner(BasePartitioner):
    """Encoder-driven partitioning using semantic clustering (DBSCAN)."""
    
    def __init__(
        self, 
        encoder: Encoder, 
        eps: float = 0.45, 
        min_samples: int = 2,
        time_penalty_factor: float = 0.05
    ):
        self._encoder = encoder
        self._eps = eps
        self._min_samples = min_samples
        self._time_penalty = time_penalty_factor

    async def partition(self, window: MessageWindow) -> List[Partition]:
        if not window.messages:
            return []
            
        if not _SKLEARN_AVAILABLE:
            logger.warning("[SemanticPartitioner] scikit-learn is not installed. Falling back to single partition. "
                           "Run `pip install scikit-learn` to enable semantic clustering.")
            return [Partition(indices=list(range(len(window.messages))))]
        
        if self._encoder.dim == 0:
            return [Partition(indices=list(range(len(window.messages))))]

        from ..utils.perf import performance_timer

        # 1. Extract embeddings. Prefer vectors already attached by MessageRouter's
        # background brain task; only encode missing messages.
        embeddings: list[list[float] | None] = [
            getattr(m, "embedding", None) for m in window.messages
        ]
        missing = [idx for idx, vec in enumerate(embeddings) if not _has_embedding(vec)]
        if missing:
            async with performance_timer("partition_encode"):
                encoded = await self._encoder.encode_batch(
                    [window.messages[idx].text for idx in missing]
                )
            for idx, vec in zip(missing, encoded):
                if _has_embedding(vec):
                    embedding = _to_embedding_list(vec)
                    window.attach_embedding(idx, embedding)
                    embeddings[idx] = embedding

        if any(not _has_embedding(vec) for vec in embeddings):
            logger.warning(
                "[SemanticPartitioner] missing embeddings after encode; falling back to single partition"
            )
            return [Partition(indices=list(range(len(window.messages))))]

        # 2. Compute semantic distances
        async with performance_timer("partition_distance"):
            dists = cosine_distances(embeddings)
        
        # 3. Apply time penalty
        times = np.array([m.timestamp for m in window.messages])
        if len(times) > 1:
            time_range = times.max() - times.min()
            if time_range > 0:
                gap_matrix = np.abs(times[:, None] - times[None, :]) / time_range
                dists += gap_matrix * self._time_penalty

        # 4. Perform clustering
        async with performance_timer("partition_cluster"):
            clustering = DBSCAN(eps=self._eps, min_samples=self._min_samples, metric="precomputed").fit(dists)
            labels = clustering.labels_
        
        clusters: Dict[int, List[int]] = {}
        noise_indices: List[int] = []
        
        for idx, label in enumerate(labels):
            if label == -1:
                noise_indices.append(idx)
            else:
                if label not in clusters:
                    clusters[label] = []
                clusters[label].append(idx)
            
        results = []
        # Normal clusters
        for indices in clusters.values():
            results.append(Partition(indices=indices))
            
        # Group all noise into one 'catch-all' partition if it's not too large, 
        # or just ignore it to keep memory clean.
        # For reliability, let's keep noise messages but group them to avoid 20+ events.
        if noise_indices:
            results.append(Partition(indices=noise_indices, metadata={"is_noise": True}))
                
        return results if results else [Partition(indices=list(range(len(window.messages))))]
