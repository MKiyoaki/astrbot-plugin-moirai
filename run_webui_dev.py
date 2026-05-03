import asyncio
from pathlib import Path
from web.server import WebuiServer
from core.repository.memory import (
    InMemoryPersonaRepository,
    InMemoryEventRepository,
    InMemoryImpressionRepository,
)

async def main():
    srv = WebuiServer(
        persona_repo=InMemoryPersonaRepository(),
        event_repo=InMemoryEventRepository(),
        impression_repo=InMemoryImpressionRepository(),
        data_dir=Path("/tmp/em_dev"),
        port=2653,
    )
    await srv.start()
    print("Open http://localhost:2653")
    await asyncio.sleep(3600)

asyncio.run(main())
