"""Independent, bounded process-I/O fault review; simulated sensors only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time

import numpy as np
from pyignite import FCBlock, IsolatedTemperatureGuard, ThermalSafetyError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tests/pyignite'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--base-commit', required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('preserve previous result; output already exists')
    report = {'base_commit': args.base_commit, 'executed_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'python': platform.python_version(), 'platform': platform.platform(), 'numpy': np.__version__,
              'sensor': 'simulated only', 'native_computation_interruption': 'outer process containment only',
              'cases': [], 'sources': {}, 'status': 'PASS'}
    for relative in ['tools/pyignite/pyignite/thermal.py', 'tools/pyignite/pyignite/supervisor.py',
                     'tools/pyignite/pyignite/_io_worker.py', 'tests/pyignite/thermal_fault_fixtures.py',
                     'tools/pyignite/review_isolation.py']:
        report['sources'][relative] = hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()
    for case in ('sensor_hang', 'fsync_hang'):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'last.json'
            g = IsolatedTemperatureGuard(path, reader_spec='thermal_fault_fixtures:healthy',
                                         io_timeout_seconds=1., cleanup_seconds=.15)
            g.poll()
            block = FCBlock([(np.eye(2, dtype=np.float32), np.zeros(2, np.float32))] * 2, temperature_guard=g)
            block(np.ones((2, 2), np.float32))
            before = path.read_bytes(); last = g.store.load()['last_completed_result']
            if case == 'sensor_hang':
                g.reader_spec = 'thermal_fault_fixtures:hang'
            else:
                g.store.store_spec = 'thermal_fault_fixtures:FsyncHangStore'
            started = time.monotonic()
            try:
                g.poll()
                result = {'case': case, 'status': 'FAIL', 'reason': 'fault was not rejected'}
            except ThermalSafetyError as exc:
                duration = time.monotonic()-started
                checked = time.monotonic()
                try:
                    g.check(); rejected = False
                except ThermalSafetyError:
                    rejected = True
                g.__exit__(None, None, None)
                receipt = exc.report['last_reader_receipt' if case == 'sensor_hang' else 'last_checkpoint_receipt']
                envelope = json.loads(path.read_bytes())
                preserved = envelope['payload']['last_completed_result'] == last
                result = {'case': case, 'fault_elapsed_seconds': duration, 'check_exit_elapsed_seconds': time.monotonic()-checked,
                          'guard': exc.report, 'last_complete_result_preserved': preserved,
                          'checkpoint_bytes_unchanged': before == path.read_bytes(),
                          'temporary_files_after_worker_death': len(list(Path(td).glob('.last.json.*'))),
                          'note': 'process cleanup and temporary-file cleanup are distinct; directory removed by harness after observation',
                          'status': 'PASS' if rejected and preserved and receipt['timed_out'] and receipt['cleanup']=='pass' and duration<3 else 'FAIL'}
            report['cases'].append(result)
            if result['status'] != 'PASS':
                report['status'] = 'FAIL'
    report['cannot_claim'] = ['Original cooperative TemperatureGuard still cannot contain blocked reader/fsync by itself.',
                              'No real overheating, power cut, independent hardware watchdog or old-CPU result.',
                              'No full model, PE parity or speed/power advantage claim.',
                              'OS-uninterruptible tasks can outlive kill deadlines; cleanup failure must remain failure.']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
