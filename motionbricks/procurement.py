"""Offline, single-SKU annual procurement ledger. No purchasing/payment adapters.

Amounts are integer minor currency units. Identity labels must come from a trusted
caller; this reference implementation does not authenticate people.
"""

from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import sqlite3


def integer(value, name, minimum=0):
    if type(value) is not int or not minimum <= value <= 10**12:
        raise ValueError(f"{name}: expected integer in [{minimum}, 10^12]")


def label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 256:
        raise ValueError("expected nonempty label of at most 256 characters")


@dataclass(frozen=True)
class Policy:
    version: str
    year: int
    currency: str
    sku: str
    supplier: str
    budget_owner: str
    buyer: str
    receiver: str
    keeper: str
    annual_budget: int
    single_order_limit: int
    landed_unit_limit: int
    target_stock: int
    initial_stock: int = 0
    reserved_stock: int = 0

    def __post_init__(self):
        for field in ("version", "currency", "sku", "supplier", "budget_owner",
                      "buyer", "receiver", "keeper"):
            label(getattr(self, field))
        for field in ("annual_budget", "single_order_limit", "landed_unit_limit",
                      "target_stock", "initial_stock", "reserved_stock"):
            integer(getattr(self, field), field)
        integer(self.year, "year", 1)
        if self.year > 9999 or self.reserved_stock > self.initial_stock:
            raise ValueError("invalid year or initial reservation")


