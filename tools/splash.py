import os
import sys
from logger.logger import COLORS

def show_splash():
    # Synthwave / Cyberpunk Palette
    magenta = f"\033[{COLORS.get('bright_magenta', '1;95')}m"
    cyan = f"\033[{COLORS.get('bright_cyan', '1;96')}m"
    reset = f"\033[{COLORS['reset']}m"
    dim = f"\033[2m"
    
    # Left half is magenta/purple, right half transforms into vibrant cyan
    splash = f"""
{magenta}    ___    __      {cyan}__  __  __{reset}
{magenta}   /   |  / /     {cyan}/ /  \ \/ /{reset}
{magenta}  / /| | / /     {cyan}/ /    \  / {reset}
{magenta} / ___ |/ /___  {cyan}/ /___  / /  {reset}
{magenta}/_/  |_/_____/ {cyan}/_____/ /_/   {reset}
{magenta} ────────────────{cyan}────────────────────────{reset}
  {cyan}ALLY{reset} {dim}• Intelligent Game Companion
  Autonomous Vision & Agent System{reset}
{magenta} ────────────────{cyan}────────────────────────{reset}
"""
    print(splash)

# def show_splash():
#     # Synthwave / Cyberpunk Palette
#     purple = f"\033[{COLORS.get('purple', '38;5;128')}m"
#     magenta = f"\033[{COLORS.get('bright_magenta', '1;95')}m"
#     cyan = f"\033[{COLORS.get('bright_cyan', '1;96')}m"
#     reset = f"\033[{COLORS['reset']}m"
#     dim = f"\033[2m"

#     splash = f"""
# {purple}     █████╗ ██╗     ██╗    {cyan} ██╗   ██╗{reset}
# {purple}    ██╔══██╗██║     ██║    {cyan} ╚██╗ ██╔╝{reset}
# {magenta}    ███████║██║     ██║    {cyan}  ╚████╔╝ {reset}
# {magenta}    ██╔══██║██║     ██║    {cyan}   ╚██╔╝  {reset}
# {magenta}    ██║  ██║███████╗███████╗  {cyan} ██║   {reset}
# {magenta}    ╚═╝  ╚═╝╚══════╝╚══════╝  {cyan} ╚═╝   {reset}
# {magenta} ────────────────{cyan}────────────────────────{reset}
#   {cyan}ALLY{reset} {dim}• Intelligent Game Companion
#   Autonomous Vision & Agent System{reset}
# {magenta} ────────────────{cyan}────────────────────────{reset}
# """
#     print(splash)