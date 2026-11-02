# Bell/CHSH numerical validation prototype

Status: experimental, offline, standard-library-only. Date: 2026-11-02.
Requested by Windy Wu; implementation and numerical study prepared with Codex.

## Scope and evidence boundary

This module extends the experimental boundary introduced by PR #7 with a separate
`CHSHRequest` / `CHSHResult` / `CHSHSampler` contract. The legacy `PairRequest`,
`PairResult`, `PhotonicPairSampler`, `SimulatedPairSampler`, and ZZ report are
unchanged. In particular, legacy `PairRequest(basis='XX')` still refuses input:
new multi-setting experiments use the new explicit contract rather than changing
the meaning of a deployed request. `OpticalClock` and `ClockReading` are reused.
No motion backend, BEC500 accuracy claim, physical entanglement measurement,
cryptographic randomness, quantum hardware execution, or acceleration is supplied.

| Evidence class | Meaning | Entanglement verification |
|---|---|---|
| `CLASSICAL_LHV` | Classical local hidden-variable numerical fixture | `NOT_PERFORMED` |
| `IDEAL_BELL_PROBABILITY` | Classical computer sampling a stipulated Bell-state probability law | `NOT_PERFORMED` |
| `DEVICE_REPORTED` | Future adapter claims device acquisition; requires device clock and raw-record digest | `NOT_PERFORMED` |
| Experimentally verified entanglement | Requires independent experimental/protocol assessment | **Not emitted by this prototype** |

Even a device label and a valid hash are declarations, not authentication. No
code path upgrades a simulation or device report to verified entanglement.
`open_hardware()` raises `HardwareUnavailable`; it never silently simulates.

## Measurement contract and accounting

Alice and Bob each specify two real **Bloch angles in radians**, defining
`M(theta) = cos(theta) Z + sin(theta) X`. Defaults are Alice `(0, pi/2)` and Bob
`(pi/4, -pi/4)`. For a linear-polarization analyzer the physical angle is half the
Bloch angle under the corresponding H/V convention; a future adapter must declare
its actual calibration, sign convention, and optical transformation.

Cell order is `(A0,B0), (A0,B1), (A1,B0), (A1,B1)`; four separate shot quotas
support unequal sample sizes. Each cell retains nine raw bins, in this order:
`(++,+-,+0,-+,--,-0,0+,0-,00)`. Here `0` means **no click**, not a bit. Local
binary outcomes are `+1,-1`. A second nine-bin array records selectively rejected
events as a subset of those raw bins. Rejection never deletes a raw event.

For every cell:

- `sum(raw) = requested attempts` and `0 <= selected_out[i] <= raw[i]`.
- Accepted coincidences include two-click events not selectively rejected.
- `accepted coincidences + rejected union = attempts`.
- No-click and selected-out categories may overlap; union accounting avoids double counting.

The primary estimator uses **all attempted trials**, assigning `+1` to each local
no-click before forming the product. This assignment is fixed in advance. If an
adapter cannot enumerate attempts or has unrecoverable outcomes, it cannot fabricate
zero-filled records and satisfy this contract honestly. Rejected events whose
binary outcomes are retained still contribute their recorded outcomes to the
primary estimator. A second, conspicuously labeled diagnostic discards no-clicks
and selectively rejected events. Its interval cannot repair selection bias.

## Independent baseline models

### Local hidden variables

A trial samples uniformly from the eight deterministic tables
`(a0,a1,b0,b1) in {-1,+1}^4` with
`a0*b0+a0*b1+a1*b0-a1*b1 = +2`. Alice reads only `a[x]` and Bob only `b[y]`.
The same table distribution is used for every setting; it is independent of the
chosen setting. This gives correlations `(1/2,1/2,1/2,-1/2)` and population
`S=2`. Exhaustive enumeration tests all 16 deterministic local tables: each has
signed CHSH value `+2` or `-2`. Mixtures therefore obey `|S| <= 2`.

### Ideal Bell probability law

