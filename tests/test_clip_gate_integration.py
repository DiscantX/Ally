import unittest
from unittest.mock import MagicMock, patch
from PIL import Image

from collectors.configured_collector import GenericHudCollector, CollectorConfig
from collectors.base import RawObservation
from ally.core import AllyCore
from vision.screen_category_store import CategoryMatch


class TestClipGateIntegration(unittest.TestCase):
    @patch("collectors.configured_collector.ScreenCollector")
    def test_capture_off_game_skip(self, mock_screen_collector_cls):
        mock_screen = mock_screen_collector_cls.return_value
        mock_screen.rect.is_foreground.return_value = True
        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8) if 'np' in globals() else None
        # Use numpy correctly
        import numpy as np
        fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_screen.capture_bgr.return_value = fake_frame
        mock_screen.change_detector.has_changed.return_value = True

        clip_cls = MagicMock()
        clip_cls.enabled = True
        clip_cls.encode_image.return_value = np.array([1.0, 0.0])

        store = MagicMock()
        match = CategoryMatch(kind="off_game", text="a web browser", top_probability=0.9, margin=0.5, confident=True)
        store.for_game.return_value.classify.return_value = match

        config = CollectorConfig(game_id="test_game", window_title="Test", layout_dir="nonexistent", source_tag="test")
        collector = GenericHudCollector(config, clip_classifier=clip_cls, category_store=store)

        obs = collector.capture()
        self.assertEqual(obs.skip_scribe_reason, "off_game")

    @patch("collectors.configured_collector.ScreenCollector")
    def test_capture_not_foreground(self, mock_screen_collector_cls):
        mock_screen = mock_screen_collector_cls.return_value
        mock_screen.rect.is_foreground.return_value = False

        config = CollectorConfig(game_id="test_game", window_title="Test", layout_dir="nonexistent", source_tag="test")
        collector = GenericHudCollector(config)

        obs = collector.capture()
        self.assertEqual(obs.skip_scribe_reason, "not_foreground")
        mock_screen.capture_bgr.assert_not_called()

    @patch("ally.core.MemoryDB")
    @patch("ally.core.ClipClassifier")
    @patch("ally.core.ScreenCategoryStore")
    def test_ally_core_off_game_run_turn(self, mock_store_cls, mock_clip_cls, mock_db_cls):
        core = AllyCore(game_id="test_game")
        core.scribe = MagicMock()
        core.memory_manager = MagicMock()

        img = Image.new("RGB", (100, 100))
        obs = RawObservation(image=img, skip_scribe_reason="off_game", screen_category="a web browser")

        ended = core.run_turn(obs)
        core.scribe.extract.assert_not_called()
        core.memory_manager.record_turn.assert_not_called()

    @patch("ally.core.MemoryDB")
    @patch("ally.core.ClipClassifier")
    @patch("ally.core.ScreenCategoryStore")
    def test_ally_core_normal_run_turn(self, mock_store_cls, mock_clip_cls, mock_db_cls):
        core = AllyCore(game_id="test_game")
        core.scribe = MagicMock()
        scribe_res = MagicMock()
        scribe_res.screen_name_guess = "combat_screen"
        scribe_res.screen_elements = []
        scribe_res.genre_guess = "strategy"
        scribe_res.genre_confidence = 0.9
        core.scribe.extract.return_value = scribe_res

        core.ally = MagicMock()
        ally_out = MagicMock()
        ally_out.analysis = "test analysis"
        ally_out.actions = []
        core.ally.decide.return_value = ally_out

        core.category_store = mock_store_cls.return_value
        core.collector = MagicMock()
        core.collector.config.game_id = "test_game"

        img = Image.new("RGB", (100, 100))
        obs = RawObservation(image=img, skip_scribe_reason="none", confirmed_facts=[])

        ended = core.run_turn(obs)
        core.scribe.extract.assert_called_once()
        core.category_store.maybe_learn.assert_called_once_with("combat_screen", "test_game")


if __name__ == "__main__":
    unittest.main()
