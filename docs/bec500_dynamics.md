# BEC500: a CPU reference for collective two-mode dynamics

This extends the [BEC500 interface](bec500_interface.md) from a classical binomial
fixture to a **numerical quantum-state simulation**. It is not a hardware backend,
verified BEC preparation, entanglement witness, or demonstrated computational
advantage. The existing classical fixture remains available and unchanged.

## Model and conventions

There are exactly N=500 indistinguishable bosons in two fixed modes, without loss,
extra modes or a thermal cloud. The ordered basis is
`|n0,500-n0>`, for `n0=0,...,500`: **501 complex amplitudes**, not 2^500 qubit states.
The approximation assumes those two modes suffice; its validity for a real trap
has not been established. The Rb-87 interface label does not supply trap-dependent
couplings or scattering parameters: coefficients below are phenomenological.

Define `m=(n0-n1)/2`. The time-independent Hamiltonian is

\[
H/\hbar=-J(a_0^\dagger a_1+a_1^\dagger a_0)+U m^2+\delta m.
\]

`Parameters.tunnelling`, `interaction` and `bias` mean J, U and delta, in rad/s.
Time is in seconds. Compared with the on-site interaction
`U/2 * [n0(n0-1)+n1(n1-1)]`, this drops the constant
`U*(N*N/4-N/2)`. It changes only a global phase; reported energy uses the centered
Hamiltonian above. H is a real symmetric tridiagonal matrix; the n-to-n+1 entry is
`-J*sqrt((n+1)*(500-n))`.

Initial conditions are either a number state `fock_n0`, or a fixed-N spin-coherent
state with amplitude proportional to
`sqrt(binomial(N,n) * p**n * (1-p)**(N-n)) * exp(i*n*phase)`, where
`p=(1+imbalance)/2`. Phase is in [-pi,pi] radians. This is a number-conserving
spin-coherent state, not an optical Glauber coherent state. `fock_n0` is used only
for a number state; `imbalance` and `phase` only for a coherent state.

## Reproduce without CUDA

From the repository root, use an isolated Python 3.12/3.13 environment:

```sh
python3.12 -m venv .venv-bec
. .venv-bec/bin/activate
python -m pip install -r tools/bec_dynamics/requirements.txt
python -m unittest discover -s tests/bec_dynamics -v
python -m motionbricks.bec_dynamics --compare > /tmp/bec500-comparison.json
```

The pinned target is NumPy 2.3.5 / SciPy 1.16.3. Do not install the root project's
CUDA dependencies for this module. It imports no Warp, TensorRT, ONNX Runtime,
JAX or quantum SDK. To obtain one trajectory instead of the four-run comparison,
omit `--compare`; J, U, bias, duration, samples, phase and imbalance have CLI flags.

`scipy.sparse.linalg.expm_multiply` applies `exp(-i H t/hbar)` to the initial state.
It uses complex128 amplitudes, uniform output times including zero, sparse matrix
storage and an explicit trace. This is finite-model evolution to numerical
precision, not an exact physical description of a condensate. Sample count sets
output times, not a user-selected integration step size.

Each trajectory checks finiteness, norm error <=1e-8 and energy drift divided by
`max(1, max absolute row sum of H/hbar)` <=1e-8. Failed checks raise an error;
evolved states are **not renormalized to conceal drift**. Fixed particle number is
imposed by the basis, not separately discovered by simulation. Initial-state
preparation is normalized explicitly. Only the final sampling probability vector
is normalized after conservation checks to satisfy NumPy's sampling requirements.

Reports contain times, imbalance `<n0-n1>/500`, number-difference variance,
first-order coherence `2*|<a0^dagger a1>|/500`, energy, norms, final number
probabilities, tolerances, initial/trajectory hashes, versions, OS/architecture and
measured solver time. Bytes hashed are little-endian complex128 in time/basis order.
The whole record hash includes elapsed time, so it is not a deterministic fixture
hash. Trajectory hashes are compared within the same tested environment; exact
byte agreement across CPUs/versions is not promised. Timing covers the solver,
not setup, observables, sampling or report hashing, and is not a benchmark claim.

Software bounds: 2–1001 output times and
`duration*(500*|J|+62500*|U|+250*|bias|) <= 20000`. These limit requested work, not
physical admissibility or guaranteed wall time. There is no hardware execution
mode in this module.

## Controlled comparison and first computational task

`compare_initial_states()` evaluates two coherent states with the same imbalance
and opposite phases, using (1) U=0 and (2) the requested U, holding all other
parameters fixed. The common Hamiltonian within each case evolves both states.
For each time, it reports the total variation distance of their number-readout
distributions and the optimal equal-prior single-shot success probability for this
specified readout: `(1+TV)/2`. This assumes known distributions and an ideal
number measurement; it is not a trained classifier or an experimental accuracy.

