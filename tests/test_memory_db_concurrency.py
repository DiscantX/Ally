"""Tests for MemoryDB thread safety."""
import threading
import tempfile
import os
import unittest

from brain.memory.db import MemoryDB


class TestMemoryDBConcurrency(unittest.TestCase):
    def setUp(self):
        """Create a temporary database for each test."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_memory.db")
        self.db = MemoryDB(db_path=self.db_path, player_id="test_player")

    def tearDown(self):
        """Clean up temporary database."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_concurrent_writes(self):
        """Verify that MemoryDB handles concurrent write operations safely."""
        errors = []

        def writer(thread_id):
            try:
                for i in range(20):
                    self.db.save_narrative_entry(
                        player_id="test_player",
                        game_id=f"game_{thread_id}",
                        save_id="save1",
                        turn=i,
                        tier="short",
                        summary=f"Turn {i} from thread {thread_id}"
                    )
            except Exception as e:
                errors.append(f"Thread {thread_id} error: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent writes raised errors: {errors}")

    def test_concurrent_reads_and_writes(self):
        """Verify that MemoryDB handles concurrent read and write operations safely."""
        # First, populate with some data
        for i in range(10):
            self.db.save_narrative_entry(
                player_id="test_player",
                game_id="game1",
                save_id="save1",
                turn=i,
                tier="short",
                summary=f"Initial turn {i}"
            )

        errors = []

        def reader():
            try:
                for _ in range(30):
                    entries = self.db.get_narrative_entries(
                        player_id="test_player",
                        game_id="game1",
                        save_id="save1",
                        tier="short"
                    )
                    self.assertIsInstance(entries, list)
            except Exception as e:
                errors.append(f"Reader error: {e}")

        def writer():
            try:
                for i in range(20, 50):
                    self.db.save_narrative_entry(
                        player_id="test_player",
                        game_id="game1",
                        save_id="save1",
                        turn=i,
                        tier="short",
                        summary=f"Concurrent turn {i}"
                    )
            except Exception as e:
                errors.append(f"Writer error: {e}")

        threads = [
            threading.Thread(target=reader) for _ in range(3)
        ] + [
            threading.Thread(target=writer) for _ in range(2)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent read/write raised errors: {errors}")

    def test_concurrent_entity_operations(self):
        """Verify that entity operations are thread-safe."""
        errors = []

        def entity_writer(thread_id):
            try:
                for i in range(10):
                    entity_id = f"ent_thread{thread_id}_{i}"
                    self.db.upsert_entities(
                        player_id="test_player",
                        game_id="game1",
                        save_id="save1",
                        entities=[{
                            "entity_id": entity_id,
                            "entity_type": "test",
                            "canonical_name": f"Entity {entity_id}",
                            "aliases": "[]",
                            "status": "active",
                            "facts": "[]",
                            "first_seen": 0,
                            "last_seen": 0,
                            "importance": 0,
                            "external_id": None
                        }]
                    )
            except Exception as e:
                errors.append(f"Entity writer {thread_id} error: {e}")

        threads = [threading.Thread(target=entity_writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent entity operations raised errors: {errors}")


if __name__ == "__main__":
    unittest.main()
