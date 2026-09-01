"""Standalone diagnostic: live verification of Google GenAI TTS support via client.interactions.

Per the speech phase 1 plan's Phase 0, before writing any provider code we must
verify the real shape of the SDK response (the Interactions API documentation
drifts, and this codebase has been burned by Interactions API shape
assumptions before -- see `docs/ally_decision_log.md` and the sibling script
`debug_raw_interactions_stream.py`).

This script, against a real GOOGLE_API_KEY in the environment, will:

  1. Try both candidate TTS model names and report which one(s) the account
     actually has access to:
       - "gemini-3.1-flash-tts-preview"   (newer, preferred)
       - "gemini-2.5-flash-preview-tts"   (older, fallback per spec)
  2. For each accessible model, call client.interactions.create(...) WITHOUT
     stream=True. Print the full shape of the returned object so the actual
     attribute path to the base64 audio payload is confirmed (docs suggest
     `interaction.output_audio.data` -- confirm that's real, not something
     nested under interaction.candidates[0]).
  3. Call the same request WITH stream=True. Iterate the returned stream and
     print each event's shape so the attribute path to per-chunk audio deltas
     is confirmed (docs suggest `event.event_type == "step.delta"` then
     `event.delta.type == "audio"` then `event.delta.data` -- confirm exactly,
     including whether event_type / delta.type are strings or enums).
  4. Time each call (wall-clock seconds, start-of-call to first-audio-byte
     for streaming, or to the full response for non-streaming) on a short
     ~10-word prompt so the "is this fast enough to feel conversational"
     question has a real number attached in the handoff notes.

Usage:
    python tools/debug_raw_tts_stream.py
    python tools/debug_raw_tts_stream.py --text "Your custom prompt here."
    python tools/debug_raw_tts_stream.py --skip-non-streaming
    python tools/debug_raw_tts_stream.py --skip-streaming

If GOOGLE_API_KEY is not set in the environment (or in a .env in the project
root) the script will print a clear notice and exit without making any
network calls -- this matches the spec's intent: the script is "temporary
but committed," and re-running it on a machine without a key must not
crash, it must just no-op with a useful message.
"""

from __future__ import annotations

import argparse
import base64
import inspect
import os
import sys
import time
import traceback
from typing import Any, Iterable, Optional

# Force UTF-8 stdout on Windows -- matches sibling debuggers.
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv

    load_dotenv(override=True)
except Exception as exc:  # pragma: no cover -- dotenv should always be available
    print(f"[warn] could not import python-dotenv: {exc!r}", file=sys.stderr)

from google import genai  # noqa: E402  (import after dotenv)


# Candidate TTS models to test, in order of preference. The first one that
# responds successfully (200 + audio data) becomes the recommended default
# in the phase 1 config; the other is recorded as a known fallback so the
# config default can be swapped without re-running this script.
CANDIDATE_MODELS: tuple[str, ...] = (
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
)

# Voices documented as available on both candidate models. We pick Kore
# (matches the config default the spec already locked in), and one more
# (Charon) as a sanity check that voice is a real parameter and not silently
# ignored.
CANDIDATE_VOICES: tuple[str, ...] = ("Kore", "Charon")

DEFAULT_PROMPT = "Say cheerfully: testing one two three four five six seven."


