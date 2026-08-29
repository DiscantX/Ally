# CLAUDE_LED_TASK: Migrate GeminiProvider to the Interactions API

> Handoff spec from Claude to ZooCode. **Use Architect mode to split this into
> one top-level sub-task sequence per phase, implemented and committed in
> order.** Do not start a phase before the previous one is implemented and
> its tests pass. **Phase 0 is the most important phase in this document —
> read the "why" below before touching any code.**

---

## 0. Why this migration, and why Phase 0 is mandatory

`GeminiProvider` currently calls `client.models.generate_content()` /
`generate_content_stream()` (the legacy `generateContent` API). Production
thought-summary streaming (`generate_structured_stream_field`'s
`on_thought_*` callbacks) was built against this API and, after two
implementation passes, still shows no thinking output anywhere. Research
into current Gemini docs and open SDK issues turned up a real, documented
failure cluster specific to `generateContent` + `response_schema` (JSON
mode) + `include_thoughts`: thought parts can arrive with no `part.thought`
flag set at all, or simply not be generated on low-complexity prompts at
low thinking levels. This is plausibly a real bug in `generateContent`
itself for this exact combination, not something fixable by more tweaking
on our end.

Google's own current guidance is to move to the **Interactions API**
(`client.interactions.create(...)`) going forward. It's a better structural
fit for this exact problem: thought summaries are a **dedicated event
type** in the stream (`step.delta` with `delta.type == "thought_summary"`),
not an inferred boolean flag riding on an ordinary text part. It also has
a direct structured-output equivalent and is the API surface Google is
steering new development toward, which is why the person running this
project wants to standardize on it now rather than patch around
`generateContent`'s behavior.

