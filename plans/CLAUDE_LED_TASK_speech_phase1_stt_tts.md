# Speech Phase 1: Player↔Ally Voice Chat (STT input + Gemini TTS output)

## Purpose & context

Ally is gaining voice chat: the player can talk to Ally instead of typing,
and Ally's chat replies can be spoken back. This is **Track 1** from the
earlier speech design conversation (`CLAUDE_NOTES_speech_system_design.md`,
if it's still around — not needed to do this task, just background). Track
1 is committed; nothing in this spec relates to "Track 2" (Ally overhearing
game audio in the background), which remains explicitly undecided and
out of scope.

This is a **new, standalone-but-adjacent capability**, not a change to how
Ally reasons. The player's transcribed speech becomes ordinary text that
enters exactly where typed chat already enters. Ally's spoken replies are
audio generated from the *existing* `AllyChatOutput.response` text, added
as a side-effect listener on hooks that already exist — Ally's reasoning
core, `send_message()`, and the chat schema are **not modified** by this
task.

A separate standalone repo (`gemini_speech_project/`) has speech code
(Vosk STT, gapless audio playback, Gemini Live plumbing) built for a
different, Live-API-centric design. **Do not import or depend on that
package.** Three of its files (`recognizer.py`, `assembler.py`,
`player.py`) are being ported — copied and adapted, not referenced — into
this project's own tree per the file map below, because they need real
changes (logger conventions, config source, threading model) that make an
installed dependency pure friction. Everything else in that repo
(`companion.py`, the loopback plugin) is **not part of this task** — leave
it alone, it's a separate project now.

## Scope

**In scope for this task:**

1. A provider-agnostic `TTSProvider` interface + a `GeminiTTSProvider`
   implementation (mirrors the existing `LLMProvider`/`RetryableProviderMixin`
   pattern in `infrastructure/llm/base_provider.py`).
2. A ported, adapted local STT engine (Vosk-based) + push-to-talk /
   open-mic capture modes.
3. Wiring both into the existing Qt prod overlay (`gui_qt/prod/`) with
   zero changes to `AllyCore`'s reasoning path — this is purely additive,
   listening on hooks that already exist (`InputBar.message_sent`,
   `on_chat_stream_chunk`, `on_chat_stream_finalize`).
4. New config keys, non-fatal degrade if the Vosk model or TTS call isn't
   available.

**Explicitly out of scope — do not build any of this:**

- `LiveApiBackend` / any Gemini Live API session. That's Phase 2, contingent
  on Phase 1 existing as an A/B baseline. Nothing in this task should
  create a Live API connection.
- A formal `ChatBackend` abstraction unifying text-pipeline vs. Live. Not
  needed yet — see "Why no `ChatBackend` this pass" below.
- Track 2 (game-audio loopback listening). Do not port `companion.py`,
  `loopback.py`, or `filter.py` from `gemini_speech_project/` at all.
- Speaking Ally's spontaneous gameplay commentary (`AllyOutput.analysis`,
  the `on_analysis_stream_*` hooks). This task only speaks **chat replies**
  (`AllyChatOutput.response`, the `on_chat_stream_*` hooks). Ambient
  commentary staying silent is intentional scope discipline, not an
  oversight — flag it in your Phase 0/handoff notes if you think it's
  trivial to also wire, but do not build it without confirmation.
- A volume/mute button in the input bar. A config-level on/off toggle for
  each direction is in scope (see config keys below); an in-overlay
  quick-access control is explicitly deferred.
- Global OS hotkeys for push-to-talk. Push-to-talk is a button in the
  overlay window, held with the mouse — nothing system-wide.
- Audio input/output device selection UI. Use system default devices.
- Any change to `brain/reasoning/ally_agent.py`, `brain/knowledge/schema/schema.py`,
  or `AllyCore.send_message()`'s existing logic.

### Why no `ChatBackend` this pass

