# MTGA Integration — Research & Planning Notes

Preserves a full planning thread (data sourcing, tool evaluation, real log
analysis, enum verification) for adding Magic: The Gathering Arena support
to Ally. Written in the same spirit as `docs/ally_decision_log.md` — this
could be merged into that file later, or kept standalone and referenced
from it, since it's scoped narrowly to one game's Collector rather than
core pipeline architecture. Where a conclusion changes something in the
core pipeline (Collector interface, EntityRegistry, StateSandbox), that's
called out explicitly so it's easy to cross-reference against the main
decision log.

---

## 1. Why MTGA is a good test of the anticipated "structured API" seam

The decision log already reserved a seam for this:

> "A plugin (a bespoke Collector implementation) is still the right
> answer for a game that needs something structurally different from
> 'screenshot + OCR' — the concrete motivating case, per the original
> design doc, is a CommunicationMod-style internal API returning exact
> GameState JSON instead of pixels."

MTGA's `Player.log` (once "Detailed Logs / Plugin Support" is enabled in
Arena's own settings) is exactly that case: a local file emitting exact,
structured game state — not pixels, not OCR. This document works through
how to actually build that Collector.

---

## 2. Data sources evaluated

### 2.1 Live game state → `Player.log`

- Location varies by platform/install: Windows default
  `%APPDATA%\..\LocalLow\Wizards Of The Coast\MTGA\Player.log`; Steam
  installs and Mac differ. The file is **overwritten every session start**
  (a `Player-prev.log` backup exists for the immediately prior session).
- Enabling detailed logs is a **one-time manual step the player takes in
  Arena's own settings**, not a pipeline step — it's a prerequisite like
  installing the game, not a per-turn human-approval gate, so it doesn't
  conflict with the project's "no manual step required for forward
  progress" principle.
- Confirmed against a real captured log (see §4): gives full battlefield,
  hand, stack, life totals, zones, turn/phase/step — everything Ally
  needs turn-to-turn. This makes the Scribe (vision extraction) entirely
  unnecessary for this game — not just reduced, as with calibrated-HUD
  OCR, but fully bypassed. Screenshot capture becomes optional/cosmetic
  only (Ally commenting on visuals), never required for facts.

### 2.2 Card database → two real options

- **Arena's own local files**: `MTGA_Data\Downloads\Data\data_cards_<hash>.mtga`
  and `data_loc_<hash>.mtga`. Keyed by Arena's internal numeric `grpId` —
  the same ID the log's game-state messages reference directly, so **no
  ID-mapping problem**. `python-mtga` (PyPI) already wraps this, reading
  straight from a local MTGA install, zero network calls.
- **Scryfall bulk data** (gzipped JSONL, daily export): richer — full
  oracle text, rulings, every printing — but keyed by Scryfall/multiverse
  IDs, not `grpId`. Needs a crosswalk; MTGJSON's `AllPrintings` includes
  Arena-ID identifiers for this purpose.
- **Decision**: local Arena files as the source of truth for gameplay
  lookups (matches the project's existing local-first bias, same
  reasoning as the `fastembed`-over-API decision for embeddings).
  Scryfall only as an optional enrichment layer if oracle text depth
  matters later for Ally's commentary.
- Each `gameObject` in the log carries a `grpId` directly, so
  `grpId → local card DB → title` is sufficient for the common case.
  There's also a `name` field in the log, but it's a **numeric
  localization ID**, not a display string — safe to ignore in favor of
  the `grpId` lookup for the main flow.

### 2.3 Third-party tools evaluated — verdict: build our own parser

**`frcaton/mtga-tracker-daemon`** — a compiled background HTTP server that
reads MTGA's **process memory** (not the log). Endpoints: `/status`,
`/cards` (owned collection), `/playerId`, `/inventory`, `/matchState`
(rank info only), `/allCardsConnectionString` + `/allCards` (SQLite
access to the card DB). **Does not expose live battlefield/hand/stack
state at all** — no endpoint for it. Its only genuine value-add
(clean SQLite card-DB access vs. hand-parsing raw `.mtga` files) is
already solved more simply by a local-file reader with one less moving
part (no background process to launch/health-check/trust). **Not used.**