**The risk**: this API is very new (weeks old at the time of writing this
spec). Exact config key names (does `generation_config` take
`thinking_level`, or only `thinking_summaries`? does `input` accept a
multimodal list the way `contents` does, for Scribe's image+prompt calls?)
are not fully confirmed from documentation alone. **Phase 0 exists to
answer these questions against the real installed SDK and a real API call,
before any integration code is written** — exactly the discipline that
worked for the earlier `partial-json-parser` integration (see
`docs/ally_decision_log.md`) and that was explicitly skipped once before
with bad results (`debug_raw_stream.py` exists because of that prior
failure). Do not repeat that mistake here. If what you observe in Phase 0
differs from what this spec assumes in Phases 1+, **adapt the later phases
to match reality and say so explicitly in your completion notes** — do not
silently force reality to match this document.

---

## 1. Non-Negotiable Constraints

- Follow `CLAUDE.md`: full type hints, `Optional[...]`/`| None` explicit,
  dataclasses/Pydantic over loose dicts, no `# type: ignore` to silence
  Pylance — fix the actual type issue.
- Follow the project's autonomy principle: nothing here requires a human to
  approve/confirm anything mid-pipeline.
- Test conventions: `unittest.TestCase` subclasses (see `tests/README.md`).
  No test may make a real network call — mock `client.interactions.create`
  throughout.
- Documentation stays honest: update `docs/ally_decision_log.md`,
  `docs/roadmap.md`, and `docs/changelog.md` in the same pass (§7).
- **Preserve every existing public method signature on `GeminiProvider`**:
  `generate_structured()`, `generate_structured_stream()`,
  `generate_structured_stream_field()`, and their parameter lists, stay
  exactly as callers already use them. This is deliberate — it means
  `Scribe`, `Ally`, `NarrativeMemoryManager`, `PersonalityMemoryManager`,
  and `goodies/geneology.py` need **zero changes**, since they only ever
  call these three methods and never touch `self.client` directly. This
  migration is scoped to `GeminiProvider`'s internals plus its tests, not
  a repo-wide rewrite.
- Do not change `Ally.decide()`/`decide_stream()`/`chat()`/`chat_stream()`
  signatures or prompt-building logic. Do not change `Scribe.extract()`'s
  signature.
- `infrastructure/llm/model_lister.py` (`client.models.list()`) is
  **out of scope** — model listing is a different API surface than
  generation and is not part of this migration.

---

## 2. Phase 0 — Mandatory SDK Verification (do not skip, do not guess)

### 2.1 Confirm SDK version supports Interactions

Run:

```bash
python -c "import google.genai as g; print(getattr(g, '__version__', '(no __version__)'))"
pip show google-genai
```

The Interactions API needs `google-genai >= 2.0.0`. If the installed
version is older, update `requirements.txt`'s `google-genai` line to
`google-genai>=2.0.0` and run `pip install -r requirements.txt --upgrade`.
Paste the before/after version into your completion notes.

### 2.2 Write and run a throwaway introspection + live-call script

Create a **temporary** script (do not commit it — delete before finishing
this phase, or keep it only if you fold its findings into a permanent
diagnostic tool per §2.3) that does all of the following, in order, against
the real API:

```python
import inspect
from google import genai

client = genai.Client()

print("--- hasattr(client, 'interactions') ---")
print(hasattr(client, "interactions"))

print("\n--- dir(client.interactions) ---")
print(dir(client.interactions))

print("\n--- inspect.signature(client.interactions.create) ---")
print(inspect.signature(client.interactions.create))
```

Then, using whatever the real signature shows, make a **real, live call**
against the actual model this project configures for Ally (read it from
`configs/user_config.json` / `get_model("ally_model", ...)` rather than
guessing a model string) with:

1. A simple text-only prompt, `stream=True`, `generation_config` attempting
   `{"thinking_summaries": "auto"}`, and **no** `response_format` — confirm
   `step.delta` events arrive with `delta.type == "thought_summary"` and
   `delta.type == "text"`, and print every event's raw repr.
2. The same call, but now **also** passing `response_format` shaped like
   `{"type": "text", "mime_type": "application/json", "schema":
   AllyOutput.model_json_schema()}` (import the real `AllyOutput` from
   `brain.knowledge.schema.schema`) — confirm structured output and
   thinking summaries compose in the same call. Print every event's raw
   repr. **This is the single most important check in this phase** — if
   thinking and structured output don't compose in one call, say so loudly
   in your completion notes and stop before Phase 1; that would change
   this migration's shape significantly and needs a design decision, not
   a workaround improvised mid-implementation.
3. Repeat with a `thinking_level`-style key if `generation_config` accepts
   one (try `"thinking_level": "high"` inside `generation_config`, and
   separately try a nested `"thinking_config": {"thinking_level": "high"}`
   shape if the flat key errors) — determine which shape, if any, actually
   controls thinking amount for Interactions, distinct from
   `thinking_summaries` (which only controls whether summaries are
   *returned*, not how much the model *thinks*). If neither works, note
   that thinking-amount control may not yet be exposed on Interactions for
   this model and thinking will run at whatever the model's default is.
4. A **multimodal** call: `input` containing both an image (load any small
   local PNG, e.g. from `images/` if present, else generate a trivial
   in-memory PIL image) and a text prompt, non-streaming, with a simple
   response_format schema — confirm whether `input` accepts a list of
   parts the way `contents` does for `generate_content`, and if so, what
   shape (list of raw objects? list of dicts? something else?). **This
   directly affects whether `Scribe.extract()`'s call path can migrate at
   all** — Scribe passes `[image, prompt]`.
5. A deliberately-failing call (bad model name, e.g. `"not-a-real-model"`)
   — confirm what exception type is raised, and whether it's still
   `google.genai.errors.ClientError`/`ServerError` (the types
   `retry_with_gemini_backoff` currently catches) or something new.

### 2.3 Record findings permanently

Create `debug_raw_interactions_stream.py` at the repo root (sibling to the
existing `debug_raw_stream.py`, which stays as-is — do not delete or modify
it, it remains useful for comparing against the legacy API). This new
script should be a cleaned-up, permanent version of whatever you ran ad hoc
above: dumps raw events for a streaming Interactions call with thinking +
structured output against the real configured Ally model, with the same
"never mocked, always live" spirit as `debug_raw_stream.py`.

In `_extract_new_field_text`'s replacement (§3.3) and anywhere else this
spec's assumed API shape mattered, add a code comment with the **actual**
observed output — same convention as the existing
`_extract_new_field_text` docstring in `gemini_provider.py`
(`# Verified against partial_json_parser==... installed in this
environment` — do the equivalent here, e.g. `# Verified against
google-genai==<version>: client.interactions.create(...) with
generation_config={"thinking_summaries": "auto"} returns step.delta events
shaped <...>`).

**If Phase 0 finds that structured output + thinking summaries do not
compose in a single call (§2.2 item 2), or that multimodal `input` isn't
supported in a workable shape (§2.2 item 4), stop and report this instead
of proceeding to Phase 1.** Those are the two findings that would change
this spec's design, not just its implementation details.

---

## 3. Phase 1 — Rewrite `GeminiProvider` internals

Everything below assumes Phase 0 confirmed the API shapes described. Adjust
to match what you actually observed if it differs — see §0.

### 3.1 `generate_structured()`

Replace the `client.models.generate_content(...)` call with
`client.interactions.create(model=..., input=contents, response_format={
"type": "text", "mime_type": "application/json", "schema":
schema.model_json_schema()}, generation_config=<thinking config if
thinking_level given, per Phase 0's confirmed shape>)`. Final parse: same
as today —`schema.model_validate_json(...)`, sourced from whatever Phase 0
confirmed holds the full text (`interaction.output_text` per the documented
convenience property, unless Phase 0 found otherwise).

Keep the `@retry_with_gemini_backoff(max_retries=5)` decorator on this
method, adjusted per Phase 0 item 5's findings if the exception types
differ from `errors.ClientError`/`errors.ServerError`.

Keep the existing `GeminiProvider._first_gen_done` one-time timing log
behavior unchanged.

### 3.2 `generate_structured_stream()` (diagnostic thinking-trace method)

Still diagnostic-only (used by
`tooling/tools/perspective_thinking_diagnostic.py`), but migrate its
internals too — no reason to keep two different generation call
conventions in one file once this migration lands. Iterate
`client.interactions.create(..., stream=True)`'s events; route
`step.delta` events with `delta.type == "thought_summary"` to
`on_thought_chunk` (extract text per whatever `delta.content` shape Phase 0
confirmed); accumulate `delta.type == "text"` events into a buffer; parse
the buffer into `schema` once the stream ends, exactly as today.

### 3.3 `generate_structured_stream_field()` + `_extract_new_field_text()`

This is the one production callers depend on for live text (`Ally.
decide_stream()`/`chat_stream()`) **and** thinking
(`on_thought_begin/chunk/reset/finalize`). Rewrite the streaming loop to
consume `client.interactions.create(..., stream=True)` events instead of
raw chunk/part objects:

- `step.delta` with `delta.type == "thought_summary"` → same
  begin/chunk/finalize lifecycle as today (`on_thought_begin` on first such
  event since the last reset, `on_thought_chunk` per event, `on_thought_
  finalize` once a non-thought delta arrives or the stream ends).
- `step.delta` with `delta.type == "text"` → append to `json_buffer`
  exactly as legacy `part.text` did today; `_extract_new_field_text()`'s
  logic (the `partial_json_parser` diffing, including the
  `startswith(previous_value) and len(current) > len(previous)` guard)
  **does not need to change** — it operates on the same kind of growing
  JSON-text buffer regardless of which API produced it. Keep this method
  as-is other than updating its docstring's "Verified against" comment
  with real output if the exact chunk-splitting behavior changed under the
  new API (rerun the equivalent of §2.1's verification against
  `client.interactions.create` output specifically, and paste that too).
- Retry-and-reset semantics (`on_stream_reset` fires before a retry begins
  producing new chunks, mid-stream failures retry the whole call from
  scratch) are unchanged in spirit — reimplement against whatever exception
  types Phase 0 confirmed.
- Final return value: same as today, `schema.model_validate_json(full
  buffer)` — the streamed text is still a best-effort live preview,
  finalize hooks still reconcile against this validated result exactly as
  the existing `on_analysis_stream_finalize`/`on_chat_stream_finalize`
  wiring in `AllyCore` already does (that wiring in `core.py` needs **no
  changes** — it only calls `Ally.decide_stream()`/`chat_stream()`, which
  keep their exact signatures).

### 3.4 Thinking level / thinking config plumbing

Wherever `self._map_thinking_level(thinking_level)` currently converts a
string/`ThinkingLevel` into the legacy `types.ThinkingConfig`, replace with
whatever `generation_config` shape Phase 0 confirmed actually controls
thinking amount for Interactions (§2.2 item 3). If Phase 0 found no working
amount-control key, keep `generation_config={"thinking_summaries": "auto"}`
only (summaries on, amount left at model default) and note this
limitation explicitly in your completion notes and in
`docs/roadmap.md` (§7.2) rather than inventing a config key that doesn't
do anything.

### 3.5 Imports and cleanup

Remove now-unused imports (`types.ThinkingConfig`, `types.ThinkingLevel`
direct references) only if genuinely unused after the rewrite — `types`
may still be needed for other things; check before deleting the import
wholesale. `get_available_thinking_levels()` in this same file (used by
`interfaces/gui/settings_window.py`) stays as-is unless Phase 0's findings
mean thinking levels are no longer a meaningful concept for this project
going forward — if so, flag that as a follow-up design question rather
than silently changing the settings UI's behavior in this task.

---

## 4. Phase 2 — `Scribe`'s multimodal call path

Only touch this phase if Phase 0 (§2.2 item 4) confirmed multimodal
`input` works. `Scribe.extract()` itself needs no signature change — it
still calls `self.provider.generate_structured(model=..., contents=[image,
prompt], schema=ScribeOutput, thinking_level=...)`. The only change is
internal to `generate_structured()` (§3.1): confirm the `contents=[image,
prompt]` list, when passed through as `input=contents`, still produces a
correct multimodal call under the new internals. Add a small manual
verification here: run the existing single-image mode (`python main.py
images/<some_image>.png`, or any image under `images/` if present) and
confirm Scribe still extracts real screen elements, not empty/garbage
output. If Phase 0 found `input` needs a different shape for multimodal
content than a flat list, adapt `generate_structured()`'s internals to
convert `contents` into that shape — the Scribe call site itself still
should not need to change.

---

## 5. Phase 3 — Update tests

Every test that currently mocks `client.models.generate_content` or
`client.models.generate_content_stream` needs its mock target updated to
`client.interactions.create`. Search the repo for these patterns
(`grep -rn "generate_content" tests/`, `grep -rn "generate_content_stream"
tests/`) rather than assuming you know the full list — at minimum this
includes `tests/test_gemini_provider_stream_field.py` and
`tests/test_gemini_provider_stream.py`. For each:

- Reshape mock return values from the legacy chunk/part `MagicMock`
  structure to whatever Interactions event shape Phase 0 confirmed
  (`event.event_type`, `event.delta.type`, `event.delta.text` /
  `event.delta.content.text`).
- Preserve every existing test's *intent* (what scenario it's checking —
  split-across-chunks reconstruction, malformed-intermediate-buffer
  handling, retry-with-reset ordering, no-content-raises-ValueError) even
  though the mock's shape changes underneath it.
