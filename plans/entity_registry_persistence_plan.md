# Sub-Plan: Pass 1 Step 7 — EntityRegistry Persistence

## Overview
This sub-plan specifies the implementation details for persisting `EntityRegistry` state across Ally process restarts while a run (`save_id`) remains open. It bridges the gap between the in-memory `EntityRegistry` and the SQLite `entities` table in `memory/db.py`.

---

## 1. Idempotent Migration / Schema Update (`memory/db.py`)
- **Table Alteration**: The existing `entities` table in `MemoryDB._init_db()` lacks a `save_id` column and the unique constraint needs to cover `(player_id, game_id, save_id, entity_id)`.
- **Implementation Approach**:
  - Update the `entities` table creation DDL if creating fresh tables.
  - Add an idempotent migration block inside `_init_db()` using a try/except guard around `ALTER TABLE entities ADD COLUMN save_id TEXT NOT NULL DEFAULT 'default_save'`.
  - Update unique constraints / indexes if needed, or ensure queries filter and upsert properly by `(player_id, game_id, save_id, entity_id)`.

---

## 2. DB Query Methods (`memory/db.py`)
- Add methods to `MemoryDB`:
  - `load_entities(player_id: str, game_id: str, save_id: str) -> list[dict[str, Any]]`: Selects all entity rows matching the scope.
  - `upsert_entities(player_id: str, game_id: str, save_id: str, entities: list[dict[str, Any]]) -> None`: Inserts or replaces entity records on duplicate `(player_id, game_id, save_id, entity_id)`. Serializes lists (`aliases`, `facts`) to JSON strings via `json.dumps()`.

---

## 3. EntityRegistry Changes (`state/entity_registry.py`)
- **Constructor Arguments**: Update `EntityRegistry.__init__` to accept:
  - `player_id: str`
  - `game_id: str`
  - `save_id: str`
  - `db: MemoryDB | None = None`
- **Initialization & Loading**:
  - If `db` is provided, call `db.load_entities(player_id, game_id, save_id)` upon initialization.
  - Populate `self._entities` using `Entity.from_row(row)` (with JSON decoding of `aliases` and `facts`).
  - Rebuild `self._external_id_index` and update `self._next_id` based on loaded entity IDs (e.g. parsing `ent_XXXX`).
- **Serialization Helpers**:
  - Add `to_row() -> dict[str, Any]` on `Entity` (or helper methods) that serializes `aliases` and `facts` to JSON strings.
  - Add `Entity.from_row(row: dict[str, Any]) -> Entity` that parses JSON back into lists.
- **Persistence on Mutation**:
  - In `resolve_or_create()`, after updating `self._entities` and `self._external_id_index`, if `self.db` is present, call `self.db.upsert_entities(...)` for all touched or newly created entities.

---

## 4. Wiring in `main.py`
- Update instantiation of `EntityRegistry` in `main.py`:
  - Pass `player_id`, `game_id`, `save_id` (from `SaveTracker.resolve_save_id`), and the `MemoryDB` instance (`db`).
  - Ensure that when a run concludes and a new `save_id` is resolved, a new `EntityRegistry` instance (or re-initialized registry) is created for the new run scope.

---

## 5. Unit Test Design (`state/test_entity_registry_persistence.py`)
- Create `state/test_entity_registry_persistence.py` following project test conventions (`unittest`, fixture-based):
  - **Test 1 (Persistence & Reload)**: Create an `EntityRegistry` with a test scope `(player_id, game_id, save_id)`, resolve some elements, verify entities are saved to DB. Instantiate a fresh `EntityRegistry` with the same scope, verify all entities, aliases, facts, and external IDs are loaded correctly and resolution works post-reload.
  - **Test 2 (Scope Isolation)**: Verify that querying with a *different* `save_id` starts with an empty registry.