def _print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _summarize_audio_blob(blob: Any) -> Optional[str]:
    """Best-effort summary of an audio payload found anywhere on an object.

    Returns a short human-readable string describing the audio (or None if
    nothing looked like audio). We keep this self-contained so we can
    apply it to both the non-streaming response and each streaming event
    without depending on internal SDK types.
    """
    if blob is None:
        return None
    # Direct bytes
    if isinstance(blob, (bytes, bytearray)):
        return f"raw bytes, len={len(blob)}"
    # Base64 string
    if isinstance(blob, str):
        # Heuristic: a base64 payload of meaningful length.
        if len(blob) > 32 and blob.strip()[:64].isalnum() or "=" in blob:
            try:
                decoded = base64.b64decode(blob, validate=False)
                return f"base64 string, len={len(blob)} (decoded ~{len(decoded)} bytes)"
            except Exception:
                return f"string of len={len(blob)} (not decodable as base64)"
        return f"string of len={len(blob)}"
    # Object with `.data`
    data_attr = getattr(blob, "data", None)
    if data_attr is not None and data_attr is not blob:
        inner = _summarize_audio_blob(data_attr)
        if inner is not None:
            mime = getattr(blob, "mime_type", None) or getattr(blob, "mimeType", None)
            return f"object.data -> {inner}" + (f" (mime_type={mime!r})" if mime else "")
    return None


def _find_audio_payload(obj: Any, _depth: int = 0) -> Optional[str]:
    """Walk an arbitrary object looking for what *looks* like an audio payload.

    Used to confirm whether the documented path (`interaction.output_audio.data`)
    is the real one or whether the payload is buried under a different
    attribute (e.g. `interaction.candidates[0].content.parts[0].inline_data`).
    We cap recursion to avoid pathological cycles.
    """
    if _depth > 6 or obj is None:
        return None
    summary = _summarize_audio_blob(obj)
    if summary is not None:
        return summary
    # Try common shapes:
    for attr in ("output_audio", "audio", "inline_data", "audio_data"):
        if hasattr(obj, attr):
            child = getattr(obj, attr)
            if child is not None and child is not obj:
                summary = _summarize_audio_blob(child) or _find_audio_payload(child, _depth + 1)
                if summary:
                    return f"{attr} -> {summary}"
    # Candidates list shape (legacy Gemini API path)
    candidates = getattr(obj, "candidates", None)
    if candidates:
        for idx, cand in enumerate(candidates):
            if cand is None:
                continue
            content = getattr(cand, "content", None)
            if content is not None:
                parts = getattr(content, "parts", None)
                if parts:
                    for pidx, part in enumerate(parts):
                        if part is None:
                            continue
                        inline = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
                        if inline is not None:
                            summary = _summarize_audio_blob(inline)
                            if summary:
                                return f"candidates[{idx}].content.parts[{pidx}].inline_data -> {summary}"
    return None


def _describe_event(event: Any) -> str:
    """One-line description of a streamed event's shape -- safe to call
    on anything, used to dump every event from the streaming response.
    """
    parts: list[str] = []
    et = getattr(event, "event_type", None)
    if et is not None:
        parts.append(f"event_type={et!r}")
    delta = getattr(event, "delta", None)
    if delta is not None:
        dtype = getattr(delta, "type", None)
        ddata = getattr(delta, "data", None)
        parts.append(f"delta.type={dtype!r}")
        if ddata is not None:
            audio_summary = _summarize_audio_blob(ddata)
            if audio_summary:
                parts.append(f"delta.data={audio_summary}")
            else:
                parts.append(f"delta.data type={type(ddata).__name__}")
    # Also report the "real" audio path if it doesn't live under delta:
    if delta is None or getattr(delta, "data", None) is None:
        any_audio = _find_audio_payload(event)
        if any_audio:
            parts.append(f"audio@ {any_audio}")
    # If we still have no useful info, dump the attribute keys for visibility.
    if not parts:
        try:
            keys = [a for a in dir(event) if not a.startswith("_")]
            parts.append(f"attrs={keys[:30]}")
        except Exception:
            parts.append("(could not introspect)")
    return "  ".join(parts)