- `tests/test_ally_stream.py`, `tests/test_ally.py`, and any test that
  mocks `GeminiProvider` itself (i.e. mocks `provider.generate_structured`
  or `provider.generate_structured_stream_field` directly, not
  `client.models.*`) should need **no changes** — this is the payoff of
  preserving `GeminiProvider`'s public signatures per §1. If you find a
  test in this category that does need changes, that's a signal something
  in §1's constraint was violated — fix the violation, don't patch the
  test to match.
- `tests/test_ally_core.py`'s streaming-hook tests (added by the earlier
  streaming task) mock at the `Ally`/`AllyCore` level and should also need
  no changes.

Run `python -m unittest discover tests` after this phase and confirm zero
regressions before proceeding.

---

## 6. Phase 4 — Fix the Tkinter GUI thinking-hook gap (bundled bug fix)

Independent of the API migration, but discovered during this review and
worth fixing in the same pass since it touches the same area: **`interfaces/
gui/tkinter_app.py` never connects `core.on_thinking_stream_begin/chunk/
reset/finalize` to anything** — only `main.py`'s headless branch wires
them. The GUI has no thinking-display surface at all today, so add one.

### 6.1 A minimal thinking display in the GUI

Reuse the existing "Recent Turns"-style rendering pattern already in
`interfaces/gui/overlay_api.py`'s `update_medium_term_summary()` (a
distinctly-tagged block appended to the feedback text history) as the
model. Add to `OverlayApiMixin`:

