"""CPU-only crew-led countdown simulation; never issues a launch command.

Zero is a timing boundary, not consent. Caller authenticates identities and
serializes monotonic snapshots. This research prototype is not flight software.
"""
from dataclasses import dataclass
from enum import Enum
import math
from .zero_guard import divide


class Phase(str, Enum):
    HOLD = 'HOLD'
    COUNTING = 'COUNTING'
    AWAITING_CONFIRMATION = 'AWAITING_CONFIRMATION'
    REVIEW_REQUESTED = 'REVIEW_REQUESTED'
    ABORTED = 'ABORTED'


@dataclass(frozen=True)
class CrewVote:
    crew_id: str
    decision: str
    epoch: int
    timestamp_s: float


@dataclass(frozen=True)
class Snapshot:
    sequence: int
    timestamp_s: float
    ground_go: bool
    vehicle_go: bool
    votes: tuple[CrewVote, ...]


@dataclass(frozen=True)
class Decision:
    phase: Phase
    remaining_s: float
    epoch: int
    reason: str
    request_review: bool = False  # Simulation event, never launch permission.


def _finite(v):
    try:
        return type(v) in (int, float) and math.isfinite(v)
    except OverflowError:
        return False


class CrewCountdown:
    """Single-owner model with fresh unanimous GO and independent interlocks.

    HOLD freezes remaining time and changes the consent epoch. Resume is explicit.
    Crossing zero cannot confirm: a later confirmation with fresh evidence is
    required. Caller must bind confirm to an authenticated crew command.
    """
    def __init__(self, crew_ids, *, duration_s=10.0, max_age_s=0.5,
                 max_gap_s=0.5, window_end_s=60.0):
        crew_ids = tuple(crew_ids)
        if (not crew_ids or any(type(c) is not str or not c.strip() for c in crew_ids)
                or len(set(crew_ids)) != len(crew_ids)):
            raise ValueError('unique nonempty crew identities required')
        if any(not _finite(v) or v <= 0 for v in
               (duration_s, max_age_s, max_gap_s, window_end_s)):
            raise ValueError('timing configuration must be finite and positive')
        self.crew_ids = frozenset(crew_ids)
        self.duration_s = self.remaining_s = float(duration_s)
        self.max_age_s, self.max_gap_s = max_age_s, max_gap_s
        self.window_end_s = window_end_s
        self.phase, self.epoch = Phase.HOLD, 0
        self._last_time, self._sequence = None, -1
        self._gate_time = None

    def progress(self):
        return divide(self.duration_s - self.remaining_s, self.duration_s)

    def _decision(self, reason, request_review=False):
        return Decision(self.phase, self.remaining_s, self.epoch, reason, request_review)

    def _hold(self, reason):
        if self.phase != Phase.HOLD:
            self.epoch += 1
        self.phase = Phase.HOLD
        return self._decision(reason)

    def _abort(self, reason):
        self.phase = Phase.ABORTED
        self.epoch += 1
        return self._decision(reason)

    def step(self, now_s, snapshot=None, *, command='tick', crew_actor=None):
        if self.phase == Phase.ABORTED:
            return self._decision('abort latched; create a new session')
        if command == 'abort':
            return self._abort('explicit abort')
        if command == 'hold':
            return self._hold('explicit hold; review withdrawn locally')
        if command not in ('tick', 'resume', 'confirm'):
            return self._hold('unknown command')
        if command in ('resume', 'confirm') and (type(crew_actor) is not str or crew_actor not in self.crew_ids):
            return self._hold('resume/confirm requires a configured crew actor')
        if not _finite(now_s):
            return self._hold('invalid clock')
        if now_s >= self.window_end_s:
            return self._abort('simulation window expired')
        previous = self._last_time
        if previous is not None and now_s <= previous:
            return self._hold('clock did not advance')
        self._last_time = now_s
        if previous is not None and now_s - previous > self.max_gap_s:
            return self._hold('missed monitoring deadline')
        if not isinstance(snapshot, Snapshot):
            return self._hold('missing snapshot')
        if (type(snapshot.sequence) is not int or snapshot.sequence <= self._sequence
                or not _finite(snapshot.timestamp_s)
                or not 0 <= now_s - snapshot.timestamp_s <= self.max_age_s):
            return self._hold('stale, future, or replayed snapshot')
        self._sequence = snapshot.sequence
        if type(snapshot.votes) is not tuple or any(not isinstance(v, CrewVote) for v in snapshot.votes):
            return self._hold('invalid crew vote structure')
        for v in snapshot.votes:
            if type(v.crew_id) is str and v.crew_id in self.crew_ids and v.decision == 'ABORT':
                return self._abort('crew abort')
        if snapshot.ground_go is not True or snapshot.vehicle_go is not True:
            return self._hold('ground or vehicle interlock not GO')
        ids = [v.crew_id for v in snapshot.votes]
        if (any(type(i) is not str for i in ids) or len(ids) != len(self.crew_ids)
                or set(ids) != self.crew_ids):
            return self._hold('missing, duplicate, or unknown crew identity')
        for v in snapshot.votes:
            if (v.decision != 'GO' or type(v.epoch) is not int or v.epoch != self.epoch
                    or not _finite(v.timestamp_s)
                    or not 0 <= now_s - v.timestamp_s <= self.max_age_s
                    or v.timestamp_s > snapshot.timestamp_s):
                return self._hold('crew has not supplied current explicit GO')
        if self.phase == Phase.REVIEW_REQUESTED:
            return self._decision('review already requested; no repeated event')
        if self.phase == Phase.HOLD:
            if command != 'resume':
                return self._decision('explicit resume required')
            self.phase = Phase.COUNTING if self.remaining_s > 0 else Phase.AWAITING_CONFIRMATION
            if self.phase == Phase.AWAITING_CONFIRMATION:
                self._gate_time = now_s
            return self._decision('resumed with current crew GO')
        if self.phase == Phase.COUNTING:
            self.remaining_s = max(0.0, self.remaining_s - (now_s - previous))
            if self.remaining_s == 0:
                self.phase = Phase.AWAITING_CONFIRMATION
                self._gate_time = now_s
            return self._decision('time boundary reached; confirmation still required'
                                  if self.remaining_s == 0 else 'counting')
        if command == 'confirm':
            if any(v.timestamp_s <= self._gate_time for v in snapshot.votes):
                return self._decision('new crew GO after time boundary required')
            self.phase = Phase.REVIEW_REQUESTED
            return self._decision('crew-confirmed simulation review request', True)
        return self._decision('awaiting explicit confirmation')