The earlier design conversation sketched a `ChatBackend` interface
(`TextPipelineBackend` vs. `LiveApiBackend`) specifically to let both
coexist and be A/B tested. Since `LiveApiBackend` isn't being built this
pass, that abstraction has no second implementation to abstract over yet
— building it now would be speculative generality with no current
caller. Phase 2 will introduce it then, wrapping what this task builds.
Don't create `ally/chat_backend.py` or similar in this pass.

---

## File map

### New files

| Path | Purpose |
| --- | --- |
| `infrastructure/tts/__init__.py` | Package init |
| `infrastructure/tts/base_provider.py` | `TTSProvider` ABC, `SynthesizedAudio` dataclass |
| `infrastructure/tts/providers/__init__.py` | Package init |
| `infrastructure/tts/providers/gemini_tts_provider.py` | `GeminiTTSProvider` |
| `infrastructure/tts/audio_player.py` | Ported/adapted `AudioPlayer` (from `gemini_speech_project/src/gemini_speech/player.py`) |
| `infrastructure/stt/__init__.py` | Package init |
| `infrastructure/stt/recognizer.py` | Ported/adapted `SpeechRecognizer` (from `.../recognizer.py`) |
| `infrastructure/stt/assembler.py` | Ported/adapted `UtteranceAssembler` (from `.../assembler.py`) |
| `gui_qt/prod/voice_input_controller.py` | Qt-side glue: owns `SpeechRecognizer`, runs capture on a background thread, emits a Qt signal with finalized transcript text |
| `brain/reasoning/voice_output_controller.py` | Subscribes to `AllyCore.on_chat_stream_chunk`/`on_chat_stream_finalize`, drives `GeminiTTSProvider` + `AudioPlayer` |
| `tools/debug_raw_tts_stream.py` | Phase 0 live-verification script (see Phase 0 below); **temporary but committed**, matches the existing convention of `debug_raw_interactions_stream.py` / `debug_raw_thinking_stream_shape.py` |
| `tests/test_tts_base_provider.py` | Unit tests for `TTSProvider`'s default `synthesize_stream()` sentence-splitting behavior |
| `tests/test_voice_input_controller.py` | Unit tests for mode switching (push-to-talk vs open-mic) and graceful degrade when the Vosk model dir is missing |

### Modified files

