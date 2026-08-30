"""Standalone diagnostic: dumps the RAW shape of what the installed
google-genai SDK actually returns from a streaming call with
include_thoughts=True, with zero abstraction in between.

This is deliberately NOT using GeminiProvider.generate_structured_stream()
-- the whole point is to bypass that method entirely and see the raw
chunk/part objects the SDK hands back, since the bug we're chasing is
"the wrapper claims to work but nothing visibly streams." If the wrapper
turns out to be wrong about attribute names (part.thought, part.text) or
method names (generate_content_stream), this script will show that
directly instead of silently swallowing it the way a mocked unit test
would.

Never touches AllyCore, MemoryDB, or any production call path. Safe to
run standalone, doesn't need a screenshot or game running.

Usage:
    python debug_raw_stream.py
    python debug_raw_stream.py --thinking-level high
    python debug_raw_stream.py --model gemini-3.5-flash-lite --thinking-level high
"""

import argparse
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv(override=True)


class DummySchema(BaseModel):
    """Trivial structured-output schema -- just enough to force
    response_mime_type=application/json + response_schema, matching the
    exact config shape generate_structured_stream() uses in production.
    We don't care about the answer's content, only whether/how thought
    chunks show up on the way there."""
    answer: str
    reasoning_summary: str


PROMPT = (
    "Think step by step about which is heavier: a kilogram of feathers "
    "or a kilogram of steel. Walk through your reasoning before answering. "
    "Then answer in the 'answer' field, and put a one-sentence summary of "
    "your reasoning in 'reasoning_summary'."
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw Gemini stream chunk dumper.")
    parser.add_argument("--model", default="gemini-3.5-flash-lite", help="Model name to call.")
    parser.add_argument(
        "--thinking-level", default="high",
        choices=["minimal", "low", "medium", "high"],
        help="Thinking level to request. Defaults to 'high' -- some lower "
             "levels may not produce any thought parts at all, which would "
             "look identical to 'streaming is broken' but isn't.",
    )
    args = parser.parse_args()

    print(f"--- SDK / package info ---")
    try:
        import google.genai as genai_pkg
        print(f"google-genai module file: {genai_pkg.__file__}")
        print(f"google-genai version attr: {getattr(genai_pkg, '__version__', '(no __version__ attr)')}")
    except Exception as e:
        print(f"Could not introspect google-genai package: {e}")

    print(f"\nhasattr(types, 'ThinkingConfig'): {hasattr(types, 'ThinkingConfig')}")
    if hasattr(types, "ThinkingConfig"):
        try:
            import inspect
            sig = inspect.signature(types.ThinkingConfig.__init__)
            print(f"ThinkingConfig.__init__ signature: {sig}")
        except Exception as e:
            print(f"Could not inspect ThinkingConfig signature: {e}")

    print(f"\nhasattr(types, 'ThinkingLevel'): {hasattr(types, 'ThinkingLevel')}")
    if hasattr(types, "ThinkingLevel"):
        try:
            print(f"ThinkingLevel members: {[item.name for item in types.ThinkingLevel]}")
        except Exception as e:
            print(f"Could not enumerate ThinkingLevel: {e}")

    client = genai.Client()

    print(f"\nhasattr(client.models, 'generate_content_stream'): "
          f"{hasattr(client.models, 'generate_content_stream')}")
    # List every attribute on client.models that looks stream-related,
    # in case the real method has a different name in this SDK version.
    stream_like = [a for a in dir(client.models) if "stream" in a.lower()]
    print(f"Attributes on client.models containing 'stream': {stream_like}")

    thinking_level_map = {
        "minimal": getattr(types.ThinkingLevel, "MINIMAL", None) if hasattr(types, "ThinkingLevel") else None,
        "low": getattr(types.ThinkingLevel, "LOW", None) if hasattr(types, "ThinkingLevel") else None,
        "medium": getattr(types.ThinkingLevel, "MEDIUM", None) if hasattr(types, "ThinkingLevel") else None,
        "high": getattr(types.ThinkingLevel, "HIGH", None) if hasattr(types, "ThinkingLevel") else None,
    }
    lvl = thinking_level_map.get(args.thinking_level)
    print(f"\nResolved ThinkingLevel for '{args.thinking_level}': {lvl!r}")

    try:
        thinking_config = types.ThinkingConfig(thinking_level=lvl, include_thoughts=True)
    except Exception as e:
        print(f"\n!!! Failed to construct ThinkingConfig(thinking_level=..., include_thoughts=True): {e}")
        print("This alone could be the whole bug -- if this call itself raises "
              "or silently drops include_thoughts, no thought parts will ever "
              "come back regardless of what the streaming loop does.")
        sys.exit(1)

    print(f"\n--- Calling {args.model} with model={args.model}, "
          f"thinking_level={args.thinking_level} ---\n")

    try:
        stream = client.models.generate_content_stream(
            model=args.model,
            contents=[PROMPT],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=DummySchema,
                thinking_config=thinking_config,
            ),
        )
    except Exception as e:
        print(f"!!! generate_content_stream() call itself raised: {e}")
        print("If this is an AttributeError on client.models, the method name "
              "has changed in this SDK version -- check the 'stream' attribute "
              "list printed above for the real name.")
        sys.exit(1)

    chunk_count = 0
    thought_chunk_count = 0
    content_chunk_count = 0
    empty_chunk_count = 0

    for chunk in stream:
        chunk_count += 1
        print(f"\n=== chunk #{chunk_count} ===")
        print(f"  raw repr: {chunk!r}")

        if not chunk.candidates:
            print("  (no candidates on this chunk)")
            empty_chunk_count += 1
            continue

        candidate = chunk.candidates[0]
        if not candidate.content or not candidate.content.parts:
            print("  (candidate has no content.parts)")
            empty_chunk_count += 1
            continue

        for i, part in enumerate(candidate.content.parts):
            is_thought = getattr(part, "thought", "NO_THOUGHT_ATTR")
            text = getattr(part, "text", "NO_TEXT_ATTR")
            text_preview = (text[:80] + "...") if isinstance(text, str) and len(text) > 80 else text
            print(f"  part[{i}]: thought={is_thought!r}  text={text_preview!r}")

            if is_thought is True:
                thought_chunk_count += 1
            elif isinstance(text, str) and text:
                content_chunk_count += 1

    print(f"\n--- SUMMARY ---")
    print(f"Total chunks received: {chunk_count}")
    print(f"Chunks with no usable candidate/content: {empty_chunk_count}")
    print(f"Parts with thought=True: {thought_chunk_count}")
    print(f"Parts treated as content (non-thought, non-empty text): {content_chunk_count}")

    if chunk_count == 0:
        print("\n!!! Zero chunks received at all -- the stream iterator produced "
              "nothing. Check API key / network / model name first.")
    elif thought_chunk_count == 0:
        print("\n!!! Chunks arrived, but none had thought=True. Either:")
        print("    (a) this SDK/model doesn't expose part.thought the way we expect, or")
        print("    (b) include_thoughts isn't actually being honored by the API for "
              "this model/thinking_level combination, or")
        print("    (c) the model chose not to think for this prompt at this level.")
        print("    Try --thinking-level high if you weren't already, and compare "
              "against a model you know supports thinking summaries.")
    else:
        print("\nThought chunks ARE coming back from the SDK. If the production "
              "diagnostic script still shows nothing, the bug is in "
              "GeminiProvider.generate_structured_stream()'s routing/printing "
              "logic, not in the SDK/API layer -- compare its part.thought check "
              "against what's printed above.")


if __name__ == "__main__":
    main()
