"""Strip @ts-nocheck from xray files; restore on those that don't compile."""
import pathlib
import subprocess
import sys

base = pathlib.Path('src/pages/xray')
all_files = sorted([f for f in base.rglob('*') if f.is_file() and f.suffix in ('.ts', '.tsx')])


def priority(p):
    parts = p.parts
    if 'types' in parts:
        return 0
    if 'utils' in parts:
        return 1
    if 'core' in parts:
        return 2
    if len(parts) >= 2 and parts[-2] == 'ui':
        return 3
    if 'hooks' in parts:
        return 4
    if 'editors' in parts and len(parts) >= 2 and parts[-2] in ('inbound', 'outbound', 'dns', 'routing', 'settings', 'shared'):
        return 5
    if 'editors' in parts:
        return 6
    return 7


all_files.sort(key=lambda p: (priority(p), str(p)))

candidates = [f for f in all_files if f.read_text(encoding='utf-8').startswith('// @ts-nocheck')]
print(f'Candidates with @ts-nocheck: {len(candidates)}')

removed = []
for f in candidates:
    orig = f.read_text(encoding='utf-8')
    new = orig.replace('// @ts-nocheck\n', '', 1)
    f.write_text(new, encoding='utf-8')
    removed.append(f)

r = subprocess.run(['npm', 'run', 'typecheck'], capture_output=True, text=True, shell=True)
if r.returncode == 0:
    print(f'SUCCESS: all {len(removed)} files compile clean')
    sys.exit(0)

errlines = r.stdout + r.stderr
err_files = set()
sep = chr(92)  # backslash
for line in errlines.splitlines():
    if ': error TS' in line:
        path = line.split('(', 1)[0].replace(sep, '/').strip()
        err_files.add(path)
print(f'tsc reports errors in {len(err_files)} files; restoring nocheck on those')

restored = 0
for f in removed:
    rel = str(f).replace(sep, '/')
    if any(rel.endswith(ef) or ef.endswith(rel) for ef in err_files):
        orig_text = f.read_text(encoding='utf-8')
        f.write_text('// @ts-nocheck\n' + orig_text, encoding='utf-8')
        restored += 1

print(f'Restored nocheck on {restored} files; cleaned {len(removed) - restored} files net')