| Path | Change |
| --- | --- |
| `requirements.txt` | Add `vosk` and `sounddevice` (see Phase 0 — confirm exact versions against what's importable, don't guess) |
| `storage/configs/config_manager.py` | Add default values for the new config keys (see Config section) — **view this file first**, it wasn't in your original context bundle; match its existing pattern for defaults exactly |
| `gui_qt/prod/input_bar.py` | Add mic `QToolButton` left of the mode toggle; wire push-to-talk (`pressed`/`released`) or open-mic (`clicked`, checkable) depending on config; on finalized transcript, populate the text edit and call the existing `_handle_send()` path (reuse, don't duplicate) |
| `gui_qt/prod/overlay_window.py` | Increase `_docked_width` and `_expanded_max_width` slightly to make room for the new button (see GUI section for exact numbers); instantiate `VoiceInputController` and connect it to `InputBar`; instantiate `VoiceOutputController` and connect it to `AllyCore`'s chat-stream hooks (via `CoreBridge` or directly — see GUI section) |
| `.gitignore` | Confirm `model/` is already ignored (it is — line already present) — no change needed unless you add a differently-named model directory, in which case update this file to match |

Do not modify any file not listed above. If you find yourself needing to
touch `brain/reasoning/core.py`, `brain/reasoning/ally_agent.py`, or
`brain/knowledge/schema/schema.py` to make this work, **stop and report
back** — that means a design assumption in this spec is wrong, not that
you should route around it.

---

## Phase 0 — Mandatory live SDK verification (do this before writing any provider code)

Per this project's established convention (see `CLAUDE.md` and the
provider-abstraction task's own Phase 0), verify real SDK behavior with a
standalone script before writing integration code. Documentation drifts;
this codebase has been burned by this exact category of bug before (the
Interactions API thinking-stream parsing bug, `docs/ally_decision_log.md`).

Write `tools/debug_raw_tts_stream.py`. It must, against a real API key:

1. Call `client.interactions.create(model=<candidate>, input="Say cheerfully: testing one two three.", response_format={"type": "audio"}, generation_config={"speech_config": [{"voice": "Kore"}]})` **without** `stream=True`. Print the full shape of the returned object (`dir()`, or better, `vars()`/repr on whatever holds the audio). Confirm:
   - The exact attribute path to the base64 audio payload (docs suggest `interaction.output_audio.data` — confirm this is real, not `interaction.candidates[0]...` or something else).
   - Whether a mime type / sample rate / channel count is reported anywhere on the response, or whether you must assume 24000 Hz / mono / 16-bit PCM (per Google's documented default for these TTS models) with no confirmation field.
2. Call the same request **with** `stream=True`. Iterate the returned stream and print each event's shape. Confirm:
   - The exact attribute path to a per-chunk audio delta (docs suggest `event.event_type == "step.delta"` then `event.delta.type == "audio"` then `event.delta.data` as base64 — confirm exactly, including whether `event_type`/`delta.type` are strings or enums).
   - Whether chunks arrive as complete, independently-decodable WAV/PCM fragments or as one continuous raw PCM stream that must be concatenated before it's valid audio (this determines whether `AudioPlayer.enqueue()` can receive each chunk directly or whether chunks need buffering first).
3. Try both `model="gemini-3.1-flash-tts-preview"` and, as a fallback candidate, `model="gemini-2.5-flash-preview-tts"` (older doc references use this name). Confirm which one(s) the account/API key actually has access to. Record the working model name — this becomes the default in config.
4. Print the actual latency for a short (~10 word) synthesis call, streaming and non-streaming, so the "is this fast enough to feel conversational" question has a real number attached in your handoff notes.

**Bail-out condition:** if none of the candidate model names work, or the
response shape is meaningfully different from what's assumed above in a
way that would require restructuring `GeminiTTSProvider`'s interface
(not just an internal parsing tweak), **stop and report back** rather
than guessing at a workaround.

Document your findings as code comments at the top of
`infrastructure/tts/providers/gemini_tts_provider.py`, the same way
`gemini_provider.py`'s existing Phase 0 findings are documented inline —
follow that file's comment style exactly.

Also verify (cheap, no API call needed): confirm `vosk` and `sounddevice`
import cleanly and confirm which pinned versions in
`gemini_speech_project/pyproject.toml` (`vosk>=0.3.30`,
implicit `sounddevice`) are compatible with this project's already-pinned
`numpy==2.5.2` and `pywin32==312`. Add matching pins to `requirements.txt`.

---

## Phase 1 — `TTSProvider` base interface

`infrastructure/tts/base_provider.py`. Zero vendor SDK imports, matching
`infrastructure/llm/base_provider.py`'s own rule.

```python
@dataclass
class SynthesizedAudio:
    pcm_data: bytes
    sample_rate: int
    channels: int
    sample_width: int  # bytes per sample, e.g. 2 for int16
```

```python
class TTSProvider(ABC):
    supports_style_direction: bool = False
    supports_streaming: bool = False

    @abstractmethod
    def synthesize(self, text: str) -> SynthesizedAudio:
        ...

    def synthesize_stream(
        self, text_stream: Iterator[str], on_audio_chunk: Callable[[SynthesizedAudio], None]
    ) -> None:
        """Default: buffer text_stream to naive sentence boundaries
        (scan for '.', '!', '?' followed by whitespace or end-of-stream),
        call synthesize() per complete sentence, invoke on_audio_chunk
        with each result. This lets a non-streaming provider work through
        the same call shape as a real streaming one. Real streaming
        providers override this entirely for lower latency -- they should
        NOT call this default implementation.

        Known limitation, state it in a comment: this naive splitter can
        mis-split on abbreviations/decimals (e.g. "Mr. Smith", "3.5").
        Per design conversation, this is accepted as-is for now --
        revisit only if real dialogue surfaces major mis-splits, do not
        pre-solve it.
        """
        # implement the sentence-boundary buffering here
```

Also add a `RetryableProviderMixin`-style retry helper if `GeminiTTSProvider`
needs one (it will, for the same rate-limit/transient-error reasons
`GeminiProvider` does) — reuse `infrastructure.llm.base_provider.RetryableProviderMixin`
directly rather than duplicating it; it's already provider-agnostic (no
Gemini-specific code in it), so `GeminiTTSProvider` can inherit both
`TTSProvider` and that existing mixin, exactly the way `GeminiProvider`
inherits `LLMProvider` and it.

---

## Phase 2 — `GeminiTTSProvider`

`infrastructure/tts/providers/gemini_tts_provider.py`. Implement against
whatever Phase 0 actually confirmed — do not implement against the
assumed shape in this doc without having run Phase 0 first.

- `supports_style_direction = True` (Gemini TTS takes natural-language
  style instructions in the prompt text itself, per the docs — e.g.
  "Say cheerfully: ..." — no special API parameter, just prompt
  construction; document this in the class docstring so callers know
  style direction means "prepend/wrap the text," not a config field).
- `supports_streaming = True`, with a real `synthesize_stream()` override
  using the streaming call path confirmed in Phase 0.
- `synthesize()` uses the non-streaming call path.
- Constructor accepts an optional `genai.Client` (default: construct its
  own), same pattern as `GeminiProvider.__init__`.
- Config-driven model name and voice name (see Config section) — do not
  hardcode `"Kore"` or the model string outside of config defaults.
- Retry wrapped via the shared `RetryableProviderMixin`, same
  `_is_retryable_error`/`_extract_retry_delay` shape as `GeminiProvider`.

---

## Phase 3 — Port STT engine files

Copy `gemini_speech_project/src/gemini_speech/recognizer.py` →
`infrastructure/stt/recognizer.py`, and `.../assembler.py` →
`infrastructure/stt/assembler.py`. Required adaptations, not a verbatim
copy:

- Replace `print(..., file=sys.stderr)` calls with `infrastructure.logger.log(..., level="warning")` / `level="error"`, matching this project's logging convention throughout (see `CLAUDE.md`'s Logging Guidelines — no manual `[ModuleName]` prefixes, the logger infers it from `MODULE_NAME`/file registry).
- Add a `MODULE_NAME = "SpeechRecognizer"` (and similarly for the
  assembler) at module level so `infrastructure/logger/logger.py`'s
  `REGISTRY`-based attribution works. Add both to `REGISTRY` in
  `infrastructure/logger/logger.py` following the existing dict shape
  (pick unused colors from the existing palette).
