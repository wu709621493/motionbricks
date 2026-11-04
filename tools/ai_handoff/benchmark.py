"""Paired, reproducible synthetic protocol study; never invokes an AI model."""

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import platform
import random
from statistics import median
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from motionbricks.ai_handoff import Broker, Evidence, Task, adapt, canonical, digest, make_message

CASES = (
    "valid_cm", "valid_m", "valid_mm", "duplicate", "unit_error", "unknown_unit",
    "missing_coordinate", "wrong_coordinate", "missing_source", "wrong_source",
    "missing_model_version", "conflicting_duplicate", "expired", "evidence_expired",
    "revision_changed", "withdrawn", "unauthorized_sender", "unauthorized_operation",
    "unauthorized_receiver", "unauthorized_release", "bad_conversion", "bad_receipt",
    "withdraw_after_release", "revise_after_release", "expire_after_release",
)
VALID = {"valid_cm", "valid_m", "valid_mm", "duplicate"}
POST_RELEASE = {"withdraw_after_release", "revise_after_release", "expire_after_release"}


def fixtures(seed=20261104, per_case=10):
    rng = random.Random(seed)
    result = []
    for case in CASES:
        for n in range(per_case):
            # Integer source distances ensure all unit conversions fit the contract.
            unit = {"valid_m": "m", "valid_mm": "mm"}.get(case, "cm")
            result.append(dict(case=case, task_id=f"{case}-{n:02}",
                               value=str(rng.randrange(1, 10000)), unit=unit))
    rng.shuffle(result)
    return result


def run_case(fixture, topology, budget=100):
    case = fixture["case"]
    evidence = Evidence("fixture:" + fixture["task_id"], fixture["value"], fixture["unit"],
                        "synthetic-world", 5 if case == "evidence_expired" else 30)
    task = Task(fixture["task_id"], evidence, max_work=budget)
    broker = Broker([task], topology=topology)
    message = make_message(task)
    data = asdict(message)
    changes = {
        "unit_error": {"unit": "m"}, "unknown_unit": {"unit": "inch"},
        "wrong_coordinate": {"coordinate_frame": "robot-local"},
        "wrong_source": {"evidence_sha256": "0" * 64},
        "unauthorized_operation": {"operation": "physical_execute"},
    }
    data.update(changes.get(case, {}))
    missing = {"missing_coordinate": "coordinate_frame", "missing_source": "evidence_ref",
               "missing_model_version": "model_version"}
    if case in missing:
        del data[missing[case]]
    now = 30 if case == "expired" else 5 if case == "evidence_expired" else 1
    sender = "intruder" if case == "unauthorized_sender" else task.sender
    key = (task.task_id, 1, "m1")
    if case == "bad_conversion":
        # Mutation control: preserve well-formed metadata, corrupt the arithmetic.
        with patch("motionbricks.ai_handoff.adapt",
                   side_effect=lambda m: replace(adapt(m), value="99999999")):
            receipt = broker.submit(canonical(data), principal=sender, now=now)
    else:
        receipt = broker.submit(canonical(data), principal=sender, now=now)
    if receipt.ok and case == "duplicate":
        duplicate = broker.submit(canonical(data), principal=sender, now=now)
        if not duplicate.ok:
            receipt = duplicate
    if receipt.ok and case == "conflicting_duplicate":
        receipt = broker.submit(replace(message, value="99999").to_json(), principal=sender, now=now)
    if receipt.ok:
        understood = receipt.artifact
        if case == "bad_receipt":
            understood = replace(understood, frame="wrong-frame")
        receiver = "observer-a" if case == "unauthorized_receiver" else task.recipient
        receipt = broker.acknowledge(key, understood, principal=receiver, now=now)
    if receipt.ok:
        receipt = broker.verify(key, principal=task.validator, now=now)
    if receipt.ok:
        if case == "revision_changed":
            broker.revise(task.task_id, 2, principal=task.owner, now=now)
        if case == "withdrawn":
            broker.cancel(task.task_id, principal=task.owner, now=now)
        publisher = task.recipient if case == "unauthorized_release" else task.publisher
        receipt = broker.release(key, principal=publisher, now=now)
    if receipt.ok and case in POST_RELEASE:
        rid = broker.releases[0].release_id
        if case == "withdraw_after_release":
            broker.cancel(task.task_id, principal=task.owner, now=now)
        elif case == "revise_after_release":
            broker.revise(task.task_id, 2, principal=task.owner, now=now)
        receipt = broker.read_release(rid, principal=task.recipient,
                                      now=30 if case == "expire_after_release" else now)
    valid = case in VALID
    unsafe = (bool(broker.releases) and not valid and case not in POST_RELEASE) or (
        case in POST_RELEASE and receipt.ok)
    completed = valid and receipt.ok and receipt.state == "RELEASED"
    return dict(task_id=task.task_id, case=case, valid=valid, completed=completed,
                unsafe_release=unsafe, outcome=receipt.code, state=receipt.state,
                historical_releases=len(broker.releases), invalidations=len(broker.invalidations),
                **dict(broker.usage(task.task_id)))


