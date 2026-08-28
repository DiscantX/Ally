import os
import tempfile
import unittest

from brain.memory.db import MemoryDB
from brain.knowledge.schema.schema import ScreenElement
from brain.state.entity_registry import EntityRegistry, ResolvableElement


class TestEntityRegistryPersistence(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "test_registry.db")
        self.db = MemoryDB(self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_persistence_and_reload(self):
        player_id = "test_player"
        game_id = "test_game"
        save_id = "save_alpha"

        registry = EntityRegistry(
            player_id=player_id,
            game_id=game_id,
            save_id=save_id,
            db=self.db,
        )

        elements = [
            ScreenElement(id="el_1", label="Goblin", description="A fierce green goblin", box_2d=[0, 0, 10, 10]),
            ResolvableElement(label="Hero", description="Main character", external_id="ext_hero_1", entity_type="character"),
        ]

        touched = registry.resolve_or_create(elements, turn=1)
        self.assertEqual(len(touched), 2)

        # Reload fresh registry with same scope
        registry_reloaded = EntityRegistry(
            player_id=player_id,
            game_id=game_id,
            save_id=save_id,
            db=self.db,
        )

        self.assertEqual(len(registry_reloaded._entities), 2)
        # Check that external_id and aliases/facts loaded correctly
        goblin_ent = None
        hero_ent = None
        for ent in registry_reloaded._entities.values():
            if ent.canonical_name == "Goblin":
                goblin_ent = ent
            elif ent.canonical_name == "Hero":
                hero_ent = ent

        self.assertIsNotNone(goblin_ent)
        self.assertEqual(goblin_ent.facts, ["A fierce green goblin"])
        self.assertEqual(goblin_ent.first_seen_turn, 1)

        self.assertIsNotNone(hero_ent)
        self.assertEqual(hero_ent.external_id, "ext_hero_1")
        self.assertEqual(hero_ent.entity_type, "character")
        self.assertEqual(hero_ent.facts, ["Main character"])

        # Test resolution post-reload
        new_elements = [
            ScreenElement(id="el_2", label="Goblin", description="Goblin strikes back", box_2d=[0, 0, 10, 10]),
        ]
        touched_again = registry_reloaded.resolve_or_create(new_elements, turn=2)
        self.assertEqual(len(touched_again), 1)
        self.assertEqual(touched_again[0].entity_id, goblin_ent.entity_id)
        self.assertEqual(len(touched_again[0].facts), 2)

    def test_scope_isolation(self):
        player_id = "test_player"
        game_id = "test_game"

        # Save 1
        reg1 = EntityRegistry(player_id=player_id, game_id=game_id, save_id="save_1", db=self.db)
        reg1.resolve_or_create([ScreenElement(id="1", label="Dragon", description="Fire breathing", box_2d=[0,0,1,1])], turn=1)

        # Save 2 (different save_id)
        reg2 = EntityRegistry(player_id=player_id, game_id=game_id, save_id="save_2", db=self.db)
        self.assertEqual(len(reg2._entities), 0)


if __name__ == "__main__":
    unittest.main()
