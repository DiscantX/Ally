import unittest
from PIL import Image
from brain.reasoning.core import AllyCore
from ingestion.collectors.base import RawObservation, ConfirmedFact


class TestAllyCore(unittest.TestCase):
    def test_ally_core_initialization_and_turn(self):
        core = AllyCore(image_path=None, personality_name="Scout")
        core.initialize_run()

        events = []
        core.on_status_update = lambda screen, event: events.append(("status", screen, event))
        core.on_state_summary = lambda summary: events.append(("summary", summary))
        core.on_prompt_update = lambda prompt: events.append(("prompt", prompt))
        core.on_feedback = lambda feedback: events.append(("feedback", feedback))
        core.on_eta_ready = lambda: events.append(("eta",))

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
        core.on_chat_message = lambda sender, msg: messages.append((sender, msg))

        core.send_message("Hello Ally", message_type="chat")
        # Wait briefly for background thread
        import time
        time.sleep(0.1)
        self.assertTrue(any("Game loop hasn't started yet" in m[1] for m in messages))


if __name__ == "__main__":
    unittest.main()