- `SpeechRecognizer.__init__` currently raises `FileNotFoundError` if the
  Vosk model directory is missing. **Keep the raise** (callers need to
  know), but the caller (`VoiceInputController`, Phase 5) must catch it
  and degrade non-fatally — log a warning, disable/hide the mic button,
  do not crash `AllyCore` or the GUI. This matches the existing pattern
  for a missing calibrated layout directory (`build_screen_layouts`) —
  a missing optional local asset is a logged, non-fatal state throughout
  this codebase, not an exception that propagates.
- `VOSK_MODEL_PATH` and `MIC_SAMPLE_RATE` currently come from
  `gemini_speech/config.py`. Replace with reads from
  `cabinet.configs.config_manager.load_user_config()` (new keys —
  see Config section), matching how every other component in this
  codebase sources its tunables. `SpeechRecognizer.__init__` should
  accept `model_path`/`samplerate` as constructor args with config-backed
  defaults, same style as `Scribe.__init__`.
- `UtteranceAssembler` needs no real changes beyond the logging/`MODULE_NAME`
  treatment — it's already dependency-free besides `time`.

---

## Phase 4 — Port `AudioPlayer`

Copy `gemini_speech_project/src/gemini_speech/player.py` →
`infrastructure/tts/audio_player.py`. Adaptations:

