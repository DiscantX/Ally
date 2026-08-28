import os
import shutil

def move_dir(src, dest):
    if os.path.exists(src):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if os.path.exists(dest):
            # If dest exists, merge/move contents
            for item in os.listdir(src):
                s_item = os.path.join(src, item)
                d_item = os.path.join(dest, item)
                if os.path.exists(d_item):
                    if os.path.isdir(d_item) and os.path.isdir(s_item):
                        # recursive move or shutil.copytree
                        for sub in os.listdir(s_item):
                            shutil.move(os.path.join(s_item, sub), os.path.join(d_item, sub))
                    else:
                        if os.path.exists(d_item):
                            if os.path.isdir(d_item):
                                shutil.rmtree(d_item)
                            else:
                                os.remove(d_item)
                        shutil.move(s_item, d_item)
                else:
                    shutil.move(s_item, d_item)
            try:
                shutil.rmtree(src)
            except OSError:
                pass
        else:
            shutil.move(src, dest)
        print(f"Moved {src} -> {dest}")
    else:
        print(f"Source {src} does not exist.")

def main():
    # 1. ingestion/
    os.makedirs("ingestion", exist_ok=True)
    with open(os.path.join("ingestion", "__init__.py"), "w") as f:
        f.write("# Ingestion domain (Collectors & Plugins)\n")
    move_dir("collectors", "ingestion/collectors")
    move_dir("plugins", "ingestion/plugins")

    # 2. interfaces/
    os.makedirs("interfaces", exist_ok=True)
    with open(os.path.join("interfaces", "__init__.py"), "w") as f:
        f.write("# Interfaces domain (GUI & Visuals)\n")
    move_dir("gui", "interfaces/gui")
    move_dir("visuals", "interfaces/visuals")

    # 3. infrastructure/
    os.makedirs("infrastructure", exist_ok=True)
    with open(os.path.join("infrastructure", "__init__.py"), "w") as f:
        f.write("# Infrastructure domain (LLM & Logger)\n")
    move_dir("llm", "infrastructure/llm")
    move_dir("logger", "infrastructure/logger")

    # 4. storage/
    os.makedirs("storage", exist_ok=True)
    with open(os.path.join("storage", "__init__.py"), "w") as f:
        f.write("# Storage domain (Configs, Data, Snapshots)\n")
    move_dir("configs", "storage/configs")
    move_dir("data", "storage/data")
    move_dir("snapshots", "storage/snapshots")

    # 5. tooling/
    os.makedirs("tooling", exist_ok=True)
    with open(os.path.join("tooling", "__init__.py"), "w") as f:
        f.write("# Tooling domain (Tools & Goodies)\n")
    move_dir("tools", "tooling/tools")
    move_dir("goodies", "tooling/goodies")

    print("Phase 2 file movement completed successfully.")

if __name__ == "__main__":
    main()
