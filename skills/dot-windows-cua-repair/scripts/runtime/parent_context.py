"""Read only selected context from the launcher's verified immediate parent."""
import json
import os
from pathlib import Path
import sys
import psutil

PROXY_KEYS = ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY',
              'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
BROWSER_KEYS = ('BROWSER_USE_ACCESS_PIPE_PATH', 'BROWSER_USE_ACCESS_EXECUTOR_ID',
                'BROWSER_USE_ACCESS_VERIFYING_IDENTITY')
REMOTE = 'https://codex-cloud-environments.chatgpt.com/api'


def inspect_parent(parent, expected_exe, fixes):
    result = {'kind': 'other', 'env': {}, 'proxy_env': {}}
    if parent is None or os.path.normcase(parent.exe()) != os.path.normcase(expected_exe):
        return result
    args = parent.cmdline()[1:]
    if not any(role in args for role in ('app-server', 'exec-server')):
        return result
    if parent.username().casefold() != psutil.Process().username().casefold():
        raise RuntimeError('Codex parent belongs to a different user')
    work = 'exec-server' in args
    if work:
        if '--remote' not in args or args.index('--remote') + 1 >= len(args):
            raise RuntimeError('Work executor endpoint missing')
        if args[args.index('--remote') + 1] != REMOTE:
            raise RuntimeError('Unexpected Work executor endpoint')
    env = parent.environ()
    result['kind'] = 'local-work' if work else 'local-codex'
    if 'proxy' in fixes:
        result['proxy_env'] = {key: env[key] for key in PROXY_KEYS if env.get(key)}
    if work and 'browser' in fixes:
        selected = {key: env.get(key, '') for key in BROWSER_KEYS}
        if not all(selected.values()):
            raise RuntimeError('Work browser access context incomplete')
        result['env'] = selected
    return result


def main():
    config = json.loads(Path(__file__).with_name('repair-context.json').read_text())
    launcher = psutil.Process().parent()
    if launcher is None or launcher.pid != int(sys.argv[1]):
        raise RuntimeError('Context reader must be called by its launcher')
    print(json.dumps(inspect_parent(launcher.parent(), config['codex_exe'], config['fixes'])))


if __name__ == '__main__':
    main()
