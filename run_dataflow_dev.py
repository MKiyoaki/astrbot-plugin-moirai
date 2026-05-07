"""End-to-end data flow test for the memory plugin.

This script processes a mock chat history, triggers LLM-based event extraction,
verifies storage, and then tests RAG-based recall and prompt injection.

Configurations:
1. LMStudio: API_URL="http://localhost:1234/v1", API_KEY="lm-studio", MODEL="any"
2. DeepSeek:  API_URL="https://api.deepseek.com", API_KEY="your_key", MODEL="deepseek-chat"
"""

import asyncio
import json
import os
import time
from pathlib import Path
from datetime import datetime

# --- LLM CONFIGURATION ---
# Default to LMStudio. Change these to test with DeepSeek or other providers.
# LLM_API_URL = "http://localhost:1234/v1"
# LLM_API_KEY = "lm-studio"
# LLM_MODEL = "any"

# Example DeepSeek Config (Uncomment to use):
LLM_API_URL = "https://api.deepseek.com"
LLM_API_KEY = "KEY"
LLM_MODEL = "deepseek-v4-flash"
# -------------------------

DEV_DB = Path(".dev_data") / "dataflow_test.db"
MOCK_DATA_PATH = Path("tests/mock_data/mock_chat.json")

async def main():
    from core.utils.llm import SimpleLLMClient, MockProviderBridge
    from core.repository.sqlite import (
        SQLiteEventRepository, SQLitePersonaRepository, SQLiteImpressionRepository, db_open
    )
    from core.managers.memory_manager import MemoryManager
    from core.managers.recall_manager import RecallManager
    from core.managers.context_manager import ContextManager
    from core.adapters.astrbot import MessageRouter
    from core.adapters.identity import IdentityResolver
    from core.boundary.detector import EventBoundaryDetector
    from core.extractor.extractor import EventExtractor
    from core.embedding.encoder import NullEncoder # Use local encoder if available
    from core.config import PluginConfig, RetrievalConfig, InjectionConfig, ContextConfig
    from core.domain.models import Event
    
    class ProviderRequest:
        def __init__(self, prompt: str, system_prompt: str = "", messages: list = None):
            self.prompt = prompt
            self.system_prompt = system_prompt
            self.messages = messages or []
            self.contexts = []

    # 0. Setup Environment
    DEV_DB.parent.mkdir(parents=True, exist_ok=True)
    if DEV_DB.exists():
        DEV_DB.unlink()

    print("="*80)
    print(f"RUNNING DATAFLOW DEV TEST | LLM: {LLM_MODEL} @ {LLM_API_URL}")
    print("="*80)

    # 1. Initialize Components
    llm_client = SimpleLLMClient(LLM_API_URL, LLM_API_KEY, LLM_MODEL)
    mock_provider = MockProviderBridge(llm_client)

    async with db_open(DEV_DB, migration_auto_backup=False) as db:
        event_repo = SQLiteEventRepository(db)
        persona_repo = SQLitePersonaRepository(db)
        impression_repo = SQLiteImpressionRepository(db)
        
        # Use NullEncoder for simplicity, or change to SentenceTransformerEncoder if local model exists
        encoder = NullEncoder()
        
        # We need a dummy Config object
        raw_cfg = {
            "retrieval_top_k": 3,
            "retrieval_token_budget": 1000,
            "boundary_max_messages": 200, # Large enough to not trigger prematurely
            "vcm_enabled": True
        }
        cfg = PluginConfig(raw_cfg)

        from core.retrieval.hybrid import HybridRetriever
        retriever = HybridRetriever(event_repo, encoder)
        memory = MemoryManager(event_repo, retriever, encoder)
        recall = RecallManager(retriever, cfg.get_retrieval_config(), cfg.get_injection_config())
        context_manager = ContextManager(cfg.get_context_config())
        resolver = IdentityResolver(persona_repo)
        detector = EventBoundaryDetector(cfg.get_boundary_config())

        # EventExtractor with our Mock LLM Provider
        extractor = EventExtractor(
            event_repo=event_repo,
            provider_getter=lambda: mock_provider,
            encoder=encoder,
            extractor_config=cfg.get_extractor_config(),
            ipc_enabled=False # Disable IPC for this test to focus on memory
        )

        extraction_futures = []

        async def on_event_close(event: Event, window):
            print(f"\n[System] Event boundary detected! Triggering LLM extraction for topic: {event.topic}...")
            # We track the task to wait for it later
            task = asyncio.create_task(extractor(event, window))
            extraction_futures.append(task)

        router = MessageRouter(
            event_repo=event_repo,
            identity_resolver=resolver,
            detector=detector,
            context_manager=context_manager,
            on_event_close=on_event_close
        )

        # 2. Process Mock Data
        print("\n[Phase 1] Feeding mock chat history into the system...")
        with open(MOCK_DATA_PATH, "r", encoding="utf-8") as f:
            messages = json.load(f)

        session_id = "test:group_1" # Standard format: platform:group_id

        for msg in messages:
            # Simulate message arrival
            t_str = msg["time"]
            t_obj = datetime.strptime(t_str, "%H:%M:%S")
            now = datetime.now()
            t_final = now.replace(hour=t_obj.hour, minute=t_obj.minute, second=t_obj.second).timestamp()
            
            await router.process(
                platform="test",
                physical_id=msg["nickname"],
                display_name=msg["nickname"],
                text=msg["content"],
                raw_group_id="group_1",
                now=t_final
            )

        # Force flush at the end to close the last event
        print("\n[Phase 1] Reached end of mock data. Flushing router...")
        await router.flush_all()

        # Wait for all LLM extractions to finish
        if extraction_futures:
            print(f"[Phase 1] Waiting for {len(extraction_futures)} LLM extraction tasks...")
            await asyncio.gather(*extraction_futures)

        # --- CHECKPOINT 1: Database Verification ---
        print("\n" + "-"*30 + " CHECKPOINT 1: DB VERIFICATION " + "-"*30)
        events = await event_repo.list_all()
        print(f"Total Events Stored: {len(events)}")
        for i, e in enumerate(events):
            print(f"Event #{i+1}: ID={e.event_id[:8]} | Topic={e.topic}")
        
        if not events:
            print("ERROR: No events stored. Dataflow failed at extraction phase.")
            return
        else:
            print("SUCCESS: Events extracted and stored via real LLM.")

        # --- PHASE 2: Retrieval & Prompt Injection ---
        print("\n[Phase 2] Testing RAG Retrieval and Prompt Injection...")
        
        query = "之前那个叫 Rain 的人是不是含沪量很高？他都说了些什么？"
        sid_rag = "test:group_1"
        group_id = "group_1"

        # Mock a ProviderRequest (what AstrBot gives us)
        req = ProviderRequest(
            prompt="You are now in a chatroom. The user asks: " + query,
            system_prompt="You are a helpful assistant.",
            messages=[]
        )

        # 1. Inference BEFORE memory injection
        print(f"\n[LLM] Generating response WITHOUT memory for query: '{query}'")
        resp_no_mem = await llm_client.text_chat(req.prompt, req.system_prompt)
        print(f"Response (No Memory): \n>>> {resp_no_mem.completion_text}")

        # 2. Perform Recall and Injection
        print("\n[System] Performing recall and injection...")
        await recall.recall_and_inject(
            query=query,
            req=req,
            session_id=sid_rag,
            group_id=group_id
        )
        # Manually signal recall hit to VCM for demonstration
        context_manager.update_state(sid_rag, recall_hit=True)

        # --- CHECKPOINT 2: Final Prompt & Response Comparison ---
        print("\n" + "-"*30 + " CHECKPOINT 2: PROMPT & STATE " + "-"*30)
        print(f"Current VCM State: {context_manager.get_state(sid_rag).value.upper()}")
        print("\nFinal System Prompt (Injected Preview):")
        preview = req.system_prompt[:500] + "..." if len(req.system_prompt) > 500 else req.system_prompt
        print(f"\"\"\"\n{preview}\n\"\"\"")
        
        print(f"\n[LLM] Generating response WITH memory...")
        resp_with_mem = await llm_client.text_chat(req.prompt, req.system_prompt)
        
        print("\n" + "="*20 + " COMPARISON " + "="*20)
        print(f"QUERY: {query}")
        print("-" * 40)
        print(f"BEFORE MEMORY:\n{resp_no_mem.completion_text}")
        print("-" * 40)
        print(f"AFTER MEMORY (RAG):\n{resp_with_mem.completion_text}")
        print("="*52)

        # --- PHASE 3: VCM State Stress Test ---
        print("\n[Phase 3] VCM State Stress Test (Focused -> Eviction -> Drift)")
        # Create a new session with small window
        small_cfg = ContextConfig(vcm_enabled=True, window_size=5)
        stress_cm = ContextManager(small_cfg)
        stress_sid = "test:stress"
        
        print(f"Initial State: {stress_cm.get_window(stress_sid, create=True).session_id} -> {stress_cm.get_state(stress_sid).value}")
        
        # 1. Fill to trigger EVICTION (80% of 5 = 4 messages)
        win = stress_cm.get_window(stress_sid)
        for i in range(4):
            win.add_message("u", f"stress {i}", time.time())
            state = stress_cm.update_state(stress_sid)
            print(f"Msg {i+1}: State -> {state.value}")
            
        # 2. Trigger DRIFT
        state = stress_cm.update_state(stress_sid, drift_detected=True)
        print(f"Topic Drift Detected: State -> {state.value}")
        
        # 3. Recovery
        state = stress_cm.update_state(stress_sid)
        print(f"New Message After Drift: State -> {state.value}")

    print("\n[Done] End-to-end dataflow and VCM test complete.")

if __name__ == "__main__":
    asyncio.run(main())
