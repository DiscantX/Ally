# The following is a suggested code sample to grab free inference models from Hugging Face
# and to make api requests. It has not been tested, nor has it been written to fit in with
# the code bases actual provider architecture. It needs to be properly reviewed, rewritten, and implemented.
# It is currently dead code; nothing connects to it.

# When rewriting, look to the existing base_provider and gemini_provider modules for
# hints on expected architecture aand structure.

import os
from PIL import Image
from huggingface_hub import HfApi, InferenceClient


# 1. Initialize API and Client
# Pull token from environment variable or replace directly
HF_TOKEN = os.getenv("HF_TOKEN", "your_hf_token_here")
api = HfApi(token=HF_TOKEN)
client = InferenceClient(token=HF_TOKEN)

print("🔍 Scanning Hugging Face Hub for warm multimodal models...")

# 2. Programmatically fetch warm, free, multimodal models
# We filter for 'image-text-to-text' (the task ID for Vision LLMs) and ensure they are 'warm'
models = api.list_models(
    filter="image-text-to-text",
    inference="warm",
    sort="downloads",  # Sort by downloads to surface the community's "best" choices
    direction=-1,
    limit=5
)

warm_multimodal_list = [model.model_id for model in models]

if not warm_multimodal_list:
    # Fallback to a universally supported free-tier vision model if list is blank
    BEST_MODEL = "meta-llama/Llama-3.2-11B-Vision-Instruct"
    print(f"⚠️ No active dynamic list returned. Falling back to industry best: {BEST_MODEL}")
else:
    print(f"✅ Found {len(warm_multimodal_list)} warm multi-modal models.")
    for idx, m_id in enumerate(warm_multimodal_list):
        print(f"   [{idx + 1}] {m_id}")
    
    # Selecting the #1 sorted model as the 'best' based on active community use/downloads
    BEST_MODEL = warm_multimodal_list[0]

print(f"\n🚀 Selected 'Best' Model for Inference: {BEST_MODEL}")

# 3. Create a dummy image for the request architecture
# (In real usage, replace this with your actual image file path or image URL string)
img = Image.new('RGB', (100, 100), color = 'blue')
img.save('temp_sample.jpg')

# 4. Standard Request Architecture using the Python SDK
# Note: The free serverless tier utilizes OpenAI-compatible chat completion formatting
try:
    response = client.chat_completion(
        model=BEST_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe the main color of this image and what it represents."},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "https://wikimedia.org"
                        }
                    }
                ]
            }
        ],
        max_tokens=100
    )
    
    # 5. Extract and print the output
    output_text = response.choices[0].message.content
    print(f"\n📝 Model Response:\n{output_text}")

except Exception as e:
    print(f"\n❌ Inference Error: {e}")
    print("Note: If you hit a 503 error, the model is currently experiencing a cold start. Retry in 20 seconds.")

# Clean up local image
if os.path.exists("temp_sample.jpg"):
    os.remove("temp_sample.jpg")
