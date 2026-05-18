import pytest
import asyncio
from core.extractor.partitioner import LlmPartitioner, SemanticPartitioner, Partition
from core.boundary.window import MessageWindow, RawMessage
from core.embedding.encoder import Encoder

class MockEncoder:
    def __init__(self, dim=4):
        self.dim = dim
    async def encode_batch(self, texts):
        # Return dummy embeddings
        import numpy as np
        return np.random.rand(len(texts), self.dim)

@pytest.mark.asyncio
async def test_llm_partitioner_returns_single_partition():
    p = LlmPartitioner()
    w = MessageWindow("s", "g")
    w.add_message("u1", "hi", 100.0)
    w.add_message("u2", "hello", 101.0)
    
    parts = await p.partition(w)
    assert len(parts) == 1
    assert parts[0].indices == [0, 1]

@pytest.mark.asyncio
async def test_semantic_partitioner_clustering():
    # We use high EPS to keep them together or low to split
    # Since we use random embeddings, behavior is unpredictable without fixed data
    # Let's mock the embeddings more carefully
    class FixedEncoder:
        def __init__(self): self.dim = 2
        async def encode_batch(self, texts):
            import numpy as np
            # Topic A: [1, 0], Topic B: [0, 1]
            vecs = []
            for t in texts:
                if "TopicA" in t: vecs.append([1.0, 0.0])
                else: vecs.append([0.0, 1.0])
            return np.array(vecs)

    p = SemanticPartitioner(FixedEncoder(), eps=0.1)
    w = MessageWindow("s", "g")
    w.add_message("u1", "TopicA msg 1", 100.0)
    w.add_message("u1", "TopicA msg 2", 101.0)
    w.add_message("u2", "TopicB msg 1", 102.0)
    
    parts = await p.partition(w)
    # Should result in 2 clusters
    assert len(parts) == 2
    # Sort to be safe
    parts.sort(key=lambda x: x.indices[0])
    assert parts[0].indices == [0, 1]
    assert parts[1].indices == [2]
