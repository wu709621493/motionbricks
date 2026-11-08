# Independent pull request plan and approval record

Date: 2026-11-04. Repository: `wu709621493/motionbricks` only.
Reviewed base: `c815923647042726ea5be5447f70ebea4caf6b13`.
No existing tracked source or inference file is modified.
The user explicitly approved submission of these ten files and creation of a
draft PR on 2026-11-04. Only approval-status wording was updated after review;
code, tests, workflow and recorded benchmark data match the approved package.

## Proposed title

`feat: add bounded subprocess radix protocol and fault-injection lab`

## Proposed PR body

PR #28 executes trusted arithmetic backends in the caller's process, so a hanging
backend cannot be terminated independently. This change adds a separate standard-
library POSIX supervisor and single-request worker. Binary and balanced-ternary
requests cross a bounded versioned JSON pipe protocol; responses must match the
current attempt and pass an independent integer oracle. Crashes, timeout, stale
or malformed responses, duplicate attempts and incorrect arithmetic fail explicitly
without replacing results with a reference computation.

The addition includes process-group cleanup, controlled fault workers, a seeded
conversion/IPC benchmark, a six-job GPU-free Linux/macOS CI matrix, an optional
serial binary/ternary composition, and English technical/results documentation.
The current TensorRT, ONNX and in-process radix implementations are unchanged.

Validation: see `docs/radix_ipc/results.md` for the exact locally executed commands,
counts, environment and observed measurements. Cross-platform CI is configured
but not yet executed. Hardware isolation, native ternary execution, TPU inference,
HDD computation, energy benefits and Linux-fragility causation are not claimed.

## Proposed added files

| Path | Purpose |
| --- | --- |
| `motionbricks/radix_ipc.py` | Versioned framing/admission, subprocess supervisor, oracle, replay ledger and mixed mode |
| `motionbricks/radix_worker.py` | One-request worker using the existing backends |
| `tools/radix_ipc_benchmark.py` | Seeded workloads, stage timing, source hashes and raw trials |
| `tests/radix_ipc/fixture_worker.py` | Isolated test-only fault behaviors |
| `tests/radix_ipc/test_ipc.py` | Protocol, arithmetic, lifecycle and failure tests |
| `.github/workflows/radix-ipc.yml` | Six CPU-only OS/Python CI jobs and benchmark artifact |
| `docs/radix_ipc.md` | Protocol, timing semantics, limitations, TPU/HDD feasibility and sources |
| `docs/radix_ipc/results.md` | Local test results and benchmark interpretation |
| `docs/radix_ipc/benchmark_linux_x86_64_py312.json` | Raw local benchmark evidence |
| `docs/radix_ipc/pr_plan.md` | This approval scope and proposed PR text |

## GitHub actions after approval only

1. Read current `main` and compare it with the reviewed base. If it has advanced,
   apply only these ten additions to the newer base, inspect any conflicts and
   rerun affected checks. A material change in scope requires renewed review.
2. Create branch `feat/radix-ipc-fault-lab-20261104` in the user's fork, based on
   the checked base. If it already exists, inspect it; do not overwrite it.
3. Commit exactly the reviewed additions with message
   `feat: add bounded subprocess radix protocol and fault-injection lab`.
   Exclude local helper files, caches, raw captured test logs and unrelated files.
4. Push only that branch and create a **draft** PR targeting the fork's `main`,
   using the title/body above plus the final validation counts.
5. Read the actual checks for that exact head commit and report any failures or
   missing runs. Approval to create the draft PR does not authorize merging it,
   enabling auto-merge, changing repository settings or submitting upstream.

Equivalent reviewable Git operations (not executed during preparation):

```sh
git fetch origin main
git switch -c feat/radix-ipc-fault-lab-20261104 origin/main
# Apply the reviewed patch only if preparing a fresh checkout.
git apply --check motionbricks_radix_ipc.patch
git apply motionbricks_radix_ipc.patch
python -S -W error::ResourceWarning -m unittest discover -s tests/radix_ipc -v
python -S -m unittest discover -s tests/radix_portability -v
python -S -m unittest discover -s tests/preflight -v
python -S -m unittest discover -s tests/examples -v
git add motionbricks/radix_ipc.py motionbricks/radix_worker.py \
  tools/radix_ipc_benchmark.py tests/radix_ipc/fixture_worker.py \
  tests/radix_ipc/test_ipc.py .github/workflows/radix-ipc.yml \
  docs/radix_ipc.md docs/radix_ipc/results.md \
  docs/radix_ipc/benchmark_linux_x86_64_py312.json docs/radix_ipc/pr_plan.md
git diff --cached --check
git diff --cached --stat
git commit -m "feat: add bounded subprocess radix protocol and fault-injection lab"
git push -u origin feat/radix-ipc-fault-lab-20261104
```

The connected GitHub API may be used for equivalent branch/tree/commit/PR
operations. The scope is identical: one fork branch, one reviewed commit, one
draft PR. There are no remote writes in the preparation stage.
