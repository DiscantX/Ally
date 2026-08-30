import os
from google import genai
from google.genai import types

print("=== INSPECTING CLIENT INTERACTIONS ==")
client = genai.Client()
print("client.interactions attributes/methods:", dir(client.interactions))

try:
    from google.genai._gaos.types.interactions.turn import Turn
    from google.genai._gaos.types.interactions.textcontent import TextContent
    from google.genai._gaos.types.interactions.imagecontent import ImageContent
    
    for cls in (Turn, TextContent, ImageContent):
        print(f"--- {cls.__name__} ---")
        print(cls.model_fields)
        print()
except Exception as e:
    print("Error importing via direct _gaos path:", e)
    # Search for Turn, TextContent, ImageContent in types or google.genai
    import inspect
    for name, obj in inspect.getmembers(types):
        if any(k in name.lower() for k in ["turn", "content", "interaction"]):
            print(f"types.{name}: {obj}")
            if inspect.isclass(obj):
                try:
                    print("  model_fields:", obj.model_fields)
                except Exception:
                    pass