For `|Phi+> = (|00>+|11>)/sqrt(2)`, in this real XZ plane,
`P(a,b | theta_A,theta_B) = [1 + a*b*cos(theta_A-theta_B)]/4`.
The implementation draws a uniform local outcome and samples the second outcome
conditional on their product. This is a centralized probability simulator, **not**
a local hidden-variable implementation and not a physical photon experiment.
Default angles give `E=(1/sqrt(2),1/sqrt(2),1/sqrt(2),-1/sqrt(2))` and
`S=2*sqrt(2)`. Tests check probability normalization, nonnegativity, unbiased
marginals, ZZ correlation, and this analytic maximum.

### Noise, losses, and adversarial controls

Independent local flips with probability `p` multiply ideal correlations by
`(1-2p)^2`. Independent local loss probability `l`, with unbiased detected local
marginals and `+1` assignment, yields
`S_all = (1-l)^2*(1-2p)^2*S_clean + 2*l^2`.
These are simplified readout/erasure models; they do not model dark counts,
multi-pair emission, detector dead time, drift, or a full quantum noise channel.

The deliberate joint-selection control removes a configured fraction of
coincidences whose product loses the CHSH game. At full rejection its diagnostic
`S=4` even for the classical model. This is explicitly a joint analyst-side
selection attack, not a local detection mechanism.

A **separate local detection attack** samples shared hidden values
`(gx,gy,r)`, with uniform guessed settings and uniform sign `r`. It fixes Alice's
outputs to `r` and Bob's to `r*(-1)^(gx*gy)` for either local input. Alice detects
only if `x=gx`, Bob only if `y=gy`. Each detector depends on its own setting and
shared lambda only; no detector needs the other side's actual setting. Coincidence
probability is 1/4 at every setting, so even equal observed efficiencies can hide
the bias. Coincidence-only correlations produce `S=4`; all-trial expectations are
`E_xy = (1 + (-1)^(x*y))/4`, giving `S=1.5`. This fixture shows why matching
acceptance rates alone cannot establish fair sampling.

## Estimators and uncertainty

For cell k, after the primary local no-click assignment, let `Z_ki = A_ki B_ki`:

`E_hat_k = sum_i Z_ki / n_k`

`S_hat = E_hat_00 + E_hat_01 + E_hat_10 - E_hat_11`.

Both signed S and its absolute value are reported. The sign pattern is fixed in
advance; the code does not maximize over relabelings or tune angles on the same
sample. A finite empirical S can exceed 2 or even the population quantum bound
through sampling variation; these are bounds on the relevant population models.

For independent trials, an unbiased estimate of `Var(E_hat_k)` is
`(1-E_hat_k^2)/(n_k-1)`, for `n_k>1`. The descriptive standard error of signed S
is the square root of the sum of these four variance estimates. At `n=1`, SE is
undefined and returned as null. At a saturated empirical correlation this SE can
be zero; it must **not** be read as zero population uncertainty.

The inferential interval instead uses weighted Hoeffding. Each contribution to S
has range length `2/n_k`, so the sum of squared ranges is `4*sum_k(1/n_k)`.
With predeclared failure probability alpha, a conservative two-sided radius is

`r = sqrt(2*log(2/alpha)*sum_k(1/n_k))`.

The interval is `[S_hat-r,S_hat+r]` intersected with `[-4,4]`. It remains nonzero
at saturated empirical counts and needs no Gaussian approximation. The boolean
`interval_excludes_local_range` asks whether this interval misses `[-2,2]`;
it is a **model-conditional statistical diagnostic**, not entanglement certification.
No p-value, sigma significance, or posterior probability of entanglement is claimed.

Assumptions: independent bounded trials; fixed quotas, angles, sign convention,
loss assignment, and alpha; stable per-setting probability laws; no outcome-dependent
stopping or trial exclusion from the primary analysis. For the local bound, the
hidden-variable distribution must also be setting-independent with local responses.
The deterministic PRNG is treated as an offline numerical surrogate for independent
sampling, not a physical or cryptographically secure setting generator.

For coincidence-only diagnostics, an IID conditional retained distribution can
support a sampling-error interval conditional on retained counts. It is an interval
for a **selected population**, which need not obey the classical bound 2. If any
cell is empty, the diagnostic returns `INSUFFICIENT_DATA` and no S or interval.
Sequential stopping, memory effects, predictable settings, drift, or hardware
correlations invalidate this simple analysis and require a new statistical protocol.

## Reproducible study and provenance