def _try_non_streaming(client: genai.Client, model: str, prompt: str) -> dict[str, Any]:
    """Call interactions.create without stream=True; record shape + latency."""
    print(f"  -> non-streaming call (model={model!r}) ...")
    t0 = time.perf_counter()
    try:
        response = client.interactions.create(
            model=model,
            input=prompt,
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": "Kore"}]},
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"  !! call failed after {elapsed:.3f}s: {type(exc).__name__}: {exc}")
        return {"ok": False, "elapsed_s": elapsed, "error": repr(exc)}

    elapsed = time.perf_counter() - t0
    print(f"  -> call returned in {elapsed:.3f}s")
    print(f"  -> response type: {type(response).__name__}")

    # Dump top-level attributes so we can see the actual shape.
    try:
        public_attrs = [a for a in dir(response) if not a.startswith("_")]
        print(f"  -> public attrs: {public_attrs}")
    except Exception:
        pass

    # Print repr of output_audio if it exists (the spec's documented path).
    if hasattr(response, "output_audio"):
        oa = response.output_audio
        print(f"  -> response.output_audio: {oa!r}")
        if oa is not None:
            for sub in ("data", "mime_type", "mimeType", "sample_rate_hz", "channels"):
                if hasattr(oa, sub):
                    val = getattr(oa, sub)
                    if isinstance(val, (bytes, bytearray)):
                        print(f"       output_audio.{sub}: bytes len={len(val)}")
                    elif isinstance(val, str) and len(val) > 80:
                        print(f"       output_audio.{sub}: str len={len(val)} (head={val[:32]!r}...)")
                    else:
                        print(f"       output_audio.{sub}: {val!r}")

    audio_path = _find_audio_payload(response)
    print(f"  -> audio payload found at: {audio_path!r}")

    # Stash a hint of the audio size for the handoff notes.
    audio_size_hint: Optional[int] = None
    if hasattr(response, "output_audio") and response.output_audio is not None:
        data = getattr(response.output_audio, "data", None)
        if isinstance(data, (bytes, bytearray)):
            audio_size_hint = len(data)
        elif isinstance(data, str):
            try:
                audio_size_hint = len(base64.b64decode(data, validate=False))
            except Exception:
                pass
    return {
        "ok": True,
        "elapsed_s": elapsed,
        "audio_path": audio_path,
        "audio_size_hint": audio_size_hint,
        "type_name": type(response).__name__,
    }


