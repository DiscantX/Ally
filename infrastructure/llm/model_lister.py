import json
from google import genai
from infrastructure.logger import log, timed
from dotenv import load_dotenv

load_dotenv(override=True)

@timed
def get_available_models() -> list[str]:
    """Fetch models dynamically from Gemini SDK, fallback to static file on error."""
    try:
        client = genai.Client()
        models_list = list(client.models.list())
        
        # Filter for models that likely support text generation, then strip "models/"
        models = [
            m.name.replace("models/", "") for m in models_list
            if "gemini" in m.name and "embedding" not in m.name and "veo" not in m.name and "aqa" not in m.name
        ]
        return sorted(models)
    except Exception as e:
        log("Failed to fetch models dynamically: {e}. Falling back to static config.", e=e)
        try:
            with open("configs/supported_models.json", "r") as f:
                return json.load(f)["supported_models"]
        except Exception as e_static:
            log("Failed to load fallback static config: {e_static}", e_static=e_static)
            return ["gemini-3.5-flash-lite"] # Absolute minimal fallback