The comparison also reports pure-state trace distance. The squared overlap must
remain constant, and readout TV must not exceed the initial quantum trace distance
(up to numerical tolerance). Overlap squared is used for the conservation check
because square-root distance is ill-conditioned near identical states.

Thus a changing readout score reflects conversion of phase information into
number information, not creation of distinguishability by unitary evolution.
Interactions need not improve the score. The comparison is not a universal
emergence detector, a finite-size scaling study or proof of a phase transition.

Local default example (2026-11-01, Python 3.12.14, NumPy 2.3.5, SciPy 1.16.3,
Linux x86_64): N=500, J=1, delta=0, phases +/-0.1, initial imbalance 0, t=1 s.
The number-readout single-shot success was approximately 0.978976 for U=0 and
0.895103 for U=0.002. Both started at 0.5. These are model-calculated values,
not hardware measurements or quantum advantage. For the positive-phase runs,
maximum norm errors were 2.53e-12 and 1.25e-12 respectively; energy drifts were
1.26e-9 and 6.23e-10 rad/s in the stated centered convention.

## Compatibility with prior interfaces

`DynamicsBEC500` implements the existing cold-atom `sample/close` shape and adds
`run()` to return both the sampled result and its numerical trajectory report:

```python
from motionbricks.bec_dynamics import DynamicsBEC500, Parameters
from motionbricks.cold_atoms import BECRequest, link_experiments
from motionbricks.optical_quantum import PairRequest, SimulatedClock, SimulatedPairSampler

clock = SimulatedClock()
atoms = DynamicsBEC500(clock, Parameters(), seed=7)
photons = SimulatedPairSampler(clock, seed=7)
try:
    artifact = 'a' * 64  # Replace with the artifact being associated, not a physics claim.
    br = BECRequest('dynamics-001', artifact, shots=100)
    result, trajectory = atoms.run(br, timeout_seconds=10)
    pr = PairRequest('photons-001', artifact)
    bundle = link_experiments(pr, photons.sample(pr), br, result)
finally:
    atoms.close()
    photons.close()
    clock.close()
```

Every sampled shot has 500 atoms and zero loss. Sampling is seeded by request,
parameters and explicit seed, and uses the simulated final number distribution.
The result keeps legacy evidence `SIMULATED`, identifies the CPU dynamics backend
and sets `raw_record_sha256` to the returned trajectory record hash. Here that
field binds a simulation record, not a device acquisition. The trajectory itself
uses `NUMERICAL_SIMULATION`. Preserve both records for review.

The clock remains borrowed. Its reading is taken at host simulation start; it
is not mapped to the Hamiltonian's modeled time axis. An optical clock cannot
improve numerical precision by being attached as metadata. Existing linking with
optional G1 CPU reports remains available and validates the same artifact binding;
it does not imply this Hamiltonian executes the neural model. Synchronization,
atom–photon entanglement and cross-backend parity remain unverified.

The adapter rejects invalid timeout values and discards a result returned after
the requested deadline, but **cannot interrupt an active SciPy solve**. Use process
isolation if a hard deadline is needed. Requests/close are caller-serialized,
close is idempotent, and no cached state leaks across requests. The adapter owns
no device session. Errors propagate without fallback.

## Tests and research basis

Tests cover analytic noninteracting Rabi oscillations and binomial variance,
analytic diagonal interacting evolution, an independent tridiagonal eigensolver,
Hermiticity, observable bounds, conservation, repeatability, nonfinite/bad-norm
failure injection, work limits, readout-vs-trace-distance consistency, legacy
optical linking, timeout/closure and CPU-only import isolation. Existing interface
and CPU-reference suites remain in CI. No real weights or quantum hardware are
required by this suite.

- P. W. Anderson, **More Is Different**, Science 177, 393–396 (1972),
  [doi:10.1126/science.177.4047.393](https://doi.org/10.1126/science.177.4047.393).
  Motivates testing collective organization; it does not certify this model's emergence.
- J. J. Hopfield, **Neural networks and physical systems with emergent collective
  computational abilities**, PNAS 79, 2554–2558 (1982),
  [doi:10.1073/pnas.79.8.2554](https://doi.org/10.1073/pnas.79.8.2554).
  Motivates explicit computational tasks. This closed unitary model has no
  dissipative attractor, learned memory or pattern-retrieval implementation.
- Raghavan, Smerzi, Fantoni and Shenoy, **Coherent oscillations between two weakly
  coupled Bose–Einstein condensates: Josephson effects, pi-oscillations, and
  macroscopic quantum self-trapping**, [preprint](https://arxiv.org/abs/cond-mat/9706220).
  Physical two-mode context; its mean-field treatment is distinct from our
  finite-number state-vector evolution.
- [SciPy expm_multiply](https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.expm_multiply.html).

Future work requires validated mode/trap parameters, loss/open-system modeling,
additional initial states and observables, and a separately designed encoding and
readout before attempting memory recovery. Hardware, entanglement and computational
utility must retain separate evidence gates. Existing TPU G0–G5 are unchanged.
