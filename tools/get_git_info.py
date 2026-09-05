import subprocess
import configparser
from pathlib import Path
import re

def get_git_info():
    username = "Unknown"
    # Try git config user.name via subprocess
    try:
        res = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=5)
        if res.returncode == 0:
            username = res.stdout.strip()
    except Exception:
        pass

    repo_url = "Unknown"
    config_path = Path('.git/config')
    if config_path.exists():
        config = configparser.ConfigParser()
        config.read(config_path)
        if config.has_section('remote "origin"'):
            repo_url = config.get('remote "origin"', 'url', fallback="Unknown")

    # Apply sed logic: sed -E 's/.*github\.com[:\/](.*)\.git/\1/'
    sed_output = repo_url
    match = re.search(r'github\.com[:/](.*?)(?:\.git)?$', repo_url)
    if match:
        sed_output = match.group(1)
        if sed_output.endswith('.git'):
            sed_output = sed_output[:-4]

    print(f"Git Username: {username}")
    print(f"Repo URL: {repo_url}")
    print(f"Sed Output: {sed_output}")

if __name__ == '__main__':
    get_git_info()