From the repository root, with Python 3.12 or 3.13 and no additional packages:

```bash
python tools/bell_chsh/run_study.py --output docs/results/bell_chsh_v1.json
python -m unittest discover -s tests/bell_chsh -v
python -m unittest discover -s tests/optical_quantum -v
```

The committed JSON contains 135 complete aggregate reports: both models, seeds
`0,7,42`, per-cell quotas `100,1000,10000`, seven clean/noise/loss/selection
conditions, and nine additional local-detection controls. Every primary interval
uses `alpha=0.05/135`; the union bound gives at least 95% simultaneous coverage
under the stated assumptions, without requiring independence between reports.
Common random streams deliberately couple noise/loss comparisons within a model.
Models, settings, and source/noise/loss/selection mechanisms have distinct seeded
streams. Shot counts use prefixes of the same streams; sweeps are not independent
experimental replications. No best seed is selected.

A separate exploratory distribution retains all 200 seeds `0..199` at 20 trials
per cell with individual 95% intervals. These exploratory intervals are not a
familywise discovery analysis. The study records every S, its seed and report hash,
and the counts above 2 and outside the individual intervals.

Reports bind configuration, counts, clock metadata, evidence class, uncertainty,
and warnings with canonical UTF-8 JSON SHA-256 (sorted keys, compact separators,
NaN forbidden; omit `record_sha256` from its own digest). The study binds the full
bundle plus source-file hashes and Python version with `study_sha256` similarly.
A separate raw digest streams canonical `[cell,trial,a,b,rejected]` lines, including
all losses and rejected events. The simulation ledger can be regenerated from the
recorded seed/configuration and source version; only counts and digests are committed.
A hash detects changes, but does not authenticate a device, guarantee completeness,
or substitute for preserving hardware acquisition files. Python/libm differences
may affect exact floating-point JSON hashes across environments; use the recorded
Python build for byte-level reproduction and compare numerical invariants otherwise.

## Numerical results

Python 3.12.14; seed 0; 10,000 attempts per cell (40,000 total).
Intervals below are the study-wide Bonferroni-adjusted Hoeffding intervals,
not standard-error bars. These rows are fixed representative configurations;
all seeds and sample sizes are included in the [JSON bundle](results/bell_chsh_v1.json).

| Model | Condition | All-trial S | Adjusted interval | Postselected S |
|---|---|---:|---|---:|
| CLASSICAL_LHV | clean | 2.0090 | [1.9261, 2.0919] | 2.0090 |
| CLASSICAL_LHV | flip_10pct | 1.2840 | [1.2011, 1.3669] | 1.2840 |
| CLASSICAL_LHV | flip_50pct | -0.0228 | [-0.1057, 0.0601] | -0.0228 |
| CLASSICAL_LHV | loss_20pct | 1.3598 | [1.2769, 1.4427] | 1.9794 |
| CLASSICAL_LHV | loss_100pct | 2.0000 | [1.9171, 2.0829] | undefined |
| CLASSICAL_LHV | selective_100pct | 2.0090 | [1.9261, 2.0919] | 4.0000 |
| CLASSICAL_LHV | loss_and_selection | 1.3598 | [1.2769, 1.4427] | 4.0000 |
| IDEAL_BELL_PROBABILITY | clean | 2.8126 | [2.7297, 2.8955] | 2.8126 |
| IDEAL_BELL_PROBABILITY | flip_10pct | 1.8076 | [1.7247, 1.8905] | 1.8076 |
| IDEAL_BELL_PROBABILITY | flip_50pct | 0.0192 | [-0.0637, 0.1021] | 0.0192 |
| IDEAL_BELL_PROBABILITY | loss_20pct | 1.8816 | [1.7987, 1.9645] | 2.8005 |
| IDEAL_BELL_PROBABILITY | loss_100pct | 2.0000 | [1.9171, 2.0829] | undefined |
| IDEAL_BELL_PROBABILITY | selective_100pct | 2.8126 | [2.7297, 2.8955] | 4.0000 |
| IDEAL_BELL_PROBABILITY | loss_and_selection | 1.8816 | [1.7987, 1.9645] | 4.0000 |
| CLASSICAL_LHV | local_detection_attack | 1.4912 | [1.4083, 1.5741] | 4.0000 |

