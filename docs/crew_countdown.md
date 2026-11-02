# Crew-led zero-boundary countdown / 尊重乘员判断的“无零”倒数

Concept requested by Mengcheng Wu (Windy Wu); implementation prepared with AI
assistance. Experimental CPU state machine for discussion and simulation only.
It contains no ignition, vehicle-control, launch-abort-system or network adapter.
This is a proposed interaction contract, not a description of an agency's current
launch procedure. Timing defaults are arbitrary test values, not flight limits.

## Meaning of “zero-free” here

Time can reach zero. Zero must never stand in for consent, readiness, missing data
or permission to launch. The countdown reaches a named AWAITING_CONFIRMATION
state. A subsequent crew confirmation, new GO votes from every configured crew
member after that boundary, and both ground/vehicle GO produce a simulation
REVIEW_REQUESTED event. This event is not authorization to fire an engine.

The existing `zero_guard.divide` computes progress as elapsed/duration, with
strictly positive configured duration. No reciprocal of remaining time, epsilon
substitution, or numeric fallback can turn a failed condition into GO.

## Authority and state transitions

| Current condition / action | Result |
|---|---|
| Initial session | HOLD; explicit crew resume required |
| Crew resume + all fresh GO + both interlocks | COUNTING; held time is not consumed |
| Any missing GO, crew HOLD, invalid input or interlock failure | HOLD; countdown freezes |
| Enter HOLD from another phase | Epoch increments; previous consent cannot resume |
| Remaining time reaches zero, even on a confirm call | AWAITING_CONFIRMATION, no event |
| Later configured crew confirm + all new post-boundary votes + interlocks | One simulation review request |
| Repeated confirmation without intervening HOLD | No duplicate review event |
| Explicit HOLD after review | Local withdrawal; new epoch and resume required |
| Explicit ABORT or valid known-crew ABORT vote | Latched ABORTED |
| Simulation window expires | Latched ABORTED; new session required |

All configured crew members have a veto; no majority rule or ground override is
implemented. Silence, duplicate identities, unknown identities, stale votes and
old-epoch GO cannot substitute for consent. Both resume and confirm identify a
configured crew actor. The calling application must authenticate that identity;
a string is not proof of who pressed a button. Humans need not repeatedly press
GO on every tick: a trusted adapter can carry a still-valid deliberate decision
within its expiry, but must not renew consent timestamps without a fresh decision.
The post-boundary confirmation requires fresh GO from every member.

Snapshots have increasing sequence numbers, finite monotonic timestamps and
bounded age. Future/stale/replayed snapshots and missed tick deadlines enter HOLD
without advancing the countdown. A known crew ABORT in a structurally valid,
fresh snapshot vetoes conflicting GO/interlocks. For a stale/broken snapshot the
result is HOLD; the separate `command='abort'` path works without telemetry or a
valid clock. ABORT is latched; resetting means creating a distinct session.

## Running the proposal

```sh
python -m unittest discover -s tests/crew_countdown -v
python tools/crew_countdown/demo.py
```

The committed `crew_countdown_demo.json` records inputs, decisions, epochs and
progress for a reproducible sequence: countdown, pilot HOLD, no automatic resume,
crew resume, zero boundary, later confirmation, duplicate suppression, abort.
`Decision.request_review` is an edge event only; it must not be treated as a
persisting authorization. A later HOLD/ABORT cannot recall a previously delivered
message in another system. This prototype has no downstream consumer and does
not guarantee distributed cancellation, durable audit, authentication or real-time
scheduling. Application-level traces must retain the inputs as the demo does.

## Validation and next evidence

CPU tests cover zero vs confirmation, pre-boundary vote rejection, crew vetoes,
ground non-override, stale/replayed/future data, clock faults, deadline gaps,
window expiry, explicit resume, frozen time, consent epochs and no duplicate event.
CI adds this suite alongside zero_guard and Bell/CHSH without removing either.

The existing Perception Theory protocol applies: L1 distinguish time from consent;
L2 paraphrase the distinction; L3 apply it to pause/resume and launch-window cases.
These are software evidence and proposed comprehension prompts only. L4 still
requires three independent human reviewers; no astronaut usability test has run.
L5/L6 human-machine and physical validation remain unperformed. The unresolved
L7 definition is not invented here. Human review should specifically ask whether
participants can veto without social pressure and distinguish review from launch.

Any future operational design needs mission-specific command authority, independent
hazard analysis, irreversible-event boundaries, communication-loss handling and
hardware validation. This model deliberately ends before operational launch control.
