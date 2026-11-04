# SPDX-License-Identifier: Apache-2.0
"""Reproducible synthetic IPC/representation measurements; no hardware claims."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from motionbricks.radix_ipc import ContractError, IPCFailure, ROOT, SubprocessDotClient, run_mixed_dot


def measure(seed=20261104, repeats=7, sizes=(1, 16, 128, 1024)):
    rng = random.Random(seed)
    runs, workloads = [], []
    for bits, trits in ((16, 11), (32, 21)):
        for size in sizes:
            low, high = -2**(bits-1), 2**(bits-1)-1
            lhs = [rng.randint(low, high) for _ in range(size)]
            rhs = [rng.randint(low, high) for _ in range(size)]
            name = f'int{bits}_n{size}'
            workloads.append({'name': name, 'lhs': lhs, 'rhs': rhs})
            client = SubprocessDotClient()
            # Page/cache warm-up only: EVERY request still launches a fresh worker.
            for backend, width in (('binary', bits), ('ternary', trits)):
                client.run(lhs, rhs, backend, width=width)
            for repeat in range(repeats):
                order = [('binary', bits), ('ternary', trits)]
                if repeat % 2:
                    order.reverse()
                for backend, width in order:
                    result = client.run(lhs, rhs, backend, width=width)
                    runs.append({'workload': name, 'repeat': repeat, **result})
    summaries = []
    for workload in workloads:
        for backend in ('binary', 'ternary'):
            selected = [r for r in runs if r['workload'] == workload['name'] and r['backend'] == backend]
            stats = {}
            for group in ('host_timing_ns', 'transport_windows_ns'):
                for key in selected[0][group]:
                    values = [r[group][key] for r in selected]
                    stats[group + '.' + key] = {'min': min(values), 'median': statistics.median(values), 'max': max(values)}
            for key in ('decode_request_ns', 'backend_execute_ns', 'encode_result_ns'):
                values = [r['worker_timing_ns'][key] for r in selected]
                stats['worker_timing_ns.' + key] = {'min': min(values), 'median': statistics.median(values), 'max': max(values)}
            summaries.append({'workload': workload['name'], 'backend': backend, 'repeats': repeats,
                              'request_bytes': selected[0]['request_bytes'],
                              'logical_input_digits': selected[0]['logical_input_digits'], 'stats': stats})
    sources = ['motionbricks/radix_ipc.py', 'motionbricks/radix_worker.py',
               'motionbricks/radix_portability.py', 'tools/radix_ipc_benchmark.py']
    return {'schema_version': 1, 'status': 'VERIFIED', 'seed': seed, 'repeats': repeats,
            'host': {'os': platform.system(), 'machine': platform.machine(), 'python': platform.python_version(),
                     'platform': platform.platform()},
            'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
            'workloads': workloads, 'runs': runs, 'summaries': summaries,
            'mixed_demo': run_mixed_dot([13, -7, 0, 42], [3, 11, -9, -2]),
            'limits': ['same-host software on binary CPU', 'fresh worker per request',
                       'IPC windows include scheduling and response-envelope preparation',
                       'backend_execute includes existing adapter validation/packing',
                       'no TPU, HDD, energy, native ternary, or model inference measurement']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, default=20261104)
    parser.add_argument('--repeats', type=int, default=7)
    parser.add_argument('--sizes', type=int, nargs='+', default=[1, 16, 128, 1024])
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.repeats <= 30 or not 1 <= len(args.sizes) <= 16 or any(not 1 <= n <= 1024 for n in args.sizes):
            raise ContractError('repeats 1..30; 1..16 sizes, each 1..1024')
        print(json.dumps(measure(args.seed, args.repeats, args.sizes), indent=2, allow_nan=False))
        return 0
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({'status': 'FAILED', 'error_type': type(exc).__name__, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
