# Virtual cockroach home: reproducible synthetic runs

The [Chinese model guide](../../docs/roach_home/README_zh.md) explains the rules,
primary sources, data definitions and limitations. The apartment and configuration
are editable JSON inputs. Everything in this directory is synthetic.

From the repository root:

```sh
python -S -m motionbricks.roach_home --house experiments/roach_home/apartment.json \
  --config experiments/roach_home/config.json --out-dir /tmp/roach-home-replay
python -S -m motionbricks.roach_home --house experiments/roach_home/apartment.json \
  --config experiments/roach_home/config.json --compare --seeds 1,2,3,4,5 \
  --out-dir /tmp/roach-home-paired
```

Open `/tmp/roach-home-replay/observe.html` locally. The complete trajectories and
replay are generated rather than committed; `generated_artifact_hashes.json`
records the original generated run's digests. `baseline_summary.json` retains its
summary and runtime. Hashes of JSON/HTML include runtime metadata, so matching
output hashes on other platforms is not promised.

## Actual local verification, 2026-11-13

- Linux x86-64, CPython 3.12.14, standard library only (`python -S`).
- 13 software tests passed, covering wall boundaries, connected doorways,
  per-step motion, population and heat conservation, resource reachability,
  deterministic seeds, paired initial conditions, scenario removals, input
  validation, output hashes, no-overwrite behavior and HTML data escaping.
- Default seed 1: 40 agents × 720 ticks. Summary window: ticks 361–720.
- Six scenarios × five paired seeds: 30 runs, 864,000 agent-ticks total.
- Exported JavaScript passed `node --check`.
- Browser visual/interaction verification: **NOT_RUN**. The environment's
  default Playwright browser executable was absent; installed Chromium also
  failed to launch because its required socket operation was denied. No browser
  playback, mobile layout or screenshot verification is claimed.
- Windows/macOS/Python 3.13 CI is defined in `roach-home.yml`; this local report
  does **not** claim those jobs have run or passed.
- Real cockroach observations, biological fitting, MotionBricks model inference,
  GPU inference, human exposure and infection validation: **NOT_RUN**.

## Synthetic comparison

Values are mean proportions over ticks 361–720, then averaged across five seeds.
They describe these rules and initialization, not measured cockroach populations.

| Scenario | Moving | In shelter | Adjacent to wall/furniture |
| --- | ---: | ---: | ---: |
| baseline | 35.21% | 52.11% | 85.03% |
| constant_light | 17.33% | 45.43% | 83.21% |
| no_food | 34.76% | 56.34% | 87.83% |
| no_water | 36.53% | 48.27% | 83.54% |
| no_shelters | 44.69% | 0.00% | 72.00% |
| no_social | 36.62% | 46.71% | 84.14% |

The permanently lit scenario has lower shelter occupancy here, despite an
explicit local light-avoidance term. Light also directly lowers movement attempt
probability, and agents start dispersed; these coupled rules can change shelter
arrival during a finite observation window. This is a diagnostic of the model,
not evidence that real cockroaches avoid shelters under light. Longer runs,
initialization checks and separate light/activity-factor ablations are needed
before interpreting the mechanism. Similarly, zero shelter occupancy after
removing all shelter labels is definitional, not a biological discovery.

See [all replicates](comparison/replicates.csv), [aggregates and paired delta
standard deviations](comparison/comparison.csv), [full comparison specification](comparison/specification.json)
and [comparison checksums](comparison/sha256.json).
