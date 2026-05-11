"""Task: Re-index all events for vector search."""
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..repository.base import EventRepository
    from ..retrieval.hybrid import HybridRetriever

logger = logging.getLogger(__name__)

async def run_reindex_all(
    event_repo: 'EventRepository',
    retriever: 'HybridRetriever',
) -> int:
    """Re-compute and store embeddings for all events in the database.
    
    Returns the count of events processed.
    """
    events = await event_repo.list_all(limit=10000)
    count = 0
    for event in events:
        try:
            await retriever.index_event(event)
            count += 1
        except Exception as exc:
            logger.warning("Failed to index event %s: %s", event.event_id, exc)
    
    logger.info("Re-indexing complete: %d events processed", count)
    return count
