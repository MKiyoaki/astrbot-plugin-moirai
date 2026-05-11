
import pytest
import random
import math
from core.domain.models import Event
from core.retrieval.hybrid import HybridRetriever
from core.embedding.encoder import NullEncoder
from core.repository.memory import InMemoryEventRepository

def make_event(event_id: str, topic: str = "") -> Event:
    return Event(
        event_id=event_id,
        group_id="g1",
        start_time=1000.0,
        end_time=1010.0,
        participants=["uid-a"],
        interaction_flow=[],
        topic=topic,
        summary="test summary",
        chat_content_tags=[],
        salience=0.5,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=1010.0,
    )

@pytest.mark.asyncio
async def test_weighted_random_sampling_distribution():
    repo = InMemoryEventRepository()
    # Create 20 events
    events = [make_event(f"e{i}", topic=f"topic {i}") for i in range(20)]
    for e in events:
        await repo.upsert(e)
    
    # We use BM25-only for simplicity in this test
    # BM25 scores will be 1/1, 1/2, 1/3 ... in the current implementation when vec is empty
    
    # T=0.1 should be very close to deterministic top-K
    retriever_low_t = HybridRetriever(
        repo, encoder=NullEncoder(), 
        weighted_random=True, 
        sampling_temperature=0.01
    )
    
    results_low_t = await retriever_low_t.search("topic", limit=5)
    # With very low T, it should almost always pick the top 5
    # top 5 are e0, e1, e2, e3, e4 (depending on BM25 return order, but InMemory repo returns in upsert order for simple prefix match)
    assert len(results_low_t) == 5
    # Since it's still random, there's a tiny chance it's different, but at T=0.01 it's extremely unlikely
    
    # T=100 should be almost uniform
    retriever_high_t = HybridRetriever(
        repo, encoder=NullEncoder(), 
        weighted_random=True, 
        sampling_temperature=100.0
    )
    
    # Run multiple times to see if we get different results
    all_seen_ids = set()
    for _ in range(10):
        results = await retriever_high_t.search("topic", limit=5)
        for r in results:
            all_seen_ids.add(r.event_id)
    
    # In uniform sampling from 20 items, 10 runs of 5 items should see more than just the top 5
    assert len(all_seen_ids) > 5

@pytest.mark.asyncio
async def test_weighted_random_no_duplicates():
    repo = InMemoryEventRepository()
    events = [make_event(f"e{i}", topic="topic") for i in range(10)]
    for e in events:
        await repo.upsert(e)
        
    retriever = HybridRetriever(
        repo, encoder=NullEncoder(), 
        weighted_random=True, 
        sampling_temperature=1.0
    )
    
    results = await retriever.search("topic", limit=5)
    assert len(results) == 5
    ids = [e.event_id for e in results]
    assert len(set(ids)) == 5  # No duplicates

@pytest.mark.asyncio
async def test_weighted_random_off_behavior():
    repo = InMemoryEventRepository()
    events = [make_event(f"e{i}", topic="topic") for i in range(10)]
    for e in events:
        await repo.upsert(e)
        
    # Default is weighted_random=False
    retriever = HybridRetriever(repo, encoder=NullEncoder(), weighted_random=False)
    
    results1 = await retriever.search("topic", limit=5)
    results2 = await retriever.search("topic", limit=5)
    
    # Should be identical
    assert [e.event_id for e in results1] == [e.event_id for e in results2]