**`rconroy293/mtga-log-client`** — 17Lands' official log-tailing client.
Initially miscategorized as Python in a secondary source; verified
directly against the actual repo and it's **C#** (WinForms, ClickOnce
deployment, log4net, Newtonsoft.Json), purpose-built to tail the log and
upload events to 17lands.com. No local API or library surface for another
process to consume — can't be used as a runtime dependency from Python.
**Value**: a currently-maintained reference for message shapes and
match-boundary detection logic (maintained because 17Lands has a
commercial incentive to track Arena's format drift), useful to read for
spec purposes, not to run.

**Verdict**: we parse `Player.log` ourselves, in Python. Once a real
sample was in hand (§4), this turned out far more tractable than
community writeups suggested.

---

## 3. Real log structure — confirmed from an actual boot→match→exit capture

Ficus supplied a real `Player.log` (one full session: boot, join a match,
play it out, exit — 7,560 lines / ~4.8MB). Findings below are from
directly parsing that file, not from documentation, which the community
itself flags as frequently stale (a 2026 writeup on the format noted
"about half of my assumptions turned out to be wrong" when checked
against real current logs).

### 3.1 Message framing — simpler than expected

Every GRE/client message is exactly **two physical lines**:

```
[UnityCrossThreadLogger]8/21/2026 6:03:37 PM: Match to <userId>: GreToClientEvent
{ "transactionId": "...", "requestId": 2, "timestamp": "...", "greToClientEvent": { ... } }
```

A header line naming the message type, then the **entire JSON payload on
one line**, however large — confirmed `json.loads()` parses it directly
with zero preprocessing, even for multi-thousand-character
`GameStateMessage` blobs. No multi-line buffering or bracket-matching
needed in the tailer; just "does this line start with `{`, and is the
previous line a recognizable header."

### 3.2 Full + Diff state pattern

`GameStateMessage.type` is either `GameStateType_Full` (exactly one, at
game start) or `GameStateType_Diff` (327 of them, in this sample). This
means MTGA state **cannot** be dropped into `StateSandbox` the way
Scribe's `current_elements` are (fully overwritten each turn) — it needs
an accumulator that applies diffs onto a running state, closer in shape
to how `EntityRegistry` persists across turns than to `StateSandbox.update()`.
Architectural implication for the pipeline: `StateSandbox` needs an
optional structured-payload extension (alongside the existing flat
`ConfirmedFact` list, not replacing it) for games like this where state is
inherently structured and progressively updated, not scalar and
overwritten. Flagged, not yet built.

### 3.3 Annotations carry the semantic events

`annotations` on a diff are the actual "what happened" facts:
`ZoneTransfer`, `DamageDealt`, `ModifiedLife`, `NewTurnStarted`,
`TokenCreated`, `TappedUntappedPermanent`, etc. Payload shape is a
generic typed key/value list:

```json
{ "key": "life", "type": "KeyValuePairValueType_int32", "valueInt32": [-13] }
```

— so the parser needs one small reusable "read this typed detail by key"
helper, not per-annotation-type field access.

### 3.4 Match boundaries — clean, redundant signals

Two independent signals agree, giving a robust boundary check:

- `STATE CHANGED {"old":"...","new":"Playing"}` /
  `{"old":"Playing","new":"MatchCompleted"}`
- `matchGameRoomStateChangedEvent.stateType`:
  `MatchGameRoomStateType_Playing` / `MatchGameRoomStateType_MatchCompleted`

### 3.5 Entity resolution is exact, not fuzzy, for this Collector

Every `gameObject` carries an exact `grpId` — no ambiguity to resolve the
way Scribe's text labels require. This motivated a **generalizable**
change to `EntityRegistry.resolve_or_create`: add an optional
`external_id` parameter so any Collector that can supply one (not just
MTGA) skips `difflib` fuzzy matching entirely and goes straight to exact
lookup/creation. Not yet built, but scoped as a core-pipeline change, not
an MTGA-only hack.

Also: `entity_type` — hardcoded to `"unknown"` today per the existing
decision log gap — gets a real forcing function here. MTGA's log data
comes with real types (creature, land, instant, planeswalker, player),
closing a gap already flagged as blocking future salience/importance
scoring.

### 3.6 No Superior Colliculus equivalent needed

Change detection / SSIM / screen classification / the bootstrapper are
all screen-capture concerns that don't apply. An `MTGACollector.capture()`
is naturally event-driven (blocks on new log lines) rather than
poll-plus-diff. `main.py`'s loop currently assumes a poll interval — worth
checking it degrades cleanly for a Collector that blocks until real data
exists rather than reflecting on every tick. Not yet resolved.

---

## 4. Enum reference — confirmed against `riQQ/MtgaProto`

`riQQ/MtgaProto` (`messages.proto`) is the protobuf schema **extracted
directly from Arena's own installer** (`Wizards.MDN.GreProtobuf.Unity.dll`,
via a GitHub Actions pipeline that re-extracts on each MTGA update) — the
most authoritative source available, since it's compiler-verified rather
than inferred from sample logs. Cross-checked against our real log sample
and both agree.

