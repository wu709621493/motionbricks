# Independent pre-merge review of PR #29

**Decision on `5b1b0dba792e7f1bc86c05a46376a83cc351df63` (2026-11-05): request changes.** Two failure paths affect process ownership and cleanup. The existing green matrix exercises ordinary termination but misses both. Land the stacked fixes into the feature branch, then check the resulting #29 head before merging to main. This is an AI-assisted engineering review under the fork owner's account.

## Findings on the original head

| Priority | Original location | Evidence and consequence | Fix in this change |
| --- | --- | --- | --- |
| P1 | `radix_ipc.py:173–198,228–239` | Instrumented a successful call and observed reaping by `poll()`, then `killpg(old_pid, SIGKILL)`. The failure path could also reap during its TERM grace. PID reuse could redirect the signal to an unrelated group. The ordering was reproduced; no unrelated group was signalled in the experiment. | Observe exit without consuming wait status, signal the owned group, then reap. Require default SIGCHLD disposition and exclusive wait ownership. Use `waitid(WNOWAIT)` where available and a kqueue exit event on macOS Python 3.12. |
| P1 | `radix_ipc.py:173–198,283–292` | Injecting EPERM at group signal with a real sleeping child raised bare `PermissionError`, left the child running and all three pipes open. The review harness recovered its child. | Continue escalation and bounded reap, attempt a direct-child kill if group KILL fails, close each pipe, and report `CLEANUP_FAILED` with errors and the initial IPC code when available. Descendants may survive denied group signals. |
| P2 | `radix_ipc.py:382`, worker final lifetime check | A real valid response with the parent's final wall-clock sample set to issuance minus 1 ns returned `VERIFIED`. The worker had the same one-sided final check. | Recheck the full half-open issuance/expiration interval on each endpoint. The monotonic parent budget remains authoritative for elapsed time. |
| P2 | `radix_ipc.py:310–320,403–421` | A 120 ms call behind a held client lock returned success after 265 ms in one probe. Mixed calls grant two independent budgets and run the final oracle outside both. | Include lock admission in the call budget. Preserve the per-partition `timeout_s` API and add optional `total_timeout_s` for a common absolute deadline, checked through the full oracle. |
| P2 | `radix_ipc.py:109–114` | Framed JSON containing `1e999` parsed to infinity, then canonicalization raised bare `ValueError` outside the protocol handler. | Normalize parse and canonicalization errors together so a corrupt worker response reports `BAD_RESPONSE`. |
| P3 | `tools/radix_ipc_benchmark.py:measure` | Repeating a size generates different random operands under the same workload label. The summary selects their pooled trials while claiming the requested repetition count. The checked-in size list is unique. | Reject repeated sizes before warming up or launching a worker. |

## Execution and fault coverage

| Source | Python / platform | Observations |
| --- | --- | --- |
| Historical Actions on original #29 | Ubuntu x86-64, Ubuntu ARM64, macOS ARM64, each on 3.12 and 3.13 | Six radix jobs and twelve CPU preflight jobs reported success. See [radix CI](https://github.com/wu709621493/motionbricks/actions/runs/41774571365) and [CPU CI](https://github.com/wu709621493/motionbricks/actions/runs/41774571220). |
| This review, original head | Linux x86-64, separately on CPython 3.12.14 and 3.13.17 | Per interpreter: 14 radix, 20 IPC, 31 preflight, 1 example passed; 2 opt-in GPU examples skipped. |
| This review, proposed fix | Same two local interpreters | Per interpreter: 14 radix, 30 IPC, 31 preflight, 1 example passed; 2 opt-in GPU examples skipped. Benchmark smoke: 16 verified recorded trials per interpreter. |

- Real fault workers cover exit 7, SIGKILL, a valid response followed by exit 8, stalled stdin, closed pipes, late results, TERM refusal and bounded floods on both output streams. The new CPU spin explicitly ignores TERM, consumes CPU and returns `TIMEOUT` in the parent with direct-child status -9. A subsequent request succeeds.
- Descendant tests cover inherited pipes on timeout and a quiet descendant after successful leader exit. A delayed marker checks for continued execution. The parent reaps only its direct child. Group KILL delivery does not establish that every descendant has been reaped.
- Corrupt frames, replay, attempt and payload identity, forged result with recomputed digest, expiration, spent IDs and recovery use the existing real subprocess path. A false but well-formed number fails the parent integer oracle. Request IDs remain client-local, bounded to 4,096 and volatile across restart. Callers receive no partial sum or substituted oracle value.
- Signal denial and the 500 ms reap-budget exhaustion are injected. The clock tests adjust observed time in one process. Shared-budget tests use a controlled monotonic clock to cover a skipped second launch and expiry at final verification. No system clock or kernel state is changed.
- Requests are capped at 256 KiB of JSON, stdout at 32 KiB plus framing and stderr at 8 KiB, with one extra detection byte. These bound transport buffers. Separate clients can run concurrently and there is no host-wide admission or memory quota. TERM grace (150 ms), reap (500 ms), scheduling, process creation and uninterruptible kernel work can extend return latency. Callers must not reap the supervisor's child externally.

