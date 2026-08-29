# CLAUDE_LED_TASK: Personality Redistill Triggers, Then Perspectives + Thinking-Trace Diagnostic

> Handoff spec from Claude to ZooCode. Two distinct, sequential phases in
> one document. **Phase 2 depends on Phase 1 being complete** — its
> composite trigger extends the exact trigger object Phase 1 builds, and
> its resolution-line addendum relies on Phase 1's journal-write path
> existing. Do not start Phase 2 before Phase 1 is implemented, tested,
> and verified working.

---

## 0. Context & Goal

Two related but separable problems are being solved here.

**Phase 1** fixes a real bug: `PersonalityMemoryManager.redistill()` is
only ever invoked from `record_reflection()`, which has exactly one call
site in the entire codebase — the player-submitted chat-feedback branch
of `AllyCore.send_message()`. Gameplay itself never writes to the
personality journal or triggers a redistill. This means the personality
digest and micro tiers (and the GUI's "Companion State" panel, which
reads them) only ever update if the player explicitly submits feedback
through the chat drawer — not the intended behavior. Phase 1 wires a
real, gameplay-driven trigger path.

**Phase 2** adds a "Perspectives" system — a Disco-Elysium-style internal
tension between competing psychological framings (Apophenia, Ataraxia,
Chreod, Phronesis) that colors Ally's commentary, mediated by whichever
personality is active. It is deliberately **text-based, not numeric
telemetry-based** — Ally has no per-game structured metrics (no
`player_deaths_this_zone`-style counters; that would be genre-specific
and Ally is explicitly genre-agnostic), so perspective scoring reads the
same free-text signals Ally already has: recent narrative-buffer text and
touched-entity facts. Phase 2 also adds a standalone diagnostic tool that
streams Gemini's real thinking tokens to the terminal so Ficus can watch
the model reason live — built as an isolated script, never wired into the
production `Ally.decide()` call path, because streaming + structured
output (`response_mime_type="application/json"` + `response_schema`)
together impose a strict two-phase stream contract (all thought chunks,
then all JSON content chunks) that the production path has no reason to
take on.

---

## 1. Non-Negotiable Constraints

- Follow `CLAUDE.md`: full type hints, `Optional[...]`/`| None` explicit,
  dataclasses/Pydantic over loose dicts, no `# type: ignore` to silence
  Pylance — fix the actual type issue.
- Follow the project's autonomy principle: nothing built here may require
  a human to notice/open/approve something before the pipeline proceeds.
  The diagnostic script in Phase 2 is an optional manual tool (same
  category as `tooling/tools/inspect_coords.py`), never a required step.
- Perspective scoring must never add an LLM/API call. It is a local,
  deterministic, cheap heuristic — same category as `looks_like_real_text()`
  or SSIM matching, not a model call. This mirrors the project's existing
  "screen classification must not add an extra API call" principle,
  generalized to perspective scoring.
- Use `infrastructure.logger.log()` for all logging, never a manual
  `[Tag]` prefix.
- Test conventions: `unittest.TestCase` subclasses, not bare pytest
  functions (see `tests/README.md`).
- Config values introduced by this task should be read via
  `config.get(key, default)` inline at the call site, with the literal
  default given below, rather than assuming a specific schema/defaults
  file exists elsewhere in `storage/configs/config_manager.py` — I don't
  have visibility into that file's internal defaults structure, so don't
  guess at it; `.get()` with an inline default is self-contained and safe
  regardless of what that file currently contains.
- Documentation stays honest: update `docs/ally_decision_log.md`,
  `docs/roadmap.md`, and `docs/changelog.md` in the same pass as the
  structural changes they describe (see §5 and §9). Follow
  `.markdownlint.yaml` for any edits to `.md` files.

---

## 2. Subdivision Instructions

**Use Architect mode to split this into two top-level sub-task
sequences, one per phase, implemented and committed in order.** Within
each phase, the numbered items below (1.1, 1.2, ... / 2.1, 2.2, ...) are
a reasonable sub-task split — dependencies are noted inline where one
item requires a prior one to exist.

```
Phase 1 (bug fix, self-contained)
  1.1 -> 1.2 -> 1.3 -> 1.4 -> 1.5 -> 1.6 (tests) -> 1.7 (docs)

Phase 2 (new feature, depends on ALL of Phase 1 being complete)
  2.1 -> 2.2 -> 2.3 -> 2.4 -> 2.5 (extends Phase 1's trigger) -> 2.6
  2.7 -> 2.8 (depends on 2.7)
  2.9 (tests, depends on everything above) -> 2.10 (docs)
```

---

## 3. Phase 1 — Personality Redistill Triggers

### 3.1 Add `significant_moment` to `AllyOutput`

**File:** `brain/knowledge/schema/schema.py`

Add a new field to `AllyOutput`:

```python
class AllyOutput(BaseModel):
    analysis: str = Field(
        description="The exact direct spoken dialogue that Ally speaks out loud to the player in first/second person ('you', 'we'). MUST NOT be internal meta-thoughts, plans, or third-person summaries."
    )
    actions: list[ActionItem]
    run_boundary: Literal["none", "run_ended"] = "none"
    significant_moment: bool = Field(
        default=False,
        description="True if this turn represents a genuinely memorable beat worth Ally remembering long-term -- a boss defeat, a major setback, a big narrative reveal, a clutch play, a milestone. False for routine turns."
    )
```

### 3.2 Prompt instruction for `significant_moment`

