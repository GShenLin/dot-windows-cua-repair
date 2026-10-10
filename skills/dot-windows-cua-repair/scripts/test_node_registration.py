"""Synthetic registration/rollback tests; never launches installed Codex or desktop tools."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import node_registration as registration
import node_registration_probe as diagnostic
from repair_files import restore


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name).resolve()
        self.root = self.home / 'plugins/cache/openai-bundled/computer-use' / registration.VERSION
        (self.root / '.codex-plugin').mkdir(parents=True)
        self.vendor = self.root / '.codex-plugin/plugin.json'
        self.vendor.write_text(json.dumps({'name': 'computer-use', 'version': registration.VERSION}))
        for name in ('node_repl.exe', 'codex.exe'):
            (self.home / name).write_bytes(b'synthetic fixture, never execute')
        self.config = self.home / 'config.toml'
        self.target = self.root / '.mcp.json'
        self.config.write_text('\n'.join([
            '[plugins."computer-use@openai-bundled"]', 'enabled = true',
            '[mcp_servers.node_repl]', 'enabled = true',
            'command = ' + json.dumps(str(self.home / 'node_repl.exe')),
            'args = []', '[mcp_servers.node_repl.env]',
            'CODEX_HOME = ' + json.dumps(str(self.home)),
            'CODEX_CLI_PATH = ' + json.dumps(str(self.home / 'codex.exe')),
            'BROWSER_USE_CODEX_APP_VERSION = "' + registration.VERSION + '"',
            'NODE_REPL_TRUSTED_SERVICES = \'{"sky":"@oai/sky/service"}\'',
            'SKY_NATIVE_PIPE = "synthetic-original"', '']), encoding='utf-8')

    def change(self, old, new):
        self.config.write_text(self.config.read_text(encoding='utf-8').replace(old, new), encoding='utf-8')

    def test_preview_exact_copy_and_rollback(self):
        originals = (self.config.read_bytes(), self.vendor.read_bytes())
        plan = registration.plan(self.home)
        self.assertFalse(self.target.exists())
        manifest = registration.install(plan, self.home / 'backup')
        self.assertEqual(json.loads(self.target.read_bytes()),
                         {'mcpServers': {'node_repl': plan['definition']}})
        self.assertEqual((self.config.read_bytes(), self.vendor.read_bytes()), originals)
        restore(manifest)
        self.assertTrue(self.target.exists())
        restore(manifest, apply=True)
        self.assertFalse(self.target.exists())
        self.assertEqual(restore(manifest, apply=True)['targets'], [])

    def test_foreign_declaration_is_preserved(self):
        self.target.write_bytes(b'{"mcpServers":{"another":{}}}')
        with self.assertRaisesRegex(ValueError, 'Existing MCP file'):
            registration.plan(self.home)
        self.assertEqual(self.target.read_bytes(), b'{"mcpServers":{"another":{}}}')

    def test_refresh_and_reverse_rollback(self):
        first = registration.install(registration.plan(self.home), self.home / 'first')
        original = self.target.read_bytes()
        self.change('synthetic-original', 'synthetic-refreshed')
        second = registration.install(registration.plan(self.home, first), self.home / 'second')
        self.assertNotEqual(self.target.read_bytes(), original)
        with self.assertRaisesRegex(ValueError, 'changed file'):
            restore(first, apply=True)
        restore(second, apply=True)
        self.assertEqual(self.target.read_bytes(), original)
        restore(first, apply=True)
        self.assertFalse(self.target.exists())

    def test_external_drift_refuses_refresh_and_rollback(self):
        manifest = registration.install(registration.plan(self.home), self.home / 'backup')
        self.target.write_bytes(b'external modification')
        with self.assertRaisesRegex(ValueError, 'changed externally'):
            registration.plan(self.home, manifest)
        with self.assertRaises(ValueError):
            restore(manifest, apply=True)

    def test_configuration_changes_after_preflight(self):
        plan = registration.plan(self.home)
        self.change('synthetic-original', 'changed-during-preflight')
        with self.assertRaisesRegex(ValueError, 'changed during preflight'):
            registration.install(plan, self.home / 'backup')
        self.assertFalse(self.target.exists())
        self.assertFalse((self.home / 'backup').exists())

    def test_disabled_missing_or_unsupported_configurations(self):
        original = self.config.read_bytes()
        cases = [('enabled = true', 'enabled = false'),
                 ('[mcp_servers.node_repl]', '[mcp_servers.unrelated]'),
                 ('@oai/sky/service', '@example/other'),
                 (registration.VERSION, 'future-build')]
        for old, new in cases:
            with self.subTest(old=old):
                self.config.write_bytes(original)
                self.change(old, new)
                with self.assertRaises(ValueError):
                    registration.plan(self.home)
                self.assertFalse(self.target.exists())

    def test_vendor_declaration_is_not_overridden(self):
        self.vendor.write_text(json.dumps({'name': 'computer-use', 'version': registration.VERSION,
                                          'mcpServers': './vendor-mcp.json'}))
        with self.assertRaisesRegex(ValueError, 'Vendor MCP declaration'):
            registration.plan(self.home)

    def test_task_identity_is_never_persisted(self):
        original = self.config.read_bytes()
        for key in registration.FORBIDDEN_ENV:
            for via_allowlist in (False, True):
                with self.subTest(key=key, via_allowlist=via_allowlist):
                    self.config.write_bytes(original)
                    if via_allowlist:
                        self.change('args = []', 'args = []\nenv_vars = ["' + key + '"]')
                    else:
                        self.change('SKY_NATIVE_PIPE =', key + ' = "synthetic"\nSKY_NATIVE_PIPE =')
                    with self.assertRaisesRegex(ValueError, 'Task-specific'):
                        registration.plan(self.home)

    def run_probe(self, v2_code=-32601, tools=None, missing_discovery=False):
        owner = self
        class FakeRpc:
            instances = []
            def __init__(self, command, env=None, cwd=None):
                self.methods = []
                self.closed = False
                self.instances.append(self)
                if env:
                    owner.assertFalse(registration.FORBIDDEN_ENV & env.keys())
            def request(self, method, params):
                self.methods.append(method)
                if method == 'capabilityRoots/discoverV1':
                    return {'roots': [{'skills': [{}], 'plugin': {'mcpConfig': None if missing_discovery else {'ok': True}}}]}
                if method == 'capabilities/discoverV2':
                    raise diagnostic.RpcError({'code': v2_code, 'message': 'synthetic'})
                if method == 'tools/list':
                    return {'tools': [{'name': name} for name in (tools if tools is not None else ['js', 'js_reset', 'turn_ended'])]}
                return {}
            def send(self, message):
                self.methods.append(message['method'])
            def close(self):
                self.closed = True
        with patch.object(diagnostic, 'Rpc', FakeRpc), patch.object(diagnostic.os, 'name', 'nt'), \
             patch.dict(os.environ, {'NODE_REPL_REQUEST_META': 'synthetic-not-to-forward'}):
            try:
                return diagnostic.probe(self.home)
            finally:
                self.assertTrue(all(r.closed for r in FakeRpc.instances))
                self.assertFalse(any('tools/call' in r.methods for r in FakeRpc.instances))

    def test_probe_reports_unsupported_v2_without_claiming_task_success(self):
        registration.install(registration.plan(self.home), self.home / 'backup')
        report = self.run_probe()
        self.assertTrue(report['local_registration_checks_passed'])
        self.assertEqual(report['v2'], {'status': 'unsupported', 'error_code': -32601})
        self.assertFalse(report['task_catalog_verified'])
        self.assertFalse(report['desktop_actions_tested'])

    def test_probe_missing_registration_does_not_pass(self):
        report = self.run_probe(missing_discovery=True)
        self.assertFalse(report['local_registration_checks_passed'])

    def test_probe_other_errors_and_missing_tools_fail_with_cleanup(self):
        with self.assertRaises(diagnostic.RpcError):
            self.run_probe(v2_code=-32000)
        with self.assertRaisesRegex(ValueError, 'Required tools missing'):
            self.run_probe(tools=['js'])


if __name__ == '__main__':
    unittest.main()
