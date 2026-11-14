"""PR #96 workloads supervised by PR #97; synthetic software contracts only."""
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/pyignite'))
from pyignite import run_supervised
from motionbricks.roach_home import Config, SCENARIOS, canonical, simulate


class RoachIntegration(unittest.TestCase):
    def test_all_scenarios_keep_seeded_results_and_output_hashes(self):
        with tempfile.TemporaryDirectory() as d:
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario):
                    out = Path(d) / scenario
                    command = [sys.executable, '-S', '-m', 'motionbricks.roach_home',
                               '--steps', '20', '--agents', '8', '--seed', '7',
                               '--scenario', scenario, '--out-dir', str(out)]
                    r = run_supervised(command, timeout_seconds=10, cwd=ROOT)
                    self.assertFalse(r['timed_out'])
                    self.assertEqual(r['exit_code'], 0, r['stderr'])
                    self.assertNotEqual(r['cleanup'], 'fail')
                    run = json.loads((out / 'run.json').read_text(encoding='utf-8'))
                    self.assertEqual(run, simulate(Config(steps=20, agents=8, seed=7), scenario=scenario))
                    manifest = json.loads((out / 'sha256.json').read_text(encoding='utf-8'))
                    self.assertEqual(set(manifest), {'run.json', 'metrics.csv', 'observe.html'})
                    for name, digest in manifest.items():
                        self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)
                    # Nonzero refusal must not alter an already complete experiment.
                    before = canonical(manifest)
                    refused = run_supervised(command, timeout_seconds=10, cwd=ROOT)
                    self.assertEqual(refused['exit_code'], 2)
                    self.assertFalse(refused['timed_out'])
                    self.assertEqual(json.loads(refused['stderr'])['status'], 'REFUSED')
                    self.assertEqual(canonical(json.loads((out / 'sha256.json').read_text(encoding='utf-8'))), before)
                    for name, digest in manifest.items():
                        self.assertEqual(hashlib.sha256((out / name).read_bytes()).hexdigest(), digest)

    def test_deadline_during_real_simulation_publishes_no_complete_run(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'interrupted'
            script = ('from motionbricks.roach_home import Config,simulate,export;'
                      'from pathlib import Path;print("SIMULATION_ENTERED",flush=True);'
                      'export(simulate(Config(agents=200,steps=7200,sample_every=10)),Path(' + repr(str(out)) + '))')
            r = run_supervised([sys.executable, '-S', '-u', '-c', script],
                               timeout_seconds=.6, cleanup_seconds=.2, cwd=ROOT)
            self.assertIn(b'SIMULATION_ENTERED', r['stdout'])
            self.assertTrue(r['timed_out'])
            self.assertEqual(r['cleanup'], 'pass')
            self.assertFalse((out / 'sha256.json').exists())

    @unittest.skipUnless(os.name == 'posix', 'owned process groups are POSIX-only')
    def test_exited_launcher_cannot_leave_a_late_result_writer(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / 'late-run'
            script = ('import time;time.sleep(.8);'
                      'from motionbricks.roach_home import Config,simulate,export;'
                      'from pathlib import Path;'
                      'export(simulate(Config(steps=1)),Path(' + repr(str(out)) + '))')
            launcher = ('import subprocess,sys;'
                        'p=subprocess.Popen([sys.executable,"-S","-c",' + repr(script) + '],'
                        'stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);'
                        'print(p.pid,flush=True)')
            r = run_supervised([sys.executable, '-c', launcher],
                               timeout_seconds=5, cleanup_seconds=.1, cwd=ROOT)
            descendant_pid = int(r['stdout'])
            try:
                self.assertEqual(r['exit_code'], 0)
                self.assertFalse(r['timed_out'])
                time.sleep(1.)
                self.assertFalse(out.exists(), 'descendant wrote results after the receipt returned')
                self.assertIn(r['cleanup'], ('pass', 'fail'))  # unknown group quiescence is failure
            finally:
                try:
                    os.kill(descendant_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    unittest.main()
