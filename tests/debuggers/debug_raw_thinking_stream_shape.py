"""Standalone diagnostic: Phase 0 live verification of thinking stream shape and SDK version.

Usage:
    python debug_raw_thinking_stream_shape.py
"""

import sys
import io
import inspect
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
from cabinet.configs.config_manager import load_user_config, get_model
from brain.knowledge.schema.schema import AllyOutput

# Force UTF-8 stdout on Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv(override=True)

def main() -> None:
    print("=== Step 1: Check SDK version ==")
    try:
        import google.genai as g
        print(f"google-genai version: {getattr(g, '__version__', '(no __version__)')}")
        print(f"google-genai module file: {getattr(g, '__file__', '(no __file__)')}")
    except Exception as e:
        print(f"Error checking SDK version: {e}")

    client = genai.Client()
    config = load_user_config()
    model_name = get_model("ally_model", config)
    print(f"Resolved ally_model name from config: {model_name!r}")

    prompt = (
        "Solve this multi-step logic puzzle step by step: "
        "Alice, Bob, and Charlie are sitting in a row. "
        "Alice is to the left of Bob. Charlie is to the right of Bob. "
        "Who is in the middle? Walk through your reasoning in detail."
    )

    print(f"\n=== Step 2: Real live streaming call with thinking_summaries='auto' ===")
    try:
        stream = client.interactions.create(
            model=model_name,
            input=prompt,
            stream=True,
            generation_config={"thinking_summaries": "auto"},
        )
        event_count = 0
        for event in stream:
            event_count += 1
            print(f"\n--- Event #{event_count} ---")
            print(f"event_type={getattr(event, 'event_type', None)!r}")
            print(f"raw event repr: {event!r}")
            delta = getattr(event, "delta", None)
            if delta is not None:
                print(f"  delta.type={getattr(delta, 'type', None)!r}")
                content = getattr(delta, "content", None)
                print(f"  delta.content={content!r} (type={type(content)})")
                if content is not None:
                    print(f"    content.type={getattr(content, 'type', None)!r}")
                    print(f"    content.text={getattr(content, 'text', None)!r}")
                print(f"  delta.text={getattr(delta, 'text', None)!r}")
        print(f"Streaming call completed. Total events: {event_count}")
    except Exception as e:
        print(f"Streaming call failed: {e!r}")

    print(f"\n=== Step 3: Repeat with response_format (structured output) set ===")
    try:
        schema = AllyOutput.model_json_schema()
        stream = stream_with_fmt = client.interactions.create(
            model=model_name,
            input="Analyze game state: You are exploring a dungeon. Answer in json.",
            stream=True,
            generation_config={"thinking_summaries": "auto"},
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        )
        event_count_fmt = 0
        thought_events_fmt = 0
        for event in stream_with_fmt:
            event_count_fmt += 1
            delta = getattr(event, "delta", None)
            if delta is not None:
                d_type = getattr(delta, "type", None)
                if d_type == "thought_summary":
                    thought_events_fmt += 1
                content = getattr(delta, "content", None)
                print(f"Structured stream event #{event_count_fmt}: delta.type={d_type!r}, content={content!r}")
        print(f"Structured stream completed. Total events: {event_count_fmt}, thought events: {thought_events_fmt}")
    except Exception as e:
        print(f"Structured stream call failed: {e!r}")

    print(f"\n=== Step 4: Confirm multimodal input shape ===")
    try:
        from google.genai._gaos.types.interactions.textcontent import TextContent
        from google.genai._gaos.types.interactions.imagecontent import ImageContent
        print(f"TextContent.model_fields: {TextContent.model_fields}")
        print(f"ImageContent.model_fields: {ImageContent.model_fields}")
    except Exception as e:
        print(f"Multimodal input shape check failed: {e!r}")

if __name__ == "__main__":
    main()
