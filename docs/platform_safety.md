# Ubuntu and Apple Silicon: bounded diagnostics and example launch

This change hardens startup and limits accidental work. It does not implement a
macOS inference backend or certify hardware temperature, power, or reliability.
The requested “M6” target is treated as macOS ARM64; no specific M6 machine was
available or tested. Apple GPU/Neural Engine support is not inferred from ARM64.

## Supported scope

| Host | CPU preflight / pose validation / example help | Bundled TensorRT examples |
| --- | --- | --- |
| Ubuntu x86-64 | Supported; locally tested on Ubuntu 24.04.3 | Requires NVIDIA CUDA, dependencies and verified assets |
| Ubuntu ARM64 | CPU path targeted by CI | Conservatively rejected by this launcher; not validated |
| macOS ARM64 | CPU path targeted by CI; mocked platform tests locally | Rejected before native runtime imports |
| macOS Intel / Rosetta | CPU path | Rejected before native runtime imports |

The platform whitelist describes the bundled runtime's tested deployment scope,
not all hardware that CUDA could theoretically support. TensorRT, TPU, Metal and
Apple Neural Engine are separate backends; changing a device string is not a port.
The [TPU protocol](tpu_integration_protocol.md) remains a proposal.

## Lightweight use on Ubuntu or macOS

Use a system Python 3.12+ without installing the project or hydrating model files:

```sh
python tools/preflight.py --model unitree_g1 --json
python -m unittest discover -s tests/preflight -v
python docs/examples/generate_once.py --help
python docs/examples/locomotion_loop.py --help
```

Do not use the root `uv sync` to install a purported macOS runtime: it still
requires TensorRT CUDA packages. CPU-only tooling does not need those dependencies.
Default preflight exit 0 means offline checks passed, even if runtime prerequisites
fail. On macOS `--probe-gpu` skips native probes and `--require-runtime` returns 1;
no CUDA, TensorRT or Warp import is attempted there.

## Bounded CUDA example execution

The new launcher never installs packages, downloads models, launches a viewer,
or changes power/fan/clock settings. On a supported host it defaults to a preview:

```sh
python tools/run_example.py generate_once --model unitree_g1
# Only with the full CUDA runtime and hydrated assets:
python tools/run_example.py generate_once --model unitree_g1 --execute --timeout 600
```

Without `--execute`, no driver probe or inference occurs. Unsupported hosts exit
2 immediately. With opt-in, at least 2 GiB of free cache disk space is required,
then every strict prerequisite must pass before an example starts. This disk floor
is a conservative early check, not a model-specific memory/capacity guarantee.
A refusal returns 2; executed-example failure/timeout returns 1; success returns 0.

Runtime library thread environment variables are set to 1 before native imports
(OMP, OpenBLAS, MKL, vecLib and NumExpr). These are library hints, not hard CPU or
GPU utilization limits. The example has a default 600-second deadline, configurable
from 1–3600 seconds, and a 1 MiB combined output budget. Output is retained and
printed when the child completes; it is not streamed to the terminal. First engine
compilation may need a larger timeout; an interrupted build may need rebuilding.

On Ubuntu/macOS, timeout, excess output or Ctrl-C kills the child process group,
including ordinary descendants. Windows cleanup kills the direct child only.
Deliberately detached processes and kernel-uninterruptible I/O are outside these
bounds. Prerequisite probes run before the example deadline, with their own
30-second limits; the example timeout is not the whole launcher wall time.
The original direct example commands remain available and do not inherit the
launcher's time/output budgets. Prefer this launcher for bounded trials.

## Diagnostic improvements

- Driver loading and `cuInit` run in a subprocess; driver failure or crash becomes
  a failed check instead of taking down the parent checker.
- External commands retain at most 64 KiB of combined output and have a 30-second
  deadline. Binary or oversized Git output becomes a diagnostic instead of
  unbounded capture or a Unicode decoding traceback.
- Pose JSON is limited to 4 MiB, manifests to 256 KiB, both UTF-8, with at most
  64 container nesting levels. Deep/oversized input is rejected before allocation
  of its full object tree.
- Asset SHA-256 reads 1 MiB chunks and checks a 30-second budget between reads.
  Exceeding it yields WARN (unverified), which blocks strict runtime admission.
- Both example scripts defer native imports, so `--help` works with Python `-S`.
  macOS and unvalidated architectures receive a clear platform message before
  inference dependencies load.

No arbitrary RAM cap is imposed: virtual address-space limits can break large
native runtimes without measuring real resident memory. CUDA build/GPU memory,
thermals, battery behavior and long-run stability still require real hardware
measurements. This change is startup/resource hygiene, not a thermal controller
or a guarantee against hardware failure. It does not change inference algorithms
or claim an inference throughput improvement.

## Verification record — 2026-11-01

Base: `aafdff4de78a6f43437d97f7604d5c636d43860c` (PR #2 merged).
Local host: Ubuntu 24.04.3 LTS, x86-64, Python 3.12.14.

- 31 CPU tests passed, including real short-lived subprocess timeout/output tests,
  POSIX descendant cleanup, invalid JSON, launch refusal and mocked macOS branches.
- Existing example source compilation passed; 2 real GPU tests skipped.
- Both example help commands ran without site packages (`python -S`).
- Actual `--execute` launch returned 2 for missing prerequisites, before inference.
- No NVIDIA/Apple/TPU inference, stress test, energy measurement or M6 hardware test.

CI now targets Ubuntu 24.04 x86-64 and ARM64 plus macOS 14 ARM64, each with Python
3.12 and 3.13, a ten-minute job limit and cancellation of superseded runs. It
records the runner's actual architecture. These are configured targets, not local
hardware results; inspect the PR checks for remote results.
Runner labels follow [GitHub's official runner reference](https://docs.github.com/en/actions/how-tos/write-workflows/choose-where-workflows-run/choose-the-runner-for-a-job),
consulted 2026-11-01. A macOS ARM64 CI run is not M6-specific certification.
