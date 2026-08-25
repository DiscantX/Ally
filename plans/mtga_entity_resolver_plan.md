# Plan: MTGA Entity & Enum Resolver Component

## 1. Overview & Objectives

This vertical slice implements the card entity resolver (`grpId` -> card details) and enum resolver (numeric codes -> human-readable phase/step/zone/color names) for the MTGA log parser, integrating them cleanly with Arena's local data files (`data_cards_<hash>.mtga`, `data_loc_<hash>.mtga`) while ensuring robust fallback behavior when local files are absent.

## 2. Component Design

### 2.1 Base Lookup & Asset Management (`plugins/mtga/resolver.py`)

Both entity resolution and enum resolution share a common pattern: mapping numeric keys (`grpId`, enum integer IDs) to semantic metadata/strings.

- **`BaseLookupResolver`**: Abstract or base class providing:
  - File discovery / path resolution in `MTGA_Data/Downloads/Data/`.
  - Caching mechanism (load once, cache in memory).
  - Graceful degradation / mock fallback when local `.mtga` files are missing.

### 2.2 Enum Resolver (`EnumResolver`)

- Encapsulates mappings confirmed in `docs/mtga_integration_notes.md`:
  - `Phase` (Beginning=1, Main1=2, Combat=3, Main2=4, Ending=5, etc.)
  - `Step` (Untap=1, Upkeep=2, Draw=3, DeclareAttack=5, etc.)
  - `ZoneType` (Library=1, Hand=2, Battlefield=3, Stack=4, Graveyard=5, Exile=6, etc.)
  - `Color` / `ManaColor`
- Methods: `resolve_phase(id)`, `resolve_step(id)`, `resolve_zone(id)`, `resolve_annotation(id)`.

### 2.3 Card Entity Resolver (`EntityResolver`)

- Locates and parses `data_cards_<hash>.mtga` and `data_loc_<hash>.mtga`.
- Parses JSON structures within `.mtga` files.
- Links `grpId` -> card record (name from localization file using title ID, card types, colors, etc.).
- Methods: `resolve_card(grp_id: int) -> Dict[str, Any]`.

## 3. Integration with Parser (`plugins/mtga/parser.py`)

- `MTGALogParser` will instantiate and utilize `EntityResolver` and `EnumResolver`.
- Game objects and zone contents will be automatically enriched with resolved card titles, types, and human-readable phase/step names.

## 4. Verification & Testing

- Create `plugins/mtga/test_resolver.py` to test both resolvers with mock data and real files (if present).
