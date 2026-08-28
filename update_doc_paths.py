import os
import glob

files = glob.glob("docs/**/*.md", recursive=True) + ["README.md"]

prefix_map = {
    "`collectors/": "`ingestion/collectors/",
    "(`collectors/": "(`ingestion/collectors/",
    "`vision/": "`brain/perception/",
    "(`vision/": "(`brain/perception/",
    "`interpretation/": "`brain/perception/",
    "(`interpretation/": "(`brain/perception/",
    "`state/": "`brain/state/",
    "(`state/": "(`brain/state/",
    "`memory/": "`brain/memory/",
    "(`memory/": "(`brain/memory/",
    "`ally/": "`brain/reasoning/",
    "(`ally/": "(`brain/reasoning/",
    "`plugins/": "`ingestion/plugins/",
    "(`plugins/": "(`ingestion/plugins/",
    "`gui/": "`interfaces/gui/",
    "(`gui/": "(`interfaces/gui/",
    "`visuals/": "`interfaces/visuals/",
    "(`visuals/": "(`interfaces/visuals/",
    "`llm/": "`infrastructure/llm/",
    "(`llm/": "(`infrastructure/llm/",
    "`logger/": "`infrastructure/logger/",
    "(`logger/": "(`infrastructure/logger/",
    "`tools/": "`tooling/tools/",
    "(`tools/": "(`tooling/tools/",
    "`goodies/": "`tooling/goodies/",
    "(`goodies/": "(`tooling/goodies/",
    "`prompts/": "`brain/knowledge/prompts/",
    "(`prompts/": "(`brain/knowledge/prompts/",
    "`schema/": "`brain/knowledge/schema/",
    "(`schema/": "(`brain/knowledge/schema/",
}

for filepath in files:
    if not os.path.isfile(filepath):
        continue
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    
    modified = content
    for old, new in prefix_map.items():
        # Prevent double replacement if already has the new prefix
        # e.g. if new prefix is already present, don't replace
        correct_new = new
        # Check if modified already contains the updated path for that item
        modified = modified.replace(old, correct_new)
        
    if modified != content:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(modified)
        print(f"Updated {filepath}")
