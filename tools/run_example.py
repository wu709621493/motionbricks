# SPDX-License-Identifier: Apache-2.0
"""Bounded, opt-in launcher for the two headless CUDA examples."""
import argparse
import shutil
import sys
from pathlib import Path

import preflight


def positive_int(value):
    value = int(value)
    if not 1 <= value <= 3600:
        raise argparse.ArgumentTypeError("expected an integer from 1 to 3600")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("example", choices=("generate_once", "locomotion_loop"))
    parser.add_argument("--model", choices=preflight.RIGS, default="soma")
    parser.add_argument("--execute", action="store_true", help="allow preflight probes and real inference")
    parser.add_argument("--timeout", type=positive_int, default=600, help="example wall-time limit, seconds (1–3600)")
    args = parser.parse_args(argv)
    supported, host = preflight.runtime_platform()
    if not supported:
        print(f"Not launched: {host} is unsupported by the bundled CUDA examples. "
              "Use python tools/preflight.py for CPU-only checks.", file=sys.stderr)
        return 2
    if not args.execute:
        print("Not launched. Add --execute to permit runtime probes, engine compilation and inference. "
              f"Example budget: {args.timeout}s; CPU library thread hints: 1; output budget: 1 MiB.")
        return 0
    root = Path(__file__).resolve().parents[1]
    # A conservative scratch-space floor, not a guarantee of enough memory/disk for every build.
    if shutil.disk_usage(root).free < 2 * 1024**3:
        print("Not launched: less than 2 GiB free disk space for runtime caches.", file=sys.stderr)
        return 2
    report = preflight.inspect(root, args.model, probe_gpu=True)
    blockers = [c for c in report['checks'] if c['status'] != 'PASS']
    if blockers:
        for check in blockers:
            print(f"{check['status']} {check['name']}: {check['detail']}", file=sys.stderr)
        print("Not launched: runtime prerequisites are incomplete.", file=sys.stderr)
        return 2
    environment = preflight.probe_environment()
    # Script-directory execution otherwise omits the repository from sys.path in some installations.
    environment['PYTHONPATH'] = str(root)
    ok, output = preflight.command(
        [sys.executable, '-u', str(root / 'docs/examples' / (args.example + '.py')), '--model', args.model],
        cwd=root, timeout=args.timeout, max_output=1024 * 1024, env=environment,
    )
    print(output)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
