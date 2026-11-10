"""Offline, generic-x86_64 build audit; not an old-hardware emulation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'native/motionbricks-core/Cargo.toml'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    # Fresh HOME for Cargo only; no modification of the user's toolchain state.
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        env = dict(os.environ, CARGO_HOME=str(temp / 'cargo'), CARGO_TARGET_DIR=str(temp / 'target'),
                   RUSTFLAGS='-C target-cpu=x86-64')
        def run(command):
            return subprocess.check_output(command, cwd=ROOT, env=env, text=True, stderr=subprocess.STDOUT, timeout=120)
        version = run(['rustc', '-vV'])
        if 'host: x86_64-unknown-linux-gnu' not in version:
            raise SystemExit('This audit is Linux x86_64 only; do not infer other platforms.')
        metadata = json.loads(run(['cargo', 'metadata', '--manifest-path', str(MANIFEST), '--locked', '--offline', '--format-version', '1']))
        assert len(metadata['packages']) == 1 and not metadata['packages'][0]['dependencies']
        start = time.perf_counter()
        build_log = run(['cargo', 'build', '--manifest-path', str(MANIFEST), '--release', '--locked', '--offline'])
        build_seconds = time.perf_counter() - start
        test_log = run(['cargo', 'test', '--manifest-path', str(MANIFEST), '--locked', '--offline'])
        probe = temp / 'target/release/parity_probe'
        stripped = temp / 'parity_probe_stripped'
        shutil.copy2(probe, stripped)
        run(['strip', str(stripped)])
        dependencies = run(['readelf', '-d', str(stripped)])
        symbols = run(['readelf', '--version-info', str(stripped)])
        glibc = sorted(set(re.findall(r'GLIBC_(\d+\.\d+(?:\.\d+)?)', symbols)),
                       key=lambda s: tuple(map(int, s.split('.'))))
        process = subprocess.run([str(stripped)], input='relu 1 1 1 1', text=True,
                                 capture_output=True, check=True, timeout=10)
        assert float(process.stdout) == 1.0
        report = {'status': 'PASS_WITH_UNVERIFIED_LEGACY_HARDWARE', 'rustc': version.strip(),
                  'third_party_crates': 0, 'offline_clean_build': True, 'clean_build_seconds': build_seconds,
                  'flags': env['RUSTFLAGS'], 'stripped_probe_bytes': stripped.stat().st_size,
                  'unstripped_probe_bytes': probe.stat().st_size,
                  'needed_libraries': re.findall(r'Shared library: \[(.*?)\]', dependencies),
                  'required_glibc_symbol_versions': glibc, 'max_required_glibc_symbol_version': glibc[-1],
                  'stripped_binary_smoke': 'PASS', 'build_log': build_log, 'test_log': test_log,
                  'not_tested': ['physical legacy CPU', 'older Linux/glibc', '32-bit', 'Windows',
                                 'bare metal/no_std', 'power consumption', 'hard real-time', 'old compiler/MSRV below 1.85']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(f'{report["status"]}: {args.output}')


if __name__ == '__main__':
    main()
