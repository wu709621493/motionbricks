# SPDX-License-Identifier: Apache-2.0
"""Test-only CLI harness: real host/entry point, no native execution permitted."""
import os
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import preflight


def audit(event, args):
    forbidden = (
        event == 'ctypes.dlopen'
        or event == 'import' and args[0].split('.')[0] in
        {'tensorrt', 'warp', 'numpy', 'motionbricks'}
        or event == 'subprocess.Popen' and Path(args[0]).name != 'git'
        or event in {'os.system', 'os.exec', 'os.posix_spawn'}
    )
    if forbidden:
        print('SAFETY_SENTINEL: forbidden ' + event, file=sys.stderr, flush=True)
        os._exit(97)  # Cannot be swallowed as an ordinary diagnostic failure.


sys.addaudithook(audit)
real_command = preflight.command


def cpu_only_command(argv, *args, **kwargs):
    if Path(argv[0]).name == 'git':
        return real_command(argv, *args, **kwargs)
    # On supported hosts only, replace precisely the three existing GPU probes.
    # Any example launch / new native path reaches the audit sentinel instead.
    if (preflight.runtime_platform()[0] and
        (argv == [sys.executable, str(ROOT / 'tools/preflight.py'), '--_cuda-driver']
         or len(argv) == 3 and argv[1] == '-c' and
         (argv[2].startswith('import tensorrt as trt;') or
          argv[2].startswith('import warp as wp;')))):
        return False, 'CPU_TEST_FIXTURE: native GPU probe disabled'
    return real_command(argv, *args, **kwargs)


preflight.command = cpu_only_command
target = sys.argv.pop(1)
sys.argv[0] = str(ROOT / 'tools' / target)
if target == 'preflight.py' and preflight.runtime_platform()[0]:
    raise SystemExit(preflight.main())
runpy.run_path(sys.argv[0], run_name='__main__')
