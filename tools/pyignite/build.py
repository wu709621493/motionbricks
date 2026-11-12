"""Explicit native build; importing PyIgnite never invokes a compiler."""
import os
import argparse
from pathlib import Path
import platform
import shlex
import subprocess

root = Path(__file__).resolve().parent
suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
if platform.system() not in ('Linux', 'Darwin'):
    parser.error('only Linux and macOS are currently supported')
output = args.output or root / 'pyignite' / ('libpyignite' + suffix)
output.parent.mkdir(parents=True, exist_ok=True)
command = shlex.split(os.environ.get('CXX', 'c++')) + [
    '-std=c++17', '-O2', '-fPIC', '-ffp-contract=off', '-Wall', '-Wextra',
    '-dynamiclib' if platform.system() == 'Darwin' else '-shared',
    str(root / 'kernels.cpp'), '-o', str(output)]
print(shlex.join(command), flush=True)
subprocess.run(command, check=True)
