"""Check local plugin discovery and MCP tool listing, never tools/call or task identity."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time

from node_registration import context, default_home, require


class RpcError(RuntimeError):
    def __init__(self, error):
        self.code = error.get('code')
        self.message = error.get('message', '')
        super().__init__(f'JSON-RPC error {self.code}')


class Rpc:
    def __init__(self, command, env=None, cwd=None):
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, encoding='utf-8', env=env, cwd=cwd,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.queue = queue.Queue()
        self.index = 0
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.queue.put(json.loads(line))
                except ValueError:
                    continue
        finally:
            self.queue.put(None)

    def send(self, message):
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', **message}) + '\n')
        self.process.stdin.flush()

    def request(self, method, params):
        self.index += 1
        self.send({'id': self.index, 'method': method, 'params': params})
        deadline = time.monotonic() + 20
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'{method} timed out')
            try:
                message = self.queue.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(f'{method} timed out') from exc
            if message is None:
                raise RuntimeError('Diagnostic process exited before response')
            if message.get('id') == self.index:
                if 'error' in message:
                    raise RpcError(message['error'])
                return message['result']

    def close(self):
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=3)
        self.process.stdout.close()


def probe(codex_home):
    require(os.name == 'nt', 'Runtime probe is Windows-only')
    data = context(codex_home)
    definition = data['definition']
    report = {'utc': datetime.now(timezone.utc).isoformat(), 'scope': 'local discovery and tools/list only',
              'task_catalog_verified': False, 'desktop_actions_tested': False}
    report['definition_matches_existing_config'] = (data['target'].is_file() and
        json.loads(data['target'].read_bytes()) == json.loads(data['payload']))
    rpc = Rpc([definition['env']['CODEX_CLI_PATH'], 'exec-server', '--listen', 'stdio'])
    try:
        rpc.request('initialize', {'clientName': 'readonly-node-registration-probe'})
        rpc.send({'method': 'initialized', 'params': {}})
        result = rpc.request('capabilityRoots/discoverV1', {'roots': [{
            'id': 'computer-use@openai-bundled', 'path': data['root'].as_uri()}]})
        root = result['roots'][0]
        report['v1'] = {'skills': len(root.get('skills', [])),
            'mcp_definition_present': bool((root.get('plugin') or {}).get('mcpConfig')),
            'has_error': bool(root.get('error')), 'warning_count': len(root.get('warnings', []))}
        try:
            result = rpc.request('capabilities/discoverV2', {'cwd': Path.cwd().as_uri()})
        except RpcError as exc:
            if exc.code != -32601:
                raise
            report['v2'] = {'status': 'unsupported', 'error_code': exc.code}
        else:
            matches = [p for p in result.get('plugins', []) if p.get('id') == 'computer-use@openai-bundled']
            report['v2'] = {'status': 'responded', 'plugin_count': len(matches),
                'mcp_definition_present': any(p.get('files', {}).get('mcpConfig') for p in matches)}
    finally:
        rpc.close()
    env = os.environ.copy()
    # Do not inherit another REPL's explicit request/identity override.
    for key in ('NODE_REPL_REQUEST_META', 'BROWSER_USE_ACCESS_PIPE_PATH',
                'BROWSER_USE_ACCESS_EXECUTOR_ID', 'BROWSER_USE_ACCESS_VERIFYING_IDENTITY'):
        env.pop(key, None)
    env.update(definition.get('env', {}))
    rpc = Rpc([definition['command'], *definition.get('args', [])], env=env, cwd=data['root'])
    try:
        rpc.request('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
            'clientInfo': {'name': 'readonly-node-tool-list-probe', 'version': '1'}})
        rpc.send({'method': 'notifications/initialized'})
        result = rpc.request('tools/list', {})
        report['tools'] = [tool['name'] for tool in result.get('tools', [])]
        require({'js', 'js_reset', 'turn_ended'} <= set(report['tools']), 'Required tools missing')
    finally:
        rpc.close()
    report['diagnostic_processes_closed'] = True
    report['source_files_unchanged'] = all(path.read_bytes() == original
        for path, original in data['sources'].items())
    report['local_registration_checks_passed'] = (report['definition_matches_existing_config'] and
        report['source_files_unchanged'] and report['v1']['mcp_definition_present'] and
        not report['v1']['has_error'] and report['v1']['warning_count'] == 0)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex-home', type=Path, default=default_home())
    parser.add_argument('--output', type=Path, help='New local report file; do not publish runtime output')
    args = parser.parse_args()
    output = json.dumps(probe(args.codex_home), ensure_ascii=False, indent=2)
    if args.output:
        with args.output.open('x', encoding='utf-8') as stream:
            stream.write(output + '\n')
    else:
        print(output)


if __name__ == '__main__':
    main()
