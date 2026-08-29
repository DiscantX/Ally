# CLAUDE_LED_TASK: Production Token-Level Streaming (Ally.decide + Ally.chat)

> Handoff spec from Claude to ZooCode. This **supersedes** an earlier explicit
> non-goal in `plans/CLAUDE_LED_TASK_personality_triggers_and_perspectives.md`
> §6, which said streaming would stay diagnostic-tool-only. That decision is
> now reversed — see §8 for the decision-log entry text. Five phases, strictly
> sequential (each depends on the one before it). **Use Architect mode to
> split this into five top-level sub-task sequences, one per phase,
> implemented and committed in order.** Do not start a phase before the
> previous one is implemented and its tests pass.

---

## 0. What this actually is (read before writing any code)

The person running this project asked for the text Ally speaks (the
`analysis` field of `AllyOutput`, and the `response` field of
`AllyChatOutput`) to visibly stream token-by-token in **both** the terminal
and the Tkinter GUI, in **production** — not just in the standalone
diagnostic script. If the connection drops mid-stream, it should retry and
visibly clear whatever partial text was already shown, then start clean.

The hard part: `generate_structured_stream()` (already built, diagnostic-
only) buffers every content chunk silently and only returns the final
parsed object once the stream ends — because partial JSON isn't valid JSON,
so you can't `schema.model_validate_json()` it mid-stream. But the raw JSON
text **does** arrive incrementally from the SDK (confirmed against a real
call — see the raw chunk dump in the design conversation this spec came
from: `{"answer":"...` arrived in one chunk, the closing `..."}` in the
next). The fix is a **partial JSON parser** — a library that can look at an
incomplete JSON string and best-effort extract whatever value currently
exists for one named field, even mid-string. Diff that against what was
already shown, emit only the new suffix. This is a well-known pattern for
streaming one field out of an LLM's structured output; we are not
inventing anything novel here, just wiring an existing library
(`partial-json-parser` on PyPI) into the existing provider/agent layers.

---

## 1. Non-Negotiable Constraints

- Follow `CLAUDE.md`: full type hints, `Optional[...]`/`| None` explicit,
  dataclasses/Pydantic over loose dicts, no `# type: ignore` to silence
  Pylance — fix the actual type issue.
- Follow the project's autonomy principle: nothing here requires a human
  to approve/confirm anything mid-pipeline. Retry-and-reset must happen
  automatically.
- Use `infrastructure.logger.log()` for all *logging* (errors, retries).
  The literal user-facing streamed text in the terminal (§5) is printed
  directly via `print()`, by design — it is output, not a log line, and
  must not get the logger's `[Module][Method]` prefix or padding.
- Test conventions: `unittest.TestCase` subclasses, not bare pytest
  functions (see `tests/README.md`). No test may make a real network call
  — mock `client.models.generate_content_stream` throughout, following
  `tests/test_ally.py`'s existing mocking pattern for `GeminiProvider`.
- Documentation stays honest: update `docs/ally_decision_log.md`,
  `docs/roadmap.md`, and `docs/changelog.md` in the same pass (§8, §9).
  Follow `.markdownlint.yaml` for any `.md` edits.
- **Do not delete or modify the behavior of `Ally.decide()` or
  `Ally.chat()`** (the existing non-streaming methods). They stay exactly
  as they are — used by tests and by
  `tooling/tools/perspective_thinking_diagnostic.py`. This task adds new
  `decide_stream()`/`chat_stream()` methods alongside them.
- **Do not modify `GeminiProvider.generate_structured_stream()`** (the
  existing diagnostic-only thinking-trace method). It stays as-is. This
  task adds a new, separate method (§2).

---

## 2. Phase 1 — Provider layer: `generate_structured_stream_field()`

### 2.1 New dependency — verify before integrating, do not skip this

Add to `requirements.txt`:

```
partial-json-parser
```

Then run `pip install -r requirements.txt` (or `pip install
partial-json-parser` directly).

**Mandatory verification step before writing any integration code.** Past
experience on this project (the earlier streaming-diagnostic task) showed
that an instruction to "verify the SDK surface before using it" was not
actually followed, and a best-guess snippet was transcribed verbatim
without confirming it against the real installed library. Do not repeat
that here. Run this exact throwaway script first, and paste its actual
printed output into a comment at the top of the new
`_extract_new_field_text` method (§2.3) as proof it was run:

```python
import partial_json_parser
print(dir(partial_json_parser))
print(help(partial_json_parser.loads))

# Hand-written incomplete JSON, simulating a mid-stream buffer:
sample = '{"analysis": "Hello wor'
result = partial_json_parser.loads(sample, partial_json_parser.Allow.ALL)
print(repr(result))
# Expect something like {'analysis': 'Hello wor'}
```

If `Allow.ALL` doesn't exist, or the returned shape isn't a plain dict with
the partial string value, or the function signature differs (e.g. `allow=`
as a required kwarg vs. positional, or a different flag name entirely),
**adjust the integration code in §2.3 to match what you actually observed,
and say so explicitly in your completion notes** — do not silently paper
over a mismatch. Regardless of the exact API shape, the integration in
§2.3 must be wrapped defensively (try/except around the parse call) so
that even if this library's real behavior differs slightly from what's
assumed here, the worst-case outcome is *chunkier* streaming (fewer,
bigger visible updates), never a crash and never visibly wrong text.

### 2.2 `generate_structured_stream_field()` — new method

**File:** `infrastructure/llm/gemini_provider.py`

Add this method to `GeminiProvider`, alongside the existing
`generate_structured` and `generate_structured_stream`. Add
`import partial_json_parser` at the top of the file (module-level, same
pattern as the other top-level imports in this file).

