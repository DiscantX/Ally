import os

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    updated = content
    # Replace imports and paths
    updated = updated.replace('from interfaces.gui_qt.', 'from interfaces.gui_qt.')
    updated = updated.replace('import interfaces.gui_qt.', 'import interfaces.gui_qt.')
    updated = updated.replace('"interfaces.gui_qt.', '"interfaces.gui_qt.')
    updated = updated.replace("'interfaces.gui_qt.", "'interfaces.gui_qt.")
    updated = updated.replace('"interfaces/gui_qt/', '"interfaces/gui_qt/')
    updated = updated.replace("'interfaces/gui_qt/", "'interfaces/gui_qt/")
    
    if updated != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(updated)
        print(f"Updated: {filepath}")

for root, dirs, files in os.walk('.'):
    if any(p in root for p in ['.git', '__pycache__', '.venv', 'venv', 'node_modules']):
        continue
    for file in files:
        if file.endswith('.py') or file.endswith('.md') or file.endswith('.tmpl'):
            process_file(os.path.join(root, file))

print("Import update script finished.")