def _try_streaming(client: genai.Client, model: str, prompt: str) -> dict[str, Any]:
    """Call interactions.create with stream=True; record per-event shape + latency."""
    print(f"  -> streaming call (model={model!r}) ...")
    t0 = time.perf_counter()
    first_audio_at: Optional[float] = None
    try:
        stream = client.interactions.create(
            model=model,
            input=prompt,
            stream=True,
            response_format={"type": "audio"},
            generation_config={"speech_config": [{"voice": "Kore"}]},
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        print(f"  !! stream creation failed after {elapsed:.3f}s: {type(exc).__name__}: {exc}")
        return {"ok": False, "elapsed_s": elapsed, "error": repr(exc)}

    event_count = 0
    audio_event_count = 0
    events_summary: list[str] = []
    total_decoded_audio_bytes = 0
    for event in stream:
        event_count += 1
        desc = _describe_event(event)
        events_summary.append(desc)
        # Track first-audio latency
        if first_audio_at is None:
            delta = getattr(event, "delta", None)
            data = getattr(delta, "data", None) if delta is not None else None
            if data is not None and _summarize_audio_blob(data) is not None:
                first_audio_at = time.perf_counter() - t0
                audio_event_count += 1
                # Try to add to a size tally too
                if isinstance(data, (bytes, bytearray)):
                    total_decoded_audio_bytes += len(data)
                elif isinstance(data, str):
                    try:
                        total_decoded_audio_bytes += len(base64.b64decode(data, validate=False))
                    except Exception:
                        pass
        elif getattr(getattr(event, "delta", None), "data", None) is not None:
            audio_event_count += 1
            data = event.delta.data
            if isinstance(data, (bytes, bytearray)):
                total_decoded_audio_bytes += len(data)
            elif isinstance(data, str):
                try:
                    total_decoded_audio_bytes += len(base64.b64decode(data, validate=False))
                except Exception:
                    pass

    total_elapsed = time.perf_counter() - t0
    print(f"  -> stream completed in {total_elapsed:.3f}s; "
          f"{event_count} events, {audio_event_count} with audio data")
    if first_audio_at is not None:
        print(f"  -> first audio chunk arrived at {first_audio_at:.3f}s (time-to-first-audio)")
    else:
        print(f"  -> !! no audio chunks were observed in the stream (no delta.data found)")
    print(f"  -> total decoded audio bytes across chunks: {total_decoded_audio_bytes}")
    print(f"  -> event-by-event summary:")
    for idx, desc in enumerate(events_summary):
        # Truncate very long lines.
        print(f"     [{idx:>3}] {desc[:240]}")

    return {
        "ok": True,
        "total_elapsed_s": total_elapsed,
        "first_audio_at_s": first_audio_at,
        "event_count": event_count,
        "audio_event_count": audio_event_count,
        "total_audio_bytes": total_decoded_audio_bytes,
        "events_summary": events_summary,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Raw TTS diagnostic dumper.")
    parser.add_argument("--text", default=DEFAULT_PROMPT,
                        help="Prompt to synthesize (default: short test phrase).")
    parser.add_argument("--model", action="append", default=None,
                        help="Restrict to specific model(s); repeatable. "
                             f"Default: all of {list(CANDIDATE_MODELS)}.")
    parser.add_argument("--skip-non-streaming", action="store_true")
    parser.add_argument("--skip-streaming", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        _print_section("GOOGLE_API_KEY not found")
        print("No GOOGLE_API_KEY (or GEMINI_API_KEY) in environment / .env.")
        print("This script is the spec's mandatory Phase 0 live-SDK verification.")
        print("It will not make any network calls and will exit 0 so CI/scheduled")
        print("runs that don't have a key still pass cleanly -- run it locally")
        print("with a real key to record the actual response shape into the")
        print("Phase 0 findings block of `infrastructure/tts/providers/gemini_tts_provider.py`.")
        return 0

    _print_section("0. Introspection of client.interactions (TTS-relevant bits)")
    client = genai.Client()
    print(f"hasattr(client, 'interactions'): {hasattr(client, 'interactions')}")
    try:
        sig = inspect.signature(client.interactions.create)
        print(f"inspect.signature(client.interactions.create): {sig}")
    except Exception as exc:
        print(f"Could not inspect signature: {exc!r}")

    models_to_try = args.model if args.model else list(CANDIDATE_MODELS)

    # Final results table -- printed at the end so it's easy to copy into
    # the provider file's Phase 0 findings comment.
    results: list[dict[str, Any]] = []

    for model in models_to_try:
        _print_section(f"Model: {model}")

        if not args.skip_non_streaming:
            print("\n--- NON-STREAMING call ---")
            ns_result = _try_non_streaming(client, model, args.text)
            results.append({"model": model, "mode": "non_streaming", **ns_result})
        else:
            print("\n--- NON-STREAMING call: SKIPPED ---")

        if not args.skip_streaming:
            print("\n--- STREAMING call ---")
            s_result = _try_streaming(client, model, args.text)
            results.append({"model": model, "mode": "streaming", **s_result})
        else:
            print("\n--- STREAMING call: SKIPPED ---")

    _print_section("Summary (copy this into gemini_tts_provider.py's Phase 0 block)")
    for r in results:
        line = f"model={r['model']!r} mode={r['mode']!r} ok={r.get('ok')!r}"
        for k, v in r.items():
            if k in ("model", "mode", "ok", "events_summary"):
                continue
            line += f" {k}={v!r}"
        print(line)
    print()
    print("Reminder: paste the exact attribute paths discovered (audio payload")
    print("location, event shapes, latency numbers) into the Phase 0 findings")
    print("comment at the top of `infrastructure/tts/providers/gemini_tts_provider.py`")
    print("before writing the provider implementation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