### 4.1 Confirmed enums (safe to hardcode in the parser)

```
enum Phase {
  None=0, Beginning=1, Main1=2, Combat=3, Main2=4, Ending=5
}

enum Step {
  None=0, Untap=1, Upkeep=2, Draw=3, BeginCombat=4, DeclareAttack=5,
  DeclareBlock=6, CombatDamage=7, EndCombat=8, End=9, Cleanup=10,
  FirstStrikeDamage=11
}

enum ManaColor {
  None=0, White=1, Blue=2, Black=3, Red=4, Green=5, Phyrexian=6,
  Generic=7, X=8, Y=9, TwoGeneric=10, AnyColor=11, Colorless=12, Snow=13
}

enum CardColor {
  Colorless=0, White=1, Blue=2, Black=3, Red=4, Green=5, Land=6, Artifact=7
}

enum ZoneType {
  None=0, Library=1, Hand=2, Battlefield=3, Stack=4, Graveyard=5,
  Exile=6, Command=7, Revealed=8, Limbo=9, Sideboard=10, Pending=11,
  PhasedOut=12, Suppressed=13
}

enum AnnotationType {
  # 118 values total — ZoneTransfer=1, LossOfGame=2, DamageDealt=3,
  # TappedUntappedPermanent=4, PhaseOrStepModified=8, ModifiedLife=10,
  # ObjectIdChanged=13, ManaPaid=34, TokenCreated=35, ResolutionStart=43,
  # ResolutionComplete=44, NewTurnStarted=48, ColorProduction=110, etc.
  # Full list in messages.proto if/when a lesser-used one is needed.
}
```

Note: our *first pass* at correlating `Phase`/`Step` ints against the
log's own human-readable `turnInfo` strings had a bug (merged phase/step
values across separate annotation objects within the same diff instead of
keeping them tied to one annotation instance) and produced a couple of
apparently-contradictory rows before the fix. Re-run correctly, it matches
the proto exactly. Worth remembering as a gotcha for anyone re-deriving
this: **don't merge fields across sibling annotations in the same diff —
tie extracted values to one annotation's own `details` list only.**

### 4.2 The open gap — and why it's structurally unresolvable from the proto alone

`AnnotationInfo.details` is declared generically in the schema:

```protobuf
message AnnotationInfo {
  uint32 id = 1;
  uint32 affectorId = 2;
  repeated uint32 affectedIds = 3;
  repeated AnnotationType type = 4;
  repeated KeyValuePairInfo details = 6;
  ...
}
```

`KeyValuePairValueType` only describes the **wire encoding** (`Int32`,
`Uint32`, `String`, `Bool`, `Float`, `Double`, ...) of a given detail
value — it carries no information about what a `"key": "type"` value
*means* for a specific annotation type. That semantic mapping lives only
in Arena's own client-side game logic, not in the wire schema, so no
proto extractor can recover it — it isn't hiding somewhere we haven't
looked yet, it's genuinely not present in the message definitions.

Confirmed **already self-describing, no decoding needed**:
`ZoneTransfer.category` (`'PlayLand'`, `'Draw'`, `'CastSpell'`,
`'Resolve'`, `'Sacrifice'`, `'Put'`, `'SBA_Damage'`), `LossOfGame.reason`
(`'SBA_LifeTotal'`), `AbilityWordActive.AbilityWordName`,
`LinkInfo.ChooseLinkType`.

