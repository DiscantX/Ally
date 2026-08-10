"""The Entity Registry: non-lossy, append-only memory of things Ally has
seen this run (characters, items, locations, objectives).

This is the answer to "are we losing important info when we compress
short-term memory" -- entities never get summarized away, only their
`facts` list grows and their `status`/`last_seen_turn` update.

Resolution strategy for this vertical slice: difflib string matching
against known names/aliases. This is the "dumb NLP first pass" from
the earlier discussion -- cheap, local, no API calls, no rate limits.
It will misfire on real aliasing ("the lieutenant" vs "Marcus") since
that's a semantic match, not a string match. The seam for fixing that is
marked below: swap resolve_or_create's matching step for an
EmbeddingProvider + vector search without touching the Entity dataclass
or anything that calls this class.
"""

import difflib
from dataclasses import dataclass, field

from schema.schema import ScreenElement


@dataclass
class Entity:
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    first_seen_turn: int = 0
    last_seen_turn: int = 0


class EntityRegistry:
    def __init__(self, match_threshold: float = 0.75):
        self._entities: dict[str, Entity] = {}
        self._next_id = 1
        self.match_threshold = match_threshold

    def _name_lookup(self) -> dict[str, str]:
        """Every known name/alias -> entity_id, lowercased."""
        lookup: dict[str, str] = {}
        for ent in self._entities.values():
            lookup[ent.canonical_name.lower()] = ent.entity_id
            for alias in ent.aliases:
                lookup[alias.lower()] = ent.entity_id
        return lookup

    def resolve_or_create(
        self, elements: list[ScreenElement], turn: int
    ) -> list[Entity]:
        touched: list[Entity] = []
        lookup = self._name_lookup()

        for el in elements:
            name = el.label.strip()
            key = name.lower()

            # --- MATCH STEP -----------------------------------------
            # TODO(embeddings): replace this difflib call with a vector
            # search over entity embeddings once EmbeddingProvider exists.
            # Everything below this block (create-vs-update, fact
            # appending) stays the same either way.
            matches = difflib.get_close_matches(
                key, lookup.keys(), n=1, cutoff=self.match_threshold
            )
            # ----------------------------------------------------------

            if matches:
                entity_id = lookup[matches[0]]
                ent = self._entities[entity_id]
                if key != ent.canonical_name.lower() and name not in ent.aliases:
                    ent.aliases.append(name)
                ent.facts.append(el.description)
                ent.last_seen_turn = turn
            else:
                ent = Entity(
                    entity_id=f"ent_{self._next_id:04d}",
                    entity_type="unknown",
                    canonical_name=name,
                    facts=[el.description],
                    first_seen_turn=turn,
                    last_seen_turn=turn,
                )
                self._next_id += 1
                self._entities[ent.entity_id] = ent
                lookup[key] = ent.entity_id

            touched.append(ent)

        return touched

    def as_context(self, entities: list[Entity]) -> str:
        """Compact text form for injecting into Ally's prompt."""
        if not entities:
            return "(no known entities yet)"
        seen = set()
        lines = []
        for ent in entities:
            if ent.entity_id in seen:
                continue
            seen.add(ent.entity_id)
            times = ent.last_seen_turn - ent.first_seen_turn + 1
            lines.append(f"- [{ent.entity_id}] {ent.canonical_name} (seen {times}x)")
        return "\n".join(lines)
