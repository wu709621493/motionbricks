# Zero-error guard (无零算法)

Concept requested by Mengcheng Wu (Windy Wu); implementation and test mapping
prepared with AI assistance. This is an opt-in CPU numerical utility, not a new
arithmetic system and not a proof of Perception Theory.

## Contract

Zero remains meaningful in positions, velocity, counts, timestamps, probabilities,
indices and masks. Do not replace every zero with epsilon. Only select operation
boundaries use a guard. The initial API accepts built-in finite int/float values,
converts to binary64, and excludes bool, complex, Decimal and tensors. Large integer
precision is not preserved. Float rounding/underflow remains possible; this is not
an arbitrary-precision implementation. Tensor/GPU/autograd paths are unchanged.

```python
from motionbricks.zero_guard import divide, log, normalize

assert divide(0, 2).value == 0
missing = divide(1, 0, policy='undefined')  # value=None, status=UNDEFINED
hold = normalize([0, 0, 0], policy='fallback', fallback=[0, 0, 0])
assert hold.status == 'FALLBACK'  # deliberately NOT a valid unit direction
```

| Operation | Zero case | Default | Explicit alternatives |
|---|---|---|---|
| divide(a, b) | b = +0 or -0, including 0/0 | ZeroDomainError | undefined / caller fallback |
| log(x) | x = +0 or -0 | ZeroDomainError | undefined / caller fallback |
| normalize(v) | all components zero | ZeroDomainError | undefined / dimension-matched fallback |

A fallback is labelled with its operation and original reason. Caller must inspect
status before consuming value. Invalid types, nonfinite input, empty vectors,
negative real log arguments and arithmetic overflow are not hidden by recovery.
Tiny nonzero divisors remain unchanged. Vector scaling avoids norm overflow and
underflow for finite input vectors. No catch-all retry can duplicate side effects.
The library never changes a controller command or clears a fault automatically.

## Existing repository integration

`motionbricks.optical_quantum.sampling_statistics(request, result)` first validates
the record, then computes acceptance fraction and ZZ correlation. All rejected
shots return correlation `UNDEFINED`/`None`; balanced accepted counts return
correlation `OK`/0. The existing `report()` schema and record hash remain unchanged.
Neither outcome proves entanglement.

SleepSupervisor regression checks preserve zero speed, tilt and origin timestamp,
while repeated tick timestamps remain faults. This is a software contract check;
it does not establish physical balance or safety. Callers must choose a recovery
policy appropriate to their domain; undefined values cannot drive actuators.

## Perception Theory L1-L7 evidence protocol

Historical numbering differs. This task uses the recent L1-L4 understanding
sequence and recent L5/L6 physical-perception extension. The earlier L5
“信达雅” translation requirement is retained as a cross-cutting review criterion,
not silently renumbered or declared passed. No authoritative latest L7 definition
was located. The older nine-layer stack is not substituted for this framework.

| Layer | Definition / attribution | This experiment and remaining evidence |
|---|---|---|
| L1 | Understand what is being discussed; user origin | Executed zero-data vs zero-error fixtures; no claim that fixtures prove subjective understanding |
| L2 | Paraphrase accurately; user origin | Operation/status/reason output plus this explanation; independent paraphrase assessment pending |
| L3 | Correct application to a new situation; AI suggestion accepted by user | Executed optical statistics and sleep transfer cases; software evidence only |
| L4 | Express the applied conclusion so at least three humans understand; user origin | NOT TESTED: recruit three reviewers independently, ask each to distinguish missing correlation from zero correlation and explain why fallback is not a measured answer; all three must answer both correctly |
| L5 | Examine human/robot perception gaps; recent user extension | NOT TESTED: requires a shared calibrated stimulus and measured human/robot responses; numeric fixtures alone are insufficient |
| L6 | Human-comparable force and temperature sensing/regulation; user extension | NOT TESTED: requires instrumented physical trials and approved acceptance thresholds |
| L7 | Latest definition unavailable | DEFINITION REQUIRED; no invented criterion or pass |

For the translation criterion, reviewers should verify that “无零” means guarded
zero-related operations, that valid zeros remain, and that uncertainty/fallback
labels survive Chinese-English paraphrase. No human language study was run.

## Reproduction

```sh
python -m unittest discover -s tests/zero_guard -v
python -m unittest discover -s tests/optical_quantum -v
python -m unittest discover -s tests/sleep_mode -v
python tools/zero_guard/evaluate.py > zero_guard_evaluation.json
```

The JSON contains executed CPU test counts and per-layer evidence status. It always
reports `all_layers_validated: false` until an actual expanded protocol is designed
and executed; passing code tests is not passing all seven layers. Test logs go to
stderr; JSON goes to stdout. The six existing Ubuntu/macOS × Python CI matrix jobs
now run the new tests. Local execution is not evidence that remote CI or hardware
trials have completed.
