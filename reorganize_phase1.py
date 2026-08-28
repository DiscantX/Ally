import os
import shutil

def move_contents(src_dir, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    if not os.path.exists(src_dir):
        print(f"Source dir {src_dir} does not exist.")
        return
    for item in os.listdir(src_dir):
        if item == "__pycache__":
            shutil.rmtree(os.path.join(src_dir, item), ignore_errors=True)
            continue
        src_path = os.path.join(src_dir, item)
        dest_path = os.path.join(dest_dir, item)
        if os.path.exists(dest_path):
            if os.path.isdir(dest_path):
                move_contents(src_path, dest_path)
                try:
                    os.rmdir(src_path)
                except OSError:
                    pass
            else:
                os.remove(dest_path)
                shutil.move(src_path, dest_path)
        else:
            shutil.move(src_path, dest_path)
    # try removing src_dir if empty
    try:
        shutil.rmtree(src_dir)
    except OSError:
        pass

def main():
    # 1. Create brain/ and subdirectories
    brain_dir = "brain"
    os.makedirs(brain_dir, exist_ok=True)
    
    # Ensure __init__.py in brain/
    init_brain = os.path.join(brain_dir, "__init__.py")
    if not os.path.exists(init_brain):
        with open(init_brain, "w") as f:
            f.write("# Brain core module\n")

    # perception
    perception_dir = os.path.join(brain_dir, "perception")
    os.makedirs(perception_dir, exist_ok=True)
    with open(os.path.join(perception_dir, "__init__.py"), "w") as f:
        f.write("# Perception module (V1, Dorsal/Ventral streams, Superior Colliculus)\n")
    
    move_contents("vision", perception_dir)
    move_contents("interpretation", perception_dir)

    # state
    state_dir = os.path.join(brain_dir, "state")
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "__init__.py"), "w") as f:
        f.write("# State module (Sensory buffer & iconic memory)\n")
    move_contents("state", state_dir)

    # memory
    memory_dir = os.path.join(brain_dir, "memory")
    os.makedirs(memory_dir, exist_ok=True)
    with open(os.path.join(memory_dir, "__init__.py"), "w") as f:
        f.write("# Memory module (Hippocampus & Prefrontal cortex memory tiers)\n")
    move_contents("memory", memory_dir)

    # reasoning
    reasoning_dir = os.path.join(brain_dir, "reasoning")
    os.makedirs(reasoning_dir, exist_ok=True)
    with open(os.path.join(reasoning_dir, "__init__.py"), "w") as f:
        f.write("# Reasoning module (Prefrontal Cortex reasoning core)\n")
    move_contents("ally", reasoning_dir)

    # knowledge
    knowledge_dir = os.path.join(brain_dir, "knowledge")
    os.makedirs(knowledge_dir, exist_ok=True)
    with open(os.path.join(knowledge_dir, "__init__.py"), "w") as f:
        f.write("# Knowledge module (Static knowledge bases)\n")
    
    prompts_dest = os.path.join(knowledge_dir, "prompts")
    os.makedirs(prompts_dest, exist_ok=True)
    with open(os.path.join(prompts_dest, "__init__.py"), "w") as f:
        f.write("# Prompts subsystem\n")
    move_contents("prompts", prompts_dest)

    schema_dest = os.path.join(knowledge_dir, "schema")
    os.makedirs(schema_dest, exist_ok=True)
    with open(os.path.join(schema_dest, "__init__.py"), "w") as f:
        f.write("# Schema subsystem\n")
    move_contents("schema", schema_dest)

    print("Phase 1 file reorganization completed successfully.")

if __name__ == "__main__":
    main()
