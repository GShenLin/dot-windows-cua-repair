"""Check package hashes, Python syntax, links and optional Node syntax without deployment."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', help='Existing node.exe for --check only')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    manifest = json.loads((root / 'references/bundle-manifest.json').read_text())
    for item in manifest['files']:
        path = root / item['path']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError(f'Bundle checksum mismatch: {path}')
    python_files = list(root.rglob('*.py'))
    for path in python_files:
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    for path in root.rglob('*.md'):
        for match in re.finditer(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = match.group(1).split('#')[0]
            if not target or '://' in target:
                continue
            if not (path.parent / target).exists():
                raise ValueError(f'Broken reference in {path}: {target}')
    js_files = list(root.rglob('*.mjs'))
    if args.node:
        for path in js_files:
            subprocess.run([args.node, '--check', str(path)], check=True, capture_output=True)
    print(json.dumps({'bundle_files': len(manifest['files']), 'python_syntax': len(python_files),
                      'node_syntax': len(js_files) if args.node else 'not requested', 'links': 'passed'}))


if __name__ == '__main__':
    main()