- `begin_streaming_thinking()` — inserts a `"── {timestamp} [THINKING]
  ──\n"` header (new text tag, e.g. `'thinking'`, dim/italic-style color —
  add `thinking_color` to `OverlayConfig` in `interfaces/gui/models.py`,
  a muted gray distinct from `dim_color`) into `feedback_text`, records
  the insert point the same way `_streaming_feedback_body_start` does.
- `append_streaming_thinking_chunk(chunk_text: str)` — same pattern as
  `append_streaming_feedback_chunk`.
- `reset_streaming_thinking()` — same pattern as `reset_streaming_
  feedback`.
- `finalize_streaming_thinking()` — no corrective reprint needed here
  (unlike the analysis/chat finalize methods) since thinking text is
  never validated against a schema field; just clear tracking state.

Wire these in `AllyOverlay.__init__` alongside the existing
`on_analysis_stream_*`/`on_chat_stream_*` connections:

```python
core.on_thinking_stream_begin.connect(self.begin_streaming_thinking)
core.on_thinking_stream_chunk.connect(self.append_streaming_thinking_chunk)
core.on_thinking_stream_reset.connect(self.reset_streaming_thinking)
core.on_thinking_stream_finalize.connect(self.finalize_streaming_thinking)
```

Initialize `self._streaming_thinking_body_start: Optional[str] = None`
alongside the existing `_streaming_feedback_body_start`/`_streaming_chat_
body_start` attributes.