- Same logging convention swap as Phase 3.
- `reference_callback` parameter (used by the original for Track-2 AEC)
  is dead weight for this task — **keep the parameter for now** rather
  than stripping it (it costs nothing to leave, and removing it would be
  a gratuitous deviation from the ported source that makes future
  diffing against the standalone repo harder for no benefit), but do not
  wire anything to it in this task. `VoiceOutputController` (Phase 6)
  constructs `AudioPlayer()` with no `reference_callback`.
- Default `samplerate` should read from the new `tts_sample_rate` config
  key (default 24000) rather than importing `TTS_SAMPLE_RATE` from the
  now-nonexistent `gemini_speech.config`.
- This class becomes the **TTS output sink**, not a Live-audio sink — its
  docstring should be updated to reflect that framing (still accurate
  mechanically, just update what it's described as being used for).

---

## Phase 5 — `VoiceInputController` (Qt glue)

`gui_qt/prod/voice_input_controller.py`. A `QObject` subclass (needs to
emit Qt signals cross-thread safely). Owns one `SpeechRecognizer` and one
`UtteranceAssembler`. Runs mic capture on a background thread (Python
`threading.Thread`, daemon, same pattern `AllyCore.send_message()` already
uses for background LLM calls — do not use `QThread` subclassing unless
you have a specific reason to, plain `threading.Thread` + Qt's
automatic cross-thread signal marshaling is sufficient and matches
existing project conventions).

Signals:
```python
class VoiceInputController(QObject):
    transcript_ready = Signal(str)   # finalized transcript text
    listening_state_changed = Signal(bool)  # for mic button visual feedback
    unavailable = Signal(str)  # human-readable reason (e.g. "Vosk model not found at ...")
```

Two modes, read from `config["stt_mode"]` (`"push_to_talk"` default, or
`"open_mic"`):

- **push_to_talk**: `start_listening()` begins capture (recognizer runs,
  audio queue drains); `stop_listening()` is called explicitly on button
  release. On release, force-flush whatever's been recognized so far
  (call the recognizer's finalization the same way `UtteranceAssembler`
  would on a natural pause, but triggered by the release event instead
  of a timeout) and emit `transcript_ready` with the result if non-empty.
  `UtteranceAssembler` is not needed for pause-detection in this mode
  (the button press *is* the boundary signal) but can still be used
  internally to accumulate fragments across the held-down duration if
  that simplifies the implementation — your call, document which you did.
- **open_mic**: continuous background capture while enabled; use
  `UtteranceAssembler` exactly as originally designed (pause-based
  finalization) to emit `transcript_ready` whenever a natural pause is
  detected, without requiring the button to be held.

Construction should attempt `SpeechRecognizer()` inside a `try/except
FileNotFoundError` and emit `unavailable` with the exception's message on
failure, rather than raising out of the constructor — the caller
(`ProdOverlayWindow`) must be able to construct `VoiceInputController`
unconditionally and just get told "not available" rather than needing
its own try/except at the call site.

---

## Phase 6 — `VoiceOutputController`

`brain/reasoning/voice_output_controller.py`. Plain Python class (no Qt
dependency — this listens on `AllyCore`'s existing `EventHook`s, which are
already thread-marshaled the same way every other consumer of them is,
e.g. `CoreBridge`). Constructed and owned by `AllyCore` (see Phase 7 for
exactly where), not by the GUI layer — this keeps voice *output* symmetric
with how every other AllyCore capability (memory, registry, collector) is
owned centrally, even though voice *input* is GUI-owned because it's
button-driven UI state.

```python
class VoiceOutputController:
    def __init__(self, tts_provider: TTSProvider, audio_player: AudioPlayer, enabled: bool = False):
        ...

    def attach(self, core: "AllyCore") -> None:
        """Subscribes to core.on_chat_stream_chunk and
        core.on_chat_stream_finalize. Does NOT subscribe to
        on_analysis_stream_* -- explicitly out of scope, see spec."""
        core.on_chat_stream_chunk.connect(self._on_chunk)
        core.on_chat_stream_finalize.connect(self._on_finalize)

    def set_enabled(self, enabled: bool) -> None:
        ...
```

Behavior:
- Buffer incoming chat-stream text chunks; feed them through
  `tts_provider.synthesize_stream()` (or `synthesize()` per completed
  sentence if the provider isn't a streaming one — same sentence-boundary
  default described in Phase 1) and push each resulting
  `SynthesizedAudio.pcm_data` into `audio_player.enqueue()` as it's
  produced, so speech starts before the full reply has finished
  streaming.
- On `on_chat_stream_reset` (mid-stream retry — this hook already exists),
  **also stop any in-flight synthesis and clear anything already queued
  in `audio_player`** that hasn't started playing yet, mirroring the
  visual reset the GUI text does. Check whether `AudioPlayer` needs a new
  `clear_pending()` method to support this (it currently has no way to
  drop unplayed chunks) — if so, add one; keep it minimal (clear the
  `deque`, don't touch whatever's already mid-playback in the current
  callback frame).
- All work triggered from `EventHook.emit()` callbacks must be wrapped in
  try/except and log on failure, **never raise** — `EventHook.emit()`
  already catches exceptions from subscribers and logs them (see
  `utils/event_hook.py`), so a bug in TTS synthesis cannot break the text
  chat path, but don't rely on that alone; keep failures contained and
  loud in the log rather than silent.
- `set_enabled(False)` must be checked before doing any synthesis work at
  all (not just before playback) so a disabled voice-output config
  doesn't spend API calls it doesn't need to.

---

## Phase 7 — GUI wiring

### `gui_qt/prod/input_bar.py`

Add a mic `QToolButton`, inserted into the existing `QHBoxLayout` **before**
`self._mode_btn` (leftmost position, per Ficus's explicit placement
decision). Object name: `inputBar__micButton`.

```python
self._mic_btn = QToolButton(self)
self._mic_btn.setObjectName("inputBar__micButton")
self._mic_btn.setText("🎤")
self._mic_btn.setToolTip("Push and hold to talk" or "Click to toggle listening" — pick based on stt_mode passed to constructor
layout.insertWidget(0, self._mic_btn)
```

`InputBar.__init__` takes a new constructor arg, `stt_mode: Literal["push_to_talk", "open_mic"] = "push_to_talk"`,
sourced by the caller (`ProdOverlayWindow`) from config. Wire the button
based on that:

- **push_to_talk**: connect `self._mic_btn.pressed` → emit a new signal
  `mic_pressed = Signal()`; connect `self._mic_btn.released` → emit
  `mic_released = Signal()`. Do not make it `setCheckable`.
- **open_mic**: `self._mic_btn.setCheckable(True)`; connect `self._mic_btn.toggled`
  → emit a new signal `mic_toggled = Signal(bool)`.

Add a public slot `on_transcript_ready(self, text: str) -> None` that
populates `self._text_edit` with `text` and calls the existing
`self._handle_send()` (reusing it exactly as typed-input does — do not
duplicate its logic). Add a public slot
`on_listening_state_changed(self, listening: bool) -> None` that swaps
`self._mic_btn`'s text/icon (e.g. `"🎤"` ↔ `"🔴"`) so the player has visual
confirmation the mic is live — follow the existing emoji-icon convention
already used for every other button in this file, don't introduce a real
icon asset.

Add a public method `set_mic_available(self, available: bool, reason: str = "") -> None`
that disables the button and sets its tooltip to `reason` when `False`
(used when `VoiceInputController` emits `unavailable`).

### `gui_qt/prod/overlay_window.py`

- Change `self._docked_width = 340` → `372` (room for the new mic
  button — one more `QToolButton` at roughly the same width as the
  existing `_expand_btn`/`_mode_btn`, ~32px). Change
  `self._expanded_max_width = 560` → `592` (same delta, keeps the
  expanded/docked ratio consistent). If your actual measured button
  width differs meaningfully from 32px once built, adjust both numbers
  to match rather than leaving a mismatched gap — the goal is "no more
  cramped than today," not these exact numbers.
- In `ProdOverlayWindow.__init__`, after constructing `self._input_bar`,
  construct `self._voice_input_controller = VoiceInputController(...)`
  reading `stt_mode` from `cabinet.configs.config_manager.load_user_config()`.
  Connect:
  - `self._voice_input_controller.transcript_ready` → `self._input_bar.on_transcript_ready`
  - `self._voice_input_controller.listening_state_changed` → `self._input_bar.on_listening_state_changed`
  - `self._voice_input_controller.unavailable` → a lambda calling `self._input_bar.set_mic_available(False, reason)`
  - `self._input_bar.mic_pressed` → `self._voice_input_controller.start_listening` (only relevant in push_to_talk mode; connecting it unconditionally is fine since the controller itself no-ops appropriately based on its own mode)
  - `self._input_bar.mic_released` → `self._voice_input_controller.stop_listening`
  - `self._input_bar.mic_toggled` → `self._voice_input_controller.set_open_mic_enabled` (add this method to the controller for the open_mic case — toggled True starts, False stops)
- `VoiceOutputController` is owned by `AllyCore`, not `ProdOverlayWindow`
  — see below for exactly where it's constructed. `overlay_window.py`
  doesn't need to know about it at all; this keeps voice-output wiring
  symmetric with how memory/registry/collector already get set up inside
  `AllyCore.initialize_run()` rather than from the GUI shell.

### `AllyCore` (read-only reference — you are not modifying `core.py` for this, see below)

Do **not** edit `brain/reasoning/core.py` to add `VoiceOutputController`
construction inline in `__init__`/`initialize_run()` — that risks
touching reasoning-critical code for an unrelated feature. Instead,
construct and `attach()` the `VoiceOutputController` from **`main.py`**,
in `_on_core_initialized()` (the Qt entry point), right where the other
post-init wiring already happens (chat message signals, dev window
connection, etc. — you'll see the exact spot, it's a short function).
This keeps `AllyCore` itself completely unaware that voice output exists,
which is the correct blast-radius boundary for an additive feature like
this — `AllyCore` doesn't need a new constructor parameter or attribute
for something that's purely a downstream listener on hooks it already
exposes.

```python
# in main.py's _on_core_initialized(loaded_core), after existing wiring:
from infrastructure.tts.providers.gemini_tts_provider import GeminiTTSProvider
from infrastructure.tts.audio_player import AudioPlayer
from brain.reasoning.voice_output_controller import VoiceOutputController
from cabinet.configs.config_manager import load_user_config

config = load_user_config()
if config.get("voice_output_enabled", False):
    tts_provider = GeminiTTSProvider()
    audio_player = AudioPlayer()
    voice_output = VoiceOutputController(tts_provider, audio_player, enabled=True)
    voice_output.attach(loaded_core)
```

---

## Config keys

Add to `storage/configs/config_manager.py`'s defaults (view the file
first and match its existing style exactly):

