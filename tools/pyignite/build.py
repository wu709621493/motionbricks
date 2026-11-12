"""Explicit builds. Legacy profiles are native-core experiments, not wheel tags."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess

ROOT = Path(__file__).resolve().parent
PROFILES = {
    'host': [],
    'p5-x87': ['-m32', '-march=pentium', '-mtune=pentium', '-mno-mmx',
               '-mno-sse', '-mno-sse2', '-mfpmath=387',
               '-fexcess-precision=standard', '-fno-tree-vectorize'],
    'ia32-sse2': ['-m32', '-march=pentium4', '-mtune=generic', '-mfpmath=sse',
                '-fno-tree-vectorize'],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--profile', choices=PROFILES, default='host')
    parser.add_argument('--kind', choices=('library', 'smoke'), default='library')
    args = parser.parse_args()
    system = platform.system()
    if system not in ('Linux', 'Darwin'):
        parser.error('only Linux and macOS are currently supported')
    if args.profile != 'host' and system != 'Linux':
        parser.error('legacy ELF32 profiles require a Linux target toolchain')
    if args.profile != 'host' and args.kind == 'library' and not args.output:
        parser.error('legacy libraries require --output; never overwrite the host library')
    suffix = '.dylib' if system == 'Darwin' else '.so'
    default = (ROOT / 'pyignite' / ('libpyignite' + suffix) if args.kind == 'library'
               else ROOT / 'build' / args.profile / 'pyignite-smoke')
    output = (args.output or default).resolve()
    if args.profile != 'host' and output == ROOT / 'pyignite' / ('libpyignite' + suffix):
        parser.error('legacy output must be separate from the host Python library')
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = shlex.split(os.environ.get('CXX', 'c++'))
    flags = ['-std=c++17', '-O2', '-fPIC', '-fno-fast-math', '-ffp-contract=off', '-Wall', '-Wextra']
    sources = [ROOT / 'kernels.cpp']
    if args.kind == 'library':
        flags += ['-dynamiclib' if system == 'Darwin' else '-shared']
    else:
        sources += [ROOT / 'smoke.cpp']
    command = compiler + flags + PROFILES[args.profile] + [str(p) for p in sources]
    command += ['-o', str(output)]
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)
    digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    manifest = {
        'schema_version': 1, 'profile': args.profile, 'kind': args.kind,
        'build_host': {'system': system, 'machine': platform.machine()},
        'command': command,
        'compiler': subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
        'sources_sha256': {p.name: digest(p) for p in sources + [ROOT / 'kernels.h', ROOT / 'build.py']},
        'binary_sha256': digest(output),
        'validation': 'BUILD_ONLY',
        'note': 'Compiler target does not certify the loader, libc, Python, NumPy, or physical hardware.',
    }
    output.with_name(output.name + '.build.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()