**File:** `brain/knowledge/prompts/ally.py`

In `ALLY_PROMPT_TEMPLATE`, immediately after the existing `run_boundary`
instruction line (the one starting `"- If the current screen is an
unambiguous end-of-run screen..."`), add:

```python
    "- Set significant_moment to true if this turn represents a genuinely memorable beat worth remembering as 'us' -- a boss defeat, a major setback, a big narrative reveal, a clutch play, a milestone. Otherwise false. Most turns are false; reserve true for moments that would stand out looking back on this run.\n\n"
```

Do not modify `ALLY_CHAT_PROMPT_TEMPLATE` — `significant_moment` is a
gameplay-turn concept only; `AllyChatOutput` is unaffected and stays as-is.

### 3.3 New trigger class: `SignificantMomentTrigger`

**File:** `brain/memory/triggers.py`

Add a new `Trigger` subclass, following the exact pattern of the existing
ones in this file:

```python
class SignificantMomentTrigger(Trigger):
    def should_trigger(self, context: dict[str, Any]) -> bool:
        return bool(context.get("significant_moment", False))
```

### 3.4 Split `PersonalityMemoryManager.record_reflection` into write + redistill

**File:** `brain/memory/personality.py`

The current `record_reflection()` always does both (append to journal,
then immediately redistill). Split this into two methods so a caller can
write to the journal cheaply and let redistill run on its own, slower
cadence — this is the mechanism that lets gameplay-driven writes stay
frequent/cheap while redistill (two LLM calls: digest + micro) stays
infrequent:

```python
def add_journal_entry(self, text: str) -> None:
    """Appends to the master journal and persists it, without triggering
    a redistill. Used by gameplay-driven journal writes (see AllyCore),
    where redistill should run on its own slower cadence rather than
    synchronously on every write -- redistilling on every write would
    mean two extra LLM calls (digest + micro) every time a gameplay
    trigger fires, which is far more frequent than the original
    chat-feedback-only call site this class was built around."""
    self._master_journal.append(text)
    self.db.save_personality_entry(self.player_id, "master", text)

def record_reflection(self, reflection_text: str) -> None:
    """Original behavior, unchanged: append + immediately redistill.
    Kept as the entry point for the chat-feedback call site specifically
    -- feedback is rare and player-paced, so an immediate synchronous
    redistill there is affordable and gives the player instant
    confirmation their feedback took effect."""
    self.add_journal_entry(reflection_text)
    self.redistill()
```

Do not change `redistill()` itself, and do not change the existing
`send_message()` chat-feedback call site in `brain/reasoning/core.py`
(`self.memory_manager.personality.record_reflection(f"Player feedback: {text}")`)
— it should keep calling `record_reflection()` exactly as it does today.

### 3.5 Expose the new methods through `MemorySystem`

**File:** `brain/memory/manager.py`

Add two lock-guarded wrapper methods to `MemorySystem`, following the
exact convention already used by `record_turn`/`get_personality_context`/etc.:

```python
def add_personality_journal_entry(self, text: str) -> None:
    with self.lock:
        self.personality.add_journal_entry(text)

def redistill_personality(self) -> None:
    with self.lock:
        self.personality.redistill()
```

### 3.6 Wire the gameplay-driven trigger into `AllyCore`

**File:** `brain/reasoning/core.py`

**In `AllyCore.__init__`**, after the existing hook/telemetry setup,
add:

```python
from brain.memory.triggers import CompositeTrigger, TurnCountTrigger, SalienceEventTrigger, SignificantMomentTrigger
```

(Extend the existing `from brain.memory.triggers import resolve_run_ended`
import line rather than adding a second import line for the same module.)

```python
self.personality_flush_trigger = CompositeTrigger([
    TurnCountTrigger(interval=config.get("personality_journal_turn_interval", 20)),
    SalienceEventTrigger(importance_threshold=8),
    SignificantMomentTrigger(),
])
self.personality_redistill_journal_interval = config.get("personality_redistill_journal_interval", 3)
self._personality_journal_writes_since_redistill: int = 0
```

**Note for whoever implements this:** the `SalienceEventTrigger` member
above is currently dormant in practice, in both the new personality
trigger and the pre-existing narrative one — nothing computes a
meaningful `importance` value most turns (see §3.7's bonus fix, which
partially addresses this for `significant_moment` specifically, but a
general per-turn salience score is still unbuilt — that's the roadmap's
"Salience Scorer" / Amygdala-analogy item, explicitly out of scope for
this task). Leave it in the composite trigger for future-readiness and
consistency with the narrative-side trigger shape; do not attempt to
build a general salience scorer here.

**In `run_turn()`**, inside the existing `if not skip_ally:` branch,
after `ally_output = self.ally.decide(...)` has been computed and
*inside* the `with self.state_lock:` block that already calls
`self.memory_manager.record_turn(...)` — add the journal-write/redistill
check right after that `record_turn` call:

```python
if self.memory_manager is not None and skip_scribe_reason != "off_game":
    self.memory_manager.record_turn(
        self.sandbox.turn,
        ally_output.analysis if not skip_ally else f"skip_ally: {reason_label}",
        importance=8 if (not skip_ally and ally_output.significant_moment) else 0,
    )

    if not skip_ally:
        personality_trigger_context: dict[str, Any] = {
            "turn": self.sandbox.turn,
            "importance": 8 if ally_output.significant_moment else 0,
            "significant_moment": ally_output.significant_moment,
        }
        if self.personality_flush_trigger.should_trigger(personality_trigger_context):
            self.memory_manager.add_personality_journal_entry(ally_output.analysis)
            self._personality_journal_writes_since_redistill += 1
            if self._personality_journal_writes_since_redistill >= self.personality_redistill_journal_interval:
                self.memory_manager.redistill_personality()
                self._personality_journal_writes_since_redistill = 0
```