```python
def generate_structured_stream_field(
    self,
    model: str,
    contents: list,
    schema: type[T],
    stream_field: str,
    on_field_chunk: Callable[[str], None] | None = None,
    on_stream_reset: Callable[[], None] | None = None,
    thinking_level: str | types.ThinkingLevel | None = None,
    max_retries: int = 5,
) -> T:
    """Streams one named string field out of a structured-output response
    as it's generated, calling on_field_chunk with only the NEW text
    since the last call (never the whole buffer, never a repeat).

    Unlike generate_structured_stream() (diagnostic-only, streams
    Gemini's own thinking-trace summaries), this method streams the
    actual CONTENT the response schema is producing -- e.g. AllyOutput's
    `analysis` field or AllyChatOutput's `response` field -- so the
    person sees Ally's words appear live, not a raw JSON blob and not an
    internal thought summary.

    Mechanism: the raw JSON text already arrives from the SDK in
    incremental pieces (confirmed against a real call -- a string value
    can be split mid-word across two chunks). This buffers all raw text
    seen so far and, after every chunk, attempts a best-effort PARTIAL
    JSON parse (via the `partial_json_parser` library) of the buffer to
    extract stream_field's current (possibly incomplete) string value.
    If that value is longer than and starts with what was already
    emitted, the new suffix is sent to on_field_chunk. If the partial
    parse fails or looks inconsistent with what's already been shown
    (e.g. transient malformed intermediate state, or a shorter value
    than before), that chunk simply contributes no visible update --
    never backtracks or shows wrong text, just waits for the next
    successful parse to catch up.

    Once the stream ends, the full buffer is parsed and validated
    EXACTLY as generate_structured() does (schema.model_validate_json)
    -- this is the return value, and is the source of truth. The
    incrementally-streamed text is a best-effort live preview; callers
    that display it should reconcile against the final validated field
    value once this method returns (see AllyCore's on_*_stream_finalize
    hooks), in case of any drift between partial-parse extraction and
    final JSON-escape-sequence resolution.

    Retry semantics: unlike generate_structured() (wrapped by the
    @retry_with_gemini_backoff decorator), this method implements retry
    manually in a loop, because a decorator retrying the whole function
    call would silently re-invoke on_field_chunk from scratch without
    ever telling the caller that previously-shown partial text is now
    stale. Before each retry attempt (not the first attempt), if
    on_stream_reset is given, it is called FIRST, so the caller (e.g. a
    GUI text widget, or a terminal printer) can visibly clear whatever
    was already shown before the retry starts producing new chunks.
    """
    thinking_config = None
    if thinking_level is not None:
        lvl = self._map_thinking_level(thinking_level)
        # Deliberately no include_thoughts here -- this path streams the
        # response schema's own content field, not a thinking-trace
        # summary. Surfacing raw chain-of-thought into what's meant to
        # be Ally's spoken dialogue would be wrong; the diagnostic
        # thinking-trace tool (generate_structured_stream) already
        # covers that separate use case.
        thinking_config = types.ThinkingConfig(thinking_level=lvl)

    attempt = 0
    while True:
        attempt += 1
        json_buffer = ""
        emitted_so_far = ""
        try:
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
                content = chunk.candidates[0].content
                if not content or not content.parts:
                    continue
                for part in content.parts:
                    text = getattr(part, "text", None)
                    if not text:
                        continue
                    json_buffer += text
                    if on_field_chunk is not None:
                        new_text, emitted_so_far = self._extract_new_field_text(
                            json_buffer, stream_field, emitted_so_far
                        )
                        if new_text:
                            on_field_chunk(new_text)

            if not json_buffer:
                raise ValueError("Streaming response produced no JSON content")
            return schema.model_validate_json(json_buffer)

        except (errors.ClientError, errors.ServerError, ValueError) as e:
            if attempt > max_retries:
                log(
                    "Gemini streaming error (max retries {max_retries} exceeded): {e}",
                    max_retries=max_retries, e=e,
                )
                raise

            if on_stream_reset is not None:
                on_stream_reset()

            delay = None
            if isinstance(e, (errors.ClientError, errors.ServerError)):
                delay = self._extract_retry_delay(e)
            if delay is None:
                delay = (2 ** attempt) + random.uniform(0, 1)

            log(
                "Gemini streaming error ({e}). Retrying attempt {attempt}/{max_retries} in {delay:.2f}s...",
                e=e, attempt=attempt, max_retries=max_retries, delay=delay,
            )
            time.sleep(delay)
```

### 2.3 `_extract_new_field_text()` — helper method

Add this private helper to `GeminiProvider`, used only by
`generate_structured_stream_field()`:

```python
def _extract_new_field_text(
    self, json_buffer: str, field_name: str, previous_value: str
) -> tuple[str, str]:
    """Best-effort incremental extraction of `field_name`'s growing
    string value from a possibly-incomplete JSON buffer. Returns
    (new_suffix_to_emit_now, updated_previous_value).

    # Verified against partial_json_parser==<VERSION> installed in this
    # environment -- see §2.1 of the handoff spec for the confirmation
    # script and its actual output. <PASTE THE REAL OUTPUT YOU OBSERVED
    # HERE AS A COMMENT>

    Defensive by construction: any failure to parse, or a value that
    isn't a string, or a value that's SHORTER than what was already
    emitted (a transient malformed intermediate parse), results in no
    update for this call -- never a crash, never visibly wrong/
    backtracked text. The next successful parse catches up.
    """
    try:
        partial_obj = partial_json_parser.loads(json_buffer, partial_json_parser.Allow.ALL)
    except Exception:
        return "", previous_value

    if not isinstance(partial_obj, dict):
        return "", previous_value

    current_value = partial_obj.get(field_name)
    if not isinstance(current_value, str):
        return "", previous_value

    if current_value.startswith(previous_value) and len(current_value) > len(previous_value):
        return current_value[len(previous_value):], current_value

    return "", previous_value
```

### 2.4 Tests (Phase 1)