def study(seed=20261104, per_case=10, budgets=(100, 6), timing=False):
    tasks = fixtures(seed, per_case)
    groups = []
    for budget in budgets:
        for topology in ("broadcast", "directed"):
            rows = [run_case(f, topology, budget) for f in tasks]
            valid = sum(r["valid"] for r in rows)
            successes = sum(r["completed"] for r in rows)
            unsafe = sum(r["unsafe_release"] for r in rows)
            group = dict(topology=topology, max_work_per_task=budget, tasks=len(rows),
                         valid_tasks=valid, invalid_attempts=len(rows) - valid,
                         completed_valid=successes, unsafe_releases=unsafe,
                         unsafe_release_rate=unsafe / (len(rows) - valid),
                         false_rejection_rate=(valid - successes) / valid,
                         decision_error_rate=(valid - successes + unsafe) / len(rows),
                         **{key: sum(r[key] for r in rows)
                            for key in ("deliveries", "bytes", "work", "acknowledgements")},
                         rows=rows)
            group["transport_messages"] = group["deliveries"] + group["acknowledgements"]
            group["work_per_valid_completion"] = group["work"] / successes if successes else None
            groups.append(group)
    if timing:
        samples = {(b, t): [] for b in budgets for t in ("broadcast", "directed")}
        # Alternate topology order; timing includes fixture host setup and gates.
        for repetition in range(10):
            for budget in budgets:
                order = ("broadcast", "directed") if repetition % 2 == 0 else ("directed", "broadcast")
                for topology in order:
                    start_cpu, start_wall = process_time_ns(), perf_counter_ns()
                    for f in tasks:
                        run_case(f, topology, budget)
                    samples[(budget, topology)].append(dict(cpu_ns=process_time_ns() - start_cpu,
                                                            elapsed_ns=perf_counter_ns() - start_wall))
        for group in groups:
            raw = samples[(group["max_work_per_task"], group["topology"])]
            group["timing"] = dict(repetitions=10, samples=raw,
                                   median_cpu_ns=median(x["cpu_ns"] for x in raw),
                                   median_elapsed_ns=median(x["elapsed_ns"] for x in raw))
    return dict(schema_version="synthetic-study/1", seed=seed, per_case=per_case,
                fixture_sha256=digest(tasks), cases=list(CASES),
                scope="In-process deterministic protocol simulation; no model inference or physical execution",
                budgets=dict(max_deliveries=16, max_handoffs=4, deadline=30), groups=groups)


def render_report(report):
    """Readable metadata and one compact JSON row per task, avoiding giant diffs."""
    header = json.dumps({k: v for k, v in report.items() if k != "groups"}, indent=2, sort_keys=True)[:-2]
    groups = []
    for group in report["groups"]:
        metadata = json.dumps({k: v for k, v in group.items() if k != "rows"}, indent=2, sort_keys=True)[:-2]
        rows = ",\n".join("    " + json.dumps(row, sort_keys=True) for row in group["rows"])
        groups.append(metadata + ',\n  "rows": [\n' + rows + "\n  ]\n}")
    return header + ',\n  "groups": [\n' + ",\n".join(groups) + "\n  ]\n}\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timing", action="store_true", help="Include non-reproducible host timings")
    parser.add_argument("--check", type=Path, help="Compare deterministic results with a committed report")
    args = parser.parse_args()
    if args.check and args.timing:
        parser.error("--check excludes --timing")
    report = study(timing=args.timing)
    if args.timing:
        report["environment"] = dict(python=platform.python_version(), os=platform.platform(),
                                     architecture=platform.machine())
    text = render_report(report)
    if args.check:
        if report != json.loads(args.check.read_text()):
            parser.exit(1, "Synthetic report differs from committed results\n")
        print("Deterministic report matches committed results")
    elif args.output:
        args.output.write_text(text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