Read the existing surrounding code in `run_turn()` carefully before
editing — the `record_turn(...)` call already exists at this location
with a two-argument call; this changes it to pass `importance=` as a
third argument (a **small bonus fix**, called out explicitly: this also
activates the narrative side's existing-but-currently-dormant
`SalienceEventTrigger` for genuinely significant turns, at zero extra
cost, since `significant_moment` is already being computed for the
personality trigger anyway) and adds the new block below it. Do not
otherwise restructure this section of `run_turn()`.

**Also in `run_turn()`**, inside the existing `if run_ended:` block
(where `self.memory_manager.close_run()` is currently called), force a
final redistill first if there are unredistilled pending writes, so a
run never closes with fresh journal entries that never made it into the
digest:

```python
if run_ended:
    log("\n--- Run ended (boundary resolved) ---")
    if self.memory_manager is not None:
        if self._personality_journal_writes_since_redistill > 0:
            self.memory_manager.redistill_personality()
            self._personality_journal_writes_since_redistill = 0
        self.memory_manager.close_run()
    self.on_chat_message.emit("coach", "Run ended! Closing session and saving cross-session memories.")
```

### 3.7 Config keys introduced (Phase 1)

Both read via `.get(key, default)` inline at the `AllyCore.__init__`
call site added in §3.6 — no other file needs editing for these:

| Key | Default | Meaning |
| --- | --- | --- |
| `personality_journal_turn_interval` | `20` | Turn-count trigger interval for gameplay-driven personality journal writes. |
| `personality_redistill_journal_interval` | `3` | Number of journal writes accumulated before a redistill (digest + micro regeneration) actually runs. |

### 3.8 Tests (Phase 1)

**File:** `tests/test_triggers.py` (extend the existing file — it already
has `TestTriggers` and `TestNarrativeManagerTriggers` classes; add a new
`TestSignificantMomentTrigger` class following the same style) — cover:

- `SignificantMomentTrigger.should_trigger` returns `True` only when
  `context["significant_moment"]` is `True`; returns `False` when the
  key is absent or `False`.

**New file:** `tests/test_personality_journal_split.py` — cover, using
the same mocking approach `tests/test_ally.py` already uses for
`GeminiProvider`-dependent classes (mock `provider.generate_structured`
so no real API call happens):

- `PersonalityMemoryManager.add_journal_entry(text)` appends to
  `_master_journal`, persists via `db.save_personality_entry`, and does
  **not** call `provider.generate_structured` (i.e. no redistill
  triggered).
- `PersonalityMemoryManager.record_reflection(text)` still does both —
  appends **and** triggers redistill (`provider.generate_structured`
  called, digest/micro updated) — confirming the chat-feedback call site
  keeps its exact original behavior.

**File:** `tests/test_ally_core.py` (extend) — add coverage, following
the existing mocking pattern already used in this file for `AllyCore`
construction and `run_turn`:

- A turn where `ally_output.significant_moment=True` (mock `Ally.decide`
  to return this) results in `memory_manager.add_personality_journal_entry`
  being called (mock `MemorySystem`/spy on the call) even though no chat
  feedback was submitted.
- After `personality_redistill_journal_interval` gameplay-driven journal
  writes accumulate, `memory_manager.redistill_personality` is called and
  the internal counter resets to 0.
- `run_turn` returning `run_ended=True` with a nonzero pending-write
  counter triggers a final `redistill_personality()` call before
  `close_run()`.

### 3.9 Docs (Phase 1)

- **`docs/ally_decision_log.md`**: append a new dated section (do not
  rewrite existing history) explaining the bug (`redistill()` only ever
  reachable via the single chat-feedback call site), the fix (gameplay
  now writes to the journal via a composite trigger — turn count,
  salience, and the new `significant_moment` signal — with journal-write
  frequency decoupled from redistill frequency), and the bonus fix
  (wiring `significant_moment` into narrative's `record_turn(importance=...)`
  call, activating its previously-dormant `SalienceEventTrigger` for
  genuinely significant turns).
- **`docs/changelog.md`**: add a dated entry (implementation-pass style,
  matching the existing entries' tone — no design rationale, just what
  changed) noting the personality digest/strategic-memory update bug fix.

---

## 4. Phase 2 — Perspectives Engine + Streaming Thinking-Trace Diagnostic

**Do not begin this phase until Phase 1 is fully implemented, tested,
and confirmed working.** Item 2.5 below directly extends the composite
trigger object Phase 1 built in §3.6; item 2.6 relies on Phase 1's
journal-write path already being reachable from gameplay.

### 4.1 `PERSPECTIVES` definitions

**New file:** `brain/reasoning/perspectives.py`

Mirror the exact structure/style of `brain/reasoning/personalities.py`
(a plain module-level dict, no class). Use the definitions already
vetted in the design conversation with Ficus — do not invent new
wording or rename the four perspectives (the naming itself — rejecting
"Paradigms," "Modalities," "Heuristics" in favor of "Perspectives" —
was a deliberate, already-settled decision):

