# Heterogeneous AI handoff and routing: executable protocol prototype

Author of the architectural direction: Mengcheng (Windy) Wu. Implementation and
technical synthesis: AI-assisted. Date: 2026-11-04. This is research in the fork,
not a statement by the upstream MotionBricks authors.

## Status and scope

This implements the CPU-only next step of [PR #20](https://github.com/wu709621493/motionbricks/pull/20)
and its [architectural proposal](../ai_collaboration_architecture_zh.md). The base
inspected for this change was `c815923647042726ea5be5447f70ebea4caf6b13`; PR #20
was merged as `dd32a537f5944051eef43f0d6c8da04d00700ea1`.

The prototype models heterogeneity through centimetre, metre and millimetre
contracts, separate producer/receiver/verifier/publisher roles, and two routing
topologies. All participants are deterministic Python objects. No LLM, DeepSeek
endpoint, learned policy, RL training, GPU, network service or robot is invoked.
No existing inference, playback, export, dependency or initialization file is
changed. The original proposal and its illustrative JSON remain historical
documents; `proposal-0.1` is not an accepted executable protocol version.

**Passing these tests is not evidence of improved AI perception, human-like
understanding, multi-model reasoning, physical safety, or safety certification.**

## Protocol and host boundary

The implementation uses only Python's standard library. `Message.from_json`
accepts exactly the version `handoff/1.0`, a bounded JSON object with no duplicate
or unknown fields. Numeric distances are ordinary non-negative decimal strings:
at most nine integer digits and six fractional digits. No coercion of floats,
booleans, exponents, NaN, missing fields or unsupported versions is allowed.
The maximum encoded request size is 4,096 bytes.

| Contract field | Enforcement |
| --- | --- |
| Protocol, task ID, task revision, message ID | Exact version, known task, current revision, canonical digest |
| Sender, recipient, operation | Match host principal and task policy; only `offline_analysis` |
| Value, unit, coordinate frame | Match the host's immutable evidence snapshot before conversion |
| Evidence reference and SHA-256 | Bind the exact synthetic evidence including its validity limit |
| Model and configuration versions | Match host-registered fixture versions; not proof of real capabilities |
| Validity, roles and budgets | Supplied by the host `Task`, never granted by message fields |

`Task` and `Evidence` are frozen dataclasses. SHA-256 identifies content; it is
not a signature, an authentication mechanism, or proof that a measurement is
true. Evidence registration is trusted input to this simulation. A consistently
wrong host snapshot can pass every protocol check. This limitation must remain
visible in any future model experiment.

The caller must serialize operations, supply authenticated principals and a
nondecreasing integer clock, and protect host objects. There is no process
isolation, persistence, transport authentication or concurrency control here.
The `principal` parameter simulates a host identity, not a model's claimed role.
Five distinct roles are required. User-controlled content cannot grant roles,
set a VERIFIED flag, authorize physical execution or refresh consent.

## State, receipt and release semantics

The accepted path is `CREATED -> VALIDATED -> DELIVERED -> ACKNOWLEDGED ->
VERIFIED -> RELEASED`. `history()` exposes an immutable state snapshot.

| Operation | Required authority and prior state | Result |
| --- | --- | --- |
| `submit` | Task sender; fresh revision and evidence | Validated, converted and delivered candidate |
| `acknowledge` | Recipient; DELIVERED | Exact restatement of value, unit, frame, source hash and converter version |
| `verify` | Independent verifier role; ACKNOWLEDGED | Exact arithmetic verification against original host evidence |
| `release` | Publisher; VERIFIED | Recheck freshness and arithmetic, then issue one immutable offline release |
| `cancel` / `revise` | Owner | Invalidate affected records, including already released results |
| `read_release` | Designated consumer | Recheck current validity before returning a historical result |

`Receipt` returns `ok`, `state`, a stable `code`, message ID and (when appropriate)
the candidate artifact. Invalid transitions and unauthorized callers receive
explicit refusals and cannot advance the stored state. A refusal receipt's state
describes that attempted operation; use `history()` for the underlying record.
Schema failures have no admitted record. Budget failures before delivery also do
not allocate records, preventing an exhausted task from accumulating new IDs.

ACKNOWLEDGED is deliberately insufficient for release. The adapter uses bounded
`Decimal` arithmetic; `ai_handoff_verify.py` independently recomputes the result
with `Fraction` and its own unit rules. The two share a lexical decimal-string
check but no conversion implementation. Both still depend on the same evidence
and Python runtime, so this is implementation diversity, not complete fault
independence. A fault-injection test makes the adapter return 120 m for 120 cm;
the receiver may acknowledge it, but the verifier rejects it.

Only cm/mm/m length conversion is supported. No coordinate transformation is
inferred; frames must match exactly. Sub-micrometre results outside the output
representation are explicitly refused as `UNREPRESENTABLE_OUTPUT`, never rounded.

Canonical message IDs are scoped to task ID and revision. Identical retries
return a `DUPLICATE` receipt without a second delivery or artifact. Reusing an ID
with different content returns `MESSAGE_ID_CONFLICT` and preserves the original.
Releasing the same record twice is refused. Message caches do not survive a
process restart; distributed exactly-once delivery is not claimed.

At `now >= min(task.expires_at, evidence.valid_until)`, release is forbidden.
Revision changes invalidate old records; cancellation is irreversible for that
task ID, even if the revision later increases. Lifecycle control is not blocked
by exhausted data-plane budgets. A withdrawn release remains in the historical
ledger and generates an invalidation entry naming its consumer. Expiry is
detected on access, not by a background scheduler. Consumers must check
`read_release`; cached copies cannot be erased or remotely recalled. Notifications
are in-memory audit entries, not delivered external messages.

## Routing and equal-budget experiment

`broadcast` and `directed` use the same task order, four-peer registry, evidence,
adapter, receipts, verifier, publisher and constraints. All broadcast peers are
authorized to see these synthetic fixtures. Broadcast creates four delivery
events; three non-target peers record `IGNORED_NOT_RECIPIENT`. Directed routing
creates only the addressed delivery. No broadcast peer is allowed to bypass the
release gate. This isolates topology rather than comparing different validators.

The fixed seed is `20261104`. There are 25 categories and 10 generated distances
per category: 250 paired tasks, of which 40 are expected to complete normally.
Cases include valid cm/m/mm and retries, mislabeled/unknown units, missing/wrong
coordinates, missing/wrong provenance, missing model version, conflicting IDs,
expired tasks/evidence, revision changes, withdrawal, unauthorized senders,
operations, acknowledgements and publishers, bad conversions, bad receipts and
three forms of post-release invalidation. The exact fixtures are regenerated by
the script and bound by a manifest digest in [results.json](results.json).

Two budgets are specified in advance: 100 and 6 work credits per task, each
with at most 16 payload deliveries, four handoffs and a deadline of tick 30.
No retry loop exists. Budgets persist across task revisions. Control/read calls
are outside data-plane credits and cannot emit a new release. The low-budget
condition intentionally tests exhaustion; its refusals must not be mistaken
for semantic fault detection.

Metrics have explicit, limited meanings:

- **Unsafe-release rate:** invalid attempts that produce a forbidden release,
  or a current read after post-release invalidation, divided by 210 invalid
  attempts. Initial releases in post-release tests are allowed and remain logged.
- **False-rejection rate:** valid tasks that fail to release, divided by 40 valid
  tasks. This includes budget exhaustion and is an availability measure.
- **Decision-error rate:** unsafe releases plus missed valid completions, divided
  by 250 tasks. Denying everything therefore does not score perfectly.
- **Payload deliveries and bytes:** serialized message-plus-artifact payloads
  delivered to peers. Bytes exclude receipts and local host calls.
- **Transport messages:** payload deliveries plus explicit semantic ACKs. Delivery
  audit entries are not transmitted receipts. Ingress, verification, publication
  and control are local calls and excluded from this transport count.
- **Work credits:** one for schema-valid known-task ingress, one for conversion,
  one per payload delivery, and one per attempted ACK/verify/release. Failed
  reservations charge no additional credits. Parsing rejects and control/read
  are not credited. Credits are a declared scheduling proxy, not CPU instructions,
  FLOPs, energy, tokens or money.
- **Measured CPU/elapsed time:** all `run_case` work, including fixture host setup,
  parsing, refusals and controls. Ten repetitions alternate topology order.
  Serialization of the final report and interpreter startup are excluded.

See [RESULTS.md](RESULTS.md) for observed counters, timings and interpretation.
Deterministic counts are checked in CI; timing is descriptive and never a pass
threshold. Repeated runs do not create additional independent tasks. No population
error estimate, confidence claim or real-model cost reduction follows from this
handcrafted distribution. The design's single-model and naming controls require
separate future experiments; they have not been run here.

## DeepSeek-R1: technical context and ethics

The original [DeepSeek-R1 preprint, v1, 22 January 2025][r1-v1] distinguishes
R1-Zero (RL after base-model pretraining without preliminary SFT) from R1's
cold-start SFT, reasoning RL, rejection-sampled SFT and broader RL stages. GRPO
uses within-group reward comparisons instead of a separate critic. R1-Zero uses
accuracy and format rewards; the paper discusses reward hacking, language mixing
and distillation into smaller Qwen/Llama models. These are training results;
they do not demonstrate this handoff architecture. “Pure RL” does not mean an
untrained model or an absence of pretraining data. [1, sections 2 and 4]

The [Nature article, published 17 September 2025][r1-nature], explicitly discusses
jailbreak and harmful fine-tuning risks, as well as limitations in structured
output, tool use, language consistency and token efficiency. Its safety evaluation
is an author-reported result under specified conditions, not a certification.
It describes rule-based rewards for verifiable reasoning and model-based rewards
for general tasks, with harmlessness assessed across the response. We cite these
as findings about the studied models, not a claim about every later DeepSeek
release or hosted configuration. [2, Methods; Ethics and safety statement;
Conclusion, limitation and future work]

Our engineering and ethical interpretation, rather than a claim made by those
papers, is the following:

| Lesson applied here | Concrete implementation or research constraint |
| --- | --- |
| A plausible explanation is not independent verification | Check final structured values against host evidence; no reasoning-text approval |
| A task score cannot grant authority | Separate receipt, verifier and publisher roles; fail closed on requested physical operations |
| Verifiers have limited coverage | State the exact arithmetic predicate and demonstrate an injected adapter fault |
| Costs must include validation | Count gate operations and record host timings, including failed tasks |
| Safety judgments are context dependent | Do not equate benchmark success or refusal rates with harmlessness or certification |
| Data and accountability need explicit ownership | Synthetic-only evidence now; future personal data need consent, access limits, retention rules and provenance |
| Withdrawal has real limits | Preserve historical releases and emit invalidation records; do not claim to erase consumers' knowledge |

There is no GRPO implementation or DeepSeek integration in this PR. A future
connector should request a bounded structured answer and a concise evidence
summary; private reasoning traces are unnecessary for protocol authorization.
Model output and retrieved source text must remain data, never policy. For actual
multi-model evaluation, pin model/checkpoint and prompt versions, include prompt
and output tokens, latency, validation overhead and service failures, and test
withheld tasks and source-conflict cases. Independent verification must be
distinguished from multiple models repeating a shared incorrect source. Human
review, consent and physical-system authority require separate workflows.

## Reproduce and review

From the repository root, with Python 3.12 or 3.13 and no dependency installation:

```bash
python -S -m unittest discover -s tests/ai_handoff -v
python -S -m tools.ai_handoff.benchmark --check docs/ai_handoff/results.json
python -S -m tools.ai_handoff.benchmark --timing --output handoff-host-results.json
python -S -m unittest discover -s tests/preflight -v
```

The dedicated [workflow](../../.github/workflows/ai-handoff.yml) runs on Ubuntu
x86-64, Ubuntu ARM64 and macOS ARM64, each with Python 3.12/3.13. It uses `-S` and
does not install MotionBricks or load GPU libraries. Host timings are uploaded as
per-job artifacts. Existing workflows remain unchanged.

The [PR plan](PR_PLAN.md) lists every added file, commands and GitHub operations.

## Primary references

1. DeepSeek-AI et al. *DeepSeek-R1: Incentivizing Reasoning Capability in LLMs via
   Reinforcement Learning*. arXiv:2501.12948v1 (2025). Sections 2.2–2.4, 4 and 5.
2. Guo, D. et al. *DeepSeek-R1 incentivizes reasoning in LLMs through reinforcement
   learning*. Nature **645**, 633–638 (2025). DOI: 10.1038/s41586-025-09422-z.
3. MotionBricks fork PR #20 and its linked proposal, read at the base SHA above.

[r1-v1]: https://arxiv.org/html/2501.12948v1
[r1-nature]: https://doi.org/10.1038/s41586-025-09422-z
