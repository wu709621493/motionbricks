# Experimental optical-clock and photonic experiment interface

Status: v0.1 classical interface + offline mock, requested by Mengcheng Wu (Windy
Wu). No optical clock, entangled-photon device, quantum computer or motion-model
quantum backend has been connected. This is an independent research extension.

## Scientific boundary

SHA-256 is a classical hash algorithm, used here to identify model bytes. It is
not specific to quantum computers. Quantum algorithms affect cryptographic threat
analysis, but optical timing and entanglement do not replace content integrity.
An unkeyed hash alone does not authenticate a device, timestamp or acquisition.
The existing G1 FP32 model identity check remains unchanged.

Optical atomic clocks provide frequency/time references. Connecting one to a
photonic experiment requires an actual time-transfer path, calibrated delays and
device readout. Timestamp precision is not accuracy; a fine tick period does not
establish small uncertainty. Entangled photons can be part of quantum computing,
networking or sensing experiments, but a matching pair of classical bits does not
establish entanglement or perform MotionBricks neural inference.

This initial interface specifies acquisition-start clock metadata and a narrow
**two-channel ZZ-basis sampling** operation. It is not a universal quantum circuit
format. Until a device and SDK are selected, we cannot specify supported optical
modes, gates, photon encoding, pulse scheduling or compilation. General quantum
program execution and ONNX-to-photonic conversion are explicitly unimplemented.

## Interface

`motionbricks.optical_quantum` uses only Python's standard library.

| Type | Contract |
| --- | --- |
| `OpticalClock` protocol | `read() -> ClockReading`, `close()` |
| `ClockReading` | source ID, named timescale and epoch, integer ticks, decimal-string tick period and standard uncertainty (seconds, k=1), calibration ID, evidence |
| `PhotonicPairSampler` protocol | synchronous `sample(PairRequest, timeout_seconds=...) -> PairResult`, `close()` |
| `PairRequest` | caller request ID, artifact SHA-256, bounded shot count, explicit `ZZ` basis |
| `PairResult` | request/artifact/basis identity, counts ordered 00/01/10/11, rejected shots, acquisition-start clock reading, backend identity, evidence and optional raw record hash |
| `report()` | validates response association and shot accounting; returns JSON-compatible metadata and canonical record SHA-256 |

Clock readings preserve integer ticks and decimal strings without conversion to
floating-point Unix timestamps. No UTC/TAI/leap-second or local-clock conversion is
implicit. Readings from different sources are not comparable without a calibrated
time-transfer model. This version does not record per-photon timestamps or claim
coincidence-window validation. The artifact hash may come from the CPU reference
report's `model_sha256`; it associates records but does not prove the optical
experiment executed that model. The module does not load or modify the model.

## Run without hardware

From the repository root, without installing root CUDA dependencies:

```sh
python -m unittest discover -s tests/optical_quantum -v
python -m motionbricks.optical_quantum --mode simulate \
  --artifact-sha256 79258d3613988b74ab84a530352ea600bbe78a1048584f059e231e44641cea16 \
  --request-id optical-fixture-001 --shots 100 --seed 42
```

The explicit `simulate` mode uses a fixed fake clock and a classical seeded PRNG.
It produces correlated 00/11 samples to exercise transport/data contracts only.
It is not a quantum circuit simulator, photon propagation model, quantum random
number generator or cryptographic random source. Repeating the same request/seed
reproduces counts independent of other requests. This does not model independent
physical repeated acquisitions; use distinct request IDs for distinct experiments.

```python
from motionbricks.optical_quantum import (
    PairRequest, SimulatedClock, SimulatedPairSampler, report,
)
clock = SimulatedClock()
sampler = SimulatedPairSampler(clock, seed=42)
try:
    request = PairRequest('trial-001', 'a' * 64, shots=100)
    record = report(request, sampler.sample(request, timeout_seconds=1.0))
finally:
    sampler.close()
    clock.close()
```

The sampler borrows its clock: closing it does not close that clock. Close is
idempotent and later use fails. The mock validates timeout values but does not
implement a timed transport or an execution deadline. Calls should be serialized
by their owner. There are no device sessions or network side effects in this PR.

`--mode hardware` always exits 2 with `BLOCKED`; no fallback is allowed. Invalid
requests exit 1. Successful simulation exits 0. Simulation is never described as
hardware execution, entanglement verification or a G1 CPU reference result.

## Future real device adapter admission

A future adapter must implement the protocols and add its own SDK/transport tests:

1. Identify vendor/device/firmware/SDK, optical encoding, supported operations,
   clock source, time-transfer chain, calibration and uncertainty budget.
2. Enforce timeouts, cancellation/cleanup, request association, acquisition-shot
   semantics and error reporting. Define loss, detection, heralding and rejected
   shots without hiding postselection. Record raw acquisition bytes and hashes.
3. Mark results `DEVICE_REPORTED` only for actual device acquisitions, with a
   device-reported clock reading and raw-record hash. These labels are declarations,
   not authenticated evidence. Add an independently reviewed authentication scheme
   if the transport requires it; do not substitute a plain digest for a signature.
4. Establish entanglement separately using a suitable multi-basis witness or Bell
   experiment, with calibration, uncertainty, loss/postselection analysis and
   relevant loopholes. ZZ correlation alone is compatible with classical mixtures.
5. Before claiming motion acceleration, specify a real algorithm/model mapping,
   compare against the CPU reference, then measure end-to-end cost and accuracy.

| Evidence | Current status |
| --- | --- |
| Schema, identity, shot accounting and lifecycle tests | Implemented offline |
| Optical clock acquisition / calibrated time transfer | BLOCKED: no adapter/device |
| Photonic device execution | BLOCKED: no adapter/device |
| Entanglement verification | NOT_PERFORMED |
| Motion inference / quantum advantage | NOT_PERFORMED / NOT_TESTED |

These checks have no authority to advance the TPU protocol's G0–G5 gates. The CPU
reference, TensorRT runtime, TPU proposal and hardware-support boundaries are
unchanged. This module is not a robot controller.

## Sources

- [NIST: hash function policy](https://csrc.nist.gov/projects/hash-functions/nist-policy-on-hash-functions).
- [NIST: Optical Clocks — The Future of Time](https://www.nist.gov/atomic-clocks/how-atomic-clocks-work/optical-clocks-future-time).
- [NIST: Atomic Clocks Meet Quantum Entanglement](https://www.nist.gov/atomic-clocks/a-powerful-tool-for-science/future-directions-atomic-clocks-meet-quantum-entanglement).

Sources motivate the distinction between timing, quantum experiments and integrity;
they do not validate this proposed interface or claim compatibility with a device.

## Compatible cold-atom extension

The [500-atom BEC interface](bec500_interface.md) reuses these public clock types
and optical records unchanged, with a tested classical record linker and optional
CPU reference metadata. This does not imply physical atom–photon coupling.

## Multi-setting numerical validation

The independent [Bell/CHSH prototype](bell_chsh_validation.md) adds explicit
Alice/Bob settings, all-trial loss accounting, finite-sample uncertainty, classical
and ideal Bell-probability simulations, and adversarial selection controls.
The legacy ZZ request and report remain unchanged. No physical entanglement is
verified by either interface.
