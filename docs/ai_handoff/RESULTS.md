# Synthetic protocol results

Recorded 2026-11-04. These are deterministic software experiments, not AI model
evaluations. The manifest digest is
`c68c2ca5e531ebd7898244a5fc4a6aa2c7378aa2f95e7967e68feff72d230a73`.
All task-level outcomes are in [results.json](results.json); metric definitions
and assumptions are in [README.md](README.md).

## Paired counters

Each row uses the same 250 tasks: 40 valid completions and 210 expected refusals
or invalidation checks. Only topology and the stated work ceiling vary.

| Work ceiling | Topology | Valid completed | Unsafe releases | False rejection | Decision error | Payload deliveries | Payload bytes | Transport messages | Work used |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | Broadcast | 40/40 | 0/210 | 0% | 0% | 560 | 354,492 | 670 | 1,280 |
| 100 | Directed | 40/40 | 0/210 | 0% | 0% | 140 | 88,623 | 250 | 860 |
| 6 | Broadcast | 0/40 | 0/210 | 100% | 16% | 560 | 354,492 | 560 | 920 |
| 6 | Directed | 30/40 | 0/210 | 25% | 4% | 140 | 88,623 | 250 | 850 |

At the normal ceiling, both conditions reject the injected faults and complete
all valid cases. **There is no observed error-rate advantage for directed routing
at that ceiling.** Payload fanout is 75% lower by construction (one peer versus
four), transport messages decrease by 62.7%, and declared work decreases by 32.8%.
These reflect this fixed topology and cost model, not a general AI efficiency law.
Work per valid completion, including invalid-case work, is 32 versus 21.5 credits.

At six credits, broadcast consumes its budget at delivery and cannot finish an
ACK/verification/release sequence. Directed routing completes the 30 ordinary
valid cases; the ten valid-retry cases require a seventh credit and fail explicitly.
This is an availability/overhead result. Many invalid tasks also stop at the budget
gate, so the tight condition alone cannot establish that a specific semantic fault
was detected. The normal-budget test asserts each fault's exact rejection code.

Post-release cancellation, revision and expiry are represented by ten cases each.
At the normal ceiling they first release, then deny current access and retain one
invalidation record. Historical records are not removed. Conflicting duplicates
leave the original candidate unchanged; that legitimate candidate is not itself
an unauthorized result.

## Measured processing cost

Local host: Linux x86-64, glibc 2.39. Ten repetitions per condition alternate
topology order. Raw samples, exact OS string and interpreter versions are preserved
in [local_measurements.json](local_measurements.json). Median milliseconds for
one full 250-task run:

| Python | Work ceiling | Broadcast CPU / elapsed | Directed CPU / elapsed |
| --- | --- | ---: | ---: |
| 3.12.14 | 100 | 23.239 / 24.189 | 21.798 / 21.805 |
| 3.12.14 | 6 | 18.160 / 18.162 | 22.230 / 22.236 |
| 3.13.17 | 100 | 27.960 / 27.963 | 24.734 / 24.738 |
| 3.13.17 | 6 | 20.405 / 20.411 | 23.724 / 23.726 |

Directed routing has lower median CPU time at the normal ceiling on this host.
At the tight ceiling, broadcast exits earlier and is faster while completing no
valid tasks. This illustrates why runtime alone is insufficient. These short
measurements are noisy, include Python fixture/broker overhead, and provide no
real-model latency, energy or cost estimate. Cross-host timing is not a CI gate.

## Verification record

| Check | Observed result |
| --- | --- |
| Python 3.12.14, `-S`, handoff unittest suite | 26 tests passed |
| Python 3.13.17, `-S`, handoff unittest suite | 26 tests passed |
| Deterministic result comparison, both interpreters | Exact JSON equality after parsing |
| Existing CPU preflight suite, Python 3.12.14 with `-S` | 31 tests passed |
| New Linux/macOS workflow | All six OS/Python jobs passed in [run 41781106625](https://github.com/wu709621493/motionbricks/actions/runs/41781106625) |
| Existing CPU workflow | All twelve jobs passed in [run 41781106747](https://github.com/wu709621493/motionbricks/actions/runs/41781106747) |

Those remote runs tested implementation commit
`cf9de42650578bd261784cb2845ce3d0b0c30387` on PR #30. Subsequent documentation-only
updates do not change the implementation; the PR checks show the current head.

The suite additionally tests hostile JSON, boolean revision coercion, unsupported
versions, exact expiry boundaries, clock rollback, denied out-of-order transitions,
source/model/config binding, lossless zero conversion, cache allocation after
budget exhaustion, cancellation despite exhausted budgets and absence of GPU
imports. The adapter fault control demonstrates that receiver acceptance alone
cannot release a wrong conversion. A second host-fault test changes an artifact
after verification and confirms the release gate rechecks it.

No GPU inference or physical execution was tested. No model weights were loaded
for inference or evaluation, and no model-serving APIs were called. The broader perception-theory claims, real shared-chat
behavior, prompt injection resistance, real evidence correctness, process security
and human comprehension remain unmeasured.
