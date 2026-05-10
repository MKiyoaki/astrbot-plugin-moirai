
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
