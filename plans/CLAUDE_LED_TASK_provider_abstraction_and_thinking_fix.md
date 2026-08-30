# CLAUDE_LED_TASK: Provider-Agnostic LLM Base Interface + Fix Thinking-Stream Parsing

> Handoff spec from Claude to ZooCode. **Use Architect mode to split this into
> one top-level sub-task sequence per phase, implemented and committed in
> order.** Do not start a phase before the previous one is implemented and
> its tests pass. **Phase 0 is mandatory and must be run against the real,
> live SDK before any other code changes** — see §0 for why, and do not
> treat this document's claims about event shapes as ground truth until
> Phase 0 confirms them against the actually-installed `google-genai`
> version.

---

## 0. Why this task, and what Phase 0 must actually prove

Two things are happening in the same pass because they're related:

**(A) Thinking still doesn't display**, even after the soft-schema
workaround (`generate_soft_structured_stream_field` /
`generate_soft_structured_stream`). Research against Google's current
Interactions API docs (the API has moved a lot since the last verification
pass — it went GA in June 2026, well after this project's original Phase 0
checks) surfaces a specific, plausible root cause in the CURRENT code:

For a streaming `thought_summary` delta, the confirmed real shape is:

```python
event.event_type == "step.delta"
event.delta.type == "thought_summary"
event.delta.content.type == "text"
event.delta.content.text   # <-- the actual thought text lives HERE
```

`delta.content` is a **nested object** (with its own `.type`/`.text`), not
a plain string. `GeminiProvider`'s current extraction logic is:

```python
delta_content = getattr(delta, "content", None)
delta_text_attr = getattr(delta, "text", None)
delta_text = delta_content if isinstance(delta_content, str) else (delta_text_attr if isinstance(delta_text_attr, str) else "")
```

