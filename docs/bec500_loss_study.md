# BEC500 numerical accuracy, atom removal and replenishment

This is a reproducible **finite-model numerical investigation**, with a separate
classical Hopfield failure/replacement control. It does not report experiments,
500 independently addressable qubits, a BEC Hopfield implementation or physical
quantum-computer accuracy. The previous interfaces and hardware gates are unchanged.

## What Hopfield contributes, and what does not transfer

Hopfield's 1982 paper [1] describes content-addressable memory and robustness to
component failure. The paper titled *Spin-glass models of neural networks* is by
Amit, Gutfreund and Sompolinsky (1985) [2], analyzing Hopfield/Little models. These
are related sources, not the same paper or author attribution.

For the classical control we use binary spins, symmetric Hebbian couplings with
zero diagonal, asynchronous updates and energy
`E=-1/2 sum_ij W_ij s_i s_j`. Energy cannot increase under our update rule (ties
leave spins unchanged). This gives a concrete recall/failure test.

The two-mode BEC has collective spin S=N/2, with Hamiltonian
`H/hbar=-2J*Sx+U*Sz^2+delta*Sz`. It has no independently specified random W_ij,
frustrated coupling graph, learned patterns or dissipative recall attractors.
Deleting a Hopfield node is therefore **not** the same operation as losing an
indistinguishable atom. We transfer the experimental question—how robust is a
specified task to removing constituents—not a claimed device equivalence.

## Three meanings of accuracy

1. **Numerical accuracy inside the model:** sparse exponential propagation versus
   independent tridiagonal eigendecomposition, shared-time output-grid checks,
   norm/energy conservation, and density-matrix trace/Hermiticity/positivity.
2. **Physical model accuracy:** unknown without trap modes, temperature, scattering,
   interaction calibration, loss rates, preparation/readout errors and experimental
   data. Agreement between solvers does not bound the two-mode approximation error.
3. **Task accuracy:** optimal equal-prior single-shot discrimination of two known
   initial phases using ideal number readout. This is not hardware gate fidelity,
   learned recall accuracy or a universal measure of quantum computing quality.

For the existing default case (N=500, dimension=501, J=1, U=0.002, delta=0 rad/s,
initial coherent imbalance=0, phase=+0.1, t=0..1 s, 21 output times):

| Numerical audit | Observed maximum |
| --- | ---: |
| State L2 difference: sparse vs independent spectral solver | 4.64e-12 |
| Absolute population-probability difference | 1.11e-13 |
| State L2 difference at shared times, 21 vs 41 outputs | 5.12e-12 |
| Norm error | 1.25e-12 |
| Centered energy drift, H/hbar | 6.23e-10 rad/s |

Both solvers use double precision; this is independent-algorithm consistency,
not a rigorous arbitrary-precision error certificate. The 21/41 comparison changes
output sampling, not a SciPy integrator time step. The predefined state-comparison
failure threshold is 1e-8. Existing analytic Rabi and diagonal-Hamiltonian tests
remain in the dynamics suite. Particle number is fixed by the chosen sector.

## Removal channel and replacement hypothesis

The study evolves the two initial states (phases +/-0.1) until **t=0.5 s**, applies
exactly k removals at that instant, then evolves until t=1 s. It does not model
Poisson waiting times, continuous Lindblad evolution, two-/three-body loss,
heating or the probability of observing exactly k losses.

For a density matrix rho in the N-particle sector, one unobserved, mode-blind,
equal-per-atom loss is modeled by

\[
\mathcal L_N(\rho)=\frac{a_0\rho a_0^\dagger+a_1\rho a_1^\dagger}{N}.
\]

This is trace-preserving because sum a_i^dagger a_i=N on that sector. We sum the
unobserved branches, retaining the mixed state; choosing one branch would instead
be a conditioned measurement. Repeated losses take dimension 501 to 501-k. They
are not implemented by cutting rows off a state vector or renormalizing a pure
state. Losing an atom from a spin-coherent product state leaves the corresponding
smaller coherent state, whereas losing one atom from a NOON state destroys its
unobserved inter-mode coherence; both limiting cases are tested.

