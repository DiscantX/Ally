import os
import sys
import io
import base64
from PIL import Image
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

with open("introspection_output.txt", "w", encoding="utf-8") as f:
    f.write("=== Proving §1.2 Live Calls with correct model and shapes ===\n")

    from google.genai._gaos.types.interactions.textcontent import TextContent
    from google.genai._gaos.types.interactions.imagecontent import ImageContent

    client = genai.Client()
    model_name = "gemini-3.6-flash"

    # 1. Text-only live call
    try:
        tc = TextContent(type="text", text="Hello from verified text-only test!")
        res1 = client.interactions.create(
            model=model_name,
            input=[tc],
        )
        f.write(f"SUCCESS Text-only call! Response text: {getattr(res1, 'output_text', None) or getattr(res1, 'text', None)}\n")
    except Exception as e:
        f.write(f"FAILED Text-only call: {e!r}\n")

    # 2. Image + Text live call
    try:
        img = Image.new("RGB", (10, 10), color="blue")
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        img_bytes = buffered.getvalue()
        img_b64 = base64.b64encode(img_bytes).decode("utf-8")

        ic = ImageContent(type="image", data=img_b64, mime_type="image/png")
        tc2 = TextContent(type="text", text="Describe this blue image.")

        res2 = client.interactions.create(
            model=model_name,
            input=[ic, tc2],
        )
        f.write(f"SUCCESS Image+Text call! Response text: {getattr(res2, 'output_text', None) or getattr(res2, 'text', None)}\n")
    except Exception as e:
        f.write(f"FAILED Image+Text call: {e!r}\n")

print("Done running live verification script.")