**New file:** `tests/test_gemini_provider_stream_field.py`. Mock
`client.models.generate_content_stream` to yield a sequence of fake chunks
(same `MagicMock` pattern as the existing
`tests/test_gemini_provider_stream.py`, but with `part.text` values that
are pieces of a growing JSON string, e.g. simulate
`'{"analysis": "Hel'`, then `'lo there, '`, then `'friend!"}'` across
three chunks). Cover:

- Chunks arrive covering a growing `analysis` value split across chunk
  boundaries (including mid-word splits) -- assert `on_field_chunk` is
  called with only the NEW suffix each time, and that concatenating every
  call's argument reconstructs the final `analysis` value exactly, with
  no repeats and no gaps.
- The final returned object is the fully validated Pydantic model
  (`schema.model_validate_json` of the complete buffer), matching
  `generate_structured()`'s existing final-parse behavior.
- No-content stream still raises `ValueError`, same as
  `generate_structured_stream()`'s existing behavior.
- A malformed/unparseable intermediate buffer state (mock
  `partial_json_parser.loads` to raise on one specific call, succeed on
  others) does not crash the method and does not call `on_field_chunk`
  for that one chunk -- the next successful chunk still produces a
  correct (possibly larger) diff.
- Retry-with-reset: mock `generate_content_stream` to raise a retryable
  error (`errors.ClientError` or similar) partway through the FIRST call
  (after at least one chunk was already yielded and `on_field_chunk`
  already called at least once), then succeed on the second call. Assert:
  `on_stream_reset` is called exactly once, before any chunks from the
  second attempt are emitted via `on_field_chunk`. Assert the final
  returned object is valid and matches only the successful (second)
  attempt's content.
- `on_field_chunk` and `on_stream_reset` are both optional (`None`) --
  calling without them must not raise.

Run `python -m unittest tests.test_gemini_provider_stream_field` and
confirm it passes before starting Phase 2.

---

## 3. Phase 2 — Ally layer: `decide_stream()` and `chat_stream()`

### 3.1 `Ally.decide_stream()`

**File:** `brain/reasoning/ally_agent.py`

Add `from typing import Callable` to the imports (if not already present
via another import). Add this method to the `Ally` class, alongside the
existing `decide()`:

```python
def decide_stream(
    self,
    elements_context: str,
    entities_context: str,
    genre_context: str = "unknown (not yet determined)",
    memory_context: str = "(no memory yet -- this is the first turn)",
    personality: str | None = None,
    perspective_context: str = "(no strong perspective signal this turn)",
    on_chunk: Callable[[str], None] | None = None,
    on_reset: Callable[[], None] | None = None,
) -> AllyOutput:
    """Streaming counterpart to decide() -- builds the exact same prompt,
    but streams the `analysis` field live via on_chunk as it's generated,
    with on_reset called if a mid-stream retry occurs. Returns the same
    fully-validated AllyOutput decide() would return; every other field
    (actions, run_boundary, significant_moment) is unaffected by
    streaming and only available once this call returns, same as
    before."""
    prompt = ALLY_PROMPT_TEMPLATE.format(
        personality=personality if personality else self.base_personality,
        genre=genre_context,
        memory=memory_context,
        elements=elements_context,
        entities=entities_context,
        perspectives=perspective_context,
    )
    return self.provider.generate_structured_stream_field(
        model=self.model,
        contents=[prompt],
        schema=AllyOutput,
        stream_field="analysis",
        on_field_chunk=on_chunk,
        on_stream_reset=on_reset,
        thinking_level=self.thinking_level,
    )
```

### 3.2 `Ally.chat_stream()`

Add alongside the existing `chat()`:

```python
def chat_stream(
    self,
    elements_context: str,
    entities_context: str,
    genre_context: str = "unknown (not yet determined)",
    memory_context: str = "(no memory yet -- this is the first turn)",
    personality: str | None = None,
    question: str = "",
    on_chunk: Callable[[str], None] | None = None,
    on_reset: Callable[[], None] | None = None,
) -> AllyChatOutput:
    """Streaming counterpart to chat() -- builds the exact same prompt,
    streams the `response` field live via on_chunk. NOTE: chat(), as it
    exists today, does NOT pass thinking_level to generate_structured()
    -- this appears to be a pre-existing inconsistency with decide()
    (which does pass it), not something introduced by this task.
    chat_stream() preserves that exact existing behavior (no
    thinking_level passed) rather than silently changing it. Flag this
    to Ficus in your completion notes as a possible pre-existing bug
    worth a separate decision, but do not fix it as part of this task."""
    prompt = ALLY_CHAT_PROMPT_TEMPLATE.format(
        personality=personality if personality else self.base_personality,
        genre=genre_context,
        memory=memory_context,
        elements=elements_context,
        entities=entities_context,
        question=question,
    )
    return self.provider.generate_structured_stream_field(
        model=self.model,
        contents=[prompt],
        schema=AllyChatOutput,
        stream_field="response",
        on_field_chunk=on_chunk,
        on_stream_reset=on_reset,
    )
```

### 3.3 Tests (Phase 2)

**New file:** `tests/test_ally_stream.py`. Mock `provider` (a `MagicMock`
standing in for `GeminiProvider`), following the exact mocking convention
`tests/test_ally.py` already uses. Cover:

- `decide_stream()` calls `provider.generate_structured_stream_field`
  exactly once, with `stream_field="analysis"`, `schema=AllyOutput`, and
  a `contents` list whose single prompt string contains the same
  substituted values `decide()`'s prompt would (same assertions style as
  the existing `perspective_context`-reaches-the-prompt test called for
  in the earlier task's spec, if present in `test_ally.py` -- follow that
  pattern).
- `decide_stream()` passes `on_chunk`/`on_reset` straight through as
  `on_field_chunk`/`on_stream_reset` unchanged.
