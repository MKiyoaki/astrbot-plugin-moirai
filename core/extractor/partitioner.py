from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Dict, Any

if TYPE_CHECKING:
    from ..boundary.window import MessageWindow
    from ..embedding.encoder import Encoder

logger = logging.getLogger(__name__)

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

class SemanticPartitioner(BasePartitioner):
    """Encoder-driven partitioning using semantic clustering (DBSCAN)."""
    
    def __init__(
        self, 
        encoder: Encoder, 
        eps: float = 0.35, 
        min_samples: int = 1,
        time_penalty_factor: float = 0.05
    ):
        self._encoder = encoder
        self._eps = eps
        self._min_samples = min_samples
        self._time_penalty = time_penalty_factor

    async def partition(self, window: MessageWindow) -> List[Partition]:
        if not window.messages:
            return []
        
        if self._encoder.dim == 0:
            logger.warning("[SemanticPartitioner] encoder inactive, falling back to single partition")
            return [Partition(indices=list(range(len(window.messages))))]

        # 1. Encode all messages in the window
        texts = [f"{m.display_name or m.uid}: {m.text}" for m in window.messages]
        embeddings = await self._encoder.encode_batch(texts)
        
        import numpy as np
        from sklearn.cluster import DBSCAN
        from sklearn.metrics.pairwise import cosine_distances

        # 2. Compute semantic distances
        # dists[i, j] = 1 - cos_sim(i, j)
        dists = cosine_distances(embeddings)
        
        # 3. (Optional) Apply time penalty to distances to prefer temporal contiguity
        # For each pair (i, j), increase distance based on time gap
        times = np.array([m.timestamp for m in window.messages])
        # Normalise time gaps to roughly [0, 1] within the window
        if len(times) > 1:
            time_range = times.max() - times.min()
            if time_range > 0:
                for i in range(len(times)):
                    for j in range(len(times)):
                        gap_ratio = abs(times[i] - times[j]) / time_range
                        dists[i, j] += gap_ratio * self._time_penalty

        # 4. Perform clustering
        # We use precomputed metric because we added time penalty
        clustering = DBSCAN(eps=self._eps, min_samples=self._min_samples, metric="precomputed").fit(dists)
        labels = clustering.labels_
        
        clusters: Dict[int, List[int]] = {}
        for idx, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(idx)
            
        results = []
        # -1 in DBSCAN means noise. We treat noise messages as individual partitions 
        # OR we could discard them. For now, let's group noise by sequential proximity 
        # or just treat them as individual events if they are meaningful.
        # Actually, let's just keep them for the LLM to decide.
        
        for label, indices in clusters.items():
            if label == -1:
                # Individual noise items -> separate partitions
                for i in indices:
                    results.append(Partition(indices=[i], metadata={"is_noise": True}))
            else:
                results.append(Partition(indices=indices))
                
        return results
