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
| Explicit human crew resume from HOLD + all fresh GO + both interlocks | COUNTING; held time is not consumed |
| Any missing GO, crew HOLD, invalid input or interlock failure | HOLD; countdown freezes |
| Enter HOLD from another phase | Epoch increments; previous consent cannot resume |
| Remaining time reaches zero, even on a confirm call | AWAITING_CONFIRMATION, no event |
| Later configured crew confirm + all new post-boundary votes + interlocks | One simulation review request |
| Repeated confirmation without intervening HOLD | No duplicate review event |
| Resume outside HOLD | HOLD, no time advance or review event; new epoch consent required |
| Explicit HOLD after review | Local withdrawal; new epoch and resume required |
| Explicit ABORT or valid known-crew ABORT vote | Latched ABORTED |
| Simulation window expires | Latched ABORTED; new session required |

All configured crew members have a veto; no majority rule or ground override is
implemented. Silence, duplicate identities, unknown identities, stale votes and
old-epoch GO cannot substitute for consent. Both resume and confirm identify a
configured crew actor and must originate from a deliberate human command.
Neither a scheduler, an AI agent, ground GO nor fresh telemetry may generate
resume or confirm on a human's behalf. The calling application must authenticate that identity;
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

## HOLD timing and manual recovery

The clock high-water mark (`_last_time`) and active monitoring baseline
(`_monitor_time`) serve separate purposes. Entering HOLD clears the monitoring
baseline and confirmation gate, while preserving the clock high-water mark,
snapshot sequence and remaining time. A finite forward timestamp on an explicit
HOLD updates that high-water mark. A clockless or faulty-clock HOLD still vetoes
continuation, without moving the clock backward.

`max_gap_s` bounds monitoring in COUNTING, AWAITING_CONFIRMATION and
REVIEW_REQUESTED. It does not limit deliberate time spent in HOLD. A successful
manual resume establishes a new monitoring baseline and consumes no paused time.
A gap while active still enters HOLD without consuming the unobserved interval;
recovery requires a separate human resume with fresh current-epoch unanimous GO
and both interlocks. Repeated resume outside HOLD is rejected into HOLD, rather
than acting as a tick or resetting the deadline. ABORT remains latched.

HOLD does not extend the absolute simulation window or vote/snapshot lifetimes.
At or beyond `window_end_s`, a finite supplied time aborts even on a HOLD command.
An idle CPU object has no background timer: expiry is evaluated at the next call
with a valid time. Nonfinite, equal or backward time cannot resume; clearing the
active baseline never clears the clock or replay safeguards.

For example, with `max_gap_s=1`, resume at t=0, HOLD at t=0.1 and resume at t=2
with new votes now returns COUNTING with unchanged remaining time. A tick at t=2
without the intervening HOLD instead reports `missed monitoring deadline`.

There is no launch state or launch command in this model. The modeled final
approval is only a human-confirmed simulation review request. After withdrawing
review into HOLD at zero, manual resume returns only to AWAITING_CONFIRMATION.
A separate later human confirm and unanimous GO timestamps strictly after that
resume gate are required to request review again. A tick, old vote or resume
alone cannot restore the prior review event.

This human-command contract is a design requirement, not proof that a string
argument came from a person. Authentication, human command provenance and usable
controls require a separate evaluated application. No claim is made that typical
passengers can comfortably operate a spacecraft, or that these CPU tests establish
astronaut usability or flight safety.

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
The HOLD regression suite additionally covers long pauses with and without held
ticks, active monitoring gaps, manual recovery, repeated resume, window expiry,
clockless vetoes, nonfinite/backward/equal clocks, old epochs, expired votes,
replay/future snapshots, interlocks and restoring review through two distinct
human commands. The original 13 tests passed before the fix; the added long-HOLD
case failed on the merged implementation and passes after this change.
CI runs this suite alongside zero_guard and Bell/CHSH without removing either.

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
