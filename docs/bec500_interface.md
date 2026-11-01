# 500-atom BEC research interface and compatibility

Status: experimental interface v0.1; classical fixtures only. Requested by
Mengcheng Wu (Windy Wu). The default fixture specifies **500 requested Rb-87 atoms**
and two-mode population readout. Rb-87 is an explicit initial software fixture
choice, not a claim that hardware has been selected or a BEC prepared.

## Scope and physical interpretation

An atom count is not a qubit count. A Bose–Einstein condensate, an individually
addressable neutral-atom register and a universal gate-based quantum computer have
different state/control descriptions. BEC formation and useful entanglement each
require experimental evidence. This module prepares no atoms and does not simulate
condensation, interactions, decoherence, spin squeezing or a 500-qubit wavefunction.

The first supported operation is `two_mode_population`. Mode 0/1 are abstract
readout labels, not independently addressable atom IDs. The preparation ID must
identify the actual trap, modes, calibration and protocol before a future device
adapter can interpret them. No pulse programming, Hamiltonian execution, general
circuit compilation or ONNX conversion is implemented.

## Interface and accounting

`motionbricks.cold_atoms` depends only on the standard library and the existing
`motionbricks.optical_quantum` module. It reuses its public `ClockReading`,
`OpticalClock` protocol and `HardwareUnavailable` error without modifying those
APIs or schema-version-1 optical records.

| Component | Meaning |
| --- | --- |
| `BECRequest` | request ID, artifact SHA-256, exactly 500 requested atoms, species, preparation ID, operation and 1–4096 shots |
| `PopulationShot` | actual loaded atoms, mode-0 count, mode-1 count and lost atoms, each a bounded integer |
| `BECResult` | request association, accepted population shots, rejected-shot count, acquisition-start clock, backend/evidence and optional raw-record hash |
| `ColdAtomBackend` | synchronous `sample(request, timeout_seconds=...)`, `close()` |
| `SimulatedBEC500` | deterministic classical binomial fixture, with a borrowed clock |
| `link_experiments()` | validate and link legacy optical, BEC and optional CPU run records sharing one artifact hash |

For every accepted shot, `mode_0 + mode_1 + lost_atoms == loaded_atoms <= 500`.
The difference `500 - loaded_atoms` is the loading shortfall; `lost_atoms` is the
loss after loading. Neither is silently reassigned to a populated mode. The number
of accepted shots plus rejected shots must equal requested shots. Zero detected
atoms and all-rejected results remain representable, without becoming successes in
state preparation or entanglement verification. Real imaging usually requires a
calibrated atom-number estimator and uncertainty model; this first integer-count
contract does not provide that model. A device whose readout cannot satisfy this
contract must introduce a reviewed schema extension, not silently round data.

A `DEVICE_REPORTED` result requires a device-reported clock and a raw acquisition
record SHA-256. Those labels and hashes are declarations, not authentication or
independent validation. Condensation and entanglement remain `NOT_PERFORMED` in
this report format regardless of the sampling evidence label.

## Compatibility matrix

| Existing interface | What is compatible | What is not claimed |
| --- | --- | --- |
| Optical clock | Same `ClockReading`, epoch/timescale/tick/uncertainty fields; shared borrowed clock object | Hardware synchronization, comparable epochs without time transfer, measured optical-clock precision |
| Photonic pair sampling | Existing request/result validator and report reused unchanged; linked by artifact hash | Atom–photon coupling, Bell violation or hybrid entanglement |
| G1 CPU reference | Optional single `CPUReference.run()` report; requires matching model hash, CPU provider, G1/batch-one identity and input/output/manifest hashes | A quantum execution of that ONNX graph or cross-backend numerical parity |
| CPU contract-only report | May independently validate inputs as before; cannot be attached as real CPU inference evidence | G1 advancement from synthetic tests |
| TPU protocol / TensorRT runtime | Existing code and admission gates unchanged | A new supported hardware backend or automatic fallback |

A linked bundle keeps each component's evidence separately; simulated BEC data
cannot inherit real CPU execution status. It explicitly reports
`CLASSICAL_RECORD_LINK_ONLY`, synchronization `NOT_VERIFIED`, hybrid entanglement
`NOT_VERIFIED`, parity `NOT_TESTED` and authentication `NOT_VERIFIED`. A shared
artifact hash is an association key, not proof that the experiment executed the
artifact. Request IDs are local to each modality and need not match. No timing or
causal relationship is inferred from record order.

