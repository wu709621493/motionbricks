"""Explicit native build; importing PyIgnite never invokes a compiler."""
import os
from pathlib import Path
import platform
import shlex
import subprocess

root = Path(__file__).resolve().parent
suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
command = shlex.split(os.environ.get('CXX', 'c++')) + [
    '-std=c++17', '-O2', '-fPIC', '-ffp-contract=off', '-Wall', '-Wextra',
    '-dynamiclib' if platform.system() == 'Darwin' else '-shared',
    str(root / 'kernels.cpp'), '-o', str(root / 'pyignite' / ('libpyignite' + suffix))]
print(shlex.join(command), flush=True)
subprocess.run(command, check=True)
