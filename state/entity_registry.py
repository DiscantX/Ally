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
    external_id: str | None = None  # NEW -- set only when resolved via the exact-id path


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
    def __init__(self, match_threshold: float = 0.75):
        self._entities: dict[str, Entity] = {}
        self._next_id = 1
        self.match_threshold = match_threshold
        self._external_id_index: dict[str, str] = {}  # NEW -- external_id -> entity_id

    def _name_lookup(self) -> dict[str, str]:
        """Every known name/alias -> entity_id, lowercased."""
        lookup: dict[str, str] = {}
        for ent in self._entities.values():
            lookup[ent.canonical_name.lower()] = ent.entity_id
            for alias in ent.aliases:
                lookup[alias.lower()] = ent.entity_id
        return lookup

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
        touched: list[Entity] = []
        lookup = self._name_lookup()  # frozen snapshot of pre-call state
        ext_lookup = dict(self._external_id_index)  # frozen snapshot
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
                    ent = self._entities.get(entity_id) or new_this_turn[entity_id]
                    if key != ent.canonical_name.lower() and name not in ent.aliases:
                        ent.aliases.append(name)
                    ent.facts.append(el.description)
                    ent.last_seen_turn = turn
                    if entity_type != "unknown":
                        ent.entity_type = entity_type
                else:
                    ent = Entity(
                        entity_id=f"ent_{self._next_id:04d}",
                        entity_type=entity_type,
                        canonical_name=name,
                        facts=[el.description],
                        first_seen_turn=turn,
                        last_seen_turn=turn,
                        external_id=external_id,
                    )
                    self._next_id += 1
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
                ent = self._entities[entity_id]
                if key != ent.canonical_name.lower() and name not in ent.aliases:
                    ent.aliases.append(name)
                ent.facts.append(el.description)
                ent.last_seen_turn = turn
                if entity_type != "unknown":
                    ent.entity_type = entity_type
            else:
                ent = Entity(
                    entity_id=f"ent_{self._next_id:04d}",
                    entity_type=entity_type,
                    canonical_name=name,
                    facts=[el.description],
                    first_seen_turn=turn,
                    last_seen_turn=turn,
                )
                self._next_id += 1
                new_this_turn[ent.entity_id] = ent
                # Deliberately NOT added to `lookup` here -- later elements in
                # this same batch must not match against entities created
                # earlier in this same batch.

            touched.append(ent)

        self._entities.update(new_this_turn)
        self._external_id_index.update(new_ext_ids)
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