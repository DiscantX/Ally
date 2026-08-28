"""Automatic documentation index updater.

Scans documentation directories (such as [`plans/archive/`](plans/archive/)) for markdown files
and test directories (such as [`tests/`](tests/run_tests.py:1)) for Python test files,
extracts or preserves descriptions, sorts them alphabetically, and updates
their respective index README.md files. Also supports installing a git pre-commit hook.

Usage:
    python [`tools/update_docs.py`](tools/update_docs.py:1) [--dir DIR] [--readme README] [--ext EXT] [--install-hook]
"""

import argparse
import ast
import os
import re
import sys
from infrastructure.logger import log


def parse_existing_readme(readme_path: str) -> dict[str, str]:
    """Parses existing README to extract filename -> description mappings."""
    descriptions = {}
    if not os.path.exists(readme_path):
        return descriptions

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Match lines like: - [`filename`](path): Description here.
    pattern = re.compile(r"-\s+\[`([^`]+)`\]\([^)]+\):\s*(.*)")
    for match in pattern.finditer(content):
        filename, desc = match.groups()
        descriptions[filename] = desc.strip()

    return descriptions


def extract_file_description(file_path: str, file_ext: str = ".md") -> str:
    """Extracts a short description from a file (.md or .py)."""
    if not os.path.exists(file_path):
        return "Documentation file." if file_ext == ".md" else "Test module."

    try:
        if file_ext == ".py":
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            tree = ast.parse(content)
            docstring = ast.get_docstring(tree)
            if docstring:
                first_line = docstring.strip().splitlines()[0]
                return first_line.rstrip(".") + "."
            return "Test module."
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                line_str = line.strip()
                if line_str and not line_str.startswith("#") and not line_str.startswith("---"):
                    return line_str.split(".")[0] + "."
    except Exception:
        pass

    return "Historical documentation and implementation plans." if file_ext == ".md" else "Test module."


def update_readme(target_dir: str, readme_path: str, file_ext: str = ".md", header_lines: list[str] | None = None, footer_lines: list[str] | None = None) -> None:
    """Scans target_dir for files with file_ext and updates readme_path."""
    if not os.path.exists(target_dir):
        log("Target directory {target_dir} does not exist.", target_dir=target_dir)
        return

    existing_descs = parse_existing_readme(readme_path)

    files = []
    for entry in os.listdir(target_dir):
        if entry.lower().endswith(file_ext.lower()) and entry.lower() != "readme.md" and entry.lower() != "__init__.py":
            files.append(entry)

    files.sort()

    items = []
    for filename in files:
        full_path = os.path.join(target_dir, filename)
        rel_path = f"{target_dir}/{filename}".replace("\\", "/")
        desc = existing_descs.get(filename)
        if not desc:
            desc = extract_file_description(full_path, file_ext)
        items.append(f"- [`{filename}`]({rel_path}:1): {desc}")

    section_heading = "## Archived Documents" if file_ext == ".md" else "## Test Modules"

    if header_lines is None:
        header_lines = [
            "# Archived Plans",
            "",
            "This directory contains historical implementation plans, design strategies, and architectural proposals that have been completed, superseded, or archived during the development of [`Ally`](main.py:1).",
            "",
            section_heading,
            "",
        ]
    if footer_lines is None:
        footer_lines = [
            "",
            "---",
            "",
            "*Note: These documents are preserved for historical reference and project archaeology. For current architecture and plans, consult the active [`docs/`](docs/) and [`plans/`](plans/) directories.*",
            "",
        ]

    if os.path.exists(readme_path):
        with open(readme_path, "r", encoding="utf-8") as f:
            content = f.read()
        parts = content.split(section_heading)
        if len(parts) > 1:
            header_part = parts[0].strip()
            if header_part:
                header_lines = header_part.splitlines()
                header_lines.append("")
                header_lines.append(section_heading)
                header_lines.append("")

    new_content = "\n".join(header_lines) + "\n" + "\n".join(items) + "\n" + "\n".join(footer_lines)

    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    log("Successfully updated {readme_path} with {count} items.", readme_path=readme_path, count=len(items))


def install_git_hook() -> None:
    """Installs a git pre-commit hook that automatically runs update_docs.py."""
    git_dir = ".git"
    if not os.path.exists(git_dir):
        log("No .git directory found. Skipping git hook installation.")
        return

    hooks_dir = os.path.join(git_dir, "hooks")
    os.makedirs(hooks_dir, exist_ok=True)
    hook_path = os.path.join(hooks_dir, "pre-commit")

    template_path = os.path.join(".githooks", "pre-commit")
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            hook_content = f.read()
    else:
        hook_content = """#!/bin/sh
# Pre-commit hook to automatically update documentation indices
echo "Running documentation index updater..."
python tools/update_docs.py
git add plans/archive/readme.md tests/README.md
"""

    with open(hook_path, "w", encoding="utf-8") as f:
        f.write(hook_content)

    try:
        os.chmod(hook_path, 0o755)
    except Exception:
        pass

    log("Installed git pre-commit hook at {hook_path}", hook_path=hook_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update markdown document indices and READMEs.")
    parser.add_argument("--dir", default=None, help="Directory to scan for files.")
    parser.add_argument("--readme", default=None, help="Path to README/index file.")
    parser.add_argument("--ext", default=None, help="File extension (.md or .py).")
    parser.add_argument("--install-hook", action="store_true", help="Install git pre-commit hook.")

    args = parser.parse_args()

    if args.install_hook:
        install_git_hook()

    if args.dir or args.readme or args.ext:
        target_dir = args.dir or "plans/archive"
        readme_path = args.readme or ("tests/README.md" if target_dir.startswith("tests") else "plans/archive/readme.md")
        ext = args.ext or (".py" if target_dir.startswith("tests") else ".md")
        update_readme(target_dir, readme_path, ext)
    else:
        plans_header = [
            "# Archived Plans",
            "",
            "This directory contains historical implementation plans, design strategies, and architectural proposals that have been completed, superseded, or archived during the development of [`Ally`](main.py:1).",
            "",
            "## Archived Documents",
            "",
        ]
        plans_footer = [
            "",
            "---",
            "",
            "*Note: These documents are preserved for historical reference and project archaeology. For current architecture and plans, consult the active [`docs/`](docs/) and [`plans/`](plans/) directories.*",
            "",
        ]
        update_readme("plans/archive", "plans/archive/readme.md", ".md", plans_header, plans_footer)

        tests_header = [
            "# Test Suite Documentation",
            "",
            "This directory contains unit tests, integration tests, and verification modules for [`Ally`](main.py:1). The test suite ensures core functionality, memory management, concurrency safety, triggers, and state persistence behave correctly.",
            "",
            "## Running Tests",
            "",
            "To run the test suite, you can execute the test runner script:",
            "",
            "```bash",
            "python tests/run_tests.py",
            "```",
            "",
            "Alternatively, you can use unittest discovery from the root directory:",
            "",
            "```bash",
            "python -m unittest discover tests",
            "```",
            "",
            "## Test Modules",
            "",
        ]
        tests_footer = [
            "",
            "---",
            "",
            "*Note: Test files are automatically indexed and updated via [`tools/update_docs.py`](tools/update_docs.py:1).*",
            "",
        ]
        update_readme("tests", "tests/README.md", ".py", tests_header, tests_footer)