```python
# Competing internal psychological framings, in the spirit of Disco
# Elysium's Thought Cabinet. Distinct from PERSONALITIES: a personality
# is the stable voice Ally speaks in; a perspective is an ephemeral
# internal pressure that rises and falls turn to turn, which the active
# personality then mediates. See PerspectiveEngine (perspective_engine.py)
# for how these get scored, and ally_decision_log.md for why scoring is
# text-based rather than numeric-telemetry-based.
PERSPECTIVES = {
    "Apophenia": {
        "definition": "Finding malicious patterns or intentional developer sabotage in completely random, unrelated game events.",
        "internal_urge": "To make the player paranoid about the game's hidden biases or unfair design, even where none exists.",
    },
    "Ataraxia": {
        "definition": "A state of serene, detached calmness and complete emotional indifference in the face of disaster or victory alike.",
        "internal_urge": "To wrap the player in a calm, existential blanket of cold comfort regarding setbacks and losses.",
    },
    "Chreod": {
        "definition": "A deeply grooved, hypnotic, habitual pathway of mindless, comfort-seeking gameplay loop behavior.",
        "internal_urge": "To encourage continuing to grind, gather, or sort while ignoring the larger goal at hand.",
    },
    "Phronesis": {
        "definition": "Pragmatic, dry, hyper-realistic wisdom focused exclusively on mechanics, efficiency, and resource optimization.",
        "internal_urge": "To analyze performance errors bluntly and push toward the tactically optimal choice.",
    },
}
```

### 4.2 Perspective scoring keywords (config-driven, not hardcoded)

**New file:** `storage/configs/template/perspective_keywords.json`

Keyword lists are tuning parameters, not architecture — keep them
config-driven (same reasoning as `clip_seed_categories.json`) so Ficus
can iterate on them without a code change. `Phronesis` intentionally has
an empty list: it's the baseline default framing (mirrors the original
design's `scores = {"PHRONESIS": 1.0, ...}` starting state), not
triggered by specific keywords.

```json
{
    "Apophenia": ["almost", "so close", "again", "unlucky", "one more try", "barely"],
    "Ataraxia": ["died", "defeated", "game over", "wiped", "failed", "lost the run"],
    "Chreod": ["grinding", "farming", "sorting", "organizing", "same spot", "backtrack"],
    "Phronesis": []
}
```

Flag this explicitly in a code comment as a **first-pass heuristic**,
deliberately simple (substring/keyword counting, not semantic matching),
in the same spirit as `vision/ocr.py`'s `looks_like_real_text()` --
expected to need tuning against real playtesting, not a finished
algorithm.

### 4.3 `PerspectiveEngine`

**New file:** `brain/reasoning/perspective_engine.py`

```python
"""Scores which of the four PERSPECTIVES is dominant right now, purely
from text Ally already has access to (recent narrative-buffer turns,
touched-entity facts) -- deliberately NOT from numeric game telemetry,
since Ally has no such thing for any game and adding one would be
genre-specific. This is a local, deterministic, zero-API-call heuristic
-- consistent with the project's "screen classification must not add an
extra API call" principle, generalized here to perspective scoring.

Keyword lists live in storage/configs/template/perspective_keywords.json
(config-driven, not hardcoded) so they can be tuned without a code
change -- flagged as a first-pass heuristic, expected to need revisiting
against real playtesting, same category as looks_like_real_text()'s
alnum-ratio heuristic.
"""

import json
import os
from dataclasses import dataclass

from brain.reasoning.perspectives import PERSPECTIVES
from infrastructure.logger import log

KEYWORDS_FILE = "storage/configs/template/perspective_keywords.json"
BASELINE_PERSPECTIVE = "Phronesis"


@dataclass
class PerspectiveScore:
    primary: str
    primary_score: float
    secondary: str
    secondary_score: float

    @property
    def conflict_margin(self) -> float:
        """How close the top two scores are. Small margin = a loud,
        genuinely-tense internal conflict; large margin = one framing
        clearly dominates."""
        return self.primary_score - self.secondary_score


class PerspectiveEngine:
    def __init__(self, keywords_path: str = KEYWORDS_FILE):
        self._keywords: dict[str, list[str]] = self._load_keywords(keywords_path)

    def _load_keywords(self, path: str) -> dict[str, list[str]]:
        if not os.path.exists(path):
            log("No perspective keywords file at {path} -- every perspective will score 0 (Phronesis baseline always wins).", path=path)
            return {name: [] for name in PERSPECTIVES}
        with open(path, "r") as f:
            data = json.load(f)
        return {name: data.get(name, []) for name in PERSPECTIVES}

    def score(self, recent_turns: list[str], entity_facts: list[str]) -> PerspectiveScore:
        """recent_turns: plain narrative-buffer summary strings (see
        NarrativeMemoryManager.get_recent_turn_texts). entity_facts:
        plain fact strings from this turn's touched entities. Both are
        joined and lowercased once; keyword matching is a simple
        substring count, not NLP."""
        haystack = " ".join(recent_turns + entity_facts).lower()

        scores: dict[str, float] = {name: 0.0 for name in PERSPECTIVES}
        scores[BASELINE_PERSPECTIVE] = 1.0  # baseline default, matches original design's starting state

        for name, keywords in self._keywords.items():
            for kw in keywords:
                scores[name] += haystack.count(kw.lower())

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        primary_name, primary_score = ranked[0]
        secondary_name, secondary_score = ranked[1] if len(ranked) > 1 else ranked[0]

        return PerspectiveScore(
            primary=primary_name, primary_score=primary_score,
            secondary=secondary_name, secondary_score=secondary_score,
        )

    def as_context(self, score: PerspectiveScore) -> str:
        primary_def = PERSPECTIVES[score.primary]["definition"]
        if score.primary == score.secondary:
            return f"Dominant internal framing right now: {score.primary} -- {primary_def}"
        secondary_def = PERSPECTIVES[score.secondary]["definition"]
        return (
            f"Two internal framings are in tension right now:\n"
            f"- Primary ({score.primary}): {primary_def}\n"
            f"- Secondary ({score.secondary}): {secondary_def}\n"
            "Let your established personality decide how much weight each gets -- "
            "you don't need to resolve this explicitly out loud, just let it color your reaction."
        )
```