| Key | Type | Default | Notes |
| --- | --- | --- | --- |
| `voice_input_enabled` | bool | `False` | Ships off; player opts in |
| `voice_output_enabled` | bool | `False` | Ships off; player opts in |
| `stt_mode` | str | `"push_to_talk"` | `"push_to_talk"` \| `"open_mic"` |
| `stt_model_path` | str | `"model"` | Matches the already-gitignored `model/` convention |
| `stt_sample_rate` | int | `16000` | |
| `tts_model` | str | *(whatever Phase 0 confirmed works)* | Do not hardcode a guess — this must come from your Phase 0 findings |
| `tts_voice` | str | `"Kore"` | |
| `tts_sample_rate` | int | `24000` | Must match whatever `AudioPlayer` is constructed with |

Do **not** wire these into the Settings window UI (Tkinter or Qt) in this
pass — that's a reasonable small follow-up but wasn't asked for here, and
adding UI surface beyond what's specified risks scope creep on a task
that's already fairly large. Config file defaults + `load_user_config()`
reads are sufficient for this pass; a human can hand-edit
`user_config.json` to turn voice on during testing.

---

## Manual verification checklist

After implementation, confirm each of these by hand (no test harness for
these — they need a real mic/speaker/API key):

1. With `voice_input_enabled`/`voice_output_enabled` both `False` (or the
   Vosk model dir absent), the app starts and runs exactly as before —
   mic button is visibly disabled with a sensible tooltip, no crash, no
   log spam.
