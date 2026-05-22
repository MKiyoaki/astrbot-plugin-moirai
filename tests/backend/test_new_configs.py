import asyncio
import unittest
from pathlib import Path
from core.config import PluginConfig
from core.boundary.detector import EventBoundaryDetector, BoundaryConfig
from core.boundary.window import MessageWindow

class TestNewConfigs(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.raw_config = {
            "vcm": {
                "context_max_sessions": 100,
                "context_session_idle_seconds": 3600,
                "context_window_size": 50,
                "context_max_history_messages": 1000,
                "context_cleanup_batch_size": 50
            },
            "retrieval": {
                "retrieval_top_k": 3,
                "retrieval_active_top_k": 5,
                "retrieval_token_budget": 800,
                "retrieval_salience_weight": 0.1,
                "retrieval_rrf_k": 60,
                "injection_position": "system_prompt",
                "injection_auto_clear": True,
                "show_llm_call_details": True
            },
            "relation": {
                "decay_lambda": 0.01,
                "decay_interval_hours": 24,
                "impression_injection_enabled": True,
                "impression_injection_max_items": 4,
                "impression_injection_min_confidence": 0.35
            },
            "backup": {
                "backup_enabled": True,
                "backup_retention_days": 7
            },
            "cleanup": {
                "raw_message_retention_days": 9
            },
            "boundary": {
                "summary_trigger_rounds": 30
            }
        }
        self.cfg = PluginConfig(self.raw_config)

    def test_config_parsing(self):
        # Test VCM
        vcm = self.cfg.get_context_config()
        self.assertEqual(vcm.max_sessions, 100)
        self.assertEqual(vcm.max_history_messages, 1000)
        self.assertEqual(vcm.cleanup_batch_size, 50)

        # Test Retrieval
        retrieval = self.cfg.get_retrieval_config()
        self.assertEqual(retrieval.final_limit, 3)
        self.assertEqual(retrieval.active_limit, 5)
        self.assertEqual(retrieval.salience_weight, 0.1)
        self.assertEqual(retrieval.rrf_k, 60)

        # Test Injection
        injection = self.cfg.get_injection_config()
        self.assertEqual(injection.position, "system_prompt")
        self.assertTrue(injection.auto_clear)
        self.assertTrue(injection.impression_injection_enabled)
        self.assertEqual(injection.impression_injection_max_items, 4)
        self.assertEqual(injection.impression_injection_min_confidence, 0.35)
        self.assertTrue(self.cfg.show_llm_call_details)

        # Test Decay
        decay = self.cfg.get_decay_config()
        self.assertEqual(decay.lambda_, 0.01)

        # Test Backup
        backup = self.cfg.get_backup_config()
        self.assertTrue(backup.enabled)
        self.assertEqual(backup.retention_days, 7)

        # Test raw message retention clamp surface
        cleanup = self.cfg.get_cleanup_config()
        self.assertEqual(cleanup.raw_message_retention_days, 9)

        # Test Boundary
        boundary = self.cfg.get_boundary_config()
        self.assertEqual(boundary.summary_trigger_rounds, 30)

        # Test Embedding defaults: local encoder should not add a fixed 5s
        # delay to every recall query unless the user configures throttling.
        embedding = self.cfg.get_embedding_config()
        self.assertEqual(embedding.batch_interval_ms, 50)
        self.assertEqual(embedding.request_interval_ms, 0)

        # Test persona synthesis trigger defaults
        self.assertEqual(self.cfg.persona_synthesis_trigger_messages, 30)
        self.assertEqual(self.cfg.persona_synthesis_min_events, 3)
        self.assertEqual(self.cfg.persona_synthesis_cooldown_hours, 3.0)
        self.assertEqual(self.cfg.persona_synthesis_interval_seconds, 72 * 3600)

    def test_summary_trigger_rounds(self):
        b_cfg = BoundaryConfig(summary_trigger_rounds=2)
        detector = EventBoundaryDetector(config=b_cfg)
        window = MessageWindow(session_id="test", group_id="g1")
        
        # 1 round (2 messages)
        window.add_message("u1", "hi", 1000)
        window.add_message("bot", "hello", 1001)
        should, reason = detector.should_close(window, 1002)
        self.assertFalse(should)
        
        # 2 rounds (4 messages) -> Trigger
        window.add_message("u1", "how are you", 1003)
        window.add_message("bot", "I am fine", 1004)
        should, reason = detector.should_close(window, 1005)
        self.assertTrue(should)
        self.assertEqual(reason, "summary_trigger_rounds")

    def test_raw_message_retention_days_clamped(self):
        self.assertEqual(
            PluginConfig({"cleanup": {"raw_message_retention_days": 0}})
            .get_cleanup_config()
            .raw_message_retention_days,
            1,
        )
        self.assertEqual(
            PluginConfig({"cleanup": {"raw_message_retention_days": 99}})
            .get_cleanup_config()
            .raw_message_retention_days,
            14,
        )

if __name__ == "__main__":
    unittest.main()