- `chat_stream()` calls `provider.generate_structured_stream_field`
  exactly once with `stream_field="response"`, `schema=AllyChatOutput`,
  and does **not** pass a `thinking_level` argument at all (matching
  `chat()`'s existing behavior) -- assert this explicitly by inspecting
  the mock's call kwargs.

Run `python -m unittest tests.test_ally_stream` and confirm it passes
before starting Phase 3.

---

## 4. Phase 3 — `AllyCore` wiring: new EventHooks + `run_turn()`/`send_message()`

### 4.1 New EventHooks

**File:** `brain/reasoning/core.py`

In `AllyCore.__init__`, in the existing "Observer / Event Hooks" block,
add eight new hooks alongside the existing ones (same `EventHook("name")`
pattern):

```python
self.on_analysis_stream_begin: EventHook = EventHook("on_analysis_stream_begin")
self.on_analysis_stream_chunk: EventHook = EventHook("on_analysis_stream_chunk")
self.on_analysis_stream_reset: EventHook = EventHook("on_analysis_stream_reset")
self.on_analysis_stream_finalize: EventHook = EventHook("on_analysis_stream_finalize")
self.on_chat_stream_begin: EventHook = EventHook("on_chat_stream_begin")
self.on_chat_stream_chunk: EventHook = EventHook("on_chat_stream_chunk")
self.on_chat_stream_reset: EventHook = EventHook("on_chat_stream_reset")
self.on_chat_stream_finalize: EventHook = EventHook("on_chat_stream_finalize")
```

**Lifecycle contract, for every consumer of these hooks (§5, §6):**
`begin` fires once, exactly before the first possible `chunk`. `chunk`
fires zero or more times with new text only (never the full accumulated
text, never a repeat). `reset` fires only on a mid-stream retry, meaning
"discard everything shown since the matching `begin`, a fresh attempt is
starting." `finalize` fires exactly once at the very end, with the
FULL final text (not a delta) -- consumers must treat `finalize`'s
argument as the source of truth and reconcile/replace whatever partial
text is currently displayed with it, even if that means replacing
identical text (cheap no-op) -- this guards against any drift between
the live partial-JSON preview and the actual final validated field value.

**Existing `on_feedback` and `on_chat_message` hooks are NOT removed or
renamed.** They keep firing exactly where they already fire in the code
today (do not delete any existing `.emit()` call for them) -- this task
only changes what two specific call sites are *subscribed to* them (see
§4.3, §4.4). Other subscribers, if any exist elsewhere or are added
later, keep working unaffected.

### 4.2 `run_turn()` — the real (non-skip) Ally call

Find this existing block inside `run_turn()`'s `if not skip_ally:` branch:

```python
prompt_sent_to_ally = f"Elements: {elements_context}\nEntities: {entities_context}\nGenre: {genre_context}\nMemory: {memory_context}\nPerspectives: {perspective_context}"
ally_output = self.ally.decide(
    elements_context=elements_context,
    entities_context=entities_context,
    genre_context=genre_context,
    memory_context=memory_context,
    personality=personality_context,
    perspective_context=perspective_context,
)
timings["ally"] = time.perf_counter() - t0
```

Replace it with:

```python
prompt_sent_to_ally = f"Elements: {elements_context}\nEntities: {entities_context}\nGenre: {genre_context}\nMemory: {memory_context}\nPerspectives: {perspective_context}"
self.on_analysis_stream_begin.emit()
ally_output = self.ally.decide_stream(
    elements_context=elements_context,
    entities_context=entities_context,
    genre_context=genre_context,
    memory_context=memory_context,
    personality=personality_context,
    perspective_context=perspective_context,
    on_chunk=lambda text: self.on_analysis_stream_chunk.emit(text),
    on_reset=lambda: self.on_analysis_stream_reset.emit(),
)
self.on_analysis_stream_finalize.emit(ally_output.analysis)
timings["ally"] = time.perf_counter() - t0
```

Everything below this block in `run_turn()` (actions logging, memory
recording, `significant_moment` handling, `run_boundary` resolution) is
**unchanged** -- it already only reads from `ally_output`, which is still
the same fully-validated `AllyOutput` object it always was.

### 4.3 `run_turn()` — the `skip_ally` branch

Find this existing block:

```python
ally_output = AllyOutput(
    analysis=skip_messages.get(skip_scribe_reason, skip_messages["none"]),
    actions=[],
    run_boundary="none",
)
self.on_ally_output.emit(ally_output)
```

Add immediately after it (so the skip-branch's synthesized message goes
through the exact same rendering lifecycle as a real streamed turn --
one code path in every consumer, not two):

```python
self.on_analysis_stream_begin.emit()
self.on_analysis_stream_chunk.emit(ally_output.analysis)
self.on_analysis_stream_finalize.emit(ally_output.analysis)
```

No `on_analysis_stream_reset` here -- this path is synchronous/local, not
a network call, so there is nothing to retry.

### 4.4 `send_message()` — chat streaming

Find this existing block inside `send_message()`'s `_handle()` closure:

```python
try:
    res = self.ally.chat(
        elements_context=elements_context,
        entities_context=entities_context,
        genre_context=genre_context,
        memory_context=memory_context,
        personality=personality_context,
        question=text,
    )
    with self.state_lock:
        if self.memory_manager is not None:
            self.memory_manager.record_turn(
                self.sandbox.turn,
                f"Player asked: '{text}' -> Ally answered: '{res.response}'",
                importance=5
            )
    self.on_chat_message.emit("coach", res.response)
except Exception as e:
    self.on_chat_message.emit("coach", f"(Error: {e})")
```

Replace it with:

```python
try:
    self.on_chat_stream_begin.emit()
    res = self.ally.chat_stream(
        elements_context=elements_context,
        entities_context=entities_context,
        genre_context=genre_context,
        memory_context=memory_context,
        personality=personality_context,
        question=text,
        on_chunk=lambda t: self.on_chat_stream_chunk.emit(t),
        on_reset=lambda: self.on_chat_stream_reset.emit(),
    )
    with self.state_lock:
        if self.memory_manager is not None:
            self.memory_manager.record_turn(
                self.sandbox.turn,
                f"Player asked: '{text}' -> Ally answered: '{res.response}'",
                importance=5
            )
    self.on_chat_stream_finalize.emit(res.response)
except Exception as e:
    self.on_chat_stream_reset.emit()
    self.on_chat_stream_finalize.emit(f"(Error: {e})")
```

**Do not touch any other `on_chat_message.emit(...)` call site.**
`on_chat_message` is also used for: the player's own typed message
(rendered via `append_chat_message("player", ...)` in
`interfaces/gui/chat_drawer.py`'s `_handle_send()` -- a completely
different file/method, not touched by this task at all), the
"not_started" message, the "feedback ack" message, and the "Run ended!"
message. All of those stay exactly as they are -- only the two
`"coach"` + `res.response` lines shown above are being replaced.

### 4.5 Tests (Phase 3)

**Extend** `tests/test_ally_core.py`, following its existing
mocking/construction pattern for `AllyCore`. Cover:

- Mock `Ally.decide_stream` to synchronously call `on_chunk` twice with
  fake text and `on_reset` zero times, then return a real `AllyOutput`.
  Run a turn via `run_turn()` and assert: `on_analysis_stream_begin`
  fired once, `on_analysis_stream_chunk` fired with each fake chunk in
  order, `on_analysis_stream_finalize` fired once with
  `ally_output.analysis`, and downstream behavior (memory recording,
  `on_ally_output` emission, actions) is identical to before this task
  (i.e., this is a refactor of the *call*, not of anything downstream).
- The `skip_ally` branch (mock conditions so a turn takes that path)
  still emits `on_analysis_stream_begin` /
  `on_analysis_stream_chunk` (once, with the full skip message) /
  `on_analysis_stream_finalize` (with the same skip message), and does
  **not** emit `on_analysis_stream_reset`.
- Mock `Ally.chat_stream` similarly for `send_message()` -- assert
  `on_chat_stream_begin`/`chunk`/`finalize` fire correctly, and that an
  exception raised from `chat_stream` results in
  `on_chat_stream_reset` followed by `on_chat_stream_finalize` with an
  error string, matching the `except` branch above.

Run `python -m unittest discover tests` (full suite, not just the new
file) and confirm zero regressions before starting Phase 4.

---

## 5. Phase 4 — Tkinter GUI wiring

### 5.1 Feedback panel (Ally's spoken analysis) — `overlay_api.py`

**File:** `interfaces/gui/overlay_api.py`

Add four new methods to `OverlayApiMixin`, alongside the existing
`update_feedback`. These mirror `update_feedback()`'s exact insert
logic/tags/scroll behavior, just split into stream-lifecycle stages
instead of one atomic append. Add one new instance attribute reference
(`self._streaming_feedback_body_start`, a `tk.Text` index string or
`None`) -- initialize it to `None` wherever `AllyOverlay.__init__` already
initializes similar per-instance state (near `self._feedback_entry_count
= 0` in `interfaces/gui/tkinter_app.py`).

```python
def begin_streaming_feedback(self):
    """MAIN THREAD (dispatched). Starts a new timestamped feedback entry
    with an empty body, ready to receive live text via
    append_streaming_feedback_chunk(). Mirrors update_feedback()'s
    header-insertion exactly, just split into stages."""
    def _update():
        text = self.feedback_text
        was_at_bottom = self._is_scrolled_to_bottom(text)
        timestamp = datetime.now().strftime('%H:%M:%S')

        text.config(state=tk.NORMAL)
        if self._feedback_entry_count > 0:
            text.insert(tk.END, "\n\n")
        text.insert(tk.END, f"── {timestamp} ──\n", 'timestamp')
        self._streaming_feedback_body_start = text.index(tk.END)
        text.config(state=tk.DISABLED)
        self._feedback_entry_count += 1

        if was_at_bottom:
            text.see(tk.END)
        self.status_label.config(text="Ally is responding...")
    self._dispatch(_update)

def append_streaming_feedback_chunk(self, chunk_text: str):
    def _update():
        text = self.feedback_text
        was_at_bottom = self._is_scrolled_to_bottom(text)
        text.config(state=tk.NORMAL)
        text.insert(tk.END, chunk_text, 'body')
        text.config(state=tk.DISABLED)
        if was_at_bottom:
            text.see(tk.END)
    self._dispatch(_update)

def reset_streaming_feedback(self):
    """Mid-stream retry: wipe this entry's body back to empty (keep the
    timestamp header already inserted by begin_streaming_feedback), so
    the retried attempt starts clean with no leftover text visible from
    the failed attempt."""
    def _update():
        text = self.feedback_text
        start = getattr(self, "_streaming_feedback_body_start", None)
        if start is None:
            return
        text.config(state=tk.NORMAL)
        text.delete(start, tk.END)
        text.config(state=tk.DISABLED)
        self.status_label.config(text="Connection dropped -- retrying...")
    self._dispatch(_update)

def finalize_streaming_feedback(self, final_text: str):
    """Stream complete. Corrective step: ensure the displayed body text
    exactly matches final_text -- guards against any drift between the
    incremental partial-JSON preview and the fully-validated final field
    value. Silently replaces the body if they differ (cheap no-op if
    they already match)."""
    def _update():
        text = self.feedback_text
        start = getattr(self, "_streaming_feedback_body_start", None)
        if start is not None:
            text.config(state=tk.NORMAL)
            current = text.get(start, tk.END).rstrip("\n")
            if current != final_text:
                text.delete(start, tk.END)
                text.insert(start, final_text, 'body')
            text.config(state=tk.DISABLED)
        self._feedback_data.feedback = final_text
        self._feedback_data.last_update = time.time()
        self.status_label.config(text=f"Updated: {datetime.now().strftime('%H:%M:%S')}")
    self._dispatch(_update)
```

Do not remove `update_feedback()` itself -- leave it in place, unused by
the new wiring but harmless, in case anything else calls it directly.

### 5.2 Chat drawer (Ally's chat responses) — `chat_drawer.py`

**File:** `interfaces/gui/chat_drawer.py`

Add four analogous methods to `ChatDrawerMixin`, mirroring
`append_chat_message()`'s exact insert logic for the `"coach"` role tag.
Add `self._streaming_chat_body_start: str | None = None` initialized
alongside other `AllyOverlay` per-instance state.

```python
def begin_streaming_chat_message(self):
    def _update():
        was_at_bottom = self._is_scrolled_to_bottom(self.chat_text)
        self.chat_text.config(state=tk.NORMAL)
        if self.chat_text.index('end-1c') != '1.0':
            self.chat_text.insert(tk.END, "\n\n")
        self.chat_text.insert(tk.END, "Ally\n", 'chat_label')
        self._streaming_chat_body_start = self.chat_text.index(tk.END)
        self.chat_text.config(state=tk.DISABLED)
        if was_at_bottom:
            self.chat_text.see(tk.END)
    self._dispatch(_update)

def append_streaming_chat_chunk(self, chunk_text: str):
    def _update():
        was_at_bottom = self._is_scrolled_to_bottom(self.chat_text)
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, chunk_text, "coach")
        self.chat_text.config(state=tk.DISABLED)
        if was_at_bottom:
            self.chat_text.see(tk.END)
    self._dispatch(_update)

def reset_streaming_chat_message(self):
    def _update():
        start = getattr(self, "_streaming_chat_body_start", None)
        if start is None:
            return
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.delete(start, tk.END)
        self.chat_text.config(state=tk.DISABLED)
    self._dispatch(_update)

def finalize_streaming_chat_message(self, final_text: str):
    def _update():
        start = getattr(self, "_streaming_chat_body_start", None)
        if start is not None:
            self.chat_text.config(state=tk.NORMAL)
            current = self.chat_text.get(start, tk.END).rstrip("\n")
            if current != final_text:
                self.chat_text.delete(start, tk.END)
                self.chat_text.insert(start, final_text, "coach")
            self.chat_text.config(state=tk.DISABLED)
    self._dispatch(_update)
```

Do not remove `append_chat_message()` -- it is still used unchanged for
the player's own messages and for other system messages (§4.4).

### 5.3 Wiring in `AllyOverlay.__init__`

**File:** `interfaces/gui/tkinter_app.py`

Find the existing core-hookup block:

```python
if core is not None:
    if self._on_send_message is None:
        self._on_send_message = core.send_message
    core.gui_app = self
    core.on_pipeline_image.connect(self.update_pipeline_image)
    core.on_debug_overlay.connect(self.update_debug_image)
    core.on_status_update.connect(lambda screen, event: (self.update_debug_info(screen, event), self.start_eta_countdown(15)))
    core.on_state_summary.connect(self.update_state_summary)
    core.on_prompt_update.connect(self.update_prompt)
    core.on_feedback.connect(self.update_feedback)
    core.on_chat_message.connect(self.append_chat_message)
    core.on_eta_ready.connect(self.set_eta_ready)
    core.on_connection_status.connect(self.set_connection_status)
    core.on_medium_term.connect(self.update_medium_term_summary)
    core.on_personality_state.connect(self.update_personality_state)
    core.on_strategic_memory.connect(self.update_strategic_memory)
```

Remove the `core.on_feedback.connect(self.update_feedback)` line (the
feedback panel is now driven entirely by the four streaming hooks below --
leaving both connected would double-render every turn's text). **Keep**
`core.on_chat_message.connect(self.append_chat_message)` exactly as-is --
it's still needed for the player's own messages and the other system
messages listed in §4.4.

Add:

```python
    core.on_analysis_stream_begin.connect(self.begin_streaming_feedback)
    core.on_analysis_stream_chunk.connect(self.append_streaming_feedback_chunk)
    core.on_analysis_stream_reset.connect(self.reset_streaming_feedback)
    core.on_analysis_stream_finalize.connect(self.finalize_streaming_feedback)
    core.on_chat_stream_begin.connect(self.begin_streaming_chat_message)
    core.on_chat_stream_chunk.connect(self.append_streaming_chat_chunk)
    core.on_chat_stream_reset.connect(self.reset_streaming_chat_message)
    core.on_chat_stream_finalize.connect(self.finalize_streaming_chat_message)
```

Also initialize the two new per-instance attributes referenced in §5.1/§5.2
somewhere in `__init__` near where `self._feedback_entry_count = 0` is
already set:

```python
self._streaming_feedback_body_start: Optional[str] = None
self._streaming_chat_body_start: Optional[str] = None
```

### 5.4 Manual verification (no automated Tkinter rendering tests required)

Tkinter widget rendering is not covered by automated tests elsewhere in
this project, and deep GUI rendering tests are out of proportion for this
task. Instead, after implementing, manually verify:

1. `python main.py --gui` against a live game window. Confirm Ally's
   feedback panel text visibly appears progressively (not all at once) as
   a turn completes.
2. Type a message in the chat drawer. Confirm Ally's reply visibly streams
   in progressively in the chat panel, not all at once.
3. Force a mid-stream failure to test reset visually -- easiest way:
   temporarily set `max_retries=1` and disconnect network briefly (or
   temporarily monkey-patch `generate_content_stream` to raise once) while
   a turn is in flight, confirm the partially-shown text visibly clears
   and then the retried attempt's text appears clean, with no leftover
   fragments from the failed attempt. Revert any temporary test-only
   change before finishing.

---

## 6. Phase 5 — Headless/terminal wiring

### 6.1 `TerminalStreamPrinter` — new class

**File:** `main.py`

Add this class near the top of the file (below imports, above
`STATE_LOCK`):

```python
class TerminalStreamPrinter:
    """Best-effort live terminal printer for one streaming text field,
    with an ANSI-based visual reset for mid-stream retries.

    LIMITATION, stated explicitly rather than silently: this only tracks
    explicit '\\n' characters it has printed. If the terminal soft-wraps
    a long unbroken line (no '\\n' in it) because it's wider than the
    terminal's column count, reset() will NOT correctly clear the
    wrapped portion -- that would require querying the terminal's actual
    column width, which this does not do. This is a best-effort
    convenience for the common case (a retry mid-sentence), not a
    robust terminal UI framework. Acceptable given the person explicitly
    said "if it is easy enough" for this specific piece.
    """

    def __init__(self, prefix: str):
        self.prefix = prefix
        self._newline_count = 0

    def begin(self) -> None:
        print(self.prefix, end="", flush=True)
        self._newline_count = 0

    def chunk(self, text: str) -> None:
        print(text, end="", flush=True)
        self._newline_count += text.count("\n")

    def reset(self) -> None:
        for _ in range(self._newline_count):
            print("\033[1A\033[2K", end="")
        print("\r\033[2K", end="")
        print(self.prefix, end="", flush=True)
        self._newline_count = 0

    def finalize(self, final_text: str) -> None:
        """Reprints final_text cleanly regardless of what was already
        shown -- correcting after-the-fact in a terminal can't be done
        as a text diff the way the GUI's Text widget allows, so this
        just clears and reprints once, which is cheap and only visibly
        matters in the rare drift case."""
        self.reset()
        print(final_text, flush=True)
```

### 6.2 Wiring in headless mode

**File:** `main.py`, inside `initialize_application()`'s `else:` (headless)
branch.

Find:

```python
else:
    # Headless terminal mode
    core.on_status_update.connect(lambda screen, event: None)
    core.on_state_summary.connect(lambda summary: log("Summary:\n{summary}", summary=summary))
    core.on_prompt_update.connect(lambda prompt: None)
    core.on_feedback.connect(lambda feedback: log("Feedback:\n{feedback}", feedback=feedback))
    core.on_chat_message.connect(lambda sender, msg: log("{sender}: {msg}", sender=sender, msg=msg))
    core.on_connection_status.connect(lambda conn: log("Connection: {conn}", conn=conn))
```

Remove the `core.on_feedback.connect(...)` line (feedback is now driven by
the streaming hooks below -- leaving it connected would print the full
text a second time after it already streamed in). **Keep**
`core.on_chat_message.connect(...)` exactly as-is -- other system messages
still route through it (§4.4); only the coach-response text has moved to
the new chat-stream hooks.

Add, in the same block:

```python
    analysis_printer = TerminalStreamPrinter(prefix="\nAlly: ")
    chat_printer = TerminalStreamPrinter(prefix="\nAlly (chat): ")

    core.on_analysis_stream_begin.connect(analysis_printer.begin)
    core.on_analysis_stream_chunk.connect(analysis_printer.chunk)
    core.on_analysis_stream_reset.connect(analysis_printer.reset)
    core.on_analysis_stream_finalize.connect(lambda text: analysis_printer.finalize(text))

    core.on_chat_stream_begin.connect(chat_printer.begin)
    core.on_chat_stream_chunk.connect(chat_printer.chunk)
    core.on_chat_stream_reset.connect(chat_printer.reset)
    core.on_chat_stream_finalize.connect(lambda text: chat_printer.finalize(text))
```

### 6.3 Manual verification

Run `python main.py --game <some_game>` headless. Confirm Ally's analysis
text visibly streams into the terminal word-by-word (or in small bursts)
as each turn completes, rather than appearing all at once after a delay.

---

## 7. Explicit Non-Goals for This Pass

Do not build any of the following:

- Any change to `Ally.decide()` / `Ally.chat()` (non-streaming) or
  `GeminiProvider.generate_structured_stream()` (diagnostic thinking-trace
  method) themselves. Both stay exactly as they are.
- Live streaming of Gemini's *thinking trace* into production (that
  remains the diagnostic script's job specifically -- see §2.2's
  `thinking_config` comment on why `include_thoughts` is deliberately
  omitted here).
- A robust, terminal-column-width-aware cursor-clearing implementation.
  The newline-count-based best-effort approach in §6.1 is intentionally
  the ceiling for this pass -- its limitation is documented, not silently
  accepted as correct.
- Any change to `Ally.decide()`'s or `Ally.chat()`'s prompt *content* --
  the streaming variants build byte-for-byte identical prompts, just call
  a different provider method.
- Fixing the pre-existing `chat()`/`chat_stream()` missing-`thinking_level`
  inconsistency noted in §3.2 -- flag it, don't fix it here.
- Any change to how `on_ally_output` or `on_scribe_output` hooks fire --
  those stay exactly as they are today.

---

## 8. Docs — `docs/ally_decision_log.md`

Append a new dated section (do not rewrite existing history). Cover:

- **This supersedes** the earlier explicit non-goal in
  `plans/CLAUDE_LED_TASK_personality_triggers_and_perspectives.md` §6
  ("Wiring `generate_structured_stream()` or perspective-thinking
  streaming into the production `Ally.decide()` call path... Phase 2's
  streaming work is diagnostic-tool-only"). State plainly that this was a
  reasonable initial scope decision, and that the new decision to bring
  token-level streaming into production is a deliberate reversal, made
  once the person confirmed they wanted live-streamed text (not just a
  thinking trace) in the actual gameplay/chat experience, not just the
  diagnostic tool.
- Why field-level streaming needed a *new* method
  (`generate_structured_stream_field`) rather than extending
  `generate_structured_stream()`: the two solve genuinely different
  problems (thinking-trace display vs. content-field display) and have
  different retry semantics (the new method needs a reset callback so a
  GUI/terminal consumer can visibly clear stale partial text before a
  retry begins -- the diagnostic method has no such requirement since
  it's a one-shot manual tool, not something a player watches turn after
  turn).
- Why `partial-json-parser` was chosen as the mechanism: the raw JSON
  content already arrives from the SDK in incremental pieces (verified
  against a real streamed call during design); a partial JSON parser
  lets one named field's growing value be extracted from an otherwise-
  incomplete buffer without needing to abandon `response_schema`
  validation for the final result.
- The retry-and-reset design: a network failure mid-stream retries the
  whole call from scratch (not attempting to resume/patch a partial
  response), and visibly clears whatever partial text was already shown
  to the player first, so a retry never looks like corrupted or
  duplicated dialogue.

## 9. Docs — `docs/roadmap.md`

Find and **remove** this now-stale line from the "Deferred by explicit
decision" section:

> Real-time JSON streaming (as opposed to thinking-trace streaming via
> `generate_structured_stream()`) remains deferred, since partial JSON
> chunks from structured output streams are not valid JSON until stream
> completion.

It is no longer true -- this task implements exactly that, via
best-effort partial-field extraction rather than waiting for full
validity. Do not leave a dangling reference to a deferred feature that
now exists.

## 10. Docs — `docs/changelog.md`

Add a dated entry (implementation-pass style, matching existing entries'
tone -- what changed, not why) summarizing: new
`generate_structured_stream_field()` provider method, new
`Ally.decide_stream()`/`chat_stream()`, eight new `AllyCore` EventHooks,
Tkinter feedback-panel and chat-drawer live streaming with retry-reset,
terminal live streaming via `TerminalStreamPrinter`, new
`partial-json-parser` dependency.

---

## 11. File Manifest

| Path | Phase | Action |
| --- | --- | --- |
| `requirements.txt` | 1 | Modify -- add `partial-json-parser` |
| `infrastructure/llm/gemini_provider.py` | 1 | Modify -- `generate_structured_stream_field()`, `_extract_new_field_text()` |
| `brain/reasoning/ally_agent.py` | 2 | Modify -- `decide_stream()`, `chat_stream()` |
| `brain/reasoning/core.py` | 3 | Modify -- 8 new EventHooks, `run_turn()`/`send_message()` rewiring |
| `interfaces/gui/overlay_api.py` | 4 | Modify -- 4 new streaming-feedback methods |
| `interfaces/gui/chat_drawer.py` | 4 | Modify -- 4 new streaming-chat methods |
| `interfaces/gui/tkinter_app.py` | 4 | Modify -- hook wiring, new instance attrs |
| `main.py` | 5 | Modify -- `TerminalStreamPrinter`, headless hook wiring |
| `tests/test_gemini_provider_stream_field.py` | 1 | New |
| `tests/test_ally_stream.py` | 2 | New |
| `tests/test_ally_core.py` | 3 | Modify -- extend with streaming-hook tests |
| `docs/ally_decision_log.md` | 8 | Modify -- append |
| `docs/roadmap.md` | 9 | Modify -- remove stale deferred-item line |
| `docs/changelog.md` | 10 | Modify -- append |

---

## 12. Testing Expectations

`python -m unittest discover tests` must pass with zero regressions after
every phase. Run the full suite after each phase, not just once at the
end. No test may make a real network call.

## 13. Verification Commands

```bash
python -m unittest discover tests
```

Plus the manual verification steps in §5.4 and §6.3 (GUI and headless
live-streaming, and a forced-retry visual check), since Tkinter/terminal
rendering isn't covered by the automated suite.

---

## 14. Notes for Claude's Code Review

**ZooCode: ignore this section entirely — it is not part of your task.**

When this comes back for review, check specifically:

- **Was §2.1's verification script actually run**, and is its real output
  pasted into the `_extract_new_field_text` docstring/comment as
  instructed — not just claimed. If the comment placeholder
  (`<PASTE THE REAL OUTPUT...>`) is still literally present, or absent
  entirely, that's the same failure mode as last time and worth calling
  out directly, not politely glossing over.
- **Does the partial-JSON diffing logic ever backtrack or duplicate
  text?** Read `_extract_new_field_text` carefully — the
  `startswith(previous_value) and len(current) > len(previous)` guard is
  the entire correctness mechanism here; if ZooCode "simplified" it to
  something like always emitting `current_value[len(previous_value):]`
  without the `startswith` check, that's a real bug (would emit garbage
  or negative-length slices on any transient parse inconsistency).
- **Is the retry-then-reset ordering correct** in
  `generate_structured_stream_field()` — `on_stream_reset()` must fire
  BEFORE the retry's `time.sleep()`/next attempt, not after, and must
  fire on every retry, not just the first.
- **Did `run_turn()`'s skip_ally branch actually get the three-hook
  treatment** (§4.3) — this is easy to miss since it's a small addition
  to an already-large method; if it's missing, the skip-branch message
  won't render in the GUI at all once `on_feedback`'s subscription is
  removed.
- **Was `core.on_feedback.connect(self.update_feedback)` actually
  removed** from `tkinter_app.py`, and the equivalent
  `core.on_feedback.connect(...)` removed from `main.py`'s headless
  branch — if either is still connected alongside the new streaming
  hooks, expect every turn's feedback text to visibly render twice.
- **Was `core.on_chat_message.connect(...)` left alone** in both files
  (it should NOT have been removed — only the two specific
  `res.response`-carrying emit call sites in `send_message()` changed).
- Confirm `decide()`, `chat()`, and `generate_structured_stream()` are
  byte-for-byte untouched — a diff against the pre-task versions of
  `ally_agent.py` and `gemini_provider.py` should show only additions,
  no modified lines in the existing methods.
- Confirm `docs/ally_decision_log.md`'s new entry was *appended*, and
  that it explicitly names and supersedes the earlier non-goal from the
  personality/perspectives task, per the file's own append-only,
  explicit-supersession convention.
