"""500-atom BEC research interface; only classical population fixtures supplied."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import random
import re
from typing import Protocol

from .optical_quantum import ClockReading, HardwareUnavailable, OpticalClock


def _integer(value, name, low=0, high=500):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{name} must be an integer in [{low}, {high}]')


def _text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{name} must be nonempty text')


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('expected lowercase SHA-256 hex')


def _record(payload):
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return dict(payload, record_sha256=hashlib.sha256(encoded).hexdigest())


@dataclass(frozen=True)
class BECRequest:
    request_id: str
    artifact_sha256: str
    shots: int = 10
    atom_count: int = 500  # Requested loading, not a certified measured population
    species: str = 'Rb-87'  # Explicit initial research fixture choice
    operation: str = 'two_mode_population'
    preparation_id: str = 'unvalidated-bec-preparation'

    def __post_init__(self):
        _text(self.request_id, 'request_id')
        _text(self.preparation_id, 'preparation_id')
        _hash(self.artifact_sha256)
        _integer(self.atom_count, 'atom_count', 500, 500)
        _integer(self.shots, 'shots', 1, 4096)
        if self.species != 'Rb-87' or self.operation != 'two_mode_population':
            raise ValueError('v0.1 specifies Rb-87 two-mode population readout only')


@dataclass(frozen=True)
class PopulationShot:
    loaded_atoms: int
    mode_0: int
    mode_1: int
    lost_atoms: int

    def __post_init__(self):
        for name in ('loaded_atoms', 'mode_0', 'mode_1', 'lost_atoms'):
            _integer(getattr(self, name), name)
        if self.mode_0 + self.mode_1 + self.lost_atoms != self.loaded_atoms:
            raise ValueError('mode populations plus loss must equal loaded atoms')


@dataclass(frozen=True)
class BECResult:
    request_id: str
    artifact_sha256: str
    species: str
    operation: str
    preparation_id: str
    populations: tuple[PopulationShot, ...]
    rejected_shots: int
    clock: ClockReading  # Acquisition-start, shared with the optical interface
    backend_id: str
    evidence: str
    raw_record_sha256: str | None = None

    def validate(self, request):
        if not isinstance(request, BECRequest):
            raise ValueError('expected BECRequest')
        for name in ('request_id', 'artifact_sha256', 'species', 'operation', 'preparation_id'):
            if getattr(self, name) != getattr(request, name):
                raise ValueError(f'response {name} does not match request')
        if not isinstance(self.populations, tuple) or not all(
                isinstance(p, PopulationShot) for p in self.populations):
            raise ValueError('populations must be a tuple of PopulationShot')
        _integer(self.rejected_shots, 'rejected_shots', 0, request.shots)
        if len(self.populations) + self.rejected_shots != request.shots:
            raise ValueError('accepted plus rejected shots must equal requested shots')
        if not isinstance(self.clock, ClockReading):
            raise ValueError('expected shared ClockReading')
        _text(self.backend_id, 'backend_id')
        if self.evidence not in ('SIMULATED', 'DEVICE_REPORTED'):
            raise ValueError('unsupported evidence label')
        if self.raw_record_sha256 is not None:
            _hash(self.raw_record_sha256)
        if self.evidence == 'DEVICE_REPORTED' and (
                self.clock.evidence != 'DEVICE_REPORTED' or self.raw_record_sha256 is None):
            raise ValueError('device acquisition requires device clock and raw-record hash')


class ColdAtomBackend(Protocol):
    def sample(self, request: BECRequest, *, timeout_seconds: float) -> BECResult: ...
    def close(self) -> None: ...


class SimulatedBEC500:
    """Classical binomial population fixture, NOT BEC dynamics or 500 qubits.

    Borrows the clock; callers serialize use/close. No SDK or network is loaded.
    """
    def __init__(self, clock: OpticalClock, *, seed=0):
        _integer(seed, 'seed', 0, 2**64 - 1)
        self.clock, self.seed, self.closed = clock, seed, False

    def sample(self, request, *, timeout_seconds=1.0):
        if self.closed:
            raise RuntimeError('cold-atom backend is closed')
        if not isinstance(request, BECRequest):
            raise ValueError('expected BECRequest')
        if (type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds)
                or timeout_seconds <= 0):
            raise ValueError('timeout_seconds must be finite and positive')
        # A transport-free mock validates the parameter, not a hard runtime deadline.
        identity = json.dumps(['bec500-v1', self.seed, asdict(request)], sort_keys=True).encode()
        rng = random.Random(int.from_bytes(hashlib.sha256(identity).digest(), 'big'))
        clock = self.clock.read()
        populations = []
        for _ in range(request.shots):
            n0 = sum(rng.getrandbits(1) for _ in range(500))
            populations.append(PopulationShot(500, n0, 500 - n0, 0))
        result = BECResult(request.request_id, request.artifact_sha256, request.species,
                           request.operation, request.preparation_id, tuple(populations), 0,
                           clock, 'classical-binomial-bec500-v1', 'SIMULATED')
        result.validate(request)
        return result

    def close(self):
        self.closed = True


def open_hardware(*args, **kwargs):
    raise HardwareUnavailable('No cold-atom/BEC device adapter is installed; no fallback')


def report(request: BECRequest, result: BECResult):
    result.validate(request)
    return _record({'schema_version': 1, 'request': asdict(request), 'result': asdict(result),
                    'condensation_verification': 'NOT_PERFORMED',
                    'entanglement_verification': 'NOT_PERFORMED',
                    'motion_inference': 'NOT_PERFORMED', 'quantum_advantage': 'NOT_TESTED'})


def link_experiments(pair_request, pair_result, bec_request, bec_result, *, cpu_report=None):
    """Validate and link records; does not execute, synchronize or entangle devices.

    cpu_report is one CPUReference.run() report, not the outer CLI runs wrapper.
    All evidence is declarative and unauthenticated, including imported CPU reports.
    """
    from .optical_quantum import PairRequest, PairResult, report as pair_report
    if not isinstance(pair_request, PairRequest) or not isinstance(pair_result, PairResult):
        raise ValueError('expected existing optical PairRequest/PairResult')
    optical = pair_report(pair_request, pair_result)
    bec = report(bec_request, bec_result)
    if pair_request.artifact_sha256 != bec_request.artifact_sha256:
        raise ValueError('experiments refer to different artifacts')
    artifact = bec_request.artifact_sha256
    cpu = None
    if cpu_report is not None:
        if not isinstance(cpu_report, dict):
            raise ValueError('expected one CPU run report dictionary')
        if (cpu_report.get('evidence') != 'REAL_CPU_INFERENCE'
                or cpu_report.get('model_sha256') != artifact
                or cpu_report.get('providers') != ['CPUExecutionProvider']
                or cpu_report.get('device') != 'CPU'
                or cpu_report.get('rig') != 'unitree_g1'
                or type(cpu_report.get('batch_size')) is not int
                or cpu_report['batch_size'] != 1):
            raise ValueError('CPU report must declare matching G1 batch-one CPU execution')
        for name in ('model_sha256', 'manifest_sha256', 'input_sha256', 'output_sha256'):
            _hash(cpu_report.get(name))
        # Copy through JSON to prevent callers mutating linked records afterwards.
        cpu = json.loads(json.dumps(cpu_report, allow_nan=False))
    return _record({'schema_version': 1, 'artifact_sha256': artifact,
                    'optical': optical, 'cold_atoms': bec, 'cpu_reference': cpu,
                    'compatibility': 'CLASSICAL_RECORD_LINK_ONLY',
                    'synchronization': 'NOT_VERIFIED', 'cross_backend_parity': 'NOT_TESTED',
                    'hybrid_entanglement': 'NOT_VERIFIED', 'record_authentication': 'NOT_VERIFIED'})


def main():
    import argparse
    from .optical_quantum import PairRequest, SimulatedClock, SimulatedPairSampler
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('simulate', 'hardware'), required=True)
    parser.add_argument('--artifact-sha256', required=True)
    parser.add_argument('--request-id', default='bec500-offline')
    parser.add_argument('--shots', type=int, default=10)
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--link-optical', action='store_true', help='Link an optical mock record; no physical coupling')
    args = parser.parse_args()
    try:
        request = BECRequest(args.request_id, args.artifact_sha256, shots=args.shots)
        if args.mode == 'hardware':
            open_hardware()
        clock = SimulatedClock()
        backend = SimulatedBEC500(clock, seed=args.seed)
        optical = SimulatedPairSampler(clock, seed=args.seed)
        try:
            result = backend.sample(request)
            record = report(request, result)
            if args.link_optical:
                pair = PairRequest(args.request_id + '-photonic', args.artifact_sha256, args.shots)
                record = link_experiments(pair, optical.sample(pair), request, result)
            print(json.dumps(record, indent=2))
        finally:
            optical.close()
            backend.close()
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
