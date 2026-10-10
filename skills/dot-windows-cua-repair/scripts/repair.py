"""Plan first; install only the known original CUA build with explicit --apply."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
from repair_files import digest, transaction

HERE = Path(__file__).resolve().parent
BASELINES = json.loads((HERE.parent / 'references/baselines.json').read_text())
SPAWN = 'f=e(_,[],{env:'
BRIDGED = ('f=e(i.platform==="win32"&&i.env.CUA_REPL_WINDOWS_CWD_BRIDGE?i.env.NODE_REPL_NODE_PATH:_,'
           'i.platform==="win32"&&i.env.CUA_REPL_WINDOWS_CWD_BRIDGE?[i.env.CUA_REPL_WINDOWS_CWD_BRIDGE,_]:[],{env:')


def read_config(path):
    server = json.loads(Path(path).read_text(encoding='utf-8-sig'))['mcpServers']['cua_repl']
    if len(server['args']) != 1:
        raise ValueError('Unsupported launcher arguments')
    node, launcher = Path(server['command']), Path(server['args'][0])
    if not node.is_absolute() or not launcher.is_absolute():
        raise ValueError('Expected absolute executable and launcher paths')
    if launcher.name != 'cua-repl.mjs' or launcher.parent.name != 'bin':
        raise ValueError('Unsupported launcher location')
    if launcher.parent.parent.name != 'cua-repl':
        raise ValueError('Unsupported package location')
    module = launcher.parent.parent / 'dist/lib/js/oai_js_cua_repl/src/launch.js'
    return server, node, launcher, module


def local_appdata():
    if os.name != 'nt':
        raise ValueError('Windows required')
    value = ctypes.create_unicode_buffer(32768)
    result = ctypes.windll.shell32.SHGetFolderPathW(None, 0x1C, None, 0, value)
    if result != 0 or not Path(value.value).is_dir():
        raise ValueError('Cannot resolve current-user LocalAppData KnownFolder')
    return value.value


def plan(config_path, fixes, python, appdata):
    server, node, launcher, module = read_config(config_path)
    version = server['env'].get('BROWSER_USE_CODEX_APP_VERSION')
    if version != BASELINES['cua_build']:
        raise ValueError(f'Unrecognized CUA build: {version}')
    old_launcher, old_module = launcher.read_bytes(), module.read_bytes()
    if digest(old_launcher) in BASELINES['historical_launcher_sha256']:
        raise ValueError('Known historical manual repair is already present. Do not overwrite; inspect original repair backup.')
    if digest(old_launcher) != BASELINES['launcher_sha256'] or digest(old_module) != BASELINES['launch_module_sha256']:
        raise ValueError('Unknown or modified source fingerprint; automatic patch refused')
    context = {'fixes': sorted(fixes), 'python': str(Path(python).resolve()), 'local_appdata': appdata,
               'codex_exe': server['env']['CODEX_CLI_PATH']}
    if not Path(context['codex_exe']).is_file():
        raise ValueError('Configured Codex executable missing')
    if not node.is_file():
        raise ValueError('Configured Node executable missing')
    files = [(launcher, old_launcher, (HERE / 'runtime/launcher.mjs').read_bytes()),
             (launcher.with_name('repair-context.json'), None, json.dumps(context, indent=2).encode())]
    if {'browser', 'proxy'} & fixes:
        files.append((launcher.with_name('parent_context.py'), None, (HERE / 'runtime/parent_context.py').read_bytes()))
    if 'cwd' in fixes:
        text = old_module.decode('utf-8')
        if text.count(SPAWN) != 1:
            raise ValueError('Spawn anchor mismatch')
        files.append((module, old_module, text.replace(SPAWN, BRIDGED).encode()))
        files.append((launcher.with_name('windows-cwd-bridge.mjs'), None, (HERE / 'runtime/windows-cwd-bridge.mjs').read_bytes()))
    for target, expected, _ in files:
        if expected is None and target.exists():
            raise ValueError(f'Existing helper conflicts with installation: {target}')
    return node, files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-config', required=True)
    parser.add_argument('--fixes', nargs='+', default=['all'], choices=['all', 'platform', 'cwd', 'browser', 'proxy'],
                        help='Default: all four repairs for the known affected build')
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--backup-dir', help='New unique directory; required with --apply')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if 'all' in args.fixes and len(args.fixes) != 1:
        parser.error('Use all alone, or name a subset of repairs')
    fixes = {'platform', 'cwd', 'browser', 'proxy'} if args.fixes == ['all'] else set(args.fixes)
    if {'browser', 'proxy'} & fixes:
        subprocess.run([args.python, '-I', '-c', 'import psutil'], check=True, capture_output=True)
    node, files = plan(args.mcp_config, fixes, args.python, local_appdata())
    for source in (HERE / 'runtime').glob('*.mjs'):
        subprocess.run([str(node), '--check', str(source)], check=True, capture_output=True)
    result = {'apply': args.apply, 'fixes': sorted(fixes), 'files': [
        {'target': str(p), 'before': digest(before) if before is not None else None, 'after': digest(after)}
        for p, before, after in files]}
    if args.apply:
        if not args.backup_dir:
            parser.error('--backup-dir is required for --apply')
        result['manifest'] = str(transaction(files, args.backup_dir, 'Windows CUA environment/cwd repair'))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
