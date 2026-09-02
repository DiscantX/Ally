"""The Entity Registry: non-lossy, append-only memory of things Ally has
seen this run (characters, items, locations, objectives).

This is the answer to "are we losing important info when we compress
short-term memory" -- entities never get summarized away, only their
`facts` list grows and their `status`/`last_seen_turn` update.

Two resolution strategies, chosen per-element:

- **Fuzzy** (the original vertical-slice strategy): `difflib` string
  matching against known names/aliases. Cheap, local, no API calls, no
  rate limits. Misfires on real aliasing ("the lieutenant" vs "Marcus")
  since that's a semantic match, not a string match -- expected, and the
  motivating case for a future embedding-based upgrade (see the `TODO`
  below, still unchanged by this pass).
- **Exact** (new in this pass): when a Collector can supply an
  unambiguous `external_id` for an element -- e.g. MTGA's log parser
  handing over an object's Arena `instanceId` -- fuzzy matching is
  skipped entirely in favor of a direct id -> entity_id lookup. This is
  the generalization of the seam ally_decision_log.md and
  mtga_integration_notes.md §5 both flagged: "any Collector supplying an
  exact ID skips difflib fuzzy matching," not an MTGA-specific feature.

`entity_type` also gets a real path in this pass: a Collector that knows
a real type (MTGA's resolved card `type` field -- creature, land,
instant, ...) can supply it independent of whether it also supplies an
external_id. Scribe's ScreenElement path supplies neither, so it
continues to default to "unknown" exactly as before -- this pass does
not attempt to infer type from Scribe's free-text labels.
"""

import difflib
import json
import sqlite3
import threading
from dataclasses import dataclass, field
from typing import Any

from brain.knowledge.schema.schema import ScreenElement
from brain.memory.db import MemoryDB


@dataclass
class Entity:
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str] = field(default_factory=list)
    facts: list[str] = field(default_factory=list)
    first_seen_turn: int = 0
    last_seen_turn: int = 0
    external_id: str | None = None  # NEW -- set only when resolved via the exact-id path
    status: str = "active"
    importance: int = 0

    def to_row(self) -> dict[str, Any]:
        return {
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "canonical_name": self.canonical_name,
            "aliases": json.dumps(self.aliases),
            "facts": json.dumps(self.facts),
            "first_seen": self.first_seen_turn,
            "last_seen": self.last_seen_turn,
            "external_id": self.external_id,
            "status": self.status,
            "importance": self.importance,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any] | sqlite3.Row) -> "Entity":
        aliases = row["aliases"]
        if isinstance(aliases, str):
            try:
                aliases = json.loads(aliases)
            except Exception:
                aliases = []
        facts = row["facts"]
        if isinstance(facts, str):
            try:
                facts = json.loads(facts)
            except Exception:
                facts = []
        return cls(
            entity_id=row["entity_id"],
            entity_type=row["entity_type"],
            canonical_name=row["canonical_name"],
            aliases=aliases,
            facts=facts,
            first_seen_turn=row["first_seen"],
            last_seen_turn=row["last_seen"],
            external_id=row["external_id"],
            status=row["status"] if "status" in row.keys() else "active",
            importance=row["importance"] if "importance" in row.keys() else 0,
        )


@dataclass
class ResolvableElement:
    """Generic input to resolve_or_create for Collectors that can supply
    more than a fuzzy text label. `ScreenElement` (Scribe's output)
    already structurally satisfies the label/description half of this
    -- `external_id`/`entity_type` are read via getattr with a None
    default, so a plain ScreenElement with neither attribute behaves
    exactly as it did before this pass existed.

    A Collector with exact IDs (MTGA's log parser is the concrete case,
    but this is written for any future one) constructs these instead of
    ScreenElements to opt into exact resolution and/or real typing.
    """
    label: str
    description: str
    external_id: str | None = None
    entity_type: str | None = None


