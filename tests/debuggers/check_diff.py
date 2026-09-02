import difflib

with open('interfaces/gui_qt/theming/theme.py', 'r', encoding='utf-8') as f1, open('interfaces/gui_qt/theming/theme.py', 'r', encoding='utf-8') as f2:
    d1 = f1.readlines()
    d2 = f2.readlines()

diff = list(difflib.unified_diff(d1, d2, fromfile='interfaces/gui_qt/theming/theme.py', tofile='interfaces/gui_qt/theming/theme.py'))
with open('diff_theme.txt', 'w', encoding='utf-8') as f:
    f.writelines(diff)
print('Diff generated')
