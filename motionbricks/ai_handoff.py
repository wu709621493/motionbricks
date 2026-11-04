"""Versioned, in-memory handoff simulation. No model, network or device calls.

The caller is a trusted, single-threaded host. `principal` and `now` are host
inputs, NOT fields taken from a model. This is not an authentication service,
process sandbox, durable broker, or physical authorization system.
"""

from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, localcontext
from hashlib import sha256
import json
from types import MappingProxyType

from .ai_handoff_verify import decimal_string, verify_distance

PROTOCOL = "handoff/1.0"
MAX_BYTES = 4096
STATES = ("CREATED", "VALIDATED", "DELIVERED", "ACKNOWLEDGED", "VERIFIED", "RELEASED")
TERMINAL = {"REJECTED", "EXPIRED", "CANCELLED", "INVALIDATED"}


class ProtocolError(ValueError):
    """A stable, machine-readable refusal code."""


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def digest(value: object) -> str:
    return sha256(canonical(value).encode()).hexdigest()


@dataclass(frozen=True)
class Evidence:
    ref: str
    value: str
    unit: str
    frame: str
    valid_until: int

    @property
    def sha256(self) -> str:
        return digest(asdict(self))


@dataclass(frozen=True)
class Task:
    task_id: str
    evidence: Evidence
    revision: int = 1
    sender: str = "sensor"
    recipient: str = "planner"
    validator: str = "verifier"
    publisher: str = "publisher"
    owner: str = "owner"
    model_version: str = "synthetic-sensor/1"
    config_version: str = "distance/1"
    created_at: int = 0
    expires_at: int = 30
    max_work: int = 100
    max_deliveries: int = 16
    max_handoffs: int = 4