class EntityRegistry:
    def __init__(
        self,
        player_id: str = "default_player",
        game_id: str = "default_game",
        save_id: str = "default_save",
        db: MemoryDB | None = None,
        match_threshold: float = 0.75,
    ):
        self.player_id = player_id
        self.game_id = game_id
        self.save_id = save_id
        self.db = db
        self._entities: dict[str, Entity] = {}
        self._next_id = 1
        self.match_threshold = match_threshold
        self._external_id_index: dict[str, str] = {}  # NEW -- external_id -> entity_id
        self._lock = threading.RLock()

        if self.db:
            rows = self.db.load_entities(self.player_id, self.game_id, self.save_id)
            for row in rows:
                ent = Entity.from_row(row)
                self._entities[ent.entity_id] = ent
                if ent.external_id:
                    self._external_id_index[ent.external_id] = ent.entity_id
                if ent.entity_id.startswith("ent_"):
                    try:
                        num = int(ent.entity_id.split("_")[1])
                        if num >= self._next_id:
                            self._next_id = num + 1
                    except ValueError:
                        pass

    def _name_lookup(self) -> dict[str, str]:
        """Every known name/alias -> entity_id, lowercased."""
        with self._lock:
            lookup: dict[str, str] = {}
            for ent in self._entities.values():
                lookup[ent.canonical_name.lower()] = ent.entity_id
                for alias in ent.aliases:
                    lookup[alias.lower()] = ent.entity_id
            return lookup

    def name_lookup(self) -> dict[str, str]:
        """Public accessor for the current name/alias -> entity_id lookup, for
        consumers outside EntityRegistry (e.g. GUI-side entity highlighting)."""
        return self._name_lookup()

    def resolve_or_create(
        self, elements: list[ScreenElement | ResolvableElement], turn: int
    ) -> list[Entity]:
        """Resolve each element against entities that existed *before this
        call* only. Elements are matched against frozen snapshots of the
        name lookup and the external_id index -- never against each
        other -- so two elements in the same batch never merge into one
        entity even with identical labels/ids, for the same reason
        described below for the fuzzy path. New entities created during
        this call are staged separately and only folded into
        self._entities / the lookups once the whole batch is done.

        Per-element resolution strategy:
        - If `external_id` is present (a ResolvableElement with one set):
          skip difflib entirely, resolve by exact id lookup/creation.
        - Otherwise: the original difflib fuzzy-match strategy, unchanged.

        `entity_type`, when supplied (via either element kind), is
        recorded on creation and can refine an existing entity's type
        from "unknown" to something real on a later sighting.
        """
        # Phase 1: Read snapshot (under lock, minimal work)
        with self._lock:
            touched: list[Entity] = []
            lookup = self._name_lookup()  # frozen snapshot of pre-call state
            ext_lookup = dict(self._external_id_index)  # frozen snapshot
            current_entities = dict(self._entities)
            current_ext_ids = dict(self._external_id_index)
            next_id = self._next_id

        # Phase 2: Process elements (NO lock - CPU work, difflib matching)
        new_this_turn: dict[str, Entity] = {}
        new_ext_ids: dict[str, str] = {}  # external_id -> entity_id, staged this batch

        for el in elements:
            name = el.label.strip()
            key = name.lower()
            external_id = getattr(el, "external_id", None)
            entity_type = getattr(el, "entity_type", None) or "unknown"

            # --- EXACT MATCH STEP (external_id present) ----------------
            if external_id is not None:
                entity_id = ext_lookup.get(external_id) or new_ext_ids.get(external_id)
                if entity_id:
                    ent = current_entities.get(entity_id) or new_this_turn[entity_id]
                    if key != ent.canonical_name.lower() and name not in ent.aliases:
                        ent.aliases.append(name)
                    ent.facts.append(el.description)
                    ent.last_seen_turn = turn
                    if entity_type != "unknown":
                        ent.entity_type = entity_type
                else:
                    ent = Entity(
                        entity_id=f"ent_{next_id:04d}",
                        entity_type=entity_type,
                        canonical_name=name,
                        facts=[el.description],
                        first_seen_turn=turn,
                        last_seen_turn=turn,
                        external_id=external_id,
                    )
                    next_id += 1
                    new_this_turn[ent.entity_id] = ent
                    new_ext_ids[external_id] = ent.entity_id
                touched.append(ent)
                continue
            # -------------------------------------------------------------

            # --- FUZZY MATCH STEP (difflib), unchanged from before ------
            # TODO(embeddings): replace this difflib call with a vector
            # search over entity embeddings once EmbeddingProvider exists.
            matches = difflib.get_close_matches(
                key, lookup.keys(), n=1, cutoff=self.match_threshold
            )
            # ----------------------------------------------------------

            if matches:
                entity_id = lookup[matches[0]]
                ent = current_entities[entity_id]
                if key != ent.canonical_name.lower() and name not in ent.aliases:
                    ent.aliases.append(name)
                ent.facts.append(el.description)
                ent.last_seen_turn = turn
                if entity_type != "unknown":
                    ent.entity_type = entity_type
            else:
                ent = Entity(
                    entity_id=f"ent_{next_id:04d}",
                    entity_type=entity_type,
                    canonical_name=name,
                    facts=[el.description],
                    first_seen_turn=turn,
                    last_seen_turn=turn,
                )
                next_id += 1
                new_this_turn[ent.entity_id] = ent
                # Deliberately NOT added to `lookup` here -- later elements in
                # this same batch must not match against entities created
                # earlier in this same batch.

            touched.append(ent)

        # Phase 3: Write results (under lock, minimal work)
        with self._lock:
            self._entities.update(new_this_turn)
            self._external_id_index.update(new_ext_ids)
            self._next_id = next_id

        # Phase 4: DB write (outside lock - can be slow, doesn't block other operations)
        if self.db:
            self.db.upsert_entities(
                self.player_id,
                self.game_id,
                self.save_id,
                [ent.to_row() for ent in touched],
            )

        return touched

    def as_context(self, entities: list[Entity], max_entities: int = 20) -> str:
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
        
        # Truncate if too many entities
        if len(lines) > max_entities:
            dropped = len(lines) - max_entities
            lines = lines[-max_entities:]
            lines.append(f"- ...and {dropped} earlier entities")
        
        return "\n".join(lines)
