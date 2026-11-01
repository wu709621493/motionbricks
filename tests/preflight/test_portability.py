# SPDX-License-Identifier: Apache-2.0
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
# The launcher uses its sibling preflight module in normal script execution.
sys.path.insert(0, str(ROOT / 'tools'))
import preflight as p
import run_example as launcher
sys.path.pop(0)


class ProcessTests(unittest.TestCase):
    def test_bounded_output(self):
        ok, detail = p.command([sys.executable, '-c', "import os; os.write(1, b'x'*1000000)"], max_output=1024)
        self.assertFalse(ok)
        self.assertIn('output exceeded', detail)
        self.assertLess(len(detail), 1200)

    def test_timeout(self):
        start = time.monotonic()
        ok, detail = p.command([sys.executable, '-c', 'import time; time.sleep(20)'], timeout=0.2)
        self.assertFalse(ok)
        self.assertIn('timed out', detail)
        self.assertLess(time.monotonic() - start, 5)

    def test_binary_output_is_diagnostic(self):
        ok, detail = p.command([sys.executable, '-c', "import os; os.write(1, b'\\xff')"])
        self.assertTrue(ok)
        self.assertIn('\ufffd', detail)

    def test_child_failure_and_cuda_probe_failure(self):
        ok, detail = p.command([sys.executable, '-c', 'raise SystemExit(7)'])
        self.assertFalse(ok)
        self.assertIn('exited 7', detail)
        with patch.object(p, 'command', return_value=(False, 'native child crashed')):
            self.assertEqual(p.cuda_probe(), ('FAIL', 'native child crashed'))

    @unittest.skipUnless(os.name == 'posix', 'POSIX process-group cleanup')
    def test_timeout_kills_descendant(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'escaped'
            child = f'import time; from pathlib import Path; time.sleep(1); Path({str(marker)!r}).touch()'
            parent = f'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",{child!r}]); time.sleep(20)'
            ok, detail = p.command([sys.executable, '-c', parent], timeout=0.3)
            self.assertFalse(ok)
            time.sleep(1.2)
            self.assertFalse(marker.exists(), detail)


class PortabilityTests(unittest.TestCase):
    def test_mac_never_probes_native_gpu(self):
        with patch.object(p.platform, 'system', return_value='Darwin'), \
             patch.object(p.platform, 'machine', return_value='arm64'), \
             patch.object(p, 'cuda_probe', side_effect=AssertionError('must not load CUDA')):
            report = p.inspect(ROOT, probe_gpu=True)
        self.assertEqual(report['checks'][0]['status'], 'FAIL')
        self.assertEqual(report['checks'][-1]['status'], 'SKIP')
        self.assertEqual(report['inference'], 'NOT_RUN')

    def test_host_matrix(self):
        for system, machine, expected in [('Linux', 'x86_64', True), ('Linux', 'aarch64', False),
                                          ('Darwin', 'arm64', False), ('Darwin', 'x86_64', False)]:
            with self.subTest(system=system, machine=machine), \
                 patch.object(p.platform, 'system', return_value=system), \
                 patch.object(p.platform, 'machine', return_value=machine):
                self.assertEqual(p.runtime_platform()[0], expected)

    def test_json_limits_and_nesting(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pose.json'
            path.write_text(' ' * 1025)
            with self.assertRaisesRegex(ValueError, 'exceeds'):
                p.read_json(path, 1024)
            path.write_text('[' * 3000 + '0' + ']' * 3000)
            with self.assertRaises(ValueError):
                p.read_json(path)
            path.write_bytes(b'\xff')
            with self.assertRaises(ValueError):
                p.read_json(path)

    def test_example_help_without_site_packages(self):
        for name in ('generate_once', 'locomotion_loop'):
            result = subprocess.run([sys.executable, '-S', str(ROOT / 'docs/examples' / (name + '.py')), '--help'],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('--model', result.stdout)

    def test_example_rejects_mac_before_imports(self):
        spec = importlib.util.spec_from_file_location('example_platform', ROOT / 'docs/examples/_platform.py')
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        with patch.object(guard.platform, 'system', return_value='Darwin'), \
             patch.object(guard.platform, 'machine', return_value='arm64'), \
             self.assertRaisesRegex(SystemExit, 'CPU-only'):
            guard.require_cuda_platform()


class LauncherTests(unittest.TestCase):
    def call(self, args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return launcher.main(args)

    def test_no_execute_does_not_probe(self):
        with patch.object(p, 'runtime_platform', return_value=(True, 'Linux/x86_64')), \
             patch.object(p, 'inspect', side_effect=AssertionError('no opt-in')):
            self.assertEqual(self.call(['generate_once']), 0)

    def test_mac_refused_even_with_execute(self):
        with patch.object(p, 'runtime_platform', return_value=(False, 'Darwin/arm64')), \
             patch.object(p, 'inspect', side_effect=AssertionError('unsupported')):
            self.assertEqual(self.call(['generate_once', '--execute']), 2)

    def test_low_disk_and_failed_preflight(self):
        from types import SimpleNamespace
        with patch.object(p, 'runtime_platform', return_value=(True, 'Linux/x86_64')):
            with patch.object(launcher.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)), \
                 patch.object(p, 'inspect', side_effect=AssertionError('low disk')):
                self.assertEqual(self.call(['generate_once', '--execute']), 2)
            with patch.object(launcher.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
                 patch.object(p, 'inspect', return_value={'checks':[dict(status='FAIL', name='cuda', detail='absent')]}), \
                 patch.object(p, 'command', side_effect=AssertionError('blocked')):
                self.assertEqual(self.call(['generate_once', '--execute']), 2)

    def test_explicit_execution_uses_limits(self):
        from types import SimpleNamespace
        with patch.object(p, 'runtime_platform', return_value=(True, 'Linux/x86_64')), \
             patch.object(launcher.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024**3)), \
             patch.object(p, 'inspect', return_value={'checks':[dict(status='PASS')]}), \
             patch.object(p, 'command', return_value=(True, 'done')) as command:
            self.assertEqual(self.call(['generate_once', '--execute', '--timeout', '12']), 0)
        self.assertEqual(command.call_args.kwargs['timeout'], 12)
        self.assertEqual(command.call_args.kwargs['max_output'], 1024**2)
        self.assertEqual(command.call_args.kwargs['env']['OMP_NUM_THREADS'], '1')

    def test_invalid_timeout(self):
        for value in ('0', '-1', '3601', 'nan'):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                self.call(['generate_once', '--timeout', value])
