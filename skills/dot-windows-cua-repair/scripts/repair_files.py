"""Small, hash-guarded file transactions; no service restart or recursive deletion."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write(path, data):
    path = Path(path)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(data)
    try:
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def transaction(changes, backup_dir, description):
    """changes: [(absolute target, expected current bytes or None, new bytes)]."""
    backup_dir = Path(backup_dir).absolute()
    targets = [Path(target).absolute() for target, _, _ in changes]
    if len(set(targets)) != len(targets):
        raise ValueError('Duplicate target')
    for target, (_, expected, _) in zip(targets, changes):
        if target.is_symlink() or target.resolve() != target:
            raise ValueError(f'Symlink/junction target unsupported: {target}')
        actual = target.read_bytes() if target.exists() else None
        if actual != expected:
            raise ValueError(f'Target changed since preflight: {target}')
    backup_dir.mkdir(parents=True, exist_ok=False)
    records = []
    for index, (target, (_, expected, updated)) in enumerate(zip(targets, changes)):
        backup_name = f'{index:02d}.original' if expected is not None else None
        if backup_name:
            (backup_dir / backup_name).write_bytes(expected)
        records.append({'target': str(target), 'backup': backup_name,
                        'original_sha256': digest(expected) if expected is not None else None,
                        'installed_sha256': digest(updated)})
    manifest = backup_dir / 'manifest.json'
    state = {'schema': 1, 'description': description, 'state': 'prepared', 'files': records}
    atomic_write(manifest, json.dumps(state, indent=2).encode())
    # Manifest and backups exist before the first mutation, including interrupted runs.
    for target, (_, expected, updated) in zip(targets, changes):
        actual = target.read_bytes() if target.exists() else None
        if actual != expected:
            raise ValueError(f'Target changed during installation; use manifest: {target}')
        atomic_write(target, updated)
    state['state'] = 'installed'
    atomic_write(manifest, json.dumps(state, indent=2).encode())
    return manifest


def restore(manifest, apply=False):
    manifest = Path(manifest).resolve()
    state = json.loads(manifest.read_text(encoding='utf-8'))
    if state.get('schema') != 1:
        raise ValueError('Unsupported manifest')
    changes = []
    seen = set()
    for item in state['files']:
        target = Path(item['target'])
        if not target.is_absolute() or target in seen or target.resolve() != target:
            raise ValueError('Invalid, duplicate or redirected target')
        seen.add(target)
        original = None
        if item['backup'] is not None:
            source = manifest.parent / item['backup']
            if source.resolve().parent != manifest.parent:
                raise ValueError('Backup outside transaction directory')
            original = source.read_bytes()
            if digest(original) != item['original_sha256']:
                raise ValueError('Backup checksum mismatch')
        actual = target.read_bytes() if target.exists() else None
        if actual == original:
            continue
        if actual is None or digest(actual) != item['installed_sha256']:
            raise ValueError(f'Refusing to overwrite a changed file: {target}')
        changes.append((target, actual, original))
    if apply:
        for target, expected, original in reversed(changes):
            if target.read_bytes() != expected:
                raise ValueError(f'File changed during restore: {target}')
            if original is None:
                target.unlink()  # One owned helper file, never recursive.
            else:
                atomic_write(target, original)
        state['state'] = 'restored'
        atomic_write(manifest, json.dumps(state, indent=2).encode())
    return {'apply': apply, 'targets': [str(item[0]) for item in changes]}