---

## 7. Docs

### 7.1 `docs/ally_decision_log.md`

Append a new dated section (do not rewrite existing history):

- State plainly: this supersedes `GeminiProvider`'s use of `generateContent`
  as the primary call surface. Cite the concrete reason — production
  thought-summary streaming never worked after two implementation passes
  against `generateContent` + `response_schema`, and research surfaced a
  documented failure cluster in that exact combination (thought parts
  arriving without the `part.thought` flag set, or not being generated at
  all at low thinking levels on low-complexity prompts). Interactions'
  dedicated `thought_summary` event type sidesteps the flag-sniffing
  fragility entirely.
- Record what Phase 0 actually found (the real API shapes) — this is the
  authoritative reference for future readers, since the docs for this API
  are still young and may drift.
- Note the deliberate scoping decision: `GeminiProvider`'s public method
  signatures were preserved so this migration touched exactly one file's
  internals plus its tests, not every caller.

### 7.2 `docs/roadmap.md`

Add an open item if Phase 0 found no working thinking-amount-control key
for Interactions (§3.4) — note that thinking summaries work but the
existing `thinking_level` settings UI control may currently be a no-op for
generation calls until Interactions exposes an equivalent, and that this
needs revisiting once Google documents one (or once further testing finds
the right key).

### 7.3 `docs/changelog.md`

Add a dated entry: migrated `GeminiProvider` from `generateContent` to the
Interactions API; added `debug_raw_interactions_stream.py`; added a GUI
thinking-display panel (previously wired in terminal only); updated
`requirements.txt`'s `google-genai` minimum version if changed.

---

## 8. Explicit Non-Goals for This Pass

- Migrating to Interactions' **stateful** mode (`store: true` +
  `previous_interaction_id`) for multi-turn history. This project already
  manages its own memory/context (`StateSandbox`, `EntityRegistry`,
  `MemoryManager`) and rebuilds the full prompt every call — that
  architecture is unchanged here. Stateful interactions are a separate
  design question for later, not part of this migration.
