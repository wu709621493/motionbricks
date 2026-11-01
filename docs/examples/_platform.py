# SPDX-License-Identifier: Apache-2.0
"""Check the bundled runtime platform before loading optional native modules."""
import platform


def require_cuda_platform():
    system, machine = platform.system(), platform.machine().lower()
    if system not in ('Linux', 'Windows') or machine not in ('x86_64', 'amd64'):
        raise SystemExit(
            f'The bundled TensorRT examples do not support {system}/{machine}. '
            'Use python tools/preflight.py for CPU-only diagnostics; '
            'Apple GPU/Neural Engine and TPU inference are not implemented.'
        )