### 4.4 Accessor for recent narrative-turn text

**File:** `brain/memory/narrative.py`

Add a public method to `NarrativeMemoryManager`:

```python
def get_recent_turn_texts(self, n: int = 5) -> list[str]:
    """Plain summary strings from the short-term buffer, most recent
    last -- for consumers that need raw text rather than the formatted
    build_context() blob (e.g. PerspectiveEngine)."""
    return [entry.summary for entry in list(self._short_term)[-n:]]
```

**File:** `brain/memory/manager.py`

Add the matching lock-guarded wrapper to `MemorySystem`:

```python
def get_recent_turn_texts(self, n: int = 5) -> list[str]:
    with self.lock:
        return self.narrative.get_recent_turn_texts(n)
```

### 4.5 Wire perspectives into the production `Ally.decide()` call

**File:** `brain/reasoning/ally_agent.py`

Add a new parameter to `Ally.decide()` with a safe default (so any other
call site that doesn't pass it still works):

```python
def decide(
    self,
    elements_context: str,
    entities_context: str,
    genre_context: str = "unknown (not yet determined)",
    memory_context: str = "(no memory yet -- this is the first turn)",
    personality: str | None = None,
    perspective_context: str = "(no strong perspective signal this turn)",
) -> AllyOutput:
    prompt = ALLY_PROMPT_TEMPLATE.format(
        personality=personality if personality else self.base_personality,
        genre=genre_context,
        memory=memory_context,
        elements=elements_context,
        entities=entities_context,
        perspectives=perspective_context,
    )
    ...
```

**File:** `brain/knowledge/prompts/ally.py`

In `ALLY_PROMPT_TEMPLATE`, add a `{perspectives}` slot. Insert it
immediately after the existing genre line (`"Best guess at genre so far:
{genre}\n\n"`):

```python
    "Internal perspective tension:\n{perspectives}\n\n"
```

**File:** `brain/reasoning/core.py`

In `AllyCore.__init__`, instantiate the engine:

```python
from brain.reasoning.perspective_engine import PerspectiveEngine
...
self.perspective_engine = PerspectiveEngine()
```

In `run_turn()`, inside the `if not skip_ally:` branch, compute the
score and context **before** the `ally_output = self.ally.decide(...)`
call (it needs `touched_entities`, which is already computed just above
that call in the existing code), and pass it through:

```python
recent_turns = self.memory_manager.get_recent_turn_texts(n=5) if self.memory_manager else []
entity_facts = [fact for ent in touched_entities for fact in ent.facts[-3:]]
perspective_score = self.perspective_engine.score(recent_turns, entity_facts)
perspective_context = self.perspective_engine.as_context(perspective_score)

ally_output = self.ally.decide(
    elements_context=elements_context,
    entities_context=entities_context,
    genre_context=genre_context,
    memory_context=memory_context,
    personality=personality_context,
    perspective_context=perspective_context,
)
```

Store `perspective_score` in a local variable accessible later in the
same `run_turn()` call — it's needed again in §4.6 below, for the
composite trigger context.

### 4.6 `PerspectiveConflictTrigger` — extends Phase 1's composite trigger

**File:** `brain/memory/triggers.py`

Add one more trigger class:

```python
class PerspectiveConflictTrigger(Trigger):
    def __init__(self, margin_threshold: float = 2.0):
        self.margin_threshold = margin_threshold

    def should_trigger(self, context: dict[str, Any]) -> bool:
        margin = context.get("perspective_conflict_margin")
        if margin is None:
            return False
        return margin <= self.margin_threshold
```

**File:** `brain/reasoning/core.py`

**Modify** (do not duplicate) the `self.personality_flush_trigger =
CompositeTrigger([...])` construction added in Phase 1 §3.6 — add
`PerspectiveConflictTrigger` as a fourth member:

```python
self.personality_flush_trigger = CompositeTrigger([
    TurnCountTrigger(interval=config.get("personality_journal_turn_interval", 20)),
    SalienceEventTrigger(importance_threshold=8),
    SignificantMomentTrigger(),
    PerspectiveConflictTrigger(margin_threshold=config.get("perspective_conflict_margin_threshold", 2.0)),
])
```

**Modify** the `personality_trigger_context` dict built in `run_turn()`
(Phase 1 §3.6) to include the margin from this turn's already-computed
`perspective_score` (see §4.5):

```python
personality_trigger_context: dict[str, Any] = {
    "turn": self.sandbox.turn,
    "importance": 8 if ally_output.significant_moment else 0,
    "significant_moment": ally_output.significant_moment,
    "perspective_conflict_margin": perspective_score.conflict_margin,
}
```

### 4.7 Personality digest addendum: let resolution style emerge, don't force it

**File:** `brain/knowledge/prompts/personality.py`

Per explicit decision: do **not** hardcode a "how I resolve perspective
conflict" line into any `PERSONALITIES` entry, and do not force every
personality to have one. Ally is meant to develop this over time through
the redistillation pipeline (Phase 1's mechanism), and some personalities
(e.g. `Algernon`, `Xaloc`) already imply a resolution style unambiguously
enough from their existing description that nothing further is needed —
this should emerge from what the journal actually shows, not be
predetermined.

Append one sentence to `PERSONALITY_DIGEST_PROMPT`:

```python
PERSONALITY_DIGEST_PROMPT = (
    "Based on the following master reflection journal of our companion Ally, "
    "synthesize a comprehensive personality digest (200-400 words) capturing tone, "
    "quirks, and player relationship dynamics. If the journal reveals a pattern in "
    "how this companion tends to resolve tension between conflicting internal "
    "impulses, capture that pattern briefly as part of the digest -- but only if "
    "the journal actually shows it; don't invent one that isn't there:\n\n"
    "{journal_text}"
)
```

Do not modify `PERSONALITY_MICRO_PROMPT`.

### 4.8 `GeminiProvider.generate_structured_stream()`

**File:** `infrastructure/llm/gemini_provider.py`

**Before implementing this method**, verify the exact streaming method
name and `ThinkingConfig`/`include_thoughts` parameter surface against
the *installed* `google-genai` package version in this environment (e.g.
inspect the installed package's source or use `help()`/`dir()` on
`client.models` and `types.ThinkingConfig`) — the names below
(`generate_content_stream`, `include_thoughts`) are the best-known match
for the current SDK generation based on `generate_structured()`'s
existing use of `self.client.models.generate_content(...)`, but must be
confirmed against what's actually installed rather than assumed. If the
installed SDK uses different names, use those instead and note the
discrepancy in the code review notes handoff (see §10).

Add a new method, **not** a flag on `generate_structured()` — the
calling shape is genuinely different (the caller needs to iterate chunks
for live printing, not just receive a return value):

```python
def generate_structured_stream(
    self,
    model: str,
    contents: list,
    schema: type[T],
    thinking_level: str | types.ThinkingLevel | None = None,
    on_thought_chunk: Callable[[str], None] | None = None,
) -> T:
    """Streaming counterpart to generate_structured(). Requests
    include_thoughts=True alongside the same response_mime_type/
    response_schema structured-output config used everywhere else.

    Per Gemini's two-phase stream contract when include_thoughts and a
    strict response_schema are both set: the model emits ALL thought
    chunks first (plain text, part.thought=True), then ALL JSON content
    chunks second (part.text, part.thought falsy). Partial JSON is not
    valid JSON until the stream completes -- this method never hands a
    partial chunk to json.loads() or to the caller. If on_thought_chunk
    is given, it's called once per thought-chunk's text as it arrives
    (e.g. to print it live to the terminal); JSON content chunks are
    buffered internally and the full buffer is parsed into `schema`
    only once the stream ends, exactly like generate_structured()'s
    non-streaming parse step.

    Not wrapped in @retry_with_gemini_backoff -- retrying a partially-
    consumed stream cleanly is meaningfully more complex than retrying a
    single non-streaming call, and this method is diagnostic-tool-only
    today (see tooling/tools/perspective_thinking_diagnostic.py), not on
    the production Ally.decide() path. Revisit if that changes.
    """
    thinking_config = None
    if thinking_level is not None:
        lvl = self._map_thinking_level(thinking_level)
        thinking_config = types.ThinkingConfig(thinking_level=lvl, include_thoughts=True)

    json_buffer = ""
    stream = self.client.models.generate_content_stream(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            thinking_config=thinking_config,
        ),
    )
    for chunk in stream:
        if not chunk.candidates:
            continue
        for part in chunk.candidates[0].content.parts:
            if getattr(part, "thought", False):
                if part.text and on_thought_chunk is not None:
                    on_thought_chunk(part.text)
            elif part.text:
                json_buffer += part.text

    if not json_buffer:
        raise ValueError("Streaming response produced no JSON content")
    return schema.model_validate_json(json_buffer)
```

### 4.9 Standalone diagnostic script

**New file:** `tooling/tools/perspective_thinking_diagnostic.py`

Purpose: let Ficus watch Ally's real internal reasoning stream live in
the terminal, using a genuine turn's worth of context (not synthetic
fixture text), while staying completely isolated from the production
`run_turn()`/`decide()` path. Follow the module-docstring and CLI-arg
conventions already used by `tooling/tools/inspect_coords.py` /
`tooling/tools/init_config.py`.

Behavior:

1. Accepts an image path as its one required CLI argument (same
   single-image mode `main.py` already supports).
2. Runs one real pass through `Scribe.extract()`, `StateSandbox.update()`,
   and `EntityRegistry.resolve_or_create()` against that image — reusing
   `brain.perception.scribe.Scribe`, `brain.state.sandbox.StateSandbox`,
   and `brain.state.entity_registry.EntityRegistry` directly (construct
   fresh, throwaway instances — this script must never touch a real
   player's persisted `MemoryDB`/entity registry on disk; use an
   in-memory or temp-path `MemoryDB` instance, or pass `db=None` if the
   registry supports it).
3. Builds `elements_context`, `entities_context`, and a `PerspectiveEngine`
   score/context exactly as `run_turn()` does (empty `recent_turns` is
   fine here — there's no real narrative history in a single-image
   diagnostic run; pass `entity_facts` from the just-resolved entities).
4. Builds the exact same prompt `Ally.decide()` would build (reuse
   `ALLY_PROMPT_TEMPLATE.format(...)` directly, or construct an `Ally`
   instance and read its prompt-building logic — do not hand-write a
   second copy of the template).
5. Calls `GeminiProvider.generate_structured_stream(...)` with
   `on_thought_chunk=lambda text: print(text, end="", flush=True)`.
6. Once the stream completes, pretty-prints the final parsed
   `AllyOutput` (e.g. `model_dump_json(indent=2)`) below the thought
   trace, clearly separated (e.g. a `"--- FINAL OUTPUT ---"` divider).

This script must not modify `AllyCore`, `main.py`, or any production
call site — it is purely additive tooling.

### 4.10 Config keys introduced (Phase 2)

| Key | Default | Meaning |
| --- | --- | --- |
| `perspective_conflict_margin_threshold` | `2.0` | Score-margin (primary minus secondary) at or below which a perspective conflict is "loud" enough to trigger a personality journal write. |

### 4.11 Tests (Phase 2)

**New file:** `tests/test_perspective_engine.py`:

- Text containing several `Ataraxia` keywords (e.g. "we died again,
  wiped on the last boss") scores `Ataraxia` as primary, ahead of the
  `Phronesis` baseline.
- Neutral/empty input (`recent_turns=[]`, `entity_facts=[]`) returns
  `Phronesis` as both primary and secondary (baseline default, nothing
  else scored).
- `PerspectiveScore.conflict_margin` computes `primary_score -
  secondary_score` correctly.
- Missing `perspective_keywords.json` file logs a warning and does not
  raise (falls back to empty keyword lists for every perspective, so
  `Phronesis` always wins by baseline).

**New file:** `tests/test_perspective_conflict_trigger.py` (or add to
`tests/test_triggers.py` as a new test class, matching the existing
file's convention):

- `PerspectiveConflictTrigger.should_trigger` returns `True` when
  `context["perspective_conflict_margin"]` is at or below the configured
  threshold, `False` above it, and `False` when the key is absent.

**Extend** `tests/test_ally.py`: `Ally.decide()` called with an explicit
`perspective_context` string results in that string appearing in the
prompt passed to `provider.generate_structured` (mock and inspect the
call args, following this file's existing mocking pattern).

**New file:** `tests/test_gemini_provider_stream.py`: mock
`client.models.generate_content_stream` (or whatever the verified real
method name turns out to be, per §4.8's note) to yield a sequence of
fake chunks — some with `part.thought=True`, some without — and assert:

- Every thought-chunk's text is passed to `on_thought_chunk` in order,
  and in no case is a thought chunk's text appended to the JSON buffer.
- The non-thought chunks' text is concatenated and parsed into the given
  Pydantic `schema` only once, after the full mocked stream is consumed
  — never mid-stream.
- If `on_thought_chunk` is omitted (`None`), no exception is raised and
  thought chunks are simply not surfaced anywhere.

No test should make a real network call to the Gemini API.

### 4.12 Docs (Phase 2)

- **`docs/ally_decision_log.md`**: append a new dated section covering:
  the Perspectives concept and why it's separate from `PERSONALITIES`
  (stable voice vs. ephemeral internal pressure); the explicit decision
  that perspective scoring is text-based/local/zero-API-call, never
  numeric telemetry, since Ally has no per-game structured metrics and
  building one would be genre-specific; the decision to let personality
  resolution-style emerge via redistillation rather than hardcoding it
  per `PERSONALITIES` entry; and the streaming-thinking design (why
  `generate_structured_stream()` is a separate provider method, the
  two-phase stream contract, and why it's diagnostic-only rather than
  wired into `Ally.decide()`'s production path).
- **`docs/roadmap.md`**: add an open item noting that real-time
  *JSON* streaming (as opposed to thinking-trace streaming, which this
  task delivers) remains explicitly deferred — partial JSON chunks are
  not valid JSON until the stream completes, and building a permissive/
  partial JSON parser for a live-updating GUI is real, separate,
  GUI-phase work, not something this pass attempts. Also note that
  `perspective_keywords.json`'s keyword lists are an untuned first pass,
  expected to need adjustment once played against real sessions.
- **`docs/changelog.md`**: add a dated entry (implementation-pass style)
  summarizing what shipped.
- **`README.md`**: no changes required.

---

## 5. File Manifest

| Path | Phase | Action | Purpose |
| --- | --- | --- | --- |
| `brain/knowledge/schema/schema.py` | 1 | Modify | `significant_moment` field on `AllyOutput` |
| `brain/knowledge/prompts/ally.py` | 1, 2 | Modify | `significant_moment` instruction (P1); `{perspectives}` slot (P2) |
| `brain/memory/triggers.py` | 1, 2 | Modify | `SignificantMomentTrigger` (P1); `PerspectiveConflictTrigger` (P2) |
| `brain/memory/personality.py` | 1 | Modify | Split `record_reflection` into `add_journal_entry` + `record_reflection` |
| `brain/memory/manager.py` | 1, 2 | Modify | `add_personality_journal_entry`/`redistill_personality` wrappers (P1); `get_recent_turn_texts` wrapper (P2) |
| `brain/memory/narrative.py` | 2 | Modify | `get_recent_turn_texts()` |
| `brain/reasoning/core.py` | 1, 2 | Modify | Composite trigger + `run_turn`/`close_run` wiring (P1); extend trigger, `PerspectiveEngine` wiring (P2) |
| `brain/reasoning/ally_agent.py` | 2 | Modify | `perspective_context` param on `decide()` |
| `brain/reasoning/perspectives.py` | 2 | New | `PERSPECTIVES` dict |
| `brain/reasoning/perspective_engine.py` | 2 | New | `PerspectiveEngine`, `PerspectiveScore` |
| `brain/knowledge/prompts/personality.py` | 2 | Modify | Digest-prompt addendum |
| `storage/configs/template/perspective_keywords.json` | 2 | New | Tunable keyword lists |
| `infrastructure/llm/gemini_provider.py` | 2 | Modify | `generate_structured_stream()` |
| `tooling/tools/perspective_thinking_diagnostic.py` | 2 | New | Standalone streaming diagnostic |
| `tests/test_triggers.py` | 1, 2 | Modify | New trigger test classes |
| `tests/test_personality_journal_split.py` | 1 | New | Journal-write vs. redistill split |
| `tests/test_ally_core.py` | 1 | Modify | Gameplay-driven trigger integration |
| `tests/test_perspective_engine.py` | 2 | New | Scoring heuristic |
| `tests/test_perspective_conflict_trigger.py` | 2 | New | Trigger threshold behavior |
| `tests/test_ally.py` | 2 | Modify | `perspective_context` reaches the prompt |
| `tests/test_gemini_provider_stream.py` | 2 | New | Stream chunk routing/buffering |
| `docs/ally_decision_log.md` | 1, 2 | Modify | Rationale entries |
| `docs/roadmap.md` | 2 | Modify | Deferred real-time JSON streaming, untuned keyword note |
| `docs/changelog.md` | 1, 2 | Modify | Implementation-pass entries |

---

## 6. Explicit Non-Goals for This Pass

Do not build any of the following:

- Wiring `generate_structured_stream()` or perspective-thinking
  streaming into the production `Ally.decide()` call path — Phase 2's
  streaming work is diagnostic-tool-only.
- A general-purpose per-turn salience/importance scorer (the roadmap's
  "Salience Scorer" / Amygdala-analogy item). `significant_moment` is a
  narrow, Ally-judged boolean for this specific purpose, not that.
- Live-updating partial-JSON rendering for a GUI. Only thinking-trace
  streaming (plain text) is in scope.
- Any change to `PERSONALITIES` entries themselves (no hardcoded
  resolution-style lines added to any personality description).
- Retry/backoff wrapping of `generate_structured_stream()`.
- Any GUI work (Tkinter or the in-progress PySide6 rewrite). This task
  is terminal/backend only.

---

## 7. Testing Expectations

`python -m unittest discover tests` (or `tests/run_tests.py`) must pass
with zero regressions after each phase. Run the full suite after Phase 1
before starting Phase 2, and again after Phase 2. No test introduced by
this task should make a real network call to the Gemini API — mock
`GeminiProvider`/`client.models` calls throughout, consistent with how
`tests/test_ally.py` already does this.

---

## 8. Verification Commands

After each phase:

```bash
python -m unittest discover tests
```

After Phase 2, additionally do a manual smoke test of the diagnostic
script against a real image (requires a configured `GEMINI_API_KEY`):

```bash
python tooling/tools/perspective_thinking_diagnostic.py path/to/some/screenshot.png
```

Confirm thought-chunk text visibly streams to the terminal before the
final `AllyOutput` JSON is printed, and that `significant_moment` and
`run_boundary` fields are both present in that final output.

---

## 9. Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

When this comes back for review, check specifically:

- **Phase 1's `run_turn()` edit is in exactly one place.** The
  `record_turn(...)` call already exists in `core.py`; confirm it was
  *modified in place* to add `importance=...`, not duplicated, and that
  the new journal-write block was inserted immediately after it inside
  the same `with self.state_lock:` block — not moved outside the lock.
- **The composite trigger in `AllyCore.__init__` should only be
  constructed once**, at four members after Phase 2 (not a separate
  Phase-2 trigger object sitting alongside a stale Phase-1 one with only
  three). Confirm Phase 2 actually edited the Phase-1 construction site
  rather than adding a second `CompositeTrigger` instance somewhere.
- **`add_journal_entry` must never call `provider.generate_structured`.**
  This is the entire point of the split — verify via the test, and via a
  quick read, that no redistill call leaked into the cheap path.
- **Verify the streaming SDK method name/params were actually checked
  against the installed `google-genai` version**, not just assumed from
  my best guess (`generate_content_stream`, `include_thoughts`). If they
  differ, confirm the diagnostic script and provider method were updated
  consistently to match whatever the real names are.
- **Confirm `generate_structured_stream()` never calls `json.loads()` or
  `schema.model_validate_json()` on anything but the fully-accumulated
  buffer after the stream ends.** This is the one hard safety
  requirement from the two-phase stream contract — a partial-parse
  attempt anywhere in the loop is a bug even if it happens not to raise
  during testing with short mocked responses.
- **Confirm the diagnostic script doesn't touch a real player's DB.**
  It should construct throwaway/in-memory state, never open
  `data/profiles/default_player/memory.db` or similar.
- Spot check that `perspective_keywords.json`'s keys exactly match
  `PERSPECTIVES`'s keys (case-sensitive) — a mismatch would silently
  zero out that perspective's scoring rather than erroring.
- Confirm `docs/ally_decision_log.md` entries were *appended*, not
  edited into existing sections (the file's own header states this
  convention explicitly).
