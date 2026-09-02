import filecmp, os
match, mismatch, errors = filecmp.cmpfiles('interfaces/gui_qt/theming', 'interfaces/gui_qt/theming', ['base.qss.tmpl', 'palette_hash.py', 'theme.py'])
with open('cmp_result.txt', 'w') as f:
    f.write(f'Match: {match}\n')
    f.write(f'Mismatch: {mismatch}\n')
    f.write(f'Errors: {errors}\n')
print('Done comparing')
