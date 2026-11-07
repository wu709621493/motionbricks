"""Behavioral checks for the offline procurement ledger; no network or GPU."""
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from motionbricks.procurement import Ledger, Policy


def concurrent_order(args):
    path, policy, key = args
    return Ledger(path, policy).execute(key, "order", "buyer", supplier="supplier",
                                        unit_price=600, fees=300, evidence="quote")


class ProcurementTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"ledger.sqlite"
        self.policy = Policy("v1", datetime.now(timezone.utc).year, "USD", "A4-pack",
                             "supplier", "owner", "buyer", "receiver", "keeper",
                             1_000_000, 50_000, 1_000, 20, 5, 2)
        self.ledger = Ledger(self.path, self.policy)

    def order(self, key="o1", **changes):
        data = dict(supplier="supplier", unit_price=600, fees=300, evidence="quote")
        data.update(changes)
        return self.ledger.execute(key, "order", "buyer", **data)

    def receive(self, quantity, key="r1"):
        return self.ledger.execute(key, "receive", "receiver", order_id="o1",
                                   quantity=quantity, evidence="delivery")

    def test_full_lifecycle_preserves_total_budget_charge(self):
        order = self.order()
        self.assertEqual(order["quantity"], 17)
        self.assertEqual(order["total"], 10500)
        self.assertEqual(self.ledger.snapshot()["committed"], 10500)
        self.receive(17)
        self.ledger.execute("s1", "settle", "owner", order_id="o1", evidence="invoice")
        state = self.ledger.snapshot()
        self.assertEqual((state["paid"], state["committed"], state["available_budget"]), (10500, 0, 989500))
        self.ledger.execute("i1", "issue", "keeper", quantity=2, recipient="employee",
                            purpose="office printing", evidence="slip")
        self.assertEqual(self.ledger.snapshot()["available_stock"], 18)
        self.assertEqual([e["payload"]["actor"] for e in self.ledger.events()],
                         ["buyer", "receiver", "owner", "keeper"])
        self.assertTrue(all(e["payload"]["data"]["evidence"] for e in self.ledger.events()))

    def test_replay_survives_restart_and_rejects_changed_payload(self):
        first = self.order()
        self.ledger = Ledger(self.path, self.policy)
        self.assertEqual(self.order(), first)
        with self.assertRaises(ValueError):
            self.order(unit_price=601)
        self.assertEqual(len(self.ledger.events()), 1)

    def test_receipt_and_issue_retries_are_idempotent(self):
        self.order()
        self.receive(10)
        self.receive(10)
        for _ in range(2):
            self.ledger.execute("i1", "issue", "keeper", quantity=2, recipient="team",
                                purpose="print", evidence="slip")
        self.assertEqual(self.ledger.snapshot()["stock"], 13)

    def test_partial_receipt_does_not_trigger_duplicate_replenishment(self):
        self.order()
        self.receive(7)
        self.assertEqual(self.ledger.snapshot()["in_transit"], 10)
        self.assertEqual(self.order("o2")["status"], "NO_ORDER")
        with self.assertRaises(ValueError):
            self.receive(11, "r2")
        with self.assertRaises(ValueError):
            self.ledger.execute("s1", "settle", "owner", order_id="o1", evidence="invoice")

    def test_cancel_releases_only_unreceived_commitment(self):
        self.order()
        self.ledger.execute("c1", "cancel", "buyer", order_id="o1", evidence="supplier-cancel")
        self.assertEqual(self.ledger.snapshot()["available_budget"], 1_000_000)
        with self.assertRaises(ValueError):
            self.receive(1)
        self.assertEqual(self.order("o2")["quantity"], 17)

    def test_received_order_cannot_be_cancelled_or_settled_twice(self):
        self.order()
        self.receive(17)
        with self.assertRaises(ValueError):
            self.ledger.execute("c1", "cancel", "buyer", order_id="o1", evidence="cancel")
        self.ledger.execute("s1", "settle", "owner", order_id="o1", evidence="invoice")
        with self.assertRaises(ValueError):
            self.ledger.execute("s2", "settle", "owner", order_id="o1", evidence="invoice")

    def test_numeric_supplier_and_quote_validation_rolls_back(self):
        before = self.ledger.snapshot()
        for change in [dict(unit_price=-1), dict(unit_price=True), dict(fees=0.5),
                       dict(supplier="unknown"), dict(unit_price=1000, fees=1),
                       dict(fees=1_000_001), dict(evidence=""), dict(extra="field")]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.order(**change)
        self.assertEqual(self.ledger.snapshot(), before)
        self.assertEqual(self.ledger.events(), [])

    def test_annual_and_order_caps_independently(self):
        for index, change in enumerate([dict(annual_budget=10499), dict(single_order_limit=10499)]):
            ledger = Ledger(Path(self.temp.name)/f"cap{index}.sqlite", replace(self.policy, **change))
            with self.assertRaises(ValueError):
                concurrent_order((ledger.path, ledger.policy, "o1"))
            self.assertEqual(ledger.snapshot()["committed"], 0)

    def test_reserved_stock_cannot_be_issued(self):
        with self.assertRaises(ValueError):
            self.ledger.execute("i1", "issue", "keeper", quantity=4, recipient="team",
                                purpose="print", evidence="slip")
        self.assertEqual(self.ledger.snapshot()["stock"], 5)

    def test_paid_orders_continue_to_consume_annual_budget(self):
        self.policy = replace(self.policy, annual_budget=11000)
        self.ledger = Ledger(Path(self.temp.name)/"limited.sqlite", self.policy)
        self.order()
        self.receive(17)
        self.ledger.execute("s1", "settle", "owner", order_id="o1", evidence="invoice")
        self.ledger.execute("i1", "issue", "keeper", quantity=2, recipient="team",
                            purpose="print", evidence="slip")
        with self.assertRaises(ValueError):
            self.order("o2")
        self.assertEqual(self.ledger.snapshot()["available_budget"], 500)
        self.assertEqual(self.ledger.snapshot()["committed"], 0)

    def test_expired_year_cannot_create_orders(self):
        policy = replace(self.policy, year=self.policy.year-1)
        ledger = Ledger(Path(self.temp.name)/"old.sqlite", policy)
        with self.assertRaises(ValueError):
            concurrent_order((ledger.path, policy, "o1"))

    def test_wrong_actor_and_policy_change_rejected(self):
        with self.assertRaises(ValueError):
            self.ledger.execute("o1", "order", "receiver", supplier="supplier",
                                unit_price=600, fees=300, evidence="quote")
        with self.assertRaises(ValueError):
            Ledger(self.path, replace(self.policy, annual_budget=2_000_000))

    def test_multiple_processes_share_atomic_inventory_and_budget(self):
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(concurrent_order,
                           [(self.path, self.policy, f"o{i}") for i in range(8)]))
        self.assertEqual(sum(r["status"] == "RESERVED" for r in results), 1)
        self.assertEqual(self.ledger.snapshot()["committed"], 10500)
        self.assertEqual(self.ledger.snapshot()["in_transit"], 17)

    def test_concurrent_retries_share_one_result(self):
        with ProcessPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(concurrent_order, [(self.path, self.policy, "o1")]*8))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(len(self.ledger.events()), 1)


if __name__ == "__main__":
    unittest.main()