`isinstance(delta_content, str)` is `False` for a `thought_summary` delta
(it's an object, not a string) — so this falls through to `delta.text`,
which does not exist at all on a `thought_summary` delta (only `text`-type
deltas carry `.text` directly at the delta level). **The practical effect:
`delta_text` silently resolves to `""` for every single thought chunk,
every time**, while `text`-type deltas work fine because their `.text`
attribute genuinely does exist at that level. This is consistent with
exactly what's been observed: text streaming works, thinking never has.

There is also a second, smaller dead branch: the `hasattr(event, "step")`
check that tries to pull thought text directly off `event.step` doesn't
match any real event shape currently documented — `step.start` events only
announce `step.type`, they don't carry summary text inline. That branch
should be removed, not patched.

**This is a hypothesis grounded in current docs, not a confirmed fact
about your specific installed SDK version.** Google's Interactions API is
young and has already changed shape once during this project's lifetime.
**Phase 0 exists to prove or disprove this against the real, live,
installed SDK before it's treated as fixed** — the exact discipline that
was skipped or done insufficiently before and produced the original
`Turn`/`Content` validation bug. Do not skip it again.

**(B) `GeminiProvider` needs to become one concrete implementation of a
provider-agnostic base interface**, because:

- The file has grown four near-duplicated streaming methods
  (`generate_structured_stream`, `generate_structured_stream_field`,
  `generate_soft_structured_stream`, `generate_soft_structured_stream_field`)
  with copy-pasted retry loops and JSON-buffer cleanup logic. This is a
  real maintainability problem independent of the thinking bug.
- The person wants to support OpenRouter and (eventually) OpenAI-compatible
  providers, plus a fallback router and concurrent multi-provider calls for
  future A/B testing in the GUI rewrite. None of that is possible while
  every caller talks to `GeminiProvider` directly.

Fixing (A) without doing (B) would just add a fifth near-duplicate method.
This spec does them together: fix the parsing bug **as part of** the
rewrite, in the new consolidated streaming core, and prove the fix via
Phase 0 before it's relied upon.

---

## 1. Non-Negotiable Constraints

- Follow `CLAUDE.md`: full type hints, `Optional[...]`/`| None` explicit,
  dataclasses/Pydantic over loose dicts, no `# type: ignore` to silence
  Pylance — fix the actual type issue.
- Follow the project's autonomy principle: nothing here requires a human to
  approve/confirm anything mid-pipeline.
- Test conventions: `unittest.TestCase` subclasses. No test may make a real
  network call — mock at the SDK boundary (`client.interactions.create`),
  never mock `GeminiProvider`/`LLMProvider` methods themselves in provider
  tests, or the parsing bug this spec exists to catch would be invisible
  to the test suite (see §5.1's requirement on this explicitly).
- Documentation stays honest: update `docs/ally_decision_log.md`,
  `docs/roadmap.md`, and `docs/changelog.md` in the same pass (§7).
- **Preserve every existing public call site's behavior.** After this
  task, `Scribe`, `Ally`, `NarrativeMemoryManager`,
  `PersonalityMemoryManager`, and `goodies/geneology.py` must need **zero
  changes** to their own code — they currently import
  `GeminiProvider` directly from `infrastructure.llm.gemini_provider`; a
  compatibility import must keep working (§3.5), or every import site gets
  updated in this same pass if a re-export isn't clean. Pick whichever is
  less surprising and say which you picked in your completion notes.
- Do not change `Scribe.extract()`'s or `Ally`'s public method signatures
  or prompt-building logic.
- `infrastructure/llm/model_lister.py` is **out of scope** for this pass —
  do not fold it into the new base interface yet; note it as a follow-up
  in `docs/roadmap.md` instead (§7.2).

---

## 2. Phase 0 — Mandatory Live Verification of the Thinking-Stream Shape

**Do this before writing any base-class or GeminiProvider code.**

### 2.1 Confirm the installed SDK version and re-run the basics

```bash
python -c "import google.genai as g; print(getattr(g, '__version__', '(no __version__)'))"
pip show google-genai
```

If this differs from what `gemini_provider.py`'s existing comments cite
(`google-genai==2.19.0`), note the new version explicitly in your
completion notes — a version bump is itself a plausible explanation for
shape drift.

### 2.2 Write a throwaway script proving the real event shape

Do **not** reuse any part of the existing `GeminiProvider` streaming code
for this — build it directly against the raw SDK, so a bug in the existing
wrapper can't hide the real shape from you. Using the real, currently
configured Ally model (read via `get_model("ally_model", ...)`, don't
guess a string), make a **real, live, streaming** call with
`generation_config={"thinking_summaries": "auto"}` and a prompt guaranteed
to induce visible reasoning (e.g. a multi-step logic puzzle, not "what is
2+2"). For every event yielded, print:

```python
for event in stream:
    print(f"event_type={getattr(event, 'event_type', None)!r}")
    delta = getattr(event, "delta", None)
    if delta is not None:
        print(f"  delta.type={getattr(delta, 'type', None)!r}")
        content = getattr(delta, "content", None)
        print(f"  delta.content={content!r} (type={type(content)})")
        if content is not None:
            print(f"    content.type={getattr(content, 'type', None)!r}")
            print(f"    content.text={getattr(content, 'text', None)!r}")
        print(f"  delta.text={getattr(delta, 'text', None)!r}")
```

Confirm, in your completion notes, with the literal printed output:

1. Does `event.delta.content` exist and is it a non-string object for
   `thought_summary` deltas, with the actual text at `content.text`? (This
   is §0's core hypothesis — confirm or refute it explicitly.)
2. Does `event.delta.text` exist directly (not nested) for `text`-type
   deltas?
3. Is `event.event_type` (not `event.type`) the correct attribute name on
   the event object itself, distinct from `event.delta.type`?

### 2.3 Repeat with `response_format` (structured output) also set

Same call, same prompt, but now also pass `response_format={"type": "text",
"mime_type": "application/json", "schema": AllyOutput.model_json_schema()}`
(import the real `AllyOutput`). Confirm explicitly, with printed output:
**do thought_summary deltas still arrive at all when response_format is
also set, or does adding structured output suppress them entirely?** This
is the single most important open question from §0 — if thinking summaries
genuinely stop arriving once `response_format` is set, the soft-schema
workaround stays necessary and this spec's Phase 2 consolidation must keep
both a hard-schema and soft-schema streaming path. If thinking summaries
arrive fine either way once the parsing bug (§2.2 finding) is fixed, the
soft-schema path becomes dead weight and should be removed in this pass
(see §3.4).

### 2.4 Confirm the multimodal input shape is still current

The existing `_build_interactions_input()` in `gemini_provider.py` already
has a "Verified against..." comment for `TextContent`/`ImageContent`
import paths and fields. Re-run an equivalent check:

```python
from google.genai._gaos.types.interactions.textcontent import TextContent
from google.genai._gaos.types.interactions.imagecontent import ImageContent
print(TextContent.model_fields)
print(ImageContent.model_fields)
```

If the import path or fields have changed since the existing comment was
written, note the new ones — this is what the base class's Gemini
implementation will build its content-conversion against (§3.3).

### 2.5 Record findings permanently

Do not delete the throwaway script — clean it up minimally and commit it
as `debug_raw_thinking_stream_shape.py` at the repo root, alongside the
existing `debug_raw_stream.py` and `debug_raw_interactions_stream.py` (keep
both of those as-is; this is a third, narrower diagnostic specifically for
this bug). Every finding from §2.2–§2.4 gets pasted as a code comment
wherever the corresponding logic lands in the new implementation (§3),
following this project's existing "Verified against..." convention.

**If §2.3 finds that structured output genuinely suppresses thinking
summaries, stop and flag this loudly in your completion notes before
proceeding to Phase 3** — that finding changes whether the soft-schema
path is a permanent architectural necessity or removable clutter, which
changes what Phase 3 should build.

---

## 3. Phase 1 — Base Provider Interface

Create a new subpackage: `infrastructure/llm/providers/`, and a new module
`infrastructure/llm/base_provider.py`. Nothing in `base_provider.py` may
import anything from `google.genai` or any other vendor SDK — that's the
entire point of this file.

### 3.1 Provider-agnostic content types

```python
# infrastructure/llm/base_provider.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class TextContent:
    text: str

@dataclass
class ImageContent:
    """Raw image bytes + mime type. Callers (Scribe, etc.) still pass
    PIL.Image.Image objects to provider methods as they do today --
    conversion into this shape happens once, inside each generation
    method, before dispatch to the provider-specific implementation."""
    data: bytes
    mime_type: str

Content = TextContent | ImageContent
```

Every provider method that currently accepts `contents: list` (a mix of
`str` and `PIL.Image.Image`, per existing convention) keeps accepting
exactly that at the public-method level — no caller changes. Internally,
the base class provides one shared helper,
`_normalize_contents(contents: list) -> list[Content]`, that converts
`str` → `TextContent` and `PIL.Image.Image` → `ImageContent` (PNG-encoded
bytes, matching the existing behavior in `_build_interactions_input`).
This lives in the base class since the str/PIL.Image convention itself is
project-wide, not Gemini-specific. Each provider subclass then converts
this common `list[Content]` into whatever its own SDK/API wants
(`_to_provider_input(contents: list[Content]) -> Any`, abstract).

### 3.2 The abstract base class

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(
        self, model: str, contents: list, schema: type[T],
        thinking_level: str | None = None, thinking_budget: int | None = None,
    ) -> T: ...

    @abstractmethod
    def generate_structured_stream_field(
        self, model: str, contents: list, schema: type[T], stream_field: str,
        on_field_chunk: Callable[[str], None] | None = None,
        on_stream_reset: Callable[[], None] | None = None,
        thinking_level: str | None = None, thinking_budget: int | None = None,
        max_retries: int = 5,
        on_thought_chunk: Callable[[str], None] | None = None,
        on_thought_begin: Callable[[], None] | None = None,
        on_thought_finalize: Callable[[], None] | None = None,
        on_thought_reset: Callable[[], None] | None = None,
    ) -> T: ...

    @abstractmethod
    def generate_structured_stream(
        self, model: str, contents: list, schema: type[T],
        thinking_level: str | None = None, thinking_budget: int | None = None,
        on_thought_chunk: Callable[[str], None] | None = None,
    ) -> T: ...
    """Diagnostic-only counterpart, unchanged in spirit from today's
    GeminiProvider.generate_structured_stream() -- used by
    perspective_thinking_diagnostic.py."""

    @abstractmethod
    def list_available_models(self) -> list[str]: ...

    @abstractmethod
    def list_thinking_levels(self) -> list[str]:
        """Introspected from the live SDK where possible, never a
        hardcoded literal list, per the project's existing
        get_available_thinking_levels() principle -- just moved onto
        the interface so every provider implements its own version."""

    @abstractmethod
    def supports_thinking(self, model: str) -> bool: ...

    def refresh_config(self) -> None:
        """Hook for hot-swappable settings (model/thinking-level changes
        applied without a restart). NO-OP by default in this pass --
        see docs/roadmap.md's new entry (§7.2) for why real
        implementation is deferred. Exists now so the seam is in place
        and callers (a future AllyCore settings-save wiring) have
        something to call once it's implemented."""
        pass
```

Method names and parameter lists are **identical** to the ones
`GeminiProvider` already exposes today — this is deliberate, it's what
lets `Scribe`/`Ally`/etc. need zero changes (§1).

### 3.3 Shared retry/backoff as a mixin, not copy-pasted per provider

```python
class RetryableProviderMixin:
    """Generic retry-with-backoff scaffolding. Subclasses implement the
    two provider-specific hooks; the retry loop itself is shared."""

    @abstractmethod
    def _is_retryable_error(self, error: Exception) -> bool: ...

    @abstractmethod
    def _extract_retry_delay(self, error: Exception) -> float | None: ...

    def _retry_with_backoff(self, func: Callable[[], T], max_retries: int = 5) -> T:
        # shared exponential-backoff-with-jitter loop, calling the two
        # hooks above instead of hardcoding errors.ClientError/ServerError
        ...
```

`GeminiProvider` inherits both `LLMProvider` and `RetryableProviderMixin`.
This is the concrete fix for "the retry loop is duplicated four times" —
there is exactly one retry loop in the codebase after this phase.

### 3.4 One shared streaming-event core

This is the actual consolidation of `GeminiProvider`'s four near-duplicate
streaming methods. Define, in the base module or as a Gemini-specific
internal helper (your call based on how provider-agnostic the raw event
shape realistically is — Gemini's `step.delta`/`thought_summary` framing
is unlikely to transfer to OpenRouter/OpenAI as-is, so this may need to
live in `providers/gemini_provider.py` rather than `base_provider.py`;
decide and note which in your completion notes):

```python
@dataclass
class ParsedStreamEvent:
    kind: Literal["thought_chunk", "text_chunk"]
    text: str

def _iter_gemini_stream_events(raw_stream) -> Iterator[ParsedStreamEvent]:
    """The ONE place that reads event.event_type / event.delta.type /
    event.delta.content.text / event.delta.text. Every streaming method
    in GeminiProvider must route through this -- no method may read
    delta.content or delta.text directly anymore.

    <PASTE §2.2/§2.3's CONFIRMED REAL SHAPE HERE, VERBATIM, INCLUDING
    WHETHER response_format SUPPRESSES thought_summary DELTAS -- do not
    leave this as a placeholder.>
    """
    for event in raw_stream:
        ...
```

`generate_structured_stream_field()` and `generate_structured_stream()`
both consume this generator and differ only in what they do with
`text_chunk` events (one does incremental field-extraction via
`_extract_new_field_text()`, unchanged from today; one just accumulates
into a buffer for final parsing). Both handle `thought_chunk` events
identically (the existing begin/chunk/finalize lifecycle, unchanged).

**On the soft-schema methods**: per §2.3's finding —
- If structured output does **not** suppress thinking once the parsing bug
  is fixed: delete `generate_soft_structured_stream_field()` and
  `generate_soft_structured_stream()` entirely. They were a workaround for
  a bug that's actually being fixed here, and keeping dead workaround code
  around after the real fix lands is exactly the kind of file growth this
  task is also trying to undo. Update `Ally.decide_stream()`/
  `chat_stream()` to call `generate_structured_stream_field()` (the hard-
  schema path) instead of `generate_soft_structured_stream_field()`.
- If structured output **does** genuinely suppress thinking (confirmed
  live in §2.3): keep the soft-schema path, but still route it through the
  same `_iter_gemini_stream_events()` core rather than its own copy of the
  parsing logic — the duplication is the problem regardless of which
  path(s) survive.

### 3.5 Compatibility import

`infrastructure/llm/gemini_provider.py` (the old path) should either:
(a) become a thin re-export (`from infrastructure.llm.providers.gemini_provider
import GeminiProvider`), keeping every existing `from
infrastructure.llm.gemini_provider import GeminiProvider` import working
unchanged, or (b) be deleted with every import site updated in this same
pass. Pick (a) unless you find a concrete reason it's awkward — it's less
surprising and keeps this task's diff smaller. State which you picked and
why in your completion notes.

---

## 4. Phase 2 — `providers/gemini_provider.py`: the rewrite

Move `GeminiProvider` here, inheriting `LLMProvider` +
`RetryableProviderMixin`. Requirements:

- `_is_retryable_error()` checks `isinstance(error, (errors.ClientError,
  errors.ServerError))`, matching today's behavior.
- `_extract_retry_delay()` is today's existing method, moved as-is.
- `_to_provider_input(contents: list[Content]) -> list[Any]` replaces
  today's `_build_interactions_input()` — same logic, just operating on
  the common `Content` types from §3.1 instead of raw `str`/`PIL.Image`
  (the str/PIL.Image → `Content` conversion already happened in the base
  class's `_normalize_contents()`).
- `list_available_models()` — for this pass, can delegate to the existing
  `infrastructure/llm/model_lister.py` logic (out of scope to rewrite per
  §1, but fine to call from here) or return a minimal Gemini-specific
  list; your call, note which.
- `list_thinking_levels()` — move today's module-level
  `get_available_thinking_levels()` logic here as an instance method,
  keep the module-level function too as a thin wrapper (`interfaces/gui/
  settings_window.py` imports it directly — do not break that import).
- `supports_thinking(model)` — best-effort: for this pass, a simple check
  against known thinking-capable model name patterns (`"gemini-3"` /
  `"gemini-2.5"` prefix, matching the docs' stated thinking-capable model
  families) is acceptable; note this as a coarse heuristic in a comment,
  same spirit as `looks_like_real_text()`'s documented coarseness.
- The critical fix from §0/§2: **thought_summary delta text extraction
  reads `delta.content.text` (an attribute of a nested object), never
  `delta.content` cast to `str` or `delta.text`.** This must be the one
  and only place this extraction happens (§3.4's shared core).

---

## 5. Phase 3 — Stub the Router (built now, not wired in)

Create `infrastructure/llm/provider_router.py`:

```python
class ProviderRouter:
    """Not used by AllyCore/Scribe/Ally in this pass -- exists as a
    tested, working seam for the planned fallback and A/B-testing
    features. See docs/roadmap.md for wiring status."""

    def __init__(self, providers: list[LLMProvider]):
        self.providers = providers

    def call_with_fallback(self, method_name: str, *args, **kwargs) -> Any:
        """Tries providers[0], falls through to providers[1:] on any
        exception from _is_retryable_error-eligible errors exhausting
        their own retries, or any other exception. Raises the last
        provider's exception if all fail."""
        ...

    def call_concurrent(self, method_name: str, *args, **kwargs) -> dict[int, Any]:
        """Runs the same call against every provider in self.providers
        concurrently via ThreadPoolExecutor, returns {provider_index:
        result_or_exception}. This is the seam the planned GUI A/B
        testing interface will eventually call."""
        ...
```

Write real, working unit tests for both methods against two `MagicMock`
providers (not real network calls) — this needs to actually work when
wired in later, not just exist as a stub that raises `NotImplementedError`.
Do not wire `ProviderRouter` into `AllyCore`, `Scribe`, or `Ally` in this
pass.

---

## 6. Tests

- Every test currently mocking `client.interactions.create` and asserting
  on `GeminiProvider`'s behavior needs its mock's event shape updated to
  match Phase 0's confirmed real shape (nested `delta.content.text` for
  thought summaries) — this is the test-level fix that should have existed
  before the bug shipped.
- **New test, specifically for this bug**: construct a mock stream where a
  `thought_summary` event's `delta.content` is a `MagicMock` with `.type =
  "text"` and `.text = "some thought"` (i.e. genuinely nested, not a flat
  string) and assert `on_thought_chunk` is called with `"some thought"`.
  This is the test that would have caught the original bug — a test that
  only asserts `delta.content` as a plain string would not have.
- Search the repo for every test mocking `client.models.*` or
  `client.interactions.create` (`grep -rn "interactions.create" tests/`)
  and confirm each still passes with the new consolidated streaming core
  underneath.
- `ProviderRouter` tests per §5.
- `python -m unittest discover tests` — zero regressions.

---

## 7. Docs

### 7.1 `docs/ally_decision_log.md`

Append a new dated section:

- State the actual root cause found in Phase 0 (paste the real confirmed
  shape, not this document's hypothesis) and that it was a nested-object
  vs. flat-string extraction bug, not an API incompatibility.
- Record whether structured output + thinking summaries do or don't
  compose (§2.3) — this is a real, durable fact about the API worth
  keeping for future readers.
- Record the decision to introduce `LLMProvider` as a base interface, the
  provider-agnostic `Content` types, and that `GeminiProvider` is now one
  implementation among a planned set (OpenRouter next, OpenAI-compatible
  under consideration).
- Record the explicit decision **not** to adopt Interactions'
  `previous_interaction_id` stateful mode for Ally's main reasoning loop
  (ties reasoning to Gemini-specific threading; Ally's context is
  synthesized fresh from StateSandbox/EntityRegistry/MemoryManager every
  turn, not a literal replay, so there's nothing meaningful to offload) —
  and that this question is left open specifically for `send_message()`'s
  chat path as a separate, deferred design question.

### 7.2 `docs/roadmap.md`

Add open items:

- Hot-swapping provider settings (model/thinking level applied without a
  restart) — the `refresh_config()` seam now exists on `LLMProvider`
  (no-op) but isn't wired to the GUI settings-save callback yet; that's
  its own focused follow-up task once this base interface has landed.
- OpenRouter provider implementation — not built this pass.
- `infrastructure/llm/model_lister.py` folding into the new
  `list_available_models()` interface method — deferred, noted as
  out-of-scope for this pass in §1.
- If §2.3 found structured output suppresses thinking: note this as a
  known Gemini Interactions API limitation to re-check periodically, since
  this API is still evolving quickly.

### 7.3 `docs/changelog.md`

Dated entry: fixed the thinking-stream parsing bug (nested
`delta.content.text` vs. flat string), introduced `LLMProvider` base
interface + `providers/` subpackage, moved `GeminiProvider` under it,
consolidated four streaming methods into one shared event-parsing core,
removed the soft-schema workaround methods (if §2.3 permitted), added
`ProviderRouter` (unwired stub), added `debug_raw_thinking_stream_shape.py`.

---

## 8. Explicit Non-Goals for This Pass

- Implementing OpenRouter or any OpenAI-compatible provider — designed
  for, not built.
- Wiring `ProviderRouter` into `AllyCore`/`Scribe`/`Ally` — built and
  tested, not integrated.
- Real hot-swap implementation (config re-read per call, or
  `AllyCore`-driven component refresh on settings save) — the
  `refresh_config()` seam exists as a no-op only.
- Adopting `previous_interaction_id` stateful mode anywhere.
- Rewriting `infrastructure/llm/model_lister.py`.
- Any change to `Scribe`'s or `Ally`'s prompt content or decision logic.
- GUI changes of any kind (per this project's standing rule that GUI work
  happens in its own dedicated pass).

---

## 9. File Manifest

| Path | Phase | Action |
| --- | --- | --- |
| `debug_raw_thinking_stream_shape.py` | 0 | New |
| `infrastructure/llm/base_provider.py` | 1 | New |
| `infrastructure/llm/providers/__init__.py` | 1 | New |
| `infrastructure/llm/providers/gemini_provider.py` | 2 | New (moved + rewritten from `gemini_provider.py`) |
| `infrastructure/llm/gemini_provider.py` | 1 | Modify — thin re-export, or delete (§3.5, state your choice) |
| `infrastructure/llm/provider_router.py` | 3 | New |
| `interfaces/gui/settings_window.py` | 2 | Verify only — confirm `get_available_thinking_levels` import still resolves |
| `brain/reasoning/ally_agent.py` | 2 | Modify only if soft-schema methods are removed per §3.4 (swap to hard-schema call) — otherwise untouched |
| tests mocking `client.interactions.create` | 6 | Modify — remock to real confirmed shape |
| new provider/router tests | 3, 6 | New |
| `docs/ally_decision_log.md` | 7 | Modify — append |
| `docs/roadmap.md` | 7 | Modify — append |
| `docs/changelog.md` | 7 | Modify — append |

---

## 10. Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

When this comes back for review, check specifically:

- **Was §2.2/§2.3 actually run live**, and does the pasted "confirmed
  shape" comment in `_iter_gemini_stream_events()` (or wherever it landed)
  reflect real printed output — not this document's hypothesis restated as
  fact. If the comment reads like a paraphrase of this spec rather than
  actual tool output, that's the same failure mode as before; call it out.
- **Does the fix actually address the nested `delta.content.text` shape**,
  or did ZooCode patch around the symptom without fixing the extraction
  logic itself.
- **Was the §2.3 structured-output-vs-thinking question actually
  answered**, and does the soft-schema removal-or-keep decision in Phase 2
  match what was found (not just assumed from this document's guess).
- **Is there exactly one streaming-event-parsing implementation** in
  `GeminiProvider` after this pass — spot check that none of
  `generate_structured_stream`, `generate_structured_stream_field`, or a
  surviving soft-schema variant has its own inline copy of the
  `delta.type`/`delta.content` extraction logic.
- **Zero diffs in `Scribe`, `Ally` (beyond the one conditional soft→hard
  schema swap if applicable), `NarrativeMemoryManager`,
  `PersonalityMemoryManager`, `goodies/geneology.py`** — any other change
  to these files is a signal §1's scoping constraint was violated.
- **`ProviderRouter` is real and tested, not a stub that raises
  `NotImplementedError`** — per §5, both methods must actually work
  against mock providers.
- Confirm the new unit test in §6 genuinely uses a nested-object mock for
  `delta.content` (not a flat string) — a test using a flat string mock
  would not have caught the original bug and wouldn't catch a regression
  either.
- Confirm `docs/ally_decision_log.md`'s new entry states the real,
  confirmed API behavior (including the structured-output/thinking
  composition finding) rather than a generic restatement of this spec.
