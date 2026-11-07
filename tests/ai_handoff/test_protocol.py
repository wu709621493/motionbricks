"""Adversarial API tests: observable refusals, independent oracle and lifecycle."""

from dataclasses import asdict, replace
from decimal import getcontext
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from motionbricks.ai_handoff import (
    Artifact, Broker, Evidence, Message, ProtocolError, STATES, Task, adapt,
    canonical, make_message,
)
from motionbricks.ai_handoff_verify import verify_distance


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.task = Task("distance-001", Evidence("fixture:cm", "120", "cm", "world", 30))
        self.broker = Broker([self.task])
        self.message = make_message(self.task)
        self.key = (self.task.task_id, 1, "m1")

    def submit(self, message=None, **kwargs):
        return self.broker.submit((message or self.message).to_json(),
                                  principal=kwargs.get("principal", "sensor"), now=kwargs.get("now", 1))

    def stage(self, final="VERIFIED"):
        receipt = self.submit()
        self.assertTrue(receipt.ok, receipt)
        if final == "DELIVERED":
            return receipt
        receipt = self.broker.acknowledge(self.key, receipt.artifact, principal="planner", now=1)
        self.assertTrue(receipt.ok, receipt)
        if final == "ACKNOWLEDGED":
            return receipt
        receipt = self.broker.verify(self.key, principal="verifier", now=1)
        self.assertTrue(receipt.ok, receipt)
        if final == "RELEASED":
            receipt = self.broker.release(self.key, principal="publisher", now=1)
            self.assertTrue(receipt.ok, receipt)
        return receipt

    def test_complete_history_and_offline_release(self):
        receipt = self.stage("RELEASED")
        self.assertEqual(receipt.artifact.value, "1.2")
        self.assertEqual(self.broker.history(self.key), STATES)
        release, = self.broker.releases
        self.assertFalse(release.physical_execution)
        self.assertTrue(self.broker.read_release(release.release_id, principal="planner", now=2).ok)
        self.assertEqual(self.broker.release(self.key, principal="publisher", now=2).code, "INVALID_TRANSITION")
        self.assertEqual(len(self.broker.releases), 1)

    def test_version_and_strict_schema(self):
        variants = [dict(protocol_version="handoff/2.0"), dict(task_revision=True),
                    dict(task_revision=1.0), dict(task_revision=0), dict(value=120),
                    dict(value="NaN"), dict(value="1e300"), dict(value="-1"),
                    dict(value="0" * 200), dict(coordinate_frame=" "), dict(config_version="")]
        for change in variants:
            with self.subTest(change=change):
                data = asdict(self.message) | change
                self.assertFalse(self.broker.submit(canonical(data), principal="sensor", now=1).ok)
        for field in self.message.__dataclass_fields__:
            data = asdict(self.message)
            del data[field]
            self.assertEqual(self.broker.submit(canonical(data), principal="sensor", now=1).code,
                             "SCHEMA_MISMATCH")
        data = asdict(self.message) | {"verified": True}
        self.assertEqual(self.broker.submit(canonical(data), principal="sensor", now=1).code, "SCHEMA_MISMATCH")

    def test_hostile_json_is_explicitly_rejected(self):
        inputs = ["{", "null", "[]", "[" * 1500, "\ud800", " " * 4097, 123,
                  self.message.to_json()[:-1] + ',"value":"1"}']
        for raw in inputs:
            with self.subTest(raw=str(raw)[:30]):
                self.assertFalse(self.broker.submit(raw, principal="sensor", now=1).ok)
        with self.assertRaisesRegex(ProtocolError, "DUPLICATE_JSON_KEY"):
            Message.from_json('{"x":1,"x":2}')

    def test_roundtrip_and_canonical_duplicate(self):
        self.assertEqual(Message.from_json(self.message.to_json()), self.message)
        self.assertTrue(self.submit().ok)
        usage = dict(self.broker.usage(self.task.task_id))
        receipt = self.broker.submit(json.dumps(asdict(self.message), indent=4), principal="sensor", now=1)
        self.assertTrue(receipt.duplicate)
        self.assertIsNone(receipt.artifact)
        self.assertEqual(self.broker.usage(self.task.task_id)["deliveries"], usage["deliveries"])
        self.assertEqual(self.broker.usage(self.task.task_id)["work"], usage["work"] + 1)

    def test_conflicting_duplicate_cannot_replace_original(self):
        original = self.submit()
        self.assertEqual(self.submit(replace(self.message, value="999")).code, "MESSAGE_ID_CONFLICT")
        self.assertTrue(self.broker.acknowledge(self.key, original.artifact, principal="planner", now=1).ok)

    def test_source_unit_frame_and_version_binding(self):
        for change in (dict(value="121"), dict(unit="m"), dict(coordinate_frame="local"),
                       dict(evidence_ref="fixture:other"), dict(evidence_sha256="a" * 64),
                       dict(model_version="another/1"), dict(config_version="distance/2")):
            with self.subTest(change=change):
                self.assertFalse(self.submit(replace(self.message, **change)).ok)
        self.assertEqual(self.submit(replace(self.message, unit="px")).code, "UNSUPPORTED_UNIT")
        self.assertEqual(self.submit(replace(self.message, task_id="unknown")).code, "UNKNOWN_TASK")

    def test_sender_spoofing_cannot_poison_message_id(self):
        self.assertEqual(self.submit(principal="intruder").code, "UNAUTHORIZED_SENDER")
        self.assertEqual(self.submit(replace(self.message, sender="intruder")).code, "UNAUTHORIZED_SENDER")
        self.assertTrue(self.submit().ok)

    def test_route_and_operation_are_host_policy(self):
        for message in (replace(self.message, operation="physical_execute"),
                        replace(self.message, recipient="publisher")):
            self.assertEqual(self.submit(message).code, "UNAUTHORIZED_ROUTE_OR_OPERATION")
        self.assertFalse(self.broker.deliveries)

    def test_out_of_order_and_wrong_actor_do_not_advance_state(self):
        self.submit()
        before = self.broker.history(self.key)
        self.assertEqual(self.broker.verify(self.key, principal="verifier", now=1).code, "INVALID_TRANSITION")
        self.assertEqual(self.broker.release(self.key, principal="publisher", now=1).code, "INVALID_TRANSITION")
        self.assertEqual(self.broker.acknowledge(self.key, adapt(self.message), principal="observer-a", now=1).code,
                         "UNAUTHORIZED_ACTOR")
        self.assertEqual(before, self.broker.history(self.key))
        self.assertEqual(self.broker.verify(("unknown", 1, "m1"), principal="verifier", now=1).code, "UNKNOWN_MESSAGE")

    def test_bad_receipt_is_terminal(self):
        receipt = self.submit()
        bad = replace(receipt.artifact, frame="local")
        self.assertEqual(self.broker.acknowledge(self.key, bad, principal="planner", now=1).code, "RECEIPT_MISMATCH")
        self.assertFalse(self.broker.acknowledge(self.key, receipt.artifact, principal="planner", now=1).ok)
        self.assertFalse(self.submit().ok)

    def test_independent_verifier_catches_adapter_fault(self):
        with patch("motionbricks.ai_handoff.adapt", return_value=Artifact("120", "m", "world", self.task.evidence.sha256)):
            receipt = self.submit()
        self.assertTrue(self.broker.acknowledge(self.key, receipt.artifact, principal="planner", now=1).ok)
        self.assertEqual(self.broker.verify(self.key, principal="verifier", now=1).code, "VERIFICATION_FAILED")
        self.assertFalse(self.broker.release(self.key, principal="publisher", now=1).ok)
        self.assertFalse(self.broker.releases)

    def test_release_rechecks_artifact(self):
        self.stage()
        # Deliberate host fault injection, not an exposed mutation API.
        self.broker._records[self.key].artifact = replace(adapt(self.message), value="12")
        self.assertEqual(self.broker.release(self.key, principal="publisher", now=1).code, "VERIFICATION_FAILED")

    def test_expiry_at_every_lifecycle_boundary(self):
        self.assertEqual(self.submit(now=30).code, "EXPIRED")
        for stage in ("DELIVERED", "ACKNOWLEDGED", "VERIFIED"):
            with self.subTest(stage=stage):
                self.setUp()
                receipt = self.stage(stage)
                if stage == "DELIVERED":
                    outcome = self.broker.acknowledge(self.key, receipt.artifact, principal="planner", now=30)
                elif stage == "ACKNOWLEDGED":
                    outcome = self.broker.verify(self.key, principal="verifier", now=30)
                else:
                    outcome = self.broker.release(self.key, principal="publisher", now=30)
                self.assertEqual(outcome.code, "EXPIRED")
                self.assertFalse(self.broker.releases)

    def test_evidence_expiry_and_clock_boundaries(self):
        t = replace(self.task, evidence=replace(self.task.evidence, valid_until=3), created_at=1)
        b = Broker([t])
        m = make_message(t).to_json()
        self.assertEqual(b.submit(m, principal="sensor", now=0).code, "NOT_YET_VALID")
        self.assertTrue(b.submit(m, principal="sensor", now=2).ok)
        self.assertEqual(b.submit(m, principal="sensor", now=1).code, "INVALID_CLOCK")
        self.assertEqual(b.submit(m, principal="sensor", now=True).code, "INVALID_CLOCK")
        self.assertEqual(b.submit(m, principal="sensor", now=3).code, "EXPIRED")

    def test_revision_change_invalidates_old_and_accepts_new(self):
        self.stage()
        self.assertTrue(self.broker.revise(self.task.task_id, 2, principal="owner", now=2).ok)
        self.assertEqual(self.broker.release(self.key, principal="publisher", now=2).code, "STALE_REVISION")
        self.assertEqual(self.submit(now=2).code, "STALE_REVISION")
        new = make_message(replace(self.task, revision=2))
        self.assertTrue(self.submit(new, now=2).ok)

    def test_cancel_at_every_stage_and_after_release(self):
        for stage in ("DELIVERED", "ACKNOWLEDGED", "VERIFIED", "RELEASED"):
            with self.subTest(stage=stage):
                self.setUp()
                self.stage(stage)
                self.assertTrue(self.broker.cancel(self.task.task_id, principal="owner", now=2).ok)
                self.assertEqual(self.submit(now=2).code, "CANCELLED")
                self.assertFalse(self.broker.release(self.key, principal="publisher", now=2).ok)
                if stage == "RELEASED":
                    self.assertEqual(len(self.broker.releases), 1)
                    self.assertEqual(len(self.broker.invalidations), 1)
                    release = self.broker.releases[0]
                    self.assertEqual(self.broker.read_release(release.release_id, principal="planner", now=2).code,
                                     "CANCELLED")
                    self.broker.cancel(self.task.task_id, principal="owner", now=2)
                    self.assertEqual(len(self.broker.invalidations), 1)

    def test_post_release_revision_and_expiry(self):
        for control in ("revision", "expiry"):
            self.setUp()
            self.stage("RELEASED")
            rid = self.broker.releases[0].release_id
            if control == "revision":
                self.broker.revise(self.task.task_id, 2, principal="owner", now=2)
            result = self.broker.read_release(rid, principal="planner", now=30 if control == "expiry" else 2)
            self.assertFalse(result.ok)
            self.assertEqual(len(self.broker.invalidations), 1)

    def test_controls_and_reads_require_host_roles(self):
        self.assertFalse(self.broker.cancel(self.task.task_id, principal="planner", now=1).ok)
        self.assertFalse(self.broker.revise(self.task.task_id, 2, principal="sensor", now=1).ok)
        for revision in (True, 1, 0, None):
            self.assertEqual(self.broker.revise(self.task.task_id, revision, principal="owner", now=1).code,
                             "INVALID_REVISION")
        self.stage("RELEASED")
        self.assertFalse(self.broker.read_release(self.broker.releases[0].release_id, principal="observer-a", now=1).ok)
        self.assertEqual(self.broker.read_release("unknown", principal="planner", now=1).code, "UNKNOWN_RELEASE")

    def test_work_delivery_and_handoff_budgets(self):
        for settings in (dict(max_work=1), dict(max_deliveries=1), dict(max_handoffs=1)):
            t = replace(self.task, **settings)
            b = Broker([t], topology="broadcast" if "max_deliveries" in settings else "directed")
            first = b.submit(make_message(t).to_json(), principal="sensor", now=1)
            if "max_handoffs" in settings:
                self.assertTrue(first.ok)
                first = b.submit(make_message(t, "m2").to_json(), principal="sensor", now=1)
            self.assertEqual(first.code, "BUDGET_EXHAUSTED")
            self.assertTrue(b.cancel(t.task_id, principal="owner", now=1).ok)
        # Exhaustion must not grow a cache for unlimited unadmitted message IDs.
        b = Broker([replace(self.task, max_work=1)])
        for n in range(100):
            b.submit(make_message(self.task, f"m{n}").to_json(), principal="sensor", now=1)
        self.assertEqual(len(b._records), 0)

    def test_broadcast_actual_deliveries_and_equal_gates(self):
        b = Broker([self.task], topology="broadcast")
        r = b.submit(self.message.to_json(), principal="sensor", now=1)
        self.assertTrue(r.ok)
        self.assertEqual([d.status for d in b.deliveries].count("IGNORED_NOT_RECIPIENT"), 3)
        self.assertEqual(b.usage(self.task.task_id)["deliveries"], 4)
        self.assertEqual({d.peer for d in b.deliveries}, set(b.peers))

    def test_exact_units_zero_and_precision_context(self):
        old_precision = getcontext().prec
        try:
            getcontext().prec = 2
            for value, unit, expected in (("120", "cm", "1.2"), ("1200", "mm", "1.2"),
                                           ("0", "cm", "0"), ("1.25", "m", "1.25"),
                                           ("999999999", "mm", "999999.999")):
                a = adapt(replace(self.message, value=value, unit=unit))
                self.assertEqual(a.value, expected)
                self.assertTrue(verify_distance(value, unit, "world", a.value, a.unit, a.frame))
        finally:
            getcontext().prec = old_precision
        with self.assertRaisesRegex(ProtocolError, "UNREPRESENTABLE_OUTPUT"):
            adapt(replace(self.message, value="0.000001", unit="mm"))

    def test_oracle_rejects_nonfinite_wrong_frame_and_unsupported_units(self):
        for args in (("NaN", "cm", "world", "1", "m", "world"),
                     ("120", "cm", "world", "120", "m", "world"),
                     ("120", "cm", "world", "1.2", "m", "local"),
                     ("120", "px", "world", "1.2", "m", "world")):
            self.assertFalse(verify_distance(*args))

    def test_host_configuration_fails_closed(self):
        for t in (replace(self.task, validator="sensor"), replace(self.task, max_work=True),
                  replace(self.task, expires_at=0), replace(self.task, recipient="absent")):
            with self.assertRaises(ValueError):
                Broker([t])
        with self.assertRaises(ValueError):
            Broker([self.task, self.task])

    def test_no_inference_imports(self):
        code = "import motionbricks.ai_handoff; import sys; assert not {'numpy', 'torch', 'tensorrt', 'warp'} & set(sys.modules)"
        subprocess.run([sys.executable, "-S", "-c", code], check=True, timeout=10)


if __name__ == "__main__":
    unittest.main()