The first hosted run of the fixes exposed two Darwin-specific issues: Python 3.12 kqueue handles require explicit closing, and a group containing the unreaped zombie leader can produce EPERM. The follow-up keeps the group leader reserved through signalling, defers Darwin EPERM only after observing leader exit, and probes with signal zero after reap. Only disappearance (ESRCH) clears that deferred error. Persistent or unknown groups still fail cleanup. The regression exercises both outcomes.

## Two-worker containment experiments

The local Linux host has no Docker daemon or CLI. Attempts to create a nested user/network namespace with unshare and bubblewrap failed. Two independent workers were then run concurrently under kernel-enforced seccomp filters and per-process limits, on both local Python versions. Both policies denied socket creation and capped address space at 192 MiB, open files at 32 and CPU time at 3 seconds. The stricter policy also denied clone/fork and changing process groups/sessions. Negative socket and fork probes observed EPERM.

While the stricter worker spun, the other returned a verified dot product of 11. The parent timed out the spinner, delivered TERM and KILL, and reaped status -9. A fresh worker under the stricter policy subsequently verified 11. These trials exercise specific restrictions on a shared kernel and filesystem.

The repeatable Docker lab runs two simultaneous, non-root containers with distinct PID, mount and network namespaces, separate tmpfs, a read-only root, and read-only code/test mounts. Each has no external network, zero retained capabilities, a 32-PID limit, 256 MiB memory limit and a one-CPU quota. It checks namespace identities and private markers, kills a stuck worker in one container while the other verifies arithmetic, then verifies recovery. The Ubuntu x86-64 / Python 3.13 workflow runs the script and logs the container image ID and Python version. The [first hosted two-container run](https://github.com/wu709621493/motionbricks/actions/runs/41964184897/job/127037248205) passed, including separate namespaces, private marker checks, status -9 and recovery. Normal library calls still launch trusted local workers. All configurations share a host kernel and CPU.

## Recalculation of the checked-in benchmark

Audited the [original raw data](https://github.com/wu709621493/motionbricks/blob/5b1b0dba792e7f1bc86c05a46376a83cc351df63/docs/radix_ipc/benchmark_linux_x86_64_py312.json): all four source hashes matched the reviewed checkout. Eight fixed operand sets × two encodings × seven recorded runs yielded 112 unique attempt IDs. Recomputed every full integer dot product, workload digest, per-group byte count and all 208 min/median/max triples. Backend order alternates within each workload; seven repetitions put binary first four times. One warm-up per representation and workload is excluded. Timing observations are repeated measures of the same inputs on one uncontrolled host.

| Original signed-32, 1,024-pair workload | Binary median | Ternary median | Interpretation |
| --- | ---: | ---: | --- |
| Framed request bytes | 135,542 | 104,515 | Exact and constant across seven trials. Includes 4-byte prefix, envelope and JSON sign/digit punctuation |
| Parent request preparation, ms | 20.764 | 16.013 | Dataclass conversion, hashes and JSON serialization |
| Popen span, ms | 0.466 | 0.490 | Time until Popen returns; interpreter initialization can continue afterwards |
| Request / response windows, ms | 35.806 / 3.054 | 36.046 / 2.243 | Include scheduling, startup on request side and final envelope preparation on response side |
| Write / read syscall spans, ms | 0.432 / 0.027 | 0.284 / 0.027 | Host elapsed time around I/O calls; includes surrounding Python work |
| Worker backend execution, ms | 20.800 | 33.716 | Legacy execute call including admission, encoding/decoding and digest work |
| Parent verification total, ms | 135.236 | 132.949 | Start through oracle verification; excludes subsequent report assembly |

Ternary's framed requests used 31,027 fewer bytes (22.9%). The paired end-to-end difference (ternary minus binary, same repeat) had a median of −9.653 ms and ranged from −24.901 to +2.544 ms. Six of seven pairs favored ternary in total duration. Backend execution was slower for ternary in these observations. The median paired difference answers a different question from subtracting the two marginal medians. The independent timing groups overlap; their medians cannot be added. This setup cannot isolate pure JSON cost, interpreter startup, arithmetic instructions or pipe-copy latency. It supplies no native ternary hardware, TPU, inference or energy measurements.

## Reproduce

From the checkout root on Linux or macOS:

```sh
for py in python3.12 python3.13; do
  for suite in radix_portability radix_ipc preflight examples; do
    "$py" -S -W error::ResourceWarning -m unittest discover -s "tests/$suite" -v || exit 1
  done
  "$py" -S tools/radix_ipc_benchmark.py --repeats 2 --sizes 1 128 > "smoke-$py.json" || exit 1
done

# Full benchmark; use distinct sizes and treat timings as host-specific.
python3.13 -S tools/radix_ipc_benchmark.py --seed 20261104 --repeats 7 --sizes 1 16 128 1024 > full.json

# Requires a Linux Docker daemon and access to the official Python image.
bash tools/radix_ipc_sandboxes.sh
```