@dataclass(frozen=True)
class Message:
    protocol_version: str
    task_id: str
    task_revision: int
    message_id: str
    sender: str
    recipient: str
    operation: str
    value: str
    unit: str
    coordinate_frame: str
    evidence_ref: str
    evidence_sha256: str
    model_version: str
    config_version: str

    def to_json(self) -> str:
        return canonical(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "Message":
        if not isinstance(raw, str):
            raise ProtocolError("MALFORMED_JSON")
        try:
            size = len(raw.encode("utf-8"))
        except UnicodeError:
            raise ProtocolError("MALFORMED_JSON") from None
        if size > MAX_BYTES:
            raise ProtocolError("MESSAGE_TOO_LARGE")

        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ProtocolError("DUPLICATE_JSON_KEY")
                result[key] = value
            return result

        try:
            data = json.loads(raw, object_pairs_hook=unique)
        except (ValueError, RecursionError) as exc:
            if isinstance(exc, ProtocolError):
                raise
            raise ProtocolError("MALFORMED_JSON") from None
        if not isinstance(data, dict) or set(data) != set(cls.__dataclass_fields__):
            raise ProtocolError("SCHEMA_MISMATCH")
        for key, value in data.items():
            if key == "task_revision":
                if type(value) is not int or value < 1:
                    raise ProtocolError("INVALID_REVISION")
            elif not isinstance(value, str) or not value.strip() or len(value) > 160:
                raise ProtocolError("INVALID_FIELD")
        if data["protocol_version"] != PROTOCOL:
            raise ProtocolError("UNSUPPORTED_VERSION")
        if not decimal_string(data["value"]):
            raise ProtocolError("INVALID_VALUE")
        return cls(**data)


def make_message(task: Task, message_id: str = "m1") -> Message:
    """Build a synthetic fixture, not a model inference."""
    e = task.evidence
    return Message(PROTOCOL, task.task_id, task.revision, message_id, task.sender,
                   task.recipient, "offline_analysis", e.value, e.unit, e.frame,
                   e.ref, e.sha256, task.model_version, task.config_version)


@dataclass(frozen=True)
class Artifact:
    value: str
    unit: str
    frame: str
    evidence_sha256: str
    converter_version: str = "decimal-length/1"


def adapt(message: Message) -> Artifact:
    factors = {"m": "1", "cm": "0.01", "mm": "0.001"}
    if message.unit not in factors:
        raise ProtocolError("UNSUPPORTED_UNIT")
    with localcontext() as context:
        context.prec = 32
        value = format(Decimal(message.value) * Decimal(factors[message.unit]), "f")
    # The wire contract permits six fractional places. Refuse lossy rounding.
    if "." in value:
        value = value.rstrip("0").rstrip(".")
    if not decimal_string(value):
        raise ProtocolError("UNREPRESENTABLE_OUTPUT")
    return Artifact(value, "m", message.coordinate_frame, message.evidence_sha256)


@dataclass(frozen=True)
class Receipt:
    ok: bool
    state: str
    code: str
    message_id: str | None = None
    artifact: Artifact | None = None
    duplicate: bool = False


@dataclass(frozen=True)
class Release:
    release_id: str
    task_id: str
    revision: int
    message_id: str
    artifact: Artifact
    consumer: str
    valid_until: int
    physical_execution: bool = False


@dataclass(frozen=True)
class Delivery:
    message_id: str
    peer: str
    payload_sha256: str
    status: str


@dataclass
class _Record:
    message: Message
    fingerprint: str
    state: str = "CREATED"
    artifact: Artifact | None = None
    history: list[str] = field(default_factory=lambda: ["CREATED"])
    release_id: str | None = None


class Broker:
    """Same gates for broadcast and directed topology; caller must serialize calls."""

    def __init__(self, tasks: list[Task], *, topology: str = "directed",
                 peers: tuple[str, ...] = ("planner", "observer-a", "observer-b", "observer-c")):
        if topology not in {"broadcast", "directed"} or len(set(peers)) != len(peers):
            raise ValueError("invalid topology or duplicate peers")
        if len({t.task_id for t in tasks}) != len(tasks):
            raise ValueError("duplicate task ID")
        for t in tasks:
            if (t.recipient not in peers or len({t.sender, t.recipient, t.validator,
                    t.publisher, t.owner}) != 5 or not t.task_id or not t.evidence.ref
                    or not t.evidence.frame or not decimal_string(t.evidence.value)
                    or t.evidence.unit not in {"m", "cm", "mm"}):
                raise ValueError("invalid task roles or evidence")
            for n in (t.revision, t.expires_at, t.evidence.valid_until,
                      t.max_work, t.max_deliveries, t.max_handoffs):
                if type(n) is not int or n < 1:
                    raise ValueError("invalid task limits")
            if type(t.created_at) is not int or not 0 <= t.created_at < min(t.expires_at, t.evidence.valid_until):
                raise ValueError("invalid task time")
        self._tasks = {t.task_id: t for t in tasks}
        self._records: dict[tuple[str, int, str], _Record] = {}
        self._cancelled: set[str] = set()
        self._releases: dict[str, Release] = {}
        self._invalidations: list[dict] = []
        self._deliveries: list[Delivery] = []
        self._usage = {t.task_id: dict(work=0, deliveries=0, bytes=0, handoffs=0, acknowledgements=0) for t in tasks}
        self._last_now = 0
        self.topology, self.peers = topology, tuple(peers)

    @property
    def releases(self) -> tuple[Release, ...]:
        """Historical releases; consumers must call read_release to check validity."""
        return tuple(self._releases.values())

    @property
    def invalidations(self) -> tuple[dict, ...]:
        return tuple(dict(x) for x in self._invalidations)

    @property
    def deliveries(self) -> tuple[Delivery, ...]:
        return tuple(self._deliveries)

    def usage(self, task_id: str):
        return MappingProxyType(dict(self._usage[task_id]))

    def history(self, key: tuple[str, int, str]) -> tuple[str, ...]:
        return tuple(self._records[key].history)

    def _time(self, now: int):
        if type(now) is not int or now < self._last_now:
            raise ProtocolError("INVALID_CLOCK")
        self._last_now = now

    def _charge(self, t: Task, work: int = 1, deliveries: int = 0,
                byte_count: int = 0, handoffs: int = 0):
        u = self._usage[t.task_id]
        if (u["work"] + work > t.max_work or u["deliveries"] + deliveries > t.max_deliveries
                or u["handoffs"] + handoffs > t.max_handoffs):
            raise ProtocolError("BUDGET_EXHAUSTED")
        u["work"] += work
        u["deliveries"] += deliveries
        u["bytes"] += byte_count
        u["handoffs"] += handoffs

    def _move(self, record: _Record, state: str):
        record.state = state
        record.history.append(state)
        if record.release_id and state in TERMINAL:
            self._invalidations.append(dict(release_id=record.release_id, reason=state,
                                             consumer=self._releases[record.release_id].consumer))

    def _fresh(self, message: Message, now: int):
        t = self._tasks[message.task_id]
        if t.task_id in self._cancelled:
            raise ProtocolError("CANCELLED")
        if message.task_revision != t.revision:
            raise ProtocolError("STALE_REVISION")
        if now < t.created_at:
            raise ProtocolError("NOT_YET_VALID")
        if now >= min(t.expires_at, t.evidence.valid_until):
            raise ProtocolError("EXPIRED")

    @staticmethod
    def _refusal(code: str, message_id: str | None = None) -> Receipt:
        state = {"STALE_REVISION": "INVALIDATED", "CANCELLED": "CANCELLED",
                 "EXPIRED": "EXPIRED", "INVALIDATED": "INVALIDATED"}.get(code, "REJECTED")
        return Receipt(False, state, code, message_id)

    def submit(self, raw: str, *, principal: str, now: int) -> Receipt:
        message = None
        try:
            self._time(now)
            message = Message.from_json(raw)
            t = self._tasks.get(message.task_id)
            if t is None:
                raise ProtocolError("UNKNOWN_TASK")
            self._charge(t)  # ingress, replay check, and contract check
            if principal != t.sender or message.sender != principal:
                raise ProtocolError("UNAUTHORIZED_SENDER")
            if message.operation != "offline_analysis" or message.recipient != t.recipient:
                raise ProtocolError("UNAUTHORIZED_ROUTE_OR_OPERATION")
            self._fresh(message, now)
            key = (message.task_id, message.task_revision, message.message_id)
            fingerprint = digest(asdict(message))
            if key in self._records:
                record = self._records[key]
                if record.fingerprint != fingerprint:
                    raise ProtocolError("MESSAGE_ID_CONFLICT")
                return Receipt(record.state not in TERMINAL, record.state, "DUPLICATE",
                               message.message_id, duplicate=True)
            e = t.evidence
            if (message.evidence_ref != e.ref or message.evidence_sha256 != e.sha256
                    or message.model_version != t.model_version or message.config_version != t.config_version):
                raise ProtocolError("PROVENANCE_MISMATCH")
            if message.unit not in {"m", "cm", "mm"}:
                raise ProtocolError("UNSUPPORTED_UNIT")
            if (message.value, message.unit, message.coordinate_frame) != (e.value, e.unit, e.frame):
                raise ProtocolError("EVIDENCE_MISMATCH")
            record = _Record(message, fingerprint)
            self._move(record, "VALIDATED")
            try:
                artifact = adapt(message)
                recipients = self.peers if self.topology == "broadcast" else (message.recipient,)
                payload = canonical(dict(message=asdict(message), artifact=asdict(artifact)))
                # Atomic fanout reservation; no silently truncated broadcasts.
                self._charge(t, work=1 + len(recipients), deliveries=len(recipients),
                             byte_count=len(payload.encode()) * len(recipients), handoffs=1)
            except ProtocolError:
                self._move(record, "REJECTED")
                raise
            self._records[key] = record
            record.artifact = artifact
            for peer in recipients:
                # A delivery is not semantic acceptance. Non-target peers drop it.
                status = "DELIVERED" if peer == message.recipient else "IGNORED_NOT_RECIPIENT"
                self._deliveries.append(Delivery(message.message_id, peer, digest(payload), status))
            self._move(record, "DELIVERED")
            return Receipt(True, record.state, "DELIVERED", message.message_id, artifact)
        except ProtocolError as exc:
            return self._refusal(str(exc), message.message_id if message else None)

    def _action(self, key, principal, now, expected, role, action, candidate=None):
        record = self._records.get(key)
        try:
            self._time(now)
            if record is None:
                raise ProtocolError("UNKNOWN_MESSAGE")
            t = self._tasks[record.message.task_id]
            self._charge(t)
            if principal != getattr(t, role):
                raise ProtocolError("UNAUTHORIZED_ACTOR")
            try:
                self._fresh(record.message, now)
            except ProtocolError as exc:
                if record.state not in TERMINAL:
                    self._move(record, self._refusal(str(exc)).state)
                raise
            if record.state != expected:
                raise ProtocolError("INVALID_TRANSITION")
            if action == "ACKNOWLEDGED" and candidate != record.artifact:
                self._move(record, "REJECTED")
                raise ProtocolError("RECEIPT_MISMATCH")
            if action in {"VERIFIED", "RELEASED"}:
                e, a = t.evidence, record.artifact
                if (a is None or a.evidence_sha256 != e.sha256 or a.converter_version != "decimal-length/1"
                        or not verify_distance(e.value, e.unit, e.frame, a.value, a.unit, a.frame)):
                    self._move(record, "REJECTED")
                    raise ProtocolError("VERIFICATION_FAILED")
            self._move(record, action)
            if action == "ACKNOWLEDGED":
                self._usage[t.task_id]["acknowledgements"] += 1
            if action == "RELEASED":
                rid = digest([*key, record.fingerprint])
                record.release_id = rid
                self._releases[rid] = Release(rid, t.task_id, t.revision, key[2],
                                             record.artifact, t.recipient,
                                             min(t.expires_at, t.evidence.valid_until))
            return Receipt(True, action, action, key[2], record.artifact)
        except ProtocolError as exc:
            return self._refusal(str(exc), record.message.message_id if record else None)

    def acknowledge(self, key, understood: Artifact, *, principal: str, now: int) -> Receipt:
        return self._action(key, principal, now, "DELIVERED", "recipient", "ACKNOWLEDGED", understood)

    def verify(self, key, *, principal: str, now: int) -> Receipt:
        return self._action(key, principal, now, "ACKNOWLEDGED", "validator", "VERIFIED")

    def release(self, key, *, principal: str, now: int) -> Receipt:
        return self._action(key, principal, now, "VERIFIED", "publisher", "RELEASED")

    def _control(self, task_id, principal, now, revision=None):
        try:
            self._time(now)
            t = self._tasks.get(task_id)
            if t is None:
                raise ProtocolError("UNKNOWN_TASK")
            if principal != t.owner:
                raise ProtocolError("UNAUTHORIZED_ACTOR")
            if revision is not None:
                if type(revision) is not int or revision <= t.revision:
                    raise ProtocolError("INVALID_REVISION")
                self._tasks[task_id] = replace(t, revision=revision)
                state = "INVALIDATED"
            else:
                self._cancelled.add(task_id)
                state = "CANCELLED"
            # Control is never blocked by exhausted data-plane budgets.
            for record in self._records.values():
                if record.message.task_id == task_id and record.state not in TERMINAL:
                    self._move(record, state)
            return Receipt(True, state, state)
        except ProtocolError as exc:
            return self._refusal(str(exc))

    def cancel(self, task_id: str, *, principal: str, now: int) -> Receipt:
        return self._control(task_id, principal, now)

    def revise(self, task_id: str, revision: int, *, principal: str, now: int) -> Receipt:
        if type(revision) is not int:
            return self._refusal("INVALID_REVISION")
        return self._control(task_id, principal, now, revision)

    def read_release(self, release_id: str, *, principal: str, now: int) -> Receipt:
        """Validate a historical release. Revocation cannot erase copies already read."""
        try:
            self._time(now)
            release = self._releases.get(release_id)
            if release is None:
                raise ProtocolError("UNKNOWN_RELEASE")
            if principal != release.consumer:
                raise ProtocolError("UNAUTHORIZED_ACTOR")
            key = (release.task_id, release.revision, release.message_id)
            record = self._records[key]
            try:
                self._fresh(record.message, now)
            except ProtocolError as exc:
                if record.state not in TERMINAL:
                    self._move(record, self._refusal(str(exc)).state)
                raise
            if record.state != "RELEASED":
                raise ProtocolError("INVALIDATED")
            return Receipt(True, "RELEASED", "CURRENT", release.message_id, release.artifact)
        except ProtocolError as exc:
            return self._refusal(str(exc))