For replenishment, immediately after those losses we apply k instances of the
**idealized mode-unresolved boson addition channel**

\[
\mathcal A_N(\rho)=\frac{a_0^\dagger\rho a_0+a_1^\dagger\rho a_1}{N+2}.
\]

It is trace-preserving because sum a_i a_i^dagger=N+2. This is a mathematical,
number-sector channel with bosonic weighting, not a calibrated atom-source model.
The normalized Kraus maps are explicitly tested. It assumes the added atoms occupy
the same two modes and have no retained accessible record of which branch occurred.
No specific reservoir, pulse sequence or deterministic laboratory implementation
is claimed. It is **not** inverse loss or a way to restore an unknown entangled
state. General real loading could need additional modes and a different channel.

Each event study checks density-matrix trace and Hermiticity to 1e-8, permits only
numerical eigenvalues >=-1e-8, and verifies quantum trace-distance contraction
under loss and again under replacement. No projection to a positive matrix or
post-channel renormalization conceals errors. Evolution between events is unitary;
energy across removal/addition events need not be conserved.

## Computed removal/replacement results

All probabilities below are calculated from known model distributions, not finite
experimental trials. Fidelity is `<psi_no_loss|rho_replaced|psi_no_loss>` for the
positive-phase state, after returning to the same 500-particle sector.

| Removed at t=0.5 | Remaining | Readout success after loss | Success after replenishing to 500 | Replacement fidelity to no-loss state |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 500 | 89.5103% | 89.5103% | 1.000000 |
| 1 | 499 | 89.5276% | 89.4733% | 0.997857 |
| 5 | 495 | 89.4908% | 89.3244% | 0.989299 |
| 10 | 490 | 89.4166% | 89.1370% | 0.978629 |
| 25 | 475 | 89.2916% | 88.5653% | 0.946795 |
| 50 | 450 | 88.9746% | 87.5808% | 0.894293 |
| 100 | 400 | 88.2503% | 85.4895% | 0.791134 |
| 250 | 250 | 84.3876% | 78.0679% | 0.492024 |

Removing one atom slightly improves this particular final number readout while
reducing quantum trace distance (about 0.996653 to 0.996598). This is redistribution
of accessible information under a changed evolution/readout, not information
creation. Replenishment further contracts trace distance: after 250 replacements
it is about 0.754092, compared with 0.930206 after loss alone. Atom count, task score,
state fidelity and quantum information preservation are different quantities.
The numerical variations are well above the solver discrepancy but do not establish
physical significance or general trends outside this parameter setting.

### Freshly preparing a smaller system is a different experiment

We also reprepare smaller coherent systems at t=0 and evolve them for the full
second. Two policies separate atom-number and effective-interaction effects:
fixed U=0.002, and fixed UN=1 (U=1/N). Mode functions are still assumed unchanged.

| Fresh atoms | Success with fixed U | Success with fixed UN |
| ---: | ---: | ---: |
| 500 | 89.5103% | 89.5103% |
| 450 | 89.8167% | 88.2945% |
| 400 | 89.8955% | 86.9040% |
| 250 | 88.2554% | 81.2523% |

The initial states at different N already have different distinguishability.
These are not recovery fidelities or a controlled loss experiment. A claim such
as “400 atoms are optimal” would be unsupported by this small, single-time sweep.

## Classical Hopfield control

Seed 20261101; 500 binary nodes; 20 random patterns; three noisy cues per pattern;
exactly 50 of the original 500 bits flipped. One nested random deletion order is
used. Smaller networks retain original synapses/normalization (no retraining).
Replacement restores all original weights but initializes missing spin values
randomly; it does not reveal the target's missing bits. We permit 50 asynchronous
sweeps and check energy descent. All observed trials converged.

| Retained nodes | Exact recall on retained nodes / 60 | Exact full recall after restoring nodes / 60 |
| ---: | ---: | ---: |
| 500 | 60 | 60 |
| 450 | 60 | 60 |
| 400 | 60 | 60 |
| 250 | 60 | 60 |
| 100 | 22 | 40 |
| 50 | 0 | 2 |

