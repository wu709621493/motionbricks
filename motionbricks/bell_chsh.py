"""Offline CHSH audit prototype; simulations cannot verify physical entanglement."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import itertools
import json
import math
import random
import time
from typing import Protocol

from .optical_quantum import ClockReading, OpticalClock, PairRequest, HardwareUnavailable

CELLS = ((0, 0), (0, 1), (1, 0), (1, 1))
SIGNS = (1, 1, 1, -1)
# Rows Alice, columns Bob; zero means no click, not a binary outcome.
OUTCOMES = tuple(itertools.product((1, -1, 0), repeat=2))
MODELS = ('CLASSICAL_LHV', 'IDEAL_BELL_PROBABILITY')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be integer >= {minimum}')


def finite(value, name):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f'{name} must be finite numeric')


@dataclass(frozen=True)
class CHSHRequest:
    request_id: str
    artifact_sha256: str
    # Bloch angles in radians: observable cos(theta) Z + sin(theta) X.
    alice: tuple[float, float] = (0.0, math.pi / 2)
    bob: tuple[float, float] = (math.pi / 4, -math.pi / 4)
    shots: tuple[int, int, int, int] = (1000, 1000, 1000, 1000)
    alpha: float = 0.05

    def __post_init__(self):
        PairRequest(self.request_id, self.artifact_sha256)  # shared identity contract
        for name in ('alice', 'bob'):
            angles = getattr(self, name)
            if type(angles) is not tuple or len(angles) != 2:
                raise ValueError(f'{name} requires two angles')
            for angle in angles:
                finite(angle, name)
                if abs(angle) > 2 * math.pi:
                    raise ValueError('angles must be within [-2pi, 2pi]')
        if type(self.shots) is not tuple or len(self.shots) != 4:
            raise ValueError('four shot quotas required')
        for n in self.shots:
            integer(n, 'shots', 1)
            if n > 250000:
                raise ValueError('maximum 250000 shots per cell')
        finite(self.alpha, 'alpha')
        if not 0 < self.alpha < 1:
            raise ValueError('alpha must be in (0,1)')


@dataclass(frozen=True)
class Simulation:
    model: str = 'CLASSICAL_LHV'
    local_detection_attack: bool = False
    seed: int = 0
    flip_probability: float = 0.0  # independent local bit flips
    loss_probability: float = 0.0  # independent local no-clicks
    selective_rejection: float = 0.0  # discard CHSH-losing coincidences diagnostically

    def __post_init__(self):
        if self.model not in MODELS:
            raise ValueError('unknown simulation model')
        if type(self.local_detection_attack) is not bool:
            raise ValueError('local_detection_attack must be boolean')
        if self.local_detection_attack and self.model != 'CLASSICAL_LHV':
            raise ValueError('local detection attack is a classical control only')
        integer(self.seed, 'seed')
        for name in ('flip_probability', 'loss_probability', 'selective_rejection'):
            p = getattr(self, name)
            finite(p, name)
            if not 0 <= p <= 1:
                raise ValueError(f'{name} must be in [0,1]')


@dataclass(frozen=True)
class CellCounts:
    # ALL trials are retained here, including no-click and later rejected events.
    raw: tuple[int, ...]
    selected_out: tuple[int, ...]

    def validate(self, shots):
        for counts in (self.raw, self.selected_out):
            if type(counts) is not tuple or len(counts) != 9:
                raise ValueError('nine outcome bins required')
            for count in counts:
                integer(count, 'count')
        if sum(self.raw) != shots:
            raise ValueError('raw count conservation failed')
        if any(r > n for r, n in zip(self.selected_out, self.raw)):
            raise ValueError('rejected counts exceed raw counts')


@dataclass(frozen=True)
class CHSHResult:
    request_sha256: str
    cells: tuple[CellCounts, ...]
    clock: ClockReading
    backend_id: str
    evidence: str
    raw_record_sha256: str
    simulation: Simulation | None = None

    def validate(self, request):
        if self.request_sha256 != digest(asdict(request)):
            raise ValueError('request mismatch')
        if type(self.cells) is not tuple or len(self.cells) != 4:
            raise ValueError('four cells required')
        for cell, n in zip(self.cells, request.shots):
            if not isinstance(cell, CellCounts):
                raise ValueError('invalid cell')
            cell.validate(n)
        if not isinstance(self.clock, ClockReading):
            raise ValueError('ClockReading required')
        if not isinstance(self.backend_id, str) or not self.backend_id.strip():
            raise ValueError('backend identity required')
        PairRequest('raw-record', self.raw_record_sha256)
        if self.evidence in MODELS:
            if (not isinstance(self.simulation, Simulation)
                    or self.simulation.model != self.evidence
                    or self.clock.evidence != 'SIMULATED'):
                raise ValueError('simulation provenance mismatch')
        elif self.evidence == 'DEVICE_REPORTED':
            if self.simulation is not None or self.clock.evidence != 'DEVICE_REPORTED':
                raise ValueError('invalid device provenance')
        else:
            raise ValueError('unknown evidence class')


class CHSHSampler(Protocol):
    """Adapters must enforce timeout, preserve every trial and supply raw records."""
    def sample(self, request: CHSHRequest, *, timeout_seconds: float) -> CHSHResult: ...
    def close(self) -> None: ...


# Uniform mixture over the eight deterministic strategies on the +2 facet.
# Each strategy has all four predetermined local responses, independent of settings.
LHV_STRATEGIES = tuple(t for t in itertools.product((-1, 1), repeat=4)
                      if t[0]*t[2] + t[0]*t[3] + t[1]*t[2] - t[1]*t[3] == 2)


def bell_probabilities(a, b):
    """Phi+ joint probabilities for (++,+-,-+,--); Bloch, not polarizer, angles."""
    finite(a, 'angle'); finite(b, 'angle')
    e = math.cos(a - b)
    return ((1+e)/4, (1-e)/4, (1-e)/4, (1+e)/4)


class SimulatedCHSHSampler:
    """Borrowed clock. Independent deterministic random streams per cell and mechanism."""
    def __init__(self, clock: OpticalClock, simulation=Simulation()):
        if not isinstance(simulation, Simulation):
            raise ValueError('Simulation required')
        self.clock, self.simulation, self.closed = clock, simulation, False

    def close(self):
        self.closed = True

    def sample(self, request, *, timeout_seconds=30.0):
        if self.closed:
            raise RuntimeError('sampler closed')
        if not isinstance(request, CHSHRequest):
            raise ValueError('CHSHRequest required')
        finite(timeout_seconds, 'timeout')
        if timeout_seconds <= 0:
            raise ValueError('positive timeout required')
        deadline = time.monotonic() + timeout_seconds
        if self.clock.read().evidence != 'SIMULATED':
            raise ValueError('simulated sampler requires simulated clock')
        clock = self.clock.read()
        cfg = self.simulation
        cells, raw_hash = [], hashlib.sha256()
        for k, ((x, y), n) in enumerate(zip(CELLS, request.shots)):
            # Separate streams prevent changes in rejection/noise from changing ideal trials.
            streams = [random.Random(int(digest([cfg.model, cfg.seed, k, label]), 16))
                       for label in ('source', 'noise', 'loss', 'selection')]
            source, noise, loss, selection = streams
            counts, rejected = [0]*9, [0]*9
            e = math.cos(request.alice[x] - request.bob[y])
            for trial in range(n):
                if trial % 1024 == 0 and time.monotonic() >= deadline:
                    raise TimeoutError('CHSH simulation deadline exceeded; no partial report')
                gx = gy = None
                if cfg.local_detection_attack:
                    # Shared lambda=(gx,gy,a,b), independent of actual settings.
                    # Each detector uses ONLY its own setting and lambda.
                    gx, gy = source.randrange(2), source.randrange(2)
                    a = source.choice((-1, 1))
                    b = a * (-1 if gx == gy == 1 else 1)
                elif cfg.model == 'CLASSICAL_LHV':
                    t = source.choice(LHV_STRATEGIES)
                    a, b = t[x], t[2+y]
                else:
                    a = source.choice((-1, 1))
                    b = a if source.random() < (1+e)/2 else -a
                a *= -1 if noise.random() < cfg.flip_probability else 1
                b *= -1 if noise.random() < cfg.flip_probability else 1
                a = 0 if loss.random() < cfg.loss_probability else a
                b = 0 if loss.random() < cfg.loss_probability else b
                if cfg.local_detection_attack:
                    a = a if x == gx else 0
                    b = b if y == gy else 0
                discard = (a*b == -SIGNS[k] and selection.random() < cfg.selective_rejection)
                index = OUTCOMES.index((a, b))
                counts[index] += 1
                rejected[index] += int(discard)
                raw_hash.update(canonical([k, trial, a, b, bool(discard)]) + b'\n')
            cells.append(CellCounts(tuple(counts), tuple(rejected)))
        if time.monotonic() >= deadline:
            raise TimeoutError('CHSH simulation deadline exceeded; no partial report')
        result = CHSHResult(digest(asdict(request)), tuple(cells), clock,
                            'offline-chsh-v1', cfg.model, raw_hash.hexdigest(), cfg)
        result.validate(request)
        return result


def statistics(counts, alpha, *, coincidences=False):
    """Independent fixed-size bounded samples; never a device/memory-robust p-value."""
    finite(alpha, 'alpha')
    if not 0 < alpha < 1 or len(counts) != 4:
        raise ValueError('four cells and alpha in (0,1) required')
    correlations, sizes, variances = [], [], []
    for bins in counts:
        CellCounts(tuple(bins), (0,)*9).validate(sum(bins))
        terms = [(n, (a or 1)*(b or 1)) for (a, b), n in zip(OUTCOMES, bins)
                 if not coincidences or a*b != 0]
        n = sum(count for count, _ in terms)
        sizes.append(n)
        if not n:
            return {'status': 'INSUFFICIENT_DATA', 'correlations': None,
                    'signed_S': None, 'abs_S': None, 'confidence_interval': None}
        e = sum(count*p for count, p in terms)/n
        correlations.append(e)
        variances.append((1-e*e)/(n-1) if n > 1 else None)
    s = sum(sign*e for sign, e in zip(SIGNS, correlations))
    # Weighted Hoeffding: sum ranges^2 = 4 sum_k 1/n_k.
    radius = math.sqrt(2 * sum(1/n for n in sizes) * math.log(2/alpha))
    lo, hi = max(-4., s-radius), min(4., s+radius)
    return {'status': 'OK', 'correlations': correlations, 'sample_sizes': sizes,
            'signed_S': s, 'abs_S': abs(s),
            'standard_error': (math.sqrt(sum(variances))
                               if all(v is not None for v in variances) else None),
            'confidence_interval': [lo, hi], 'alpha': alpha,
            'method': 'TWO_SIDED_WEIGHTED_HOEFFDING_INDEPENDENT_TRIALS',
            'interval_excludes_local_range': lo > 2 or hi < -2}


def report(request, result):
    result.validate(request)
    primary = statistics([c.raw for c in result.cells], request.alpha)
    diagnostic = statistics([tuple(n-r for n, r in zip(c.raw, c.selected_out))
                             for c in result.cells], request.alpha, coincidences=True)
    audit = []
    for cell in result.cells:
        no_click = sum(n for (a, b), n in zip(OUTCOMES, cell.raw) if a*b == 0)
        selected_click = sum(n for (a, b), n in zip(OUTCOMES, cell.selected_out) if a*b != 0)
        accepted = sum(cell.raw) - no_click - selected_click
        audit.append({'attempted': sum(cell.raw), 'no_click': no_click,
                      'selected_out': sum(cell.selected_out),
                      'accepted_coincidences': accepted,
                      'rejected_union': no_click + selected_click})
    record = {'schema_version': 1, 'request': asdict(request), 'result': asdict(result),
              'outcome_order': OUTCOMES, 'audit': audit,
              'primary_all_trials_no_click_plus_one': primary,
              'postselected_diagnostic_not_evidence': diagnostic,
              'statistical_scope': 'IID_FIXED_QUOTAS_ONLY; NOT_MEMORY_ROBUST',
              'entanglement_verification': 'NOT_PERFORMED',
              'device_measurement': result.evidence == 'DEVICE_REPORTED',
              'quantum_advantage': 'NOT_TESTED',
              'warning': 'Intervals quantify sampling error, not selection bias or physical validity.'}
    return dict(record, record_sha256=digest(record))


def open_hardware(*args, **kwargs):
    raise HardwareUnavailable('No CHSH hardware adapter installed; no simulation fallback')
