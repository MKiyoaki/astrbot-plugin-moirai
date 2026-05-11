import pytest
import asyncio
from core.extractor.extractor import EventExtractor
from core.repository.memory import InMemoryEventRepository
from core.boundary.window import MessageWindow
from core.embedding.encoder import NullEncoder


class MockEncoder:
    @property
    def dim(self) -> int:
        return 512

    async def encode(self, text: str):
        # Deterministic vectors for testing
        if text == "购物": return [1.0] + [0.0]*511
        if text == "买东西": return [0.95] + [0.0]*511  # Close to "购物"
        if text == "技术架构": return [0.0] * 511 + [1.0]    # Far from "购物"
        return [0.5] * 512

    async def encode_batch(self, texts):
        return [await self.encode(t) for t in texts]


class _CountingMockEncoder(MockEncoder):
    """MockEncoder that counts individual encode() vs encode_batch() calls.

    encode_batch bypasses the counting encode() so that the counter accurately
    reflects whether production code called encode() directly.
    """

    def __init__(self) -> None:
        self.encode_calls: int = 0
        self.encode_batch_calls: int = 0

    async def encode(self, text: str):
        self.encode_calls += 1
        return await MockEncoder.encode(self, text)

    async def encode_batch(self, texts):
        self.encode_batch_calls += 1
        # Call base encode logic without going through the counting encode()
        return [await MockEncoder.encode(self, t) for t in texts]

class EnhancedInMemoryRepo(InMemoryEventRepository):
    def __init__(self):
        super().__init__()
        self.canonical_tags = {} # text -> vector

    async def list_frequent_tags(self, limit: int = 50):
        return await super().list_frequent_tags(limit)

    async def search_canonical_tag(self, embedding, limit=5, threshold=0.85):
        import math
        results = []
        for tag, vec in self.canonical_tags.items():
            # Dot product as similarity since they are normalized
            sim = sum(a*b for a, b in zip(embedding, vec))
            if sim >= threshold:
                results.append((tag, sim))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    async def upsert_canonical_tag(self, tag_text, embedding):
        self.canonical_tags[tag_text] = embedding

@pytest.mark.asyncio
async def test_tag_alignment_logic():
    repo = EnhancedInMemoryRepo()
    encoder = MockEncoder()
    
    # Pre-seed canonical tag
    await repo.upsert_canonical_tag("购物", [1.0] + [0.0]*511)
    
    extractor = EventExtractor(
        event_repo=repo,
        provider_getter=lambda: None,
        encoder=encoder
    )
    
    # 1. Test alignment of similar tag
    aligned = await extractor._align_tags(["买东西"])
    assert aligned == ["购物"], "Should align '买东西' to '购物'"
    
    # 2. Test creation of new distinct tag
    aligned = await extractor._align_tags(["技术架构"])
    assert "技术架构" in aligned
    assert "技术架构" in repo.canonical_tags
    
    # 3. Test de-duplication
    aligned = await extractor._align_tags(["买东西", "购物", "技术架构"])
    assert len(aligned) == 2
    assert "购物" in aligned
    assert "技术架构" in aligned

# ---------------------------------------------------------------------------
# P2-1: _align_tags should call encode_batch once for all tags,
#        not encode() separately for each tag.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_align_tags_uses_batch_encode_not_per_tag_encode():
    """_align_tags must call encode_batch(all_tags) rather than encode(tag)
    in a loop.  With 3 tags, encode_batch should be called exactly once
    and individual encode() should not be called at all."""
    repo = EnhancedInMemoryRepo()
    encoder = _CountingMockEncoder()

    extractor = EventExtractor(
        event_repo=repo,
        provider_getter=lambda: None,
        encoder=encoder,
    )

    await extractor._align_tags(["购物", "技术架构", "闲聊"])

    assert encoder.encode_batch_calls == 1, (
        f"encode_batch should be called once, got {encoder.encode_batch_calls}"
    )
    assert encoder.encode_calls == 0, (
        f"individual encode() should not be called, got {encoder.encode_calls}"
    )


@pytest.mark.asyncio
async def test_align_tags_empty_list_no_encode():
    repo = EnhancedInMemoryRepo()
    encoder = _CountingMockEncoder()
    extractor = EventExtractor(event_repo=repo, provider_getter=lambda: None, encoder=encoder)

    result = await extractor._align_tags([])
    assert result == []
    assert encoder.encode_batch_calls == 0
    assert encoder.encode_calls == 0


# ---------------------------------------------------------------------------
# P2-2: _init_tag_seeds must NOT call asyncio.create_task in __init__.
#        Creating an EventExtractor outside an async context must not raise.
# ---------------------------------------------------------------------------

def test_extractor_construction_outside_event_loop_does_not_raise():
    """Creating EventExtractor in a sync context (no running loop) must not crash.

    Previously asyncio.create_task(_init_tag_seeds()) in __init__ would raise
    RuntimeError when no event loop was running.
    """
    import asyncio
    repo = EnhancedInMemoryRepo()
    encoder = _CountingMockEncoder()
    # This must not raise RuntimeError or any other exception
    extractor = EventExtractor(event_repo=repo, provider_getter=lambda: None, encoder=encoder)
    assert extractor is not None


@pytest.mark.asyncio
async def test_tag_seeds_initialized_on_first_call_not_at_construction():
    """encode() calls for tag seeds must not happen at construction time —
    only when __call__ (or _init_tag_seeds explicitly) is first awaited."""
    repo = EnhancedInMemoryRepo()
    encoder = _CountingMockEncoder()

    extractor = EventExtractor(event_repo=repo, provider_getter=lambda: None, encoder=encoder)

    # Right after construction — no encode calls yet (seeds not yet loaded)
    await asyncio.sleep(0)  # let any pending tasks run
    assert encoder.encode_calls == 0, (
        f"encode() must not be called at construction time, got {encoder.encode_calls}"
    )


@pytest.mark.asyncio
async def test_frequent_tags_injection():
    repo = EnhancedInMemoryRepo()
    # Add an event with tags
    from core.domain.models import Event
    import time
    await repo.upsert(Event(
        event_id="e1", 
        chat_content_tags=["购物", "闲聊"],
        start_time=time.time(),
        end_time=time.time()
    ))
    
    tags = await repo.list_frequent_tags()
    assert "购物" in tags
    assert "闲聊" in tags
