# Local validation and synthetic benchmark results

2026-11-04; local validation snapshot based on `c815923647042726ea5be5447f70ebea4caf6b13`.
These measurements were collected before submission. The user subsequently
approved the reviewed ten-file change set for a draft PR on 2026-11-04.
Remote CI status should be read from that PR; the results below remain local evidence.

## Executed validation

Environment: Linux x86_64, Python 3.12.14, kernel 6.18.57, glibc 2.39.
No GPU/TPU or project dependency installation was used. LFS model assets were not hydrated.

| Command | Observed result |
| --- | --- |
| `python -S -W error::ResourceWarning -m unittest discover -s tests/radix_ipc -v` | 20 passed in 8.263 s |
| `python -S -m unittest discover -s tests/radix_portability -v` | 14 passed in 1.227 s |
| `python -S -m unittest discover -s tests/preflight -v` | 31 passed in 2.157 s |
| `python -S -m unittest discover -s tests/examples -v` | 1 passed; 2 existing opt-in GPU tests skipped |
| `python -S tools/radix_ipc_benchmark.py` | 112 recorded trials verified; 16 warm-up requests and 2 mixed-demo partitions also verified |

Total: **66 passed, 2 skipped** across the four unittest suites. The three default
paths (binary, ternary, and mixed) returned `-122`. The 112 benchmark trials span
8 shared workloads × 2 representations × 7 repetitions. Hardware fault tolerance,
model inference, native ternary hardware, physical HDD and TPU execution were not tested.

The fault tests include real subprocess exit 7, SIGKILL termination, valid output
followed by exit 8, 0.5 s deadlines, SIGTERM refusal followed by SIGKILL, bounded
stdout/stderr floods, no stdin reads, closed pipes without exit, and a surviving
descendant retaining pipes. Direct-child reaping is asserted. A test-only delayed
descendant marker checks that group cleanup prevents later execution.

Additional protocol checks exercise framing/serialization, excessive JSON nesting,
request expiry, parent rejection after the wall-clock lifetime elapses, old response
replay, stale IDs/digests, wrong schema, invalid digits, a wrong numeric result with
a recomputed digest, duplicate IDs, explicit new-ID retries and mixed-partition failure.
Parent interruption is tested to ensure child cleanup. The first development run
exposed missing explicit JSON depth rejection; the final candidate adds a depth-12
pre-parse guard and passes the corresponding regression. No failure is reported as
a successful oracle substitute.

## Recorded benchmark

Raw observations: [benchmark_linux_x86_64_py312.json](benchmark_linux_x86_64_py312.json).
It contains complete synthetic inputs, per-attempt digests/IDs, byte counts, child
cleanup status, source hashes, raw stage timings and min/median/max summaries.
Seed 20261104; shared signed-16 and signed-32 ranges; widths 16/11 and 32/21
bits/trits; one cache warm-up per representation/size; fresh interpreter per call.
Backend order alternates between repetitions. Host load and CPU affinity were not controlled.

Each row below is the median of seven trials. Times are milliseconds, including
ordinary software overhead as defined in [the protocol note](../radix_ipc.md).

| Shared workload | Backend | Request bytes | Integer→digits | Request serialization | Backend execute | End-to-end |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| int16_n1 | binary | 442 | 0.010 | 0.040 | 0.048 | 48.578 |
| int16_n1 | ternary | 424 | 0.010 | 0.051 | 0.039 | 51.076 |
| int16_n16 | binary | 1,462 | 0.049 | 0.293 | 0.319 | 46.574 |
| int16_n16 | ternary | 1,246 | 0.043 | 0.159 | 0.206 | 47.316 |
| int16_n128 | binary | 9,078 | 0.346 | 1.488 | 1.472 | 54.572 |
| int16_n128 | ternary | 7,346 | 0.308 | 1.152 | 1.922 | 52.922 |
| int16_n1024 | binary | 70,006 | 2.445 | 13.011 | 13.106 | 107.393 |
| int16_n1024 | ternary | 56,478 | 2.426 | 9.831 | 14.003 | 94.193 |
| int32_n1 | binary | 506 | 0.012 | 0.051 | 0.061 | 47.816 |
| int32_n1 | ternary | 473 | 0.011 | 0.044 | 0.057 | 47.744 |
| int32_n16 | binary | 2,486 | 0.078 | 0.361 | 0.412 | 54.521 |
| int32_n16 | ternary | 1,972 | 0.071 | 0.309 | 0.520 | 53.614 |
| int32_n128 | binary | 17,270 | 0.587 | 2.992 | 2.885 | 62.032 |
| int32_n128 | ternary | 13,428 | 0.592 | 2.268 | 4.770 | 65.511 |
| int32_n1024 | binary | 135,542 | 4.831 | 20.764 | 20.800 | 135.236 |
| int32_n1024 | ternary | 104,515 | 4.205 | 16.013 | 33.716 | 132.949 |

### Independent stage observations for 1024 signed-32-bit pairs

| Stage | Binary median (ms) | Ternary median (ms) |
| --- | ---: | ---: |
| Parent digit encoding | 4.8314 | 4.2048 |
| Parent request serialization | 20.7637 | 16.0134 |
| Request IPC window | 35.8061 | 36.0463 |
| Worker request decode/admit | 27.2401 | 20.4375 |
| Worker backend execution | 20.8003 | 33.7162 |
| Worker result encoding/hash | 0.0399 | 0.0301 |
| Response IPC window | 3.0539 | 2.2425 |
| Parent response parse/validation | 9.1165 | 6.9722 |
| Parent result digit decoding | 0.0125 | 0.0097 |
| Parent oracle/equality | 0.0906 | 0.0913 |
| Parent end-to-end total | 135.2361 | 132.9487 |

These rows must not be summed: parent round-trip and worker/transport windows
overlap, and medians of component durations do not generally sum to the median
of their total. Request IPC includes startup/scheduling; response IPC includes
final envelope preparation. Backend execution includes legacy adapter overhead.

For the signed-32/1024 workload, ternary JSON used 104,515 bytes versus 135,542
bytes for binary JSON (about 22.9% fewer in this encoding). Its observed median
backend execution was slower, while shorter JSON reduced some conversion work.
The end-to-end observations include interpreter startup and host noise. Seven
trials on one uncontrolled host do not justify a general speed advantage. This
is not a packed-binary versus physical-trit bus comparison, energy study, or
causal test of Linux reliability.

## Unexecuted checks and remaining limits

- The six proposed GitHub jobs have **not run** for this candidate. Linux ARM64,
  macOS ARM64 and Python 3.13 are configured targets, not verified results.
- Hashes provide content association, not authentication or worker attestation.
- Replay bookkeeping is bounded, client-local and not durable across restart.
- Same-host process groups are not a security sandbox or hardware isolation.
- Pure ALU time, kernel copy time, power, TPU/HDD operation and inference remain unmeasured.
- The supervisor bounds normal timeout handling and cleanup waits, but cannot
  guarantee preemption of OS process creation or uninterruptible kernel work.

## Reproduce and review

```sh
python -S -W error::ResourceWarning -m unittest discover -s tests/radix_ipc -v
python -S -m unittest discover -s tests/radix_portability -v
python -S -m unittest discover -s tests/preflight -v
python -S -m unittest discover -s tests/examples -v
python -S tools/radix_ipc_benchmark.py --seed 20261104 --repeats 7 --sizes 1 16 128 1024 > radix-ipc-benchmark.json
```

See [the independent PR proposal](pr_plan.md) for exact files and approval-gated GitHub actions.
