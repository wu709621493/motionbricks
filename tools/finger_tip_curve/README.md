# Finger Tip to Equation: synthetic curve prototype

This standalone, CPU-only example implements **Curve inference mode** from
[the bootcamp concept note](https://github.com/Guilty-Crown-x-Gintama-Ninjas/bootcamp/blob/master/finger_tip_to_equation_transformer.md) (PR #792).
No camera, OCR, gesture intent inference, robot integration, or learned model is included.

## Reproduce

Tested with Python 3.12.14, NumPy 2.3.5, pytest 9.2.0 on Linux.
Run from this directory:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python synthetic.py
python -m pytest -q
python validate.py
python -c 'import json; from synthetic import cases; print(json.dumps(cases()["circle"]["request"]))' > /tmp/curve.json
python curve_inference.py /tmp/curve.json
```

The checked-in `synthetic_cases.json` contains 14 fully synthetic labeled cases
(seed 42). Regeneration is tested against its exact contents. `validate.py`
uses seeds 100–119 and writes `validation_results.json`; the seed sweep is an
engineering check, not an independent clinical or human-gesture benchmark.

## Unified API

```python
from curve_inference import infer_curve
result = infer_curve({
    "mode": "curve",              # must be explicitly selected by the caller
    "frame": "referenced",        # otherwise defaults to unreferenced
    "units": "cm",                # caller-supplied coordinate units
    "points": [[0, 0], [1, 1]]     # abbreviated: >=12 unique points required
})
# This abbreviated example returns insufficient_unique_points.
```

Input is one finite N-by-2 trace (maximum 5,000 samples). Referenced coordinates
must already have a known origin, orthogonal x/y axes, and equal distance units.
Transform pixels into those coordinates *before* calling the API. `units` is an
assertion, not a calibration procedure; unknown aspect ratio, perspective,
rotated graph axes, or an uncalibrated image can change model identity. A circle
under anisotropic scaling is an ellipse. Quadratics are only graphs y=f(x) in
the supplied axes, not arbitrary rotated parabolas.

Output always has `schema_version`, `status`, `reasons`, `model_family`,
`parameters`, `candidates`, and probability fields. Invalid arrays return a
structured rejection; malformed JSON / file I/O are CLI errors.

| Status | Meaning |
|---|---|
| `accepted` | A supported model is selected, conditional on the caller's frame and curve-mode assertions. |
| `needs_reference` | A local normalized shape fits, but origin/axes/scale are unconfirmed. No intended equation is identified. |
| `ambiguous` | Competing model families fit sufficiently similarly; no final model or parameters returned. |
| `rejected` | Too few unique points, degenerate extent, poor support, or inadequate circle coverage. |

Parameter conventions: line `A*x+B*y+C=0` with `A²+B²=1` (supports vertical
lines), circle `(x-h)²+(y-k)²=r²`, quadratic `y=a*x²+b*x+c`.
For accepted results the top-level parameters are in input coordinates;
for `needs_reference` they are local coordinates
`u=(x-origin_x)/isotropic_scale`, `v=(y-origin_y)/isotropic_scale`.
**All candidate parameters and errors are normalized**, including candidates
inside accepted results. The output records the normalization transform.
`equation_identified` means only a conditional model selection in the asserted
frame; it does not establish the user's intended equation or gesture semantics.
A circle could still be a zero or emphasis. The caller must obtain intent.

## Estimation and rejection policy

1. Validate finite coordinates; remove exact duplicate points so pauses cannot
   manufacture evidence. Sorting makes results independent of trace order.
2. Center at the coordinate-wise median and divide both axes by the same
   80th-percentile radial scale. Independent axis normalization is forbidden.
3. Generate 128 seeded minimal-subset proposals per family plus a full-data fit.
   Use total least squares for lines, algebraic least squares for circles, and
   vertical least squares for quadratics, then refit consensus points three times.
4. Score line and circle candidates with Euclidean distances. Quadratic proposal
   screening uses a first-order distance approximation, but final consensus and
   diagnostics use exact nearest-curve distances, solving the cubic stationary
   equation and taking the minimum over its real roots.
5. Require >=12 inliers and >=85% support within normalized distance 0.015.
   Circle support must span >=pi radians (largest angular-gap criterion).
   Quadratic normalized bend `abs(a)*x_span²` must be >=0.06; smaller curvature
   is unresolved at this policy's scale. Reject ill-conditioned design matrices.
6. Rank supported candidates by inlier RMSE. Abstain when the runner-up RMSE is
   <=max(0.003, 1.7*best_RMSE). Short-circle candidates still compete even if
   their angular coverage is insufficient; a short arc must not silently become
   a reliable parabola merely because the circle failed its coverage gate.

These thresholds are explicit prototype engineering choices, not learned or
statistically calibrated decision boundaries. Both inlier RMSE and all-point
RMSE are returned so trimming cannot hide discarded measurements. The algorithm
has no physical noise model, no guaranteed outlier breakdown point, and no
parameter confidence intervals. Algebraic/vertical refits can be biased under
errors in both coordinates. Random proposals can miss a useful hypothesis.
Near duplicates are not merged: dense clusters, correlated samples, uneven
sampling, and adversarial arrangements require further validation. There is no
smoothing/interpolation that could artificially add independent observations.

## Confidence and limits

`prediction_probability` is always `null`, and `probability_calibrated` is
always `false`. RMSE measures geometric agreement, not probability of a correct
classification. The concept note's example 0.93 is not reused as performance.
Obtaining calibrated probabilities would require representative labeled human
trajectories, split by participant/session, a held-out calibration set, and
reliability/coverage/error evaluation including out-of-family inputs.

A finite noisy trace cannot prove a unique global equation. Near-straight curves
may be represented locally as lines or rejected as ambiguous. A sufficiently
near-circular ellipse may pass as a circle at the declared tolerance. These are
resolution limits, not solved semantic inference. Restricting to three families
does not guarantee detection of every unsupported curve. CPU/memory usage is
bounded by the 5,000-point cap but this is not a real-time latency guarantee.

## Validation results

- `python -m pytest -q`: **28 passed** (0.94 s in the recorded run).
- Seed sweep: **280/280 expected outcomes**, **0 false acceptances** among the
  defined synthetic checks; see the complete machine-readable report.
- Tests cover parameter recovery, vertical lines, exact duplicates, low unique
  counts, outliers, invalid/nonfinite input, similarity transforms, deterministic
  ordering, missing frame/mode, near-line curvature, and fixture regeneration.
- Counterexamples: short circle arcs (circle/quadratic ambiguity), elongated
  ellipses, sine traces, random clouds, intersecting strokes, and heavy noise.
- The near-line test permits conservative abstention; distinguishing a very
  large-radius arc from a line is not identifiable at the chosen tolerance.
- Only this isolated example was tested. No claim is made that the unrelated
  MotionBricks test suite or macOS/Windows execution was validated.

## MotionBricks integration boundary

This fork-local research tool runs independently of MotionBricks and requires
only NumPy at runtime. Use the isolated virtual environment above: the pinned
NumPy 2.3.5 reproduction environment is separate from MotionBricks' NumPy 2.4.3
runtime environment. Do not install these requirements into the main environment.
It imports no Warp, TensorRT, model weights, graphics stack, or device controller.

Potential future authoring flow: synthetic 2-D trace -> curve proposal -> user
confirmation of intent/frame -> explicit 3-D plane and units -> sampled targets
-> pose/IK construction -> MotionBricks motion generation. Only the first curve
proposal stage is implemented here. Accepted curve parameters are not target
poses, joint commands, a dynamically feasible trajectory, or evidence of human
force/temperature perception. Temporal ordering is discarded by the estimator;
velocity, acceleration, timing, reachability and collision checks require a
separate integration stage. No live robot or character runtime is connected.

## Provenance

Ported from the Finger Tip Curve Prototype prepared for bootcamp concept PR #792.
The original implementation and synthetic validation were produced in this
research workflow; this port adds MotionBricks-specific documentation and a root
README entry. All three model families, refusal behavior, fixtures, tests and
validation scripts are retained. The bootcamp prototype was not merged upstream.
The changes target wu709621493/motionbricks, not NVIDIA's upstream repository.