2. With both enabled and a real Vosk model present: press-and-hold the
   mic button, say something, release — the said text appears in the
   input box, sends automatically, and Ally's normal text reply streams
   in as usual.
3. With `voice_output_enabled = True`: Ally's chat reply is spoken aloud,
   starting before the full text has finished streaming in the feed
   panel (not after).
4. Send a second message while the first reply is still being spoken —
   confirm no crash, and confirm audio either finishes cleanly or is
   interrupted sanely (does not need to be pretty, just must not error).
5. Set `stt_mode` to `"open_mic"`, restart, confirm continuous listening
   with pause-based auto-send works, and confirm the mic button now
   toggles instead of press-and-hold.
6. Run `python -m unittest discover tests` — new tests pass, nothing
   existing breaks.

---

## Notes for Claude's code review

**ZooCode: ignore this entire section — it is not part of the task.**

Things I'll be specifically checking when this comes back:

- Whether `VoiceOutputController` actually stayed decoupled from
  `AllyCore.__init__`/`core.py` as specified, or whether ZooCode found it
  easier to wire it in there directly. If the latter, I need to see
  *why* — it might be a legitimate reason I didn't anticipate (e.g. Qt
  thread-affinity issues with constructing `AudioPlayer`/`sounddevice`
  outside the GUI's init order), or it might be scope creep worth pushing
  back on.