- Adopting Interactions' built-in tools (Google Search grounding, URL
  context, code execution, file search) — out of scope, no current caller
  needs them.
- Changing `Scribe`'s or `Ally`'s prompt content.
- `infrastructure/llm/model_lister.py` — untouched, per §1.
- Deleting `debug_raw_stream.py` — kept as a reference/comparison tool
  against the legacy API.

---

## 9. File Manifest

| Path | Phase | Action |
| --- | --- | --- |
| `requirements.txt` | 0 | Modify if `google-genai` version needs bumping |
| `debug_raw_interactions_stream.py` | 0 | New |
| `infrastructure/llm/gemini_provider.py` | 1 | Modify — internals of all three `generate_structured*` methods |
| (no change) `brain/perception/scribe.py` | 2 | Verify only |
| `tests/test_gemini_provider_stream_field.py` | 3 | Modify — remock |
| `tests/test_gemini_provider_stream.py` | 3 | Modify — remock |
| (any other test mocking `client.models.*`) | 3 | Modify — remock |
| `interfaces/gui/overlay_api.py` | 4 | Modify — 4 new thinking-display methods |
| `interfaces/gui/models.py` | 4 | Modify — `thinking_color` field |
| `interfaces/gui/tkinter_app.py` | 4 | Modify — hook wiring, new instance attr |
| `docs/ally_decision_log.md` | 7 | Modify — append |
| `docs/roadmap.md` | 7 | Modify — append if applicable |
| `docs/changelog.md` | 7 | Modify — append |

---

## 10. Testing Expectations

`python -m unittest discover tests` must pass with zero regressions after
every phase. No test may make a real network call. Manual verification
required (no automated Tkinter/terminal rendering coverage exists):

1. `python main.py --game <some_game>` headless — confirm thinking text now
   visibly streams before the spoken analysis, and analysis still streams
   as before.
2. `python main.py --gui` — confirm the new thinking panel renders and
   updates live, and the existing feedback/chat panels are unaffected.
3. Force a retry (temporarily lower `max_retries` and monkey-patch a single
   failure, same technique as the original streaming task's manual
   verification) — confirm thinking text visibly clears and restarts
   clean, matching the existing analysis/chat reset behavior. Revert the
   temporary change before finishing.

---

## 11. Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

When this comes back for review, check specifically:

- **Was Phase 0 actually run against the real API**, and are its real
  findings pasted into the code (the `_extract_new_field_text`-style
  "Verified against..." comments) rather than left as placeholders or
  omitted. If §2.2's five checks weren't all genuinely run, that's the
  same failure mode flagged in the original streaming spec's review
  section — call it out directly.
- **Did structured output + thinking summaries actually compose in one
  call** per §2.2 item 2 — if ZooCode reports they don't, the whole Phase
  1 design (single `generate_structured_stream_field` call doing both)
  needs to be re-architected, not patched around silently.
- **Did Scribe's multimodal path get verified for real**, not assumed —
  if `input` doesn't cleanly accept `[image, prompt]`, check whether
  ZooCode either found a correct alternative shape or flagged the gap
  honestly, rather than quietly leaving Scribe broken.
- **Were `GeminiProvider`'s public signatures actually preserved** — spot
  check that `Ally`, `Scribe`, `NarrativeMemoryManager`,
  `PersonalityMemoryManager`, and `goodies/geneology.py` have zero diffs.
  Any change to those files is a signal §1's scoping constraint was
  violated.
- **Retry/reset ordering** — same check as the original streaming spec:
  `on_stream_reset` (and now also `on_thought_reset`) must fire before the
  retry's next attempt starts emitting chunks, on every retry.
- **Is the GUI thinking panel actually wired** (§6) — confirm
  `tkinter_app.py`'s `__init__` really has the four new `connect()` calls,
  not just the mixin methods existing unused.
- Confirm `docs/ally_decision_log.md`'s new entry documents the *real*
  Phase 0 findings (exact config keys, exact event shapes) rather than a
  generic restatement of this spec's assumptions — this doc is meant to be
  the durable source of truth once this API stabilizes further.
