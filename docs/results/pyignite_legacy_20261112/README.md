# PyIgnite legacy compatibility — local evidence

Base: `wu709621493/motionbricks@b6d27559016e41f2facceedd1a55c02a9939f2f7`.
Date: 2026-11-12 (Asia/Shanghai).

This was a partial local checkout fetched at the above commit plus this patch.
The local Git snapshot identifier recorded by `validate.py` is not a published
repository commit. Source hashes and build commands identify the actual files.

| Check | Result | Evidence |
|---|---|---|
| Existing + new Python contracts | 24 passed, no skips | `contracts.txt` |
| Native host smoke | 7 check groups passed; hardware health unknown | `host-smoke.json` |
| Original strict Torch parity | 8 cases passed, unchanged atol/rtol 2e-5 | `strict-parity.json` |
| Wheel + sdist | Build passed; library/license in wheel; build sources in sdist | `package-build.txt` |
| Installed wheel, isolated process outside source tree | PASS; Torch not imported | `wheel-smoke.json` |
| P5/x87 local build attempt | BLOCKED: 32-bit C++ headers/development libraries missing | `p5-build-attempt.txt` |
| IA-32/SSE2 local build attempt | Same toolchain limitation | `sse2-build-attempt.txt` |
| Physical legacy CPU / old target OS / QEMU | NOT_RUN | No claim of compatibility certification |

Wheel testing used a separate venv with system site packages and `--no-deps`;
NumPy 2.3.5 was reused. This is not proof of a fully clean dependency install.
Both a source distribution and its wheel were rebuilt after including LICENSE.
The tiny smoke is not a full G1 inference or a cache-health test. Local dynamic
PE parity does not close its previously documented cross-environment issue.

The new CI jobs compile both ELF32 targets with multilib and run on modern
x86-64 runners. Their current result belongs to the PR/commit Actions page;
this local evidence folder does not invent or pre-record their outcomes.

## Temperature/checkpoint follow-up

The first set of receipts above records the initial compatibility patch
`f45438a24c4208967829cca522f898b7d706fdd3`; its original source hashes are retained.
The follow-up adds `TemperatureGuard` and guarded FC checkpointing.

- `thermal-contracts.txt`: 37 tests passed, no skips, including 13 added sensor,
  trip, persistence, recovery and integration tests.
- `thermal-package-build.txt`: rebuilt sdist/wheel with the thermal module.
- `thermal-wheel-smoke.json`: installed wheel, simulated sensor, exact restoration
  of a complete FC output after file and directory fsync.
- `thermal-trip-simulated.json`: example checksummed checkpoint with simulated
  temperatures and the last completed result retained at a latched overheat trip.
- `thermal-source-hashes.json`: source identity for the follow-up.

This environment has no `/sys/class/hwmon`; real temperature, fan failure,
CPU destruction and power-loss behavior were NOT tested.

Initial-commit remote CI: both ELF32 jobs passed. The strict Linux x86-64 job
reproduced the retained `PE-4096-64` mismatch (3652/262144 elements, max absolute
violation 0.00012207). The independent baseline comparison reported
`PASS_NO_NEW_REGRESSION` and `strict_current_parity=FAIL`. These are different
claims; no tolerance or failing strict check was suppressed. See
[initial PyIgnite run](https://github.com/wu709621493/motionbricks/actions/runs/43154823356)
and [baseline comparison](https://github.com/wu709621493/motionbricks/actions/runs/43154823353/job/130972193392).