Among 200 small-sample classical runs, **97** had S>2,
but **0** individual Hoeffding intervals excluded [-2,2]. This is an
illustration of finite-sample fluctuation, not a calibrated empirical false-positive
rate estimate for arbitrary devices. The noiseless probability-model simulation
excludes the local range at large n under the simulator assumptions; it does not
observe physical entanglement. At 20% local loss, the probability-model
coincidence-only S remains high while the all-trial S falls below 2.

## Tests and future hardware integration

The independent `tests/bell_chsh` suite covers exact deterministic local bounds,
Bell probabilities, hand-computed unequal-size correlations/SE/intervals, negative
S, no-click assignment, empty retained samples, all-loss controls, adversarial
postselection, local detection bias, seed reproducibility, deadline refusal,
count conservation, invalid records, provenance labels, canonical hash mutation,
committed study integrity, and legacy ZZ compatibility. The existing CPU CI matrix
runs it on Ubuntu x86-64/ARM64 and macOS ARM64 with Python 3.12/3.13. Local tests do
not establish that remote CI or physical devices have passed.

A future `CHSHSampler` adapter can accept the same request and return a validated
result using the existing `OpticalClock` protocol. Before enabling inference from
real measurements, its separately reviewed acquisition protocol must address:

1. **Trial definition before detection:** retain triggers, settings, every local
   click/no-click, overflow/invalid events, aborts and reasons, and immutable raw
   files. Predetermine coincidence windows and pairing; never optimize windows
   after seeing S. Do not use only detected coincidences as the denominator.
2. **Settings and timing:** randomize unpredictable local settings independently
   of the source; preserve the setting-generation records and per-event time tags.
   This simulator processes fixed per-cell blocks, which is suitable only for its
   IID baseline assumptions. A real device must not inherit that block schedule
   as a loophole-closing design.
3. **Clock and detector calibration:** `ClockReading` is an acquisition-start
   reading, not photon timestamps. Supply detector IDs, firmware/SDK versions,
   analyzer calibrations, event time scale/epoch, uncertainty, synchronization,
   calibration files and their hashes. Optical-clock precision alone does not
   close locality, freedom-of-choice, or coincidence-time loopholes.
4. **Loss and selection audit:** validate local assignment rules and trigger
   completeness; compare singles and coincidences; investigate setting/outcome
   dependence. Nonsignaling diagnostics, detector memory, dark counts, multipair
   events and adversarial time-tag tests remain future work. Passing a marginal
   diagnostic alone would not certify fair sampling or locality.
5. **Statistical protocol:** preregister sample size, sign convention, settings,
   family of comparisons, and stopping rules. Add memory-robust martingale or
   test-supermartingale analysis for randomized trials when warranted; this
   implementation does not supply it. Never reuse the IID interval uncritically.
6. **Operational boundary:** adapters enforce transport/read deadlines, preserve
   acquisition errors, close only resources they own, and explicitly refuse
   missing SDKs. Retain device records independently of the summary hash. Audit
   provenance and experimental loopholes before a separate entanglement verdict.

This is an analysis/protocol foundation, not a hardware readiness certificate.
It deliberately leaves the existing motion and BEC modules untouched.

## Primary references

- Clauser, Horne, Shimony & Holt (1969). *Proposed Experiment to Test Local
  Hidden-Variable Theories*. Physical Review Letters 23, 880.
  https://doi.org/10.1103/PhysRevLett.23.880
- Cirel'son (1980). *Quantum generalizations of Bell's inequality*.
  Letters in Mathematical Physics 4, 93–100.
  https://doi.org/10.1007/BF00417500
- Branciard (2011). *Detection loophole in Bell experiments: How postselection
  modifies the requirements to observe nonlocality*. Physical Review A 83, 032123.
  https://doi.org/10.1103/PhysRevA.83.032123
- Sajeed, Sultana, Lim & Makarov (2020). *Bright-light detector control emulates the local bounds
  of Bell-type inequalities*. Scientific Reports 10.
  https://doi.org/10.1038/s41598-020-70045-7

The local fixtures and the weighted Hoeffding derivation above are specified in
full for reproducibility; the cited works provide the physical foundations and
experimental selection-loophole context. They do not validate this implementation.
