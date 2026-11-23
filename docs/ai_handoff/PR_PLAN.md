# Independent PR: executable handoff and routing simulation

Target: `wu709621493/motionbricks`, base `main`.
Branch: `feat/ai-handoff-router`.
Proposed title: **Add CPU-only AI handoff protocol, routing controls and paired benchmarks**.
This is a follow-up to merged PR #20. It adds files only and does not merge itself.

## File manifest

| Added path | Purpose |
| --- | --- |
| `motionbricks/ai_handoff.py` | Strict versioned contract, role checks, state transitions, routing, receipts, release and invalidation |
| `motionbricks/ai_handoff_verify.py` | Separate exact arithmetic oracle |
| `tools/ai_handoff/benchmark.py` | Seeded tasks, paired topologies, equal budgets and host timing |
| `tests/ai_handoff/test_protocol.py` | Adversarial protocol and lifecycle tests |
| `tests/ai_handoff/test_benchmark.py` | Exact fault outcomes, paired reproducibility and cost assertions |
| `.github/workflows/ai-handoff.yml` | Six CPU-only Linux/macOS and Python 3.12/3.13 jobs |
| `docs/ai_handoff/README.md` | English contract, experiment design, DeepSeek-R1 technology and ethics |
| `docs/ai_handoff/RESULTS.md` | English results, interpretation and limitations |
| `docs/ai_handoff/results.json` | Reproducible per-task outcomes and counters |
| `docs/ai_handoff/local_measurements.json` | Actual local timing samples for two interpreters |
| `docs/ai_handoff/PR_PLAN.md` | This review manifest and operation plan |

Existing runtime modules, package dependencies, original PR #20 files and existing
CI workflows are unchanged. Any checkout-only LFS differences in unrelated CSV
files are excluded from the commit.

## Validation commands

```bash
python -S -m unittest discover -s tests/ai_handoff -v
python3.13 -S -m unittest discover -s tests/ai_handoff -v
python -S -m tools.ai_handoff.benchmark --check docs/ai_handoff/results.json
python3.13 -S -m tools.ai_handoff.benchmark --check docs/ai_handoff/results.json
python -S -m tools.ai_handoff.benchmark --timing --output handoff-host-results.json
python -S -m unittest discover -s tests/preflight -v
git diff --cached --check
git diff --cached --name-status
```

The interpreter can be invoked by its installed absolute path if `python3.13`
is not on PATH. No package installation or MotionBricks editable install is needed.

## Concrete GitHub operations

1. Read `main`, PR #20, its proposal/example and current workflow definitions.
2. Prepare the eleven added files against the pinned base SHA; run the commands
   above and review the complete staged diff.
3. Create one Git tree using the base tree plus exactly the manifest paths, then
   create a commit whose parent is the inspected base commit. Create
   `refs/heads/feat/ai-handoff-router` pointing to that commit. No force push.
4. Open an ordinary reviewable PR from that branch into `main`, linking PR #20
   and the result files. Do not request reviewers, send comments or merge.
5. Read back the PR file list and head SHA, then inspect the dedicated workflow
   and existing checks. Record actual status; configured platforms are not assumed
   to have passed until their jobs complete.

Equivalent local Git/CLI operations for a maintainer with an authenticated clone:

```bash
git switch -c feat/ai-handoff-router c815923647042726ea5be5447f70ebea4caf6b13
git add motionbricks/ai_handoff.py motionbricks/ai_handoff_verify.py
git add tools/ai_handoff/benchmark.py tests/ai_handoff
git add .github/workflows/ai-handoff.yml docs/ai_handoff
git diff --cached --check
git commit -m "Add CPU-only AI handoff protocol and paired routing study"
git push -u origin feat/ai-handoff-router
gh pr create --repo wu709621493/motionbricks --base main \
  --head feat/ai-handoff-router \
  --title "Add CPU-only AI handoff protocol, routing controls and paired benchmarks" \
  --body-file /path/to/reviewed-pr-body.md
```

Review emphasis: host trust assumptions, lifecycle checks immediately before
release, post-release invalidation, bounded representations and budgets, verifier
diversity, metric denominators, and the distinction between protocol simulations
and unperformed multi-model/physical experiments.
