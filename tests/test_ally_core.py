import unittest
from unittest.mock import MagicMock
from PIL import Image
from brain.reasoning.core import AllyCore
from ingestion.collectors.base import RawObservation, ConfirmedFact


class TestAllyCore(unittest.TestCase):
    def test_ally_core_initialization_and_turn(self):
        core = AllyCore(image_path=None, personality_name="Scout")
        core.initialize_run()

        events = []
        core.on_status_update.connect(lambda screen, event: events.append(("status", screen, event)))
        core.on_state_summary.connect(lambda summary: events.append(("summary", summary)))
        core.on_prompt_update.connect(lambda prompt: events.append(("prompt", prompt)))
        core.on_feedback.connect(lambda feedback: events.append(("feedback", feedback)))
        core.on_eta_ready.connect(lambda: events.append(("eta",)))

        # Create dummy observation with skip_ally=True to avoid LLM network call in unit test
        img = Image.new("RGB", (100, 100), color="blue")
        obs = RawObservation(
            image=img,
            screen_name="test_screen",
            screen_confidence=1.0,
            confirmed_facts=[ConfirmedFact(key="health", value="100", source="ocr")],
            skip_ally=True
        )

        ended = core.run_turn(obs, include_ui=False)
        self.assertFalse(ended)
        self.assertTrue(any(e[0] == "status" for e in events))
        self.assertTrue(any(e[0] == "summary" for e in events))
        self.assertTrue(any(e[0] == "feedback" for e in events))

    def test_ally_core_chat_message_unstarted(self):
        core = AllyCore(personality_name="Scout")
        messages = []
        core.on_chat_message.connect(lambda sender, msg: messages.append((sender, msg)))

        core.send_message("Hello Ally", message_type="chat")
        # Wait briefly for background thread
        import time
        time.sleep(0.1)
        self.assertTrue(any("Game loop hasn't started yet" in m[1] for m in messages))

    def test_gameplay_driven_significant_moment_trigger(self):
        core = AllyCore(image_path=None, personality_name="Scout")
        core.initialize_run()

        from brain.knowledge.schema.schema import AllyOutput
        core.ally.decide = MagicMock(return_value=AllyOutput(
            analysis="We defeated the boss!",
            actions=[],
            significant_moment=True
        ))
        core.scribe.extract = MagicMock(return_value=MagicMock(screen_elements=[], genre_guess="RPG", genre_confidence=1.0, screen_name_guess="combat"))

        core.memory_manager.add_personality_journal_entry = MagicMock()
        core.memory_manager.redistill_personality = MagicMock()
        core.memory_manager.close_run = MagicMock()

        img = Image.new("RGB", (100, 100), color="blue")
        obs = RawObservation(
            image=img,
            screen_name="boss_screen",
            screen_confidence=1.0,
            confirmed_facts=[],
            skip_ally=False
        )

        core.run_turn(obs, include_ui=True)
        core.memory_manager.add_personality_journal_entry.assert_called_once()

    def test_redistill_threshold_accumulation_and_run_ended_flush(self):
        core = AllyCore(image_path=None, personality_name="Scout")
        core.initialize_run()
        core.personality_redistill_journal_interval = 2
        core._personality_journal_writes_since_redistill = 0

        from brain.knowledge.schema.schema import AllyOutput
        core.ally.decide = MagicMock(return_value=AllyOutput(
            analysis="Significant moment happening.",
            actions=[],
            significant_moment=True
        ))
        core.scribe.extract = MagicMock(return_value=MagicMock(screen_elements=[], genre_guess="RPG", genre_confidence=1.0, screen_name_guess="combat"))

        core.memory_manager.add_personality_journal_entry = MagicMock()
        core.memory_manager.redistill_personality = MagicMock()
        core.memory_manager.close_run = MagicMock()

        img = Image.new("RGB", (100, 100), color="blue")
        obs = RawObservation(
            image=img,
            screen_name="combat",
            screen_confidence=1.0,
            confirmed_facts=[],
            skip_ally=False
        )

        # 1st write (count = 1 < 2) -> no redistill
        core.run_turn(obs, include_ui=True)
        core.memory_manager.redistill_personality.assert_not_called()
        self.assertEqual(core._personality_journal_writes_since_redistill, 1)

        # 2nd write (count = 2 >= 2) -> triggers redistill and resets counter to 0
        core.run_turn(obs, include_ui=True)
        core.memory_manager.redistill_personality.assert_called_once()
        self.assertEqual(core._personality_journal_writes_since_redistill, 0)

        # Now test run_ended flush with nonzero writes
        core._personality_journal_writes_since_redistill = 1
        obs_ended = RawObservation(
            image=img,
            screen_name="victory",
            screen_confidence=1.0,
            confirmed_facts=[],
            skip_ally=False,
            run_ended=True
        )
        core.memory_manager.redistill_personality.reset_mock()
        core.run_turn(obs_ended, include_ui=True)
        core.memory_manager.redistill_personality.assert_called_once()
        self.assertEqual(core._personality_journal_writes_since_redistill, 0)
        core.memory_manager.close_run.assert_called()


if __name__ == "__main__":
    unittest.main()
