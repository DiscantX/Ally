import os

replacements = [
    ("from ally.", "from brain.reasoning."),
    ("import ally", "import brain.reasoning"),
    ("from vision.", "from brain.perception."),
    ("import vision", "import brain.perception"),
    ("from interpretation.", "from brain.perception."),
    ("import interpretation", "import brain.perception"),
    ("from state.", "from brain.state."),
    ("import state", "import brain.state"),
    ("from memory.", "from brain.memory."),
    ("import memory", "import brain.memory"),
    ("from prompts.", "from brain.knowledge.prompts."),
    ("import prompts", "import brain.knowledge.prompts"),
    ("from schema.", "from brain.knowledge.schema."),
    ("import schema", "import brain.knowledge.schema"),
    ("from collectors.", "from ingestion.collectors."),
    ("import collectors", "import ingestion.collectors"),
    ("from plugins.", "from ingestion.plugins."),
    ("import plugins", "import ingestion.plugins"),
    ("from gui.", "from interfaces.gui."),
    ("import gui", "import interfaces.gui"),
    ("from visuals.", "from interfaces.visuals."),
    ("import visuals", "import interfaces.visuals"),
    ("from llm.", "from infrastructure.llm."),
    ("import llm", "import infrastructure.llm"),
    ("from logger", "from infrastructure.logger"),
    ("import logger", "import infrastructure.logger"),
    ("from configs.", "from storage.configs."),
    ("import configs", "import storage.configs"),
    ("from tools.", "from tooling.tools."),
    ("import tools", "import tooling.tools"),
    ("from goodies.", "from tooling.goodies."),
    ("import goodies", "import tooling.goodies"),
]

for root, dirs, files in os.walk("."):
    if any(p in root for p in [".git", ".venv", ".env", "node_modules", "dist", "build"]):
        continue
    for file in files:
        if file.endswith(".py") and file != "update_imports.py":
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            original = content
            for old, new in replacements:
                content = content.replace(old, new)
            if content != original:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"Updated: {path}")

print("Import update script finished.")
