# Cross-process radix adaptation and fault-injection prototype

Status: approved for draft PR submission, 2026-11-04. Requested by Mengcheng Wu
(Windy Wu); implementation and technical draft prepared with AI assistance.
The user explicitly approved the reviewed ten-file change set for submission.
Approval does not include merging the PR or submitting it upstream.

Baseline: `c815923647042726ea5be5447f70ebea4caf6b13` on the user's MotionBricks fork.
It contains merged [PR #28](https://github.com/wu709621493/motionbricks/pull/28)
(`cfb5e9b43df89845f92210cd6f0e17bc6ba9837f`) and the subsequent Oyasumi merge.
All additions are independent of the existing TensorRT and CPU ONNX inference paths.
`radix_portability.py` and its tests are unchanged.

## Purpose and evidence boundary

The experiment submits an exact integer dot product to a fresh Python child,
checks its complete response, and compares the returned integer with a separate
parent-side calculation over the original integers. It preserves the binary
Python-integer backend and the balanced-trit convolution/carry backend from #28.
An optional composition partitions one vector between those two subprocess backends.

| Claim | Evidence supplied here |
| --- | --- |
| Software process separation | Distinct address spaces; bounded pipe I/O; deadline handling; group signals; direct-child reaping |
| Security sandbox | **Not provided.** The child runs trusted local code under the same OS identity |
| Hardware fault isolation | **Not provided.** Parent and child share the host, kernel, memory subsystem and CPU |
| Native ternary computation | **Not implemented or tested.** Trit arithmetic is simulated on a binary CPU |
| MotionBricks inference | **Not performed.** No models, weights, GPU runtime or live robot are involved |
| Binary arithmetic causes Linux fragility | **Not established.** This experiment cannot identify that causal relationship |

Checksums correlate contents; they are neither authentication nor protection from
malicious code. The oracle is independent of the response encoding and child
process, not independent hardware or a different implementation language.

## Run without installing project dependencies

From the repository root, with Python 3.12 or 3.13 on Linux or macOS:

```sh
python -S -W error::ResourceWarning -m unittest discover -s tests/radix_ipc -v
python -S -m unittest discover -s tests/radix_portability -v
python -S tools/radix_ipc_benchmark.py --seed 20261104 --repeats 7 --sizes 1 16 128 1024 > radix-ipc-benchmark.json
```

No `pip install .`, CUDA, TensorRT, JAX or TPU installation is needed.
The worker uses `python -I -S` and an explicit checkout path. It ignores
`PYTHONPATH` and receives only a small locale/PATH environment, not the parent's
full environment. This is import hygiene, not a security boundary.

```python
from motionbricks.radix_ipc import SubprocessDotClient, run_mixed_dot

client = SubprocessDotClient()
a, b = [13, -7, 0, 42], [3, 11, -9, -2]
assert client.run(a, b, 'binary')['value'] == -122
assert client.run(a, b, 'ternary')['value'] == -122
assert run_mixed_dot(a, b)['value'] == -122
```

For mixed execution, the first `floor(n/2)` pairs go to binary and the remainder
to ternary. Each partition must pass independently, then their sum is verified
against the full oracle. A failure returns no partial sum. This mode is serial;
by default `timeout_s` applies to each partition. Pass `total_timeout_s=5.0`
to share one absolute monotonic deadline across both partitions and the full
oracle. The earlier of the partition and task deadlines governs each worker.
A deadline bounds acceptance. Termination and reaping can take additional time.

## Wire contract, version 1

A frame is a four-byte unsigned big-endian payload length followed by canonical
UTF-8 JSON. Canonical serialization uses sorted keys, no insignificant spaces,
ASCII escaping, and no NaN/Infinity. Exactly one frame and EOF are allowed per
process in each direction. A second frame, trailing byte, duplicate JSON field,
invalid UTF-8, excessive nesting (>12), or truncated payload is rejected.
No pickle, shell command text, executable name, or native memory pointer is
accepted from a request.

Request payload limit: 256 KiB; response payload limit: 32 KiB; stderr: 8 KiB.
The parent reads at most one byte beyond a stream limit to detect overflow and
then terminates the process group. Limits are enforced during I/O. Request
vectors have 1–1024 pairs, widths 1–32 logical digits, least-significant digit
first, and the exact signed semantics of #28. Booleans and floats are rejected.

| Request field | Contract |
| --- | --- |
| `wire_version` | Integer 1, distinct from inner arithmetic `schema_version` |
| `kind` | `integer_dot` |
| `request_id` | 32 lowercase hexadecimal characters; random UUID by default |
| `issued_unix_ns`, `expires_unix_ns` | Integer same-host wall-clock lifetime, at most 60 seconds |
| `backend` | `binary` or `ternary`; checked against the payload format |
| `payload` | #28 request: `schema_version`, `format`, `lhs`, `rhs`; arrays replace tuples on the wire |
| `payload_sha256` | SHA-256 of the canonical inner request, compatible with #28's digest |

All fields are mandatory; extra fields are rejected. The parent also computes a
SHA-256 digest of the entire request envelope, binding the ID, lifetime, backend
and operand payload. The worker checks admission before calling the old backend.
It checks expiration again after the backend returns.

| Successful response field | Contract |
| --- | --- |
| `wire_version`, `request_id` | Must match the current request |
| `request_sha256` | Digest of the entire current request envelope |
| `status` | `OK`; parent reports `VERIFIED` only after all checks |
| `result` | #28 result: inner schema, inner request digest, expected output format and digits |
| `result_sha256` | Digest of the canonical result object |
| `timing_ns` | Five integer duration/clock fields described below |

For malformed requests the worker emits a small versioned `FAILED` envelope
with `error_type` and exits 2. A nonzero exit is authoritative: even correct
output followed by an abnormal exit is rejected. The parent never needs to trust
an ID from a malformed request. Normal returns require all fields, correct
framing, successful exit, matching result format and digest, valid digits,
freshness, consistent timing metadata, and exact oracle equality.

## Lifecycle, deadlines and retries

The client serializes its own calls with a lock. Each attempt launches a fresh
worker in a new POSIX session/process group. Nonblocking stdin/stdout/stderr are
multiplexed with `selectors`, so a worker that never reads input or fills stderr
cannot indefinitely block the supervisor. The caller's monotonic deadline
starts before waiting for the client lock and is checked during I/O, after process exit,
and after verification. Accepted timeouts range from 0.01 to 60 seconds.
Same-host wall-clock expiration additionally rejects stale envelopes; clock
jumps may conservatively reject work, while the parent monotonic deadline remains
the execution limit. Both endpoints check the lower and upper wall-clock bounds
at completion. A call that times out in the queue has not spent its ID. There is no network clock-synchronization claim.

On failure or caller interruption, the supervisor sends SIGTERM to its process
group, allows up to 150 ms for the leader, then sends SIGKILL to the group and
waits up to 500 ms to reap the direct child. Cleanup also targets any group
members remaining after an otherwise successful leader exit. Inability to reap
within that budget, group-signal errors and pipe-close errors report
`CLEANUP_FAILED`. Details include `cleanup_errors`, direct-child reap status and
the initial IPC error when available. A failed group kill triggers a direct-child
kill attempt. Group signals precede the final reap to keep the PGID reserved.
The caller must leave SIGCHLD at its default disposition and give the supervisor
exclusive ownership of its worker's wait status. Grandchildren are
not waitable by this parent; they are killed if they remain in the group, and
reaping is the OS/reparenting supervisor's responsibility. Fault tests cover a
child retaining inherited pipes after its parent exits.

This is not a hard real-time guarantee: process creation cannot necessarily be
interrupted, scheduling can delay handling, and an uninterruptible kernel task
can outlive the budget. Escaped process groups, hostile same-user code, child
memory exhaustion, filesystem/network access and host crashes are not contained.
Use a real sandbox/container policy or dedicated hardware for those requirements.
The parent buffer cap is not a child memory or CPU resource quota.

A client remembers up to 4096 admitted request IDs, including failures. It never
evicts: duplicate IDs fail with `DUPLICATE_ID`; a full ledger fails with
`LEDGER_FULL`. Identical input with a **new** ID is a deliberate new attempt,
not a cache hit or silent retry. A fresh client has a fresh in-memory ledger.
This is session-scoped replay resistance, not durable/global exactly-once
execution. A response from a previous process cannot satisfy a new envelope,
even when the integer operands are identical. A worker accepts only one request;
a duplicate frame in its input fails instead of executing twice.

Errors include `SPAWN_FAILED`, `EXIT`, `TIMEOUT`, `OUTPUT_LIMIT`, `BAD_FRAME`,
`BAD_RESPONSE`, `EXPIRED_RESPONSE`, `RESULT_MISMATCH` and `CLEANUP_FAILED`.
Local admission raises `ContractError`. Errors do not carry an accepted value,
and no failed backend is replaced with the oracle result or another backend.
A caller must explicitly choose any later attempt and its new ID.

## Timing definitions and reproducible cost comparison

All durations use `monotonic_ns`; Python documents this same-host clock as shared
across processes on the supported platforms. Unix time is used only for freshness.
The report keeps parent stages, child stages and IPC observations in separate
objects. **Do not sum those objects: they overlap.** Only `host_timing_ns`
components sum to that object's `total_ns`.

| Measurement | Included work and limitations |
| --- | --- |
| Parent `validate_ns` | Client queue wait, input validation, ID admission and ledger handling |
| Parent `encode_digits_ns` | Original integers to binary/trit tuples |
| Parent `serialize_request_ns` | Dataclass conversion, envelope construction, hashes and frame serialization |
| Parent `process_roundtrip_ns` | Process launch, worker startup, exchange, worker work, exit and cleanup |
| Parent `deserialize_validate_ns` | Framing/JSON validation, response identity/digests/format and telemetry checks |
| Parent `decode_digits_ns` | Verified result digits to a Python integer |
| Parent `oracle_verify_ns` | Independent integer dot product and equality check |
| Worker `decode_request_ns` | JSON parse/canonical check, request admission and digest validation |
| Worker `backend_execute_ns` | Existing `backend.execute`: arithmetic plus its admission, output construction and digest overhead |
| Worker `encode_result_ns` | Result dataclass conversion and canonical serialization/hash |
| IPC request window | First parent write attempt to complete child frame/EOF read; includes startup wait, scheduling and pipe delivery |
| IPC response window | Child result-ready mark to last parent response byte read; includes envelope hashing/serialization, flush and scheduling |
| Parent syscall totals | Time inside observed read/write calls, excluding waits; not end-to-end transfer latency |
| Process spawn / cleanup | Separate supervisor observations nested inside the round trip |

The child reports `request_received_ns` and `response_ready_ns`; its three
stages exactly fill that interval. The parent checks their order against its
own send/receive timestamps. Metadata comes from trusted worker software: this
is instrumentation consistency checking, not attestation. Pure kernel-copy time,
pure ALU time and separate final-envelope serialization are **not isolated** by
this prototype. The two IPC windows are explicit transport observations, not
network throughput or device-bus benchmarks.

The benchmark uses seed 20261104, lengths 1/16/128/1024, and two shared integer
ranges: signed 16-bit and signed 32-bit. Corresponding widths are 16 bits vs
11 trits, and 32 bits vs 21 trits. Both representations receive identical
integers within the shared range; ternary's additional range is not exploited.
One warm-up per representation primes OS caches; every call still starts a new
interpreter. Seven recorded repetitions alternate backend order. The output
contains inputs, workload digests, source hashes, host identity, all raw trials
and min/median/max summaries. Reproducible refers to workloads and procedure,
not identical IDs, timestamps or timing values.

JSON represents a logical digit as a number and punctuation, not a packed
physical bit/trit. Wire byte counts are therefore format-specific. Fewer logical
digits need not imply faster software arithmetic. There are no speed thresholds,
energy measurements, significance claims or extrapolations to real hardware.
See [local results](radix_ipc/results.md) and the raw JSON alongside them.

## Exploring TPU-only and single-HDD computation

| Interpretation | Assessment and next test |
| --- | --- |
| TPU as the only accelerator; CPU host allowed | A credible future path. Google documents a TPU VM/host and tensor accelerator. Port a bounded arithmetic kernel, prove dtype/range behavior, synchronize completion, then record host↔device transfer, compile and execution separately. This prototype supplies no TPU code or result |
| Literally TPU hardware with no host CPU, OS or runtime control | Not demonstrated by Cloud TPU's documented host architecture. Removing host orchestration requires a different autonomous system design; merely using a TPU does not establish it |
| One HDD stores operands/results while a host streams and computes | Feasible as external-memory software, but arithmetic still runs on the host. A future test should use an explicitly identified physical HDD and separate sequential I/O, CPU work, cache effects and durability policy |
| The drive's embedded controller computes a user kernel | A conditional firmware/platform research project. Some Seagate drives document a controller with a RISC-V CPU. That is an embedded electronic processor, not arithmetic performed solely by rotating platters; a supported programmable interface and available compute/memory budget would need proof |
| Bare platter/head mechanism alone executes this protocol | No implementation or general-purpose execution interface is supplied. Storage as a theoretical computation tape still needs a state-transition controller, power and I/O machinery |

TPU exactness is not automatic. For 1024 signed-32-bit pairs, the largest positive
sum is `1024 * (-2**31)**2 = 2**72`, requiring 74 signed binary bits to represent
it. A conventional fixed-width accumulator may overflow; a floating approximation
does not satisfy this exact-integer contract. Possible future restricted-range
or multi-limb/residue designs need an operator audit and adversarial parity tests.
No claim about supported TPU dtype/version is made without an actual device test.
The existing [TPU integration proposal](tpu_integration_protocol.md) remains a
separate architecture document, not an implemented inference backend.

A disk lookup table illustrates limits without pretending to measure hardware:
all signed-8-bit multiplication pairs require `2**16` two-byte products = 128 KiB.
All signed-32-bit pairs would require `2**64` eight-byte products = 128 EiB,
before indexing, metadata or redundancy. A lookup does not remove the need for
address calculation, accumulation or control logic. At an **assumed** 7200 RPM,
one rotation takes 8.33 ms and uniform random phase contributes 4.17 ms average
rotational wait; seek, controller, queue and transfer times are additional. This
is a kinematic estimate, not an observed HDD performance result. No physical HDD
is identified or tested here, no drive firmware is modified, and filesystem I/O
on this host is not mislabeled as platter computation.

## Tests and review gates

The dedicated workflow adds six proposed CPU-only jobs: Ubuntu x86-64/ARM64 and
macOS ARM64, each with Python 3.12/3.13. It installs no dependencies, runs old radix
tests, IPC/fault tests and a small benchmark, and uploads benchmark JSON.
The [pre-merge review](radix_ipc/review_29.md) separates the original CI run,
review reruns, and the two-container experiment.

Tests include signed/extreme arithmetic, 1024-element payloads larger than typical
pipe buffers, malformed/oversized/deep/duplicate/truncated frames, unsupported
versions, request/response expiration, full old-response replay, wrong result with
a recomputed digest, repeated IDs, repeated content with new IDs, failed ID reuse,
output floods, no input reads, closed pipes without exit, crashes/signals,
valid output followed by failure, TERM refusal/KILL escalation, descendants,
parent interruption, mixed-partition failure, and clean subsequent attempts.
The fault worker lives only under `tests/`; the runtime exposes no fault-mode flag.

## Primary technical sources

Consulted 2026-11-04. These document mechanisms; they do not certify this code.

1. [Python 3.12 subprocess](https://docs.python.org/3.12/library/subprocess.html):
   pipe handling, process groups, timeout cleanup and process-creation limits.
2. [Python 3.12 selectors](https://docs.python.org/3.12/library/selectors.html):
   multiplexed pipe I/O on Unix; no Windows-pipe support is claimed.
3. [Python 3.12 time](https://docs.python.org/3.12/library/time.html#time.monotonic):
   monotonic clocks and cross-process comparability.
4. [Google Cloud TPU architecture](https://docs.cloud.google.com/tpu/docs/system-architecture-tpu-vm):
   accelerator and host/VM relationship.
5. [Seagate Mozaic 3+ technical overview](https://www.seagate.com/resources/what-is-mozaic-3plus-how-does-it-work-and-what-can-it-do-for-my-data-center/):
   embedded controller responsibilities and its documented RISC-V CPU.