## Offline usage

From the repository root, no CUDA or quantum SDK installation is needed:

```sh
python -m motionbricks.cold_atoms --mode simulate \
  --artifact-sha256 79258d3613988b74ab84a530352ea600bbe78a1048584f059e231e44641cea16 \
  --request-id bec500-trial-001 --shots 10 --seed 7 --link-optical
python -m unittest discover -s tests/cold_atoms -v
```

The interface itself is standard-library-only; the CPU report compatibility test
uses NumPy from the existing CPU test environment. `--link-optical` runs both mock
adapters against the shared fake clock and emits a linked JSON bundle. It does not
run the CPU neural model. Every simulated shot loads 500 atoms, draws independent
classical bits for the two modes and reports zero loss. Nonzero loss and rejected
shots are supported by the schema and tested separately. The mock is not a
predictive BEC model. Runtime/memory scale with shots and atom count, not a full
500-qubit Hilbert space. Repeat requests/seeds reproduce fixtures, not independent
physical acquisitions.

```python
from motionbricks.optical_quantum import PairRequest, SimulatedClock, SimulatedPairSampler
from motionbricks.cold_atoms import BECRequest, SimulatedBEC500, link_experiments

artifact = 'a' * 64  # Replace with a real model/artifact hash for your records.
clock = SimulatedClock()
photons = SimulatedPairSampler(clock, seed=7)
atoms = SimulatedBEC500(clock, seed=7)
try:
    pr = PairRequest('photonic-001', artifact, shots=10)
    br = BECRequest('bec-001', artifact, shots=10)
    bundle = link_experiments(pr, photons.sample(pr), br, atoms.sample(br))
finally:
    photons.close()
    atoms.close()
    clock.close()
```

To link actual CPU evidence, supply `cpu_report=cpu_run_report` to
`link_experiments()`, where `cpu_run_report` is the second return value from
`CPUReference.run()`, or one element of the CPU CLI's `runs` array. Use its
`model_sha256` for both experiment requests. The linker rejects mismatches and
contract-only evidence and copies the CPU metadata to avoid mutable aliasing.
It validates declarations, not their authenticity; do not treat supplied JSON as
proof of hardware execution. Unknown extra CPU metadata is preserved.

The sampler borrows its clock and never closes it. Close is idempotent, use after
close fails, and callers serialize sample/close operations. The mock validates
positive finite timeout values but implements no transport deadline. Real adapters
must enforce timeouts and cleanup. `--mode hardware` always reports `BLOCKED` and
exits 2; invalid requests exit 1; successful mock execution exits 0. No device SDK,
network call or silent CPU/quantum fallback occurs.

## Admission for a future BEC device

Select device/SDK, species and mode encoding; record trap and preparation protocol,
atom-number estimator/calibration, temperature and condensate-fraction measurements
with uncertainties. Define shot/loss/postselection semantics and retain raw records.
Establish timing transfer and latency independently from the optical clock's own
uncertainty. Then validate the transport, operation limits, acquisition lifecycle,
timeouts, faults and cleanup against real hardware.

Entanglement tests need a suitable observable/witness, calibration, statistical
uncertainty and loss analysis. Any atom–photon interconnect needs independent
validation. Motion-model acceleration additionally needs an explicit algorithm
mapping, CPU numerical reference and end-to-end measurements. No such result is
provided here; the existing TPU G0–G5 gates are not advanced by these mock tests.

## Validation and sources

The new suite tests 500-atom bounds, losses/rejections, request/result association,
clock/evidence rules, deterministic repeats, close/timeout behavior, legacy optical
schema preservation, record hashes and CPU report compatibility. The CPU report
producer is exercised with an explicitly fake session: this is schema testing,
not real G1 inference. Existing optical and CPU suites remain required in CI.

Primary research motivating the distinctions above (not validating this interface):

- [Many-particle entanglement with Bose–Einstein condensates](https://arxiv.org/abs/quant-ph/0006111).
- [Squeezing and entanglement in a Bose–Einstein condensate](https://arxiv.org/abs/0810.0600).
- [Spatial entanglement patterns and EPR steering in a BEC](https://arxiv.org/abs/1708.02534).
- [Remote entanglement between a single atom and a BEC](https://arxiv.org/abs/1102.4285).
