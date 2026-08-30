"""Standalone diagnostic: live verification of client.interactions API (§2 of migration spec).

Performs all 5 verification checks against the real Google GenAI SDK (v2.19.0+):
1. Text prompt + streaming (stream=True) with generation_config={"thinking_summaries": "auto"}.
2. Critical Composition Check: Combining thinking_summaries with response_format (AllyOutput schema).
3. Thinking Amount Control: Testing thinking_level / thinking_config inside generation_config.
4. Multimodal Input Check: Testing multimodal input with client.interactions.create.
5. Exception Type Check: Calling with an invalid model name ("not-a-real-model") and catching exceptions.

Usage:
    python debug_raw_interactions_stream.py
"""

import argparse
import inspect
import sys
import io
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors
from PIL import Image
from brain.knowledge.schema.schema import AllyOutput

# Force UTF-8 stdout on Windows
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

load_dotenv(override=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw Interactions API diagnostic dumper.")
    parser.add_argument("--model", default="gemini-3.6-flash", help="Model name to call.")
    args = parser.parse_args()

    client = genai.Client()

    print("=== 0. Introspection of client.interactions ===")
    print(f"hasattr(client, 'interactions'): {hasattr(client, 'interactions')}")
    if hasattr(client, "interactions"):
        print(f"dir(client.interactions): {dir(client.interactions)}")
        try:
            sig = inspect.signature(client.interactions.create)
            print(f"inspect.signature(client.interactions.create): {sig}")
        except Exception as e:
            print(f"Could not inspect signature: {e}")

    # Check 1: Text prompt + streaming with thinking_summaries="auto"
    print("\n=== Check 1: Text prompt + streaming with thinking_summaries='auto' ===")
    try:
        stream = client.interactions.create(
            model=args.model,
            input="Think step by step about why the sky is blue. Keep it brief.",
            stream=True,
            generation_config={"thinking_summaries": "auto"},
        )
        c_count = 0
        for event in stream:
            c_count += 1
            if hasattr(event, "delta") and event.delta:
                print(f"  delta type: {getattr(event.delta, 'type', None)}")
        print(f"Check 1 completed. Total events received: {c_count}")
    except Exception as e:
        print(f"Check 1 failed with exception: {e!r}")

    # Check 2: Critical Composition Check (thinking_summaries + response_format with AllyOutput schema)
    print("\n=== Check 2: Critical Composition Check (thinking_summaries + response_format schema) ===")
    try:
        schema = AllyOutput.model_json_schema()
        stream = client.interactions.create(
            model=args.model,
            input="Analyze the game state: You are exploring a dungeon. Speak to the player.",
            stream=True,
            generation_config={"thinking_summaries": "auto"},
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
        )
        c_count = 0
        for event in stream:
            c_count += 1
            if hasattr(event, "delta") and event.delta:
                print(f"  Composition Event #{c_count} delta type: {getattr(event.delta, 'type', None)}")
        print(f"Check 2 (Composition) completed successfully! Total events received: {c_count}")
    except Exception as e:
        print(f"Check 2 (Composition) failed with exception: {e!r}")

    # Check 3: Thinking Amount Control
    print("\n=== Check 3: Thinking Amount Control ===")
    for config_variant in [
        {"thinking_summaries": "auto", "thinking_level": "high"},
        {"thinking_summaries": "auto", "thinking_config": {"thinking_level": "high"}},
    ]:
        print(f"Testing generation_config={config_variant}")
        try:
            res = client.interactions.create(
                model=args.model,
                input="What is 2+2? Think carefully.",
                generation_config=config_variant,
            )
            print(f"  Success with config {config_variant}!")
        except Exception as e:
            print(f"  Failed with config {config_variant}: {e!r}")

    # Check 4: Multimodal Input Check
    print("\n=== Check 4: Multimodal Input Check ===")
    img = Image.new("RGB", (10, 10), color="red")
    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    img_bytes = buffered.getvalue()

    for variant_name, multimodal_input in [
        ("types.Part.from_bytes", [types.Part.from_bytes(data=img_bytes, mime_type="image/png"), "Describe this red image."]),
        ("dict_image", [{"type": "image", "source": {"bytes": img_bytes, "mime_type": "image/png"}}, {"type": "text", "text": "Describe this red image."}]),
    ]:
        print(f"Testing multimodal variant: {variant_name}")
        try:
            res = client.interactions.create(
                model=args.model,
                input=multimodal_input,
                generation_config={"thinking_summaries": "auto"},
            )
            print(f"  Success with {variant_name}! Response: {res}")
            break
        except Exception as e:
            print(f"  Failed with {variant_name}: {e!r}")

    # Check 5: Exception Type Check
    print("\n=== Check 5: Exception Type Check ===")
    try:
        client.interactions.create(
            model="not-a-real-model",
            input="Hello",
        )
        print("Unexpectedly succeeded with bad model name!")
    except Exception as e:
        print(f"Caught expected exception for bad model: type={type(e)}, repr={e!r}")
        print(f"Is instance of errors.ClientError / errors.ServerError? {isinstance(e, (errors.ClientError, errors.ServerError))}")


if __name__ == "__main__":
    main()