These are 60 fixed, correlated cues from one stored-pattern ensemble, not 60
independent population experiments. No confidence interval or universal capacity
threshold is claimed. Restoring the original synaptic matrix is a strong classical
assumption absent from the BEC addition model. The different behaviors illustrate
why restoring constituents can aid an attractor memory without reversing a quantum
loss channel. We do not transfer a classical pattern-capacity formula to BEC atoms.

## Removal and replacement concepts for an eventual experiment

- **Controlled removal:** an RF/Raman outcoupler can transfer population into
  escaping states. RF output coupling has been demonstrated [4]. It is not
  automatically an exact-k, mode-blind channel: calibrate mode selectivity,
  count uncertainty, heating, phase shifts and detection back-action.
- **Replenishment:** a separately cooled reservoir could load the trap, followed by
  cooling/rethermalization and preparation. Continuous replenished condensation
  has been demonstrated in strontium [5]; that does not establish compatibility
  with this 500-atom Rb-87 setup or the isotropic channel above.
- **Known-state reset:** if the desired state is known, reprepare it and measure
  fidelity. That is reinitialization, not recovery of an unknown state or memory.
- **Protected computation:** investigate an explicit error-detecting encoding,
  syndrome measurement, feedback and reservoir/control model before claiming
  repair. Replacing an indistinguishable atom is not swapping a labeled memory cell.

Next experimental inputs needed are trap/mode definitions, calibrated U/J and
atom-number uncertainty, actual loss channels, loading distributions and state
readout. Without them, no absolute physical accuracy or removal-rate recommendation
is justified. Exact-k instantaneous loss is a useful starting calculation, not a
complete operational maintenance protocol.

## Reproduction, files and compatibility

Use the existing isolated requirements from `tools/bec_dynamics/requirements.txt`:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python tools/bec_loss/run_study.py --output-dir /tmp/bec-loss-study
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  python -m unittest discover -s tests/bec_loss -v
```

Full numeric records are checked in as
[quantum model results](results/bec_loss_results.json) and
[classical Hopfield results](results/hopfield_ablation_results.json), with source
hashes, versions, parameters and evidence labels. Defaults generated the tables
on Linux x86_64, Python 3.12.14, NumPy 2.3.5, SciPy 1.16.3, one BLAS/OpenMP thread.
The one-thread setting limits CPU oversubscription, not scientific uncertainty.
Small floating-point differences across supported environments are expected.

`bec_loss.py` uses variable-N density matrices only within this offline research
module. The old BECRequest remains exactly 500 requested atoms. No smaller-N record
is silently passed through that contract, no hardware evidence is fabricated, and
existing clock/optical/CPU/TPU interfaces are unchanged. The study is not a new
hardware adapter. Default loss counts are 0,1,5,10,25,50,100,250; a custom sweep
accepts up to 20 unique counts below 500 and remains subject to existing parameter
work limits. Full density matrices scale as (N+1)^2; no 2^500 state is allocated.

## References

1. Hopfield, J. J. (1982). *Neural networks and physical systems with emergent
   collective computational abilities*. PNAS 79, 2554–2558.
   https://doi.org/10.1073/pnas.79.8.2554
2. Amit, D. J., Gutfreund, H., Sompolinsky, H. (1985). *Spin-glass models of neural
   networks*. Physical Review A 32, 1007–1018.
   https://doi.org/10.1103/PhysRevA.32.1007
3. Li, Y., Castin, Y., Sinatra, A. (2008). *Optimum spin squeezing in Bose–Einstein
   condensates with particle losses*. Physical Review Letters 100, 210401.
   https://doi.org/10.1103/PhysRevLett.100.210401
   Context for particle-loss sensitivity; the present channel sweep is not a
   replication of its continuous-loss squeezing calculation.
4. Mewes et al. (1997). *Output Coupler for Bose-Einstein Condensed Atoms*.
   Physical Review Letters 78, 582. https://doi.org/10.1103/PhysRevLett.78.582
5. Chen et al. (2022). *Continuous Bose–Einstein condensation*. Nature 606, 683–687.
   https://doi.org/10.1038/s41586-022-04731-z
