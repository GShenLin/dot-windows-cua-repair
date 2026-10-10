"""Offline behavior checks; all mutations stay in owned temporary directories."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import psutil
from repair import plan, HERE, BASELINES
from repair_files import transaction, restore, digest


SYNTHETIC_LAUNCHER = b'// Independent launcher fixture; not vendor code.\n'
SYNTHETIC_MODULE = b'// Independent spawn-shape fixture.\nconst f=e(_,[],{env:{}});\n'


def fixture(root):
    package = root / 'node_modules/@oai/cua-repl'
    launcher = package / 'bin/cua-repl.mjs'
    module = package / 'dist/lib/js/oai_js_cua_repl/src/launch.js'
    for path, content in [(launcher, SYNTHETIC_LAUNCHER), (module, SYNTHETIC_MODULE)]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    node, codex = root / 'node.exe', root / 'codex.exe'
    node.touch()
    codex.touch()
    config = root / '.mcp.json'
    config.write_text(json.dumps({'mcpServers': {'cua_repl': {'command': str(node), 'args': [str(launcher)],
        'env': {'BROWSER_USE_CODEX_APP_VERSION': '26.1007.21434', 'CODEX_CLI_PATH': str(codex)}}}}))
    return config, launcher, module


class RepairTests(unittest.TestCase):
    def setUp(self):
        # Override fingerprints only inside these isolated test cases.
        self.baseline_patch = patch.dict(BASELINES, {
            'launcher_sha256': digest(SYNTHETIC_LAUNCHER),
            'launch_module_sha256': digest(SYNTHETIC_MODULE),
        })
        self.baseline_patch.start()
        self.addCleanup(self.baseline_patch.stop)

    def test_full_install_restore_and_repeat_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config, launcher, module = fixture(root)
            originals = {p: p.read_bytes() for p in (launcher, module)}
            _, changes = plan(config, {'platform', 'cwd', 'browser', 'proxy'}, 'python.exe', str(root))
            manifest = transaction(changes, root / 'backup', 'fixture')
            self.assertNotEqual(launcher.read_bytes(), originals[launcher])
            self.assertTrue(launcher.with_name('parent_context.py').exists())
            restore(manifest, True)
            for p, data in originals.items():
                self.assertEqual(p.read_bytes(), data)
            self.assertFalse(launcher.with_name('parent_context.py').exists())
            self.assertEqual(restore(manifest, True)['targets'], [])

    def test_unknown_version_or_drift_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config, launcher, _ = fixture(root)
            launcher.write_bytes(b'new vendor version')
            with self.assertRaisesRegex(ValueError, 'fingerprint'):
                plan(config, {'platform'}, 'python.exe', str(root))
            self.assertEqual(launcher.read_bytes(), b'new vendor version')

    def test_restore_preflights_all_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first, second = root / 'a', root / 'b'
            first.write_bytes(b'original')
            manifest = transaction([(first, b'original', b'patched'), (second, None, b'helper')], root / 'backup', 'fixture')
            second.write_bytes(b'new user changes')
            with self.assertRaisesRegex(ValueError, 'changed file'):
                restore(manifest, True)
            self.assertEqual(first.read_bytes(), b'patched')
            self.assertEqual(second.read_bytes(), b'new user changes')

    def test_selected_layer_does_not_add_other_repairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config, launcher, module = fixture(root)
            _, changes = plan(config, {'platform'}, 'python.exe', str(root))
            self.assertEqual({p for p, _, _ in changes}, {launcher, launcher.with_name('repair-context.json')})
            context = json.loads(changes[1][2])
            self.assertEqual(context['fixes'], ['platform'])

    def test_backup_tampering_blocks_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / 'a'
            target.write_bytes(b'original')
            manifest = transaction([(target, b'original', b'patched')], root / 'backup', 'fixture')
            (manifest.parent / '00.original').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'):
                restore(manifest, True)
            self.assertEqual(target.read_bytes(), b'patched')

    def test_parent_selection_and_no_secret_forwarding(self):
        spec = importlib.util.spec_from_file_location('parent_context', HERE / 'runtime/parent_context.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        class Parent:
            def exe(self): return 'codex.exe'
            def cmdline(self): return ['codex.exe', 'exec-server', '--remote', helper.REMOTE]
            def username(self): return psutil.Process().username()
            def environ(self): return {**{k: 'test-value' for k in helper.BROWSER_KEYS},
                                       'HTTPS_PROXY': 'http://127.0.0.1:1234', 'SECRET_TOKEN': 'never-forward'}
        selected = helper.inspect_parent(Parent(), 'codex.exe', ['browser', 'proxy'])
        self.assertNotIn('SECRET_TOKEN', selected['env'])
        self.assertEqual(set(selected['env']), set(helper.BROWSER_KEYS))
        self.assertEqual(set(selected['proxy_env']), {'HTTPS_PROXY'})
        self.assertEqual(helper.inspect_parent(Parent(), 'different.exe', ['proxy'])['kind'], 'other')
        class WrongEndpoint(Parent):
            def cmdline(self): return ['codex.exe', 'exec-server', '--remote', 'https://unrecognized.invalid/']
        with self.assertRaisesRegex(RuntimeError, 'endpoint'):
            helper.inspect_parent(WrongEndpoint(), 'codex.exe', ['browser'])


if __name__ == '__main__':
    unittest.main()
