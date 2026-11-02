"""Experimental optical-clock/photonic experiment boundary, not a motion backend.

Only a classical dry-run implementation is supplied. No device SDK, optical clock,
entangled photons, cryptographic randomness or quantum acceleration is provided.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random
import re
from typing import Protocol


class HardwareUnavailable(RuntimeError):
    pass


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be a nonempty string')


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f'{name} must be an integer >= {minimum}')


@dataclass(frozen=True)
class ClockReading:
    source_id: str
    time_scale: str  # TAI or a named local oscillator timescale; no implicit UTC conversion
    epoch: str
    ticks: int
    tick_period_seconds: str  # Decimal string, preserving sub-nanosecond precision
    uncertainty_seconds: str  # Standard uncertainty (k=1), not timestamp resolution
    calibration_id: str
    evidence: str  # SIMULATED or DEVICE_REPORTED; neither is independent verification

    def __post_init__(self):
        from decimal import Decimal, InvalidOperation
        for name in ('source_id', 'time_scale', 'epoch', 'calibration_id'):
            _text(getattr(self, name), name)
        _integer(self.ticks, 'ticks')
        for name in ('tick_period_seconds', 'uncertainty_seconds'):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise ValueError(f'{name} must be a decimal string')
            try:
                number = Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f'invalid {name}') from exc
            if not number.is_finite() or number < 0 or (name == 'tick_period_seconds' and number == 0):
                raise ValueError(f'invalid {name}')
        if self.evidence not in ('SIMULATED', 'DEVICE_REPORTED'):
            raise ValueError('invalid clock evidence')


@dataclass(frozen=True)
class PairRequest:
    request_id: str
    artifact_sha256: str  # Existing CPU model or experiment artifact identity
    shots: int = 100
    basis: str = 'ZZ'  # A narrow initial two-channel measurement contract

    def __post_init__(self):
        _text(self.request_id, 'request_id')
        if not isinstance(self.artifact_sha256, str) or not re.fullmatch('[0-9a-f]{64}', self.artifact_sha256):
            raise ValueError('artifact_sha256 must be lowercase SHA-256 hex')
        _integer(self.shots, 'shots', 1)
        if self.shots > 1000000:
            raise ValueError('shots exceeds interface limit')
        if self.basis != 'ZZ':
            raise ValueError('only ZZ pair sampling is specified in v0.1')


@dataclass(frozen=True)
class PairResult:
    request_id: str
    artifact_sha256: str
    basis: str
    counts: tuple[int, int, int, int]  # 00, 01, 10, 11 in that order
    rejected_shots: int
    clock: ClockReading  # Acquisition-start reading, not a timestamp per photon
    backend_id: str
    evidence: str
    raw_record_sha256: str | None = None

    def validate(self, request):
        if (self.request_id, self.artifact_sha256, self.basis) != (
                request.request_id, request.artifact_sha256, request.basis):
            raise ValueError('response does not match request')
        if not isinstance(self.counts, tuple) or len(self.counts) != 4:
            raise ValueError('counts must be a four-element tuple')
        for count in self.counts:
            _integer(count, 'count')
        _integer(self.rejected_shots, 'rejected_shots')
        if sum(self.counts) + self.rejected_shots != request.shots:
            raise ValueError('accepted plus rejected shots must equal requested shots')
        if not isinstance(self.clock, ClockReading):
            raise ValueError('clock must be ClockReading')
        _text(self.backend_id, 'backend_id')
        if self.evidence not in ('SIMULATED', 'DEVICE_REPORTED'):
            raise ValueError('invalid sampling evidence')
        if self.evidence == 'DEVICE_REPORTED' and self.clock.evidence != 'DEVICE_REPORTED':
            raise ValueError('device result requires device-reported clock evidence')
        if self.raw_record_sha256 is not None and (
                not isinstance(self.raw_record_sha256, str)
                or not re.fullmatch('[0-9a-f]{64}', self.raw_record_sha256)):
            raise ValueError('invalid raw record hash')
        if self.evidence == 'DEVICE_REPORTED' and self.raw_record_sha256 is None:
            raise ValueError('device result requires raw acquisition record hash')


class OpticalClock(Protocol):
    def read(self) -> ClockReading: ...
    def close(self) -> None: ...


class PhotonicPairSampler(Protocol):
    def sample(self, request: PairRequest, *, timeout_seconds: float) -> PairResult: ...
    def close(self) -> None: ...


class SimulatedClock:
    """Deterministic fixed reading for offline tests, NOT host/optical time."""
    def __init__(self):
        self.closed = False

    def read(self):
        if self.closed:
            raise RuntimeError('clock is closed')
        return ClockReading('simulated-clock', 'SIMULATED_LOCAL', 'fixture-origin',
                            0, '1e-15', '1e-12', 'not-calibrated', 'SIMULATED')

    def close(self):
        self.closed = True


class SimulatedPairSampler:
    """Classical correlated-bit fixture. ZZ correlation is NOT entanglement proof.

    The injected clock is borrowed, and must be closed by its owner.
    A fresh seeded PRNG per request makes retries independent of request order.
    """
    def __init__(self, clock: OpticalClock, *, seed=0):
        _integer(seed, 'seed')
        self.clock = clock
        self.seed = seed
        self.closed = False

    def sample(self, request, *, timeout_seconds=1.0):
        if self.closed:
            raise RuntimeError('sampler is closed')
        if not isinstance(request, PairRequest):
            raise ValueError('request must be PairRequest')
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or timeout_seconds <= 0):
            raise ValueError('timeout_seconds must be finite and positive')
        # This mock has no transport and no wait; hardware adapters must enforce timeout.
        identity = json.dumps([self.seed, asdict(request)], sort_keys=True).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(identity).digest(), 'big'))
        zeros = sum(rng.getrandbits(1) == 0 for _ in range(request.shots))
        result = PairResult(request.request_id, request.artifact_sha256, request.basis,
                            (zeros, 0, 0, request.shots - zeros), 0, self.clock.read(),
                            'classical-correlated-bits-v1', 'SIMULATED')
        result.validate(request)
        return result

    def close(self):
        self.closed = True


def open_hardware(*args, **kwargs):
    raise HardwareUnavailable('No optical-clock or photonic hardware adapter is installed; no fallback')


def sampling_statistics(request: PairRequest, result: PairResult):
    """Opt-in descriptive statistics; no accepted shots means no correlation.

    Keeps report() schema/hash stable. ZZ correlation is not entanglement proof.
    """
    from .zero_guard import divide
    result.validate(request)
    a, b, c, d = result.counts
    accepted = a + b + c + d
    return {'accepted_shots': accepted,
            'acceptance_fraction': asdict(divide(accepted, request.shots)),
            'zz_correlation': asdict(divide(a + d - b - c, accepted,
                                           policy='undefined')),
            'entanglement_verification': 'NOT_PERFORMED'}


def report(request: PairRequest, result: PairResult):
    """Bind a measurement record to an artifact; a hash does not authenticate it."""
    result.validate(request)
    record = {'schema_version': 1, 'request': asdict(request), 'result': asdict(result),
              'entanglement_verification': 'NOT_PERFORMED',
              'motion_inference': 'NOT_PERFORMED', 'quantum_advantage': 'NOT_TESTED'}
    encoded = json.dumps(record, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return dict(record, record_sha256=hashlib.sha256(encoded).hexdigest())


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('simulate', 'hardware'), required=True)
    parser.add_argument('--artifact-sha256', required=True)
    parser.add_argument('--request-id', default='offline-example')
    parser.add_argument('--shots', type=int, default=100)
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args()
    try:
        request = PairRequest(args.request_id, args.artifact_sha256, args.shots)
        if args.mode == 'hardware':
            open_hardware()
        clock = SimulatedClock()
        sampler = SimulatedPairSampler(clock, seed=args.seed)
        try:
            print(json.dumps(report(request, sampler.sample(request)), indent=2))
        finally:
            sampler.close()
            clock.close()
        return 0
    except HardwareUnavailable as exc:
        print(json.dumps({'status': 'BLOCKED', 'error': str(exc)}))
        return 2
    except ValueError as exc:
        print(json.dumps({'status': 'FAILED', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
