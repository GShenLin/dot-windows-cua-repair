"""Read-only inventory. No environment values, tokens, full command lines or network calls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import psutil
from repair import BASELINES, read_config
from repair_files import digest

KEYS = ('SystemDrive', 'SystemRoot', 'LOCALAPPDATA', 'HTTP_PROXY', 'HTTPS_PROXY',
        'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy',
        'BROWSER_USE_ACCESS_PIPE_PATH', 'BROWSER_USE_ACCESS_EXECUTOR_ID',
        'BROWSER_USE_ACCESS_VERIFYING_IDENTITY')


def process_report():
    reports = []
    for process in psutil.process_iter(['pid', 'ppid', 'name']):
        if (process.info['name'] or '').lower() not in ('codex.exe', 'node.exe', 'node_repl.exe', 'chatgpt.exe'):
            continue
        try:
            args = process.cmdline()
            roles = [role for role in ('app-server', 'exec-server') if role in args]
            if any(Path(arg).name == 'cua-repl.mjs' for arg in args):
                roles.append('cua-launcher')
            if any(Path(arg).name == 'trusted-worker.js' for arg in args):
                roles.append('trusted-worker')
            env = process.environ()
            parent = process.parent()
            parent_env = parent.environ() if parent else {}
            reports.append({**process.info, 'roles': roles, 'exe': process.exe(),
                'context': {key: {'present': bool(env.get(key)), 'parent_present': bool(parent_env.get(key)),
                                 'equal_to_parent': env.get(key) == parent_env.get(key) if key in env and key in parent_env else None}
                            for key in KEYS}})
        except (psutil.AccessDenied, psutil.NoSuchProcess) as exc:
            reports.append({**process.info, 'inspection_error': type(exc).__name__})
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-config')
    parser.add_argument('--output')
    args = parser.parse_args()
    codex_dir = Path(os.environ.get('CODEX_HOME', Path.home() / '.codex'))
    candidates = list((codex_dir / 'plugins/cache/openai-bundled/unified-computer-use').glob('*/.mcp.json'))
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'local_time': datetime.now().astimezone().isoformat(),
              'candidate_configs': [str(p) for p in candidates], 'processes': process_report()}
    if args.mcp_config:
        config, node, launcher, module = read_config(args.mcp_config)
        hashed = {key: digest(path.read_bytes()) for key, path in [('launcher', launcher), ('module', module)]}
        original = hashed['launcher'] == BASELINES['launcher_sha256'] and hashed['module'] == BASELINES['launch_module_sha256']
        report['selected'] = {'node': str(node), 'launcher': str(launcher), 'module': str(module), 'sha256': hashed,
            'source_state': 'known-original' if original else 'historical-repair' if hashed['launcher'] in BASELINES['historical_launcher_sha256'] else 'unknown-or-new-repair',
            'cua_build': config['env'].get('BROWSER_USE_CODEX_APP_VERSION'),
            'surfaces': config['env'].get('CUA_REPL_ENABLED_SURFACES'), 'forwarded_names': config.get('env_vars', [])}
    output = json.dumps(report, indent=2, ensure_ascii=False)
    if args.output:
        with open(args.output, 'x', encoding='utf-8') as handle:
            handle.write(output + '\n')
    else:
        print(output)


if __name__ == '__main__':
    main()
