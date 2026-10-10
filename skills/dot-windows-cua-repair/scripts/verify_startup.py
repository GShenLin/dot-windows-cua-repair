"""Start one owned MCP process with MXC metadata; no browser actions or network probe."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import psutil
from repair import read_config


def verify(config_path, task_dir):
    config, node, launcher, _ = read_config(config_path)
    task_dir = Path(task_dir).resolve()
    if not task_dir.is_dir():
        raise ValueError('Task directory must already exist')
    env = {k: v for k, v in os.environ.items() if k.upper() in {'PATH', 'SYSTEMROOT', 'TEMP', 'TMP'}}
    env.update(config['env'])
    env = {k: v for k, v in env.items() if k.lower() != 'systemdrive'}
    proc = subprocess.Popen([str(node), str(launcher)], cwd=launcher.parent, env=env,
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW)
    owned = psutil.Process(proc.pid)
    messages, errors = queue.Queue(), []

    def read_output():
        for line in proc.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                errors.append('non-json stdout')

    def read_error():
        # Classify startup faults without retaining raw diagnostics that could contain context.
        for line in proc.stderr:
            for signature in ('0x80070003', 'EPERM', 'chdir', 'timed out', 'could not start'):
                if signature in line:
                    errors.append(signature)

    threading.Thread(target=read_output, daemon=True).start()
    threading.Thread(target=read_error, daemon=True).start()

    def send(data):
        proc.stdin.write(json.dumps({'jsonrpc': '2.0', **data}) + '\n')
        proc.stdin.flush()

    def receive(request_id, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            item = messages.get(timeout=max(.01, deadline - time.monotonic()))
            if item.get('id') == request_id:
                return item
        raise TimeoutError('MCP response timeout')

    start = time.monotonic()
    try:
        send({'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2024-11-05',
             'capabilities': {}, 'clientInfo': {'name': 'cua-startup-check', 'version': '1'}}})
        if 'error' in receive(1, 15):
            raise RuntimeError('MCP initialization rejected')
        send({'method': 'notifications/initialized'})
        sandbox = {'permissionProfile': {'type': 'managed', 'file_system': {'type': 'restricted',
                   'entries': [{'path': {'type': 'special', 'value': {'kind': 'root'}}, 'access': 'read'}]},
                   'network': 'restricted'}, 'sandboxCwd': task_dir.as_uri(), 'useMxc': True,
                   'useLegacyLandlock': False}
        send({'id': 2, 'method': 'tools/call', 'params': {'name': 'js', 'arguments': {
            'code': 'nodeRepl.write("CUA_MXC_INIT_OK");', 'title': 'Check MXC startup', 'timeout_ms': 20000},
            '_meta': {'codex/sandbox-state-meta': sandbox}}})
        response = receive(2, 30)
        result = response.get('result', {})
        content = '\n'.join(x.get('text', '') for x in result.get('content', []))
        return {'passed': not response.get('error') and not result.get('isError') and 'CUA_MXC_INIT_OK' in content,
                'elapsed_seconds': round(time.monotonic() - start, 3), 'stderr_signatures': sorted(set(errors)),
                'scope': 'synthetic MXC startup only; parent context and real browser NOT tested'}
    finally:
        # Collect and stop only descendants of this retained Process identity.
        try:
            children = owned.children(recursive=True)
        except psutil.NoSuchProcess:
            children = []
        for child in reversed(children):
            try:
                child.terminate()
            except psutil.NoSuchProcess:
                pass
        if proc.poll() is None:
            proc.terminate()
        proc.wait(timeout=5)
        _, alive = psutil.wait_procs(children, timeout=3)
        if alive:
            raise RuntimeError('Owned diagnostic descendants did not exit; inspect reported PIDs: ' + ','.join(str(p.pid) for p in alive))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mcp-config', required=True)
    parser.add_argument('--task-dir', required=True)
    parser.add_argument('--output')
    args = parser.parse_args()
    result = verify(args.mcp_config, args.task_dir)
    text = json.dumps(result, indent=2)
    if args.output:
        with open(args.output, 'x', encoding='utf-8') as handle:
            handle.write(text + '\n')
    print(text)
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
