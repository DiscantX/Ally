import unittest

from brain.knowledge.schema.schema import ScreenElement
from brain.state.entity_registry import EntityRegistry
from brain.state.entity_highlighter import find_entity_mentions, HighlightSpan, MIN_NAME_LENGTH


class TestEntityHighlighter(unittest.TestCase):
    def setUp(self):
        self.registry = EntityRegistry()
        # Populate registry with entities
        elements = [
            ScreenElement(id="1", label="Marcus", description="A knight", box_2d=[0, 0, 1, 1]),
            ScreenElement(id="2", label="Marcus the Bold", description="Epithet alias", box_2d=[0, 0, 1, 1]),
            ScreenElement(id="3", label="Ai", description="Too short name (< 3 chars)", box_2d=[0, 0, 1, 1]),
            ScreenElement(id="4", label="Goblin", description="Monster", box_2d=[0, 0, 1, 1]),
        ]
        self.registry.resolve_or_create(elements, turn=1)
        # Add alias manually to entity 1 or 4 if needed, or via resolve_or_create
        # Let's add an alias to entity "Goblin" ("Ork")
        self.registry._entities["ent_0004"].aliases.append("GreenSkins")

    def test_exact_match(self):
        text = "Ally encountered a fierce Goblin in the cave."
        spans = find_entity_mentions(text, self.registry)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].matched_text, "Goblin")
        self.assertEqual(spans[0].entity_id, "ent_0004")
        self.assertEqual(text[spans[0].start:spans[0].end], "Goblin")

    def test_alias_match(self):
        text = "The GreenSkins attacked the camp."
        spans = find_entity_mentions(text, self.registry)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].matched_text, "GreenSkins")
        self.assertEqual(spans[0].entity_id, "ent_0004")

    def test_longest_match_first(self):
        text = "Marcus the Bold fought bravely."
        spans = find_entity_mentions(text, self.registry)
        # Should match "Marcus the Bold" as a single longer span, not separate "Marcus" and "Bold"
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].matched_text, "Marcus the Bold")
        self.assertEqual(spans[0].entity_id, "ent_0002")

    def test_case_insensitivity(self):
        text = "marcus appeared."
        spans = find_entity_mentions(text, self.registry)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].matched_text, "marcus")
        self.assertEqual(spans[0].entity_id, "ent_0001")

    def test_min_name_length_filtering(self):
        # "Ai" has length 2 < MIN_NAME_LENGTH (3)
        text = "Ai is thinking about the game."
        spans = find_entity_mentions(text, self.registry)
        self.assertEqual(len(spans), 0)

    def test_no_false_matches_on_unrelated_substrings(self):
        # "Goblin" vs "Goblinoid" or word boundaries
        text = "Goblinoid creatures are dangerous."
        spans = find_entity_mentions(text, self.registry)
        # "Goblin" should not match inside "Goblinoid" due to word boundaries (?<!\w)...(?!\w)
        self.assertEqual(len(spans), 0)


if __name__ == "__main__":
    unittest.main()