class Ledger:
    """Durable local SQLite ledger; each call uses its own serialized transaction.

    One database = one policy, SKU, currency and budget year. Opening it with a
    different policy fails rather than silently resetting its budget or stock.
    """

    def __init__(self, path, policy):
        self.path, self.policy = str(path), policy
        if self.path == ":memory:":
            raise ValueError("use a file-backed database")
        encoded = json.dumps(asdict(policy), sort_keys=True)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS config (id INTEGER PRIMARY KEY CHECK(id=1), policy TEXT, stock INTEGER)")
            db.execute("CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, quantity INTEGER, total INTEGER, received INTEGER DEFAULT 0, settled INTEGER DEFAULT 0, cancelled INTEGER DEFAULT 0)")
            db.execute("CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, request_id TEXT UNIQUE, payload TEXT, result TEXT, occurred_at TEXT)")
            row = db.execute("SELECT policy FROM config WHERE id=1").fetchone()
            if row and row[0] != encoded:
                raise ValueError("policy mismatch: migration requires review")
            if not row:
                db.execute("INSERT INTO config VALUES (1, ?, ?)", (encoded, policy.initial_stock))

    def _connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def _snapshot(self, db):
        stock = db.execute("SELECT stock FROM config WHERE id=1").fetchone()[0]
        paid, committed, transit = db.execute(
            "SELECT COALESCE(SUM(CASE WHEN settled=1 THEN total ELSE 0 END),0), "
            "COALESCE(SUM(CASE WHEN settled=0 THEN total ELSE 0 END),0), "
            "COALESCE(SUM(quantity-received),0) FROM orders WHERE cancelled=0"
        ).fetchone()
        return dict(stock=stock, available_stock=stock-self.policy.reserved_stock,
                    in_transit=transit, paid=paid, committed=committed,
                    available_budget=self.policy.annual_budget-paid-committed)

    def snapshot(self):
        with closing(self._connect()) as db, db:
            db.execute("BEGIN")
            return self._snapshot(db)

    def events(self):
        with closing(self._connect()) as db:
            return [dict(sequence=row[0], request_id=row[1], payload=json.loads(row[2]),
                         result=json.loads(row[3]), occurred_at=row[4])
                    for row in db.execute("SELECT * FROM events ORDER BY seq")]

    def execute(self, request_id, action, actor, **data):
        """Apply a simulated action, with payload-bound idempotency across restarts.

        order: supplier, unit_price, fees (tax + shipping), evidence (quote ref)
        receive: order_id, quantity (accepted usable packs), evidence
        issue: quantity, recipient, purpose, evidence
        settle: order_id, evidence (simulated invoice/payment ref)
        cancel: order_id, evidence
        All amounts use the policy's currency; pack size is part of the fixed SKU.
        """
        label(request_id)
        label(actor)
        roles = {"order": self.policy.buyer, "receive": self.policy.receiver,
                 "issue": self.policy.keeper, "settle": self.policy.budget_owner,
                 "cancel": self.policy.buyer}
        if action not in roles or actor != roles[action]:
            raise ValueError("action or responsible actor is outside policy")
        expected = {
            "order": {"supplier", "unit_price", "fees", "evidence"},
            "receive": {"order_id", "quantity", "evidence"},
            "issue": {"quantity", "recipient", "purpose", "evidence"},
            "settle": {"order_id", "evidence"},
            "cancel": {"order_id", "evidence"},
        }
        if set(data) != expected[action]:
            raise ValueError("unexpected or missing action fields")
        for key, value in data.items():
            if key in {"quantity", "unit_price", "fees"}:
                integer(value, key, 0 if key == "fees" else 1)
            else:
                label(value)
        payload = json.dumps(dict(action=action, actor=actor, policy=self.policy.version,
                                  data=data), sort_keys=True)
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT payload, result FROM events WHERE request_id=?", (request_id,)).fetchone()
            if prior:
                if prior[0] != payload:
                    raise ValueError("idempotency key reused with different payload")
                return json.loads(prior[1])
            state = self._snapshot(db)
            if action == "order":
                if datetime.now(timezone.utc).year != self.policy.year:
                    raise ValueError("budget year expired or not yet active")
                if data["supplier"] != self.policy.supplier:
                    raise ValueError("supplier outside policy")
                quantity = max(0, self.policy.target_stock-state["available_stock"]-state["in_transit"])
                total = quantity*data["unit_price"]+data["fees"]
                if quantity == 0:
                    result = dict(status="NO_ORDER", quantity=0, total=0)
                else:
                    if (total > state["available_budget"] or
                        total > self.policy.single_order_limit or
                        total > quantity*self.policy.landed_unit_limit):
                        raise ValueError("quote exceeds budget, order or landed-unit limit; review required")
                    db.execute("INSERT INTO orders(id,quantity,total) VALUES (?,?,?)", (request_id, quantity, total))
                    result = dict(status="RESERVED", order_id=request_id, quantity=quantity, total=total)
            elif action == "issue":
                if data["quantity"] > state["available_stock"]:
                    raise ValueError("insufficient unreserved stock")
                db.execute("UPDATE config SET stock=stock-? WHERE id=1", (data["quantity"],))
                result = dict(status="ISSUED", quantity=data["quantity"])
            else:
                order = db.execute("SELECT quantity,total,received,settled,cancelled FROM orders WHERE id=?", (data["order_id"],)).fetchone()
                if order is None or order[4]:
                    raise ValueError("unknown or cancelled order")
                quantity, total, received, settled, _ = order
                if action == "receive":
                    if data["quantity"] > quantity-received:
                        raise ValueError("receipt exceeds outstanding quantity")
                    db.execute("UPDATE orders SET received=received+? WHERE id=?", (data["quantity"], data["order_id"]))
                    db.execute("UPDATE config SET stock=stock+? WHERE id=1", (data["quantity"],))
                elif action == "settle":
                    if received != quantity or settled:
                        raise ValueError("settlement requires complete receipt and unsettled order")
                    db.execute("UPDATE orders SET settled=1 WHERE id=?", (data["order_id"],))
                else:
                    if received or settled:
                        raise ValueError("received or settled orders require manual reconciliation")
                    db.execute("UPDATE orders SET cancelled=1 WHERE id=?", (data["order_id"],))
                result = dict(status={"receive": "RECEIVED", "settle": "SETTLED", "cancel": "CANCELLED"}[action], order_id=data["order_id"])
            db.execute("INSERT INTO events(request_id,payload,result,occurred_at) VALUES (?,?,?,?)",
                       (request_id, payload, json.dumps(result, sort_keys=True), datetime.now(timezone.utc).isoformat()))
            return result


def demo():
    """Use a temporary database only; print a reproducible illustrative lifecycle."""
    from pathlib import Path
    from tempfile import TemporaryDirectory
    policy = Policy("a4-v1", datetime.now(timezone.utc).year, "USD", "A4-80gsm-500-sheet-pack",
                    "approved-supplier", "budget-owner", "procurement-owner",
                    "receiver", "warehouse-keeper", 1_000_000, 50_000, 1_000, 20, 5)
    with TemporaryDirectory() as folder:
        ledger = Ledger(Path(folder)/"demo.sqlite", policy)
        order = ledger.execute("order-1", "order", "procurement-owner", supplier=policy.supplier,
                               unit_price=600, fees=300, evidence="fictional-quote-1")
        ledger.execute("receipt-1", "receive", "receiver", order_id="order-1",
                       quantity=order["quantity"], evidence="fictional-delivery-1")
        ledger.execute("settlement-1", "settle", "budget-owner", order_id="order-1", evidence="fictional-invoice-1")
        ledger.execute("issue-1", "issue", "warehouse-keeper", quantity=2,
                       recipient="office-team", purpose="printing", evidence="fictional-issue-slip-1")
        print(json.dumps(dict(simulation_only=True, currency=policy.currency,
                              snapshot=ledger.snapshot(), events=ledger.events()), indent=2))


if __name__ == "__main__":
    demo()