Still **genuinely undecoded**, not resolvable from the proto:
`DamageDealt.type` / `DamageDealt.markDamage` (only ever saw value `1` in
this sample — nothing to contrast against yet), `ChoiceResult.Choice_Domain`
/ `Choice_Sentiment`, `AbilityWordActive.value`. These would need either
more log samples spanning different scenarios (a burn spell vs. combat
damage vs. poison, for instance) to triangulate by pattern, or can simply
be treated as opaque/unused if Ally doesn't need that granularity — the
core need is "who took how much damage," not a sub-classification of why.

---

## 5. Architectural implications for the core pipeline

Summarizing changes this exploration motivates outside of MTGA-specific
code — i.e., things that belong in `ally_decision_log.md` proper since
they generalize:

1. **New `collector_type` value** in `build_collector`'s dispatch
   (currently only `"screen_ocr"`) — e.g. `"mtga_log"` → `MTGACollector`.
   Confirms and exercises the seam the decision log already reserved for
   a CommunicationMod-style structured-API game.
2. **`EntityRegistry.resolve_or_create` gets an optional `external_id`
   parameter** — any Collector supplying an exact ID skips `difflib`
   fuzzy matching. Generalizes beyond MTGA to any future structured-API
   game.
3. **`entity_type` finally gets populated** for real, closing a gap the
   decision log already flagged as blocking salience/importance scoring.
4. **`StateSandbox` needs an optional structured-payload slot** alongside
   the existing flat `ConfirmedFacts` list — not a replacement, since
   scalar HUD-style facts are still the right shape for OCR-driven games.
   This is the first game to stress-test whether the flat-list assumption
   holds, and it doesn't, cleanly.
5. **A generic log-tailing utility** (`collectors/log_tail.py`: watch a
   file, yield new complete records) is cheap to build game-agnostically
   even though MTGA is the only log-based game today. The *parsing* of
   what a given JSON blob means stays MTGA-specific bespoke code inside
   `MTGACollector`, consistent with "plugins are a last resort, reserved
   for structurally different data paths."
6. **Turn-gating (Superior Colliculus, SSIM, bootstrapper) is simply
   unused** for this Collector type — good confirmation the pipeline
   degrades gracefully when a whole vision-side subsystem doesn't apply,
   rather than needing to be forced into every Collector.

---

## 6. Open questions / not yet resolved

- Exact enum values for `DamageDealt.type`/`markDamage` and other
  undocumented annotation-detail semantics (§4.2) — needs either more
  varied log samples or acceptance that this granularity is unneeded.
- Whether `main.py`'s poll-interval loop needs generalizing to cleanly
  support an event-driven (blocking-tail) Collector alongside the
  existing poll-based `ScreenCollector`, or whether the existing
  interface already degrades fine.
- The `StateSandbox` structured-payload extension (§5.4) — shape not yet
  designed, just identified as needed.
- Prior-knowledge mitigation reframing: the "amnesiac walkthrough"
  concern was built for narrative spoilers; MTG's actual risk is
  different (Ally defaulting to reciting known-optimal lines instead of
  being a companion). Personality/prompt question, not architecture —
  flagged so it isn't relitigated as if it were the same problem as the
  original design doc's concern.
- Whether Scryfall enrichment (oracle text/rulings) is ever actually
  needed, or local Arena card data is sufficient indefinitely.

---

## 7. Suggested next steps

1. Prototype the two-line tailer (`collectors/log_tail.py`) against the
   real sample file — this part is now fully de-risked.
2. Prototype the Full/Diff `GameStateAccumulator` and the typed-detail
   reader helper, using the confirmed enum tables in §4.1.
3. Decide the `StateSandbox` structured-payload shape (§5.4) before
   wiring `MTGACollector` fully into `main.py`.
4. Capture a second, more varied log sample (ideally one with combat
   damage from multiple sources, a spell fizzling, a mulligan, a
   concession) to chip away at the §4.2 gap and stress-test the
   accumulator against messier state transitions than a clean single
   match provides.