- Whether the Phase 0 script actually got run against a real key and the
  findings are real, or whether the inline comments in
  `gemini_tts_provider.py` just restate this doc's assumptions
  unverified. Check the model name that ended up in the config default —
  if it's `gemini-3.1-flash-tts-preview` with no comment trail explaining
  it was actually confirmed working, that's a red flag matching exactly
  the kind of skipped-verification bug that caused the original
  Interactions-API migration issues.
- Whether `synthesize_stream()`'s default sentence-splitter in
  `TTSProvider` got duplicated instead of reused inside
  `GeminiTTSProvider` — it shouldn't need its own splitting logic at all
  if `supports_streaming=True` and it overrides the method properly using
  the real per-chunk streaming API.
- Whether `EntityRegistry`/`StateSandbox`/anything in the core pipeline
  got touched at all — should be a hard zero here, this task should not
  have needed to touch `brain/state/` or `brain/knowledge/` in any way.
- Whether the push-to-talk release-to-flush logic actually forces
  finalization correctly, or whether it just waits for
  `UtteranceAssembler`'s pause timer regardless of mode (would mean
  push-to-talk doesn't actually feel like push-to-talk — it'd still lag
  by `THINKING_PAUSE_SECONDS` after release, defeating the point of the
  mode distinction).
- Double check `_docked_width`/`_expanded_max_width` numbers were
  actually adjusted based on the real button width rather than left at
  my guessed +32, and that the input bar doesn't look cramped or
  the mic button doesn't get clipped at the smallest supported window
  size.
- Confirm nothing from `gemini_speech_project/` got imported directly
  (`import gemini_speech` or a path-hack sys.path insert) anywhere —
  every used piece should be a genuine copy under `infrastructure/`.
