import asyncio
from pathlib import Path
from core.api import get_stats
from core.repository.sqlite import SQLitePersonaRepository, SQLiteEventRepository, SQLiteImpressionRepository, db_open

async def test_get_stats():
    db_path = Path("tests/mock_data/test.db")
    if db_path.exists():
        db_path.unlink()
    
    async with db_open(db_path) as db:
        # Init repos
        persona_repo = SQLitePersonaRepository(db)
        event_repo = SQLiteEventRepository(db)
        impression_repo = SQLiteImpressionRepository(db)
        
        # Record some dummy perf
        from core.utils.perf import tracker
        await tracker.record("response", 0.5)
        await tracker.record("recall", 0.1)
        await tracker.record("recall_search", 0.05)
        
        stats = await get_stats(persona_repo, event_repo, impression_repo, Path("data"), "v0.8.1")
        import json
        print(json.dumps(stats, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(test_get_stats())
