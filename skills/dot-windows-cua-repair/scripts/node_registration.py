"""Preview/register an existing desktop node_repl definition in Computer Use.

No permission changes, executable patches, task metadata, or alternate identity.
Python 3.11+ is required for the standard-library TOML parser.
"""
import argparse
import copy
import json
import os
from pathlib import Path
import tomllib

from repair_files import digest, transaction

VERSION = '26.1007.21434'
DESCRIPTION = 'Computer Use node_repl registration; exact existing desktop definition'
FORBIDDEN_ENV = {'NODE_REPL_REQUEST_META', 'BROWSER_USE_ACCESS_PIPE_PATH',
                 'BROWSER_USE_ACCESS_EXECUTOR_ID', 'BROWSER_USE_ACCESS_VERIFYING_IDENTITY'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def context(codex_home):
    home = Path(codex_home).absolute()
    root = home / 'plugins/cache/openai-bundled/computer-use' / VERSION
    config_file = home / 'config.toml'
    manifest_file = root / '.codex-plugin/plugin.json'
    config_bytes, manifest_bytes = config_file.read_bytes(), manifest_file.read_bytes()
    config = tomllib.loads(config_bytes.decode('utf-8'))
    manifest = json.loads(manifest_bytes)
    require(manifest.get('name') == 'computer-use' and manifest.get('version') == VERSION,
            'Unsupported plugin name/version')
    require('mcpServers' not in manifest, 'Vendor MCP declaration already exists; inspect it instead')
    require(config.get('plugins', {}).get('computer-use@openai-bundled', {}).get('enabled') is True,
            'Computer Use plugin is not explicitly enabled; do not change permission/enablement')
    definition = copy.deepcopy(config.get('mcp_servers', {}).get('node_repl', {}))
    require(bool(definition) and definition.get('enabled', True) is True,
            'No enabled desktop node_repl definition; do not invent one')
    require('url' not in definition, 'Expected existing stdio definition')
    env = definition.get('env', {})
    require(not (FORBIDDEN_ENV & set(env)), 'Task-specific context must not be persisted')
    require(not (FORBIDDEN_ENV & set(definition.get('env_vars', []))),
            'Task-specific context must not be forwarded by this registration')
    require(env.get('BROWSER_USE_CODEX_APP_VERSION') == VERSION, 'Runtime build mismatch')
    require(json.loads(env.get('NODE_REPL_TRUSTED_SERVICES', '{}')).get('sky') == '@oai/sky/service',
            'Existing definition does not already authorize the sky service')
    for executable, expected in [(definition.get('command'), 'node_repl.exe'),
                                 (env.get('CODEX_CLI_PATH'), 'codex.exe')]:
        require(bool(executable), f'Missing existing {expected} path')
        path = Path(executable)
        require(path.is_absolute() and path.name.lower() == expected and path.is_file(),
                f'Invalid existing {expected} path')
    require(Path(env.get('CODEX_HOME', '')).absolute() == home, 'CODEX_HOME mismatch')
    target = root / '.mcp.json'
    require(target.resolve() == target.absolute() and not target.is_symlink(),
            'Redirected plugin paths are unsupported')
    payload = (json.dumps({'mcpServers': {'node_repl': definition}}, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    return {'root': root, 'target': target, 'definition': definition, 'payload': payload,
            'sources': {config_file: config_bytes, manifest_file: manifest_bytes}}


def plan(codex_home, previous_manifest=None):
    result = context(codex_home)
    target = result['target']
    expected = target.read_bytes() if target.exists() else None
    if expected is not None:
        require(previous_manifest is not None,
                'Existing MCP file: refuse overwrite without this repair transaction manifest')
        previous = json.loads(Path(previous_manifest).read_text(encoding='utf-8'))
        require(previous.get('schema') == 1 and previous.get('description') == DESCRIPTION,
                'Not a node registration transaction')
        files = previous.get('files', [])
        require(len(files) == 1 and Path(files[0]['target']).absolute() == target.absolute(),
                'Previous transaction target mismatch')
        require(digest(expected) == files[0]['installed_sha256'], 'Existing MCP file changed externally')
    elif previous_manifest is not None:
        raise ValueError('Previous installation is absent; inspect its rollback state first')
    result['expected'] = expected
    return result


def install(result, backup_dir):
    for path, expected in result['sources'].items():
        require(path.read_bytes() == expected, 'Desktop configuration changed during preflight')
    return transaction([(result['target'], result['expected'], result['payload'])], backup_dir, DESCRIPTION)


def default_home():
    return Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, default=default_home())
    parser.add_argument('--previous-manifest', type=Path,
                        help='Owned prior registration transaction, required for refresh')
    parser.add_argument('--backup-dir', type=Path, help='New transaction directory, required with --apply')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    result = plan(args.codex_home, args.previous_manifest)
    output = {'apply': args.apply, 'plugin_version': VERSION, 'target': str(result['target']),
              'operation': 'refresh' if result['expected'] is not None else 'register',
              'exact_existing_definition': True, 'changes_required': result['expected'] != result['payload']}
    if args.apply:
        require(os.name == 'nt', 'Live registration is Windows-only')
        require(args.backup_dir is not None, '--backup-dir is required')
        output['manifest'] = str(install(result, args.backup_dir))
    print(json.dumps(output, ensure_ascii=False))


if __name__ == '__main__':
    main()
