# SPDX-License-Identifier: Apache-2.0
"""Exact integer dot-product portability lab; all execution is on a binary CPU.

The ternary and septenary adapters use digit convolution and balanced carries.
It is a software simulation, not a MotionBricks inference or hardware backend.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import platform
import sys
from time import perf_counter_ns
from typing import Protocol


SCHEMA_VERSION = 1
MAX_ITEMS = 1024
MAX_INPUT_BYTES = 65536
BINARY = 'binary_twos_complement'
TERNARY = 'balanced_ternary'
SEPTENARY = 'balanced_septenary'


class ContractError(ValueError):
    """Invalid input, unsupported format/version, or malformed output."""


class BackendFailure(RuntimeError):
    """An adapter failed; no reference result is substituted."""


class ResultMismatch(BackendFailure):
    """A well-formed result disagrees with the independent integer oracle."""


def _integer(value, name):
    if type(value) is not int:
        raise ContractError(f'{name} must be an integer (bool/float are rejected)')


def _digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class WordFormat:
    """Fixed-width, least-significant digit first; no native ABI is serialized."""
    encoding: str
    width: int

    def __post_init__(self):
        if self.encoding not in (BINARY, TERNARY, SEPTENARY):
            raise ContractError('unsupported encoding')
        _integer(self.width, 'width')
        if not 1 <= self.width <= 128:
            raise ContractError('word width must be in [1,128]')

    @property
    def radix(self):
        return {BINARY: 2, TERNARY: 3, SEPTENARY: 7}[self.encoding]

    @property
    def bounds(self):
        if self.encoding == BINARY:
            half = 2 ** (self.width - 1)
            return -half, half - 1
        half = (self.radix ** self.width - 1) // 2
        return -half, half

    def validate_digits(self, digits):
        if type(digits) is not tuple or len(digits) != self.width:
            raise ContractError('digits must be an immutable tuple of declared width')
        half = self.radix // 2
        allowed = (0, 1) if self.encoding == BINARY else range(-half, half + 1)
        if any(type(d) is not int or d not in allowed for d in digits):
            raise ContractError('digit outside declared alphabet')

    def encode(self, value):
        _integer(value, 'value')
        low, high = self.bounds
        if not low <= value <= high:
            raise ContractError(f'value {value} outside [{low},{high}]')
        digits = []
        if self.encoding == BINARY:
            value %= 2 ** self.width
            for _ in range(self.width):
                value, digit = divmod(value, 2)
                digits.append(digit)
        else:
            half = self.radix // 2
            for _ in range(self.width):
                value, remainder = divmod(value + half, self.radix)
                digits.append(remainder - half)
        return tuple(digits)

    def decode(self, digits):
        self.validate_digits(digits)
        value = 0
        for digit in reversed(digits):
            value = value * self.radix + digit
        if self.encoding == BINARY and digits[-1]:
            value -= 2 ** self.width
        return value


@dataclass(frozen=True)
class Capabilities:
    backend_id: str
    input_format: WordFormat
    execution: str
    operation: str = 'integer_dot'
    max_items: int = MAX_ITEMS
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self):
        if not isinstance(self.backend_id, str) or not self.backend_id.strip():
            raise ContractError('backend identity required')
        if not isinstance(self.input_format, WordFormat) or self.input_format.width > 32:
            raise ContractError('input width must be at most 32 digits')
        if self.execution not in ('HOST_INTEGER_REFERENCE', 'HOST_TRIT_SIMULATION',
                                  'HOST_SEPTENARY_SIMULATION'):
            raise ContractError('unsupported execution class')
        _integer(self.max_items, 'max_items')
        _integer(self.schema_version, 'schema_version')
        if not 1 <= self.max_items <= MAX_ITEMS:
            raise ContractError('invalid capacity')
        if self.operation != 'integer_dot' or self.schema_version != SCHEMA_VERSION:
            raise ContractError('unsupported operation or version')


@dataclass(frozen=True)
class EncodedRequest:
    schema_version: int
    format: WordFormat
    lhs: tuple[tuple[int, ...], ...]
    rhs: tuple[tuple[int, ...], ...]

    @property
    def sha256(self):
        return _digest(asdict(self))


@dataclass(frozen=True)
class EncodedResult:
    schema_version: int
    request_sha256: str
    format: WordFormat
    digits: tuple[int, ...]


class DotBackend(Protocol):
    capabilities: Capabilities

    def execute(self, request: EncodedRequest) -> EncodedResult: ...


def _admit(request, capabilities):
    if not isinstance(request, EncodedRequest):
        raise ContractError('EncodedRequest required')
    _integer(request.schema_version, 'schema_version')
    if request.schema_version != capabilities.schema_version:
        raise ContractError('request schema version is unsupported')
    if request.format != capabilities.input_format:
        raise ContractError('request format is unsupported by this backend')
    if type(request.lhs) is not tuple or type(request.rhs) is not tuple:
        raise ContractError('operand vectors must be immutable tuples')
    if not 1 <= len(request.lhs) == len(request.rhs) <= capabilities.max_items:
        raise ContractError('vectors must have equal, nonzero lengths within capacity')
    for vector in (request.lhs, request.rhs):
        for digits in vector:
            request.format.validate_digits(digits)


def _output_format(request):
    # 2*w + ceil(log_radix(n)) accommodates every product and their exact sum.
    extra, capacity = 0, 1
    while capacity < len(request.lhs):
        extra += 1
        capacity *= request.format.radix
    return WordFormat(request.format.encoding, 2 * request.format.width + extra)


class BinaryIntegerBackend:
    def __init__(self, width=32):
        self.capabilities = Capabilities('python-integer-v1', WordFormat(BINARY, width),
                                         'HOST_INTEGER_REFERENCE')

    def execute(self, request):
        _admit(request, self.capabilities)
        fmt = request.format
        value = sum(fmt.decode(a) * fmt.decode(b) for a, b in zip(request.lhs, request.rhs))
        output = _output_format(request)
        return EncodedResult(SCHEMA_VERSION, request.sha256, output, output.encode(value))


class BalancedTernaryBackend:
    def __init__(self, width=21):
        self.capabilities = Capabilities('python-trit-convolution-v1', WordFormat(TERNARY, width),
                                         'HOST_TRIT_SIMULATION')

    def execute(self, request):
        return _balanced_dot(request, self.capabilities)


class BalancedSeptenaryBackend:
    """Exact base-7 digit arithmetic with alphabet {-3,-2,-1,0,1,2,3}."""

    def __init__(self, width=12):
        self.capabilities = Capabilities(
            'python-septenary-convolution-v1', WordFormat(SEPTENARY, width),
            'HOST_SEPTENARY_SIMULATION')

    def execute(self, request):
        return _balanced_dot(request, self.capabilities)


def _balanced_dot(request, capabilities):
    """Convolve signed digits, then normalize; never decode whole operands."""
    _admit(request, capabilities)
    output = _output_format(request)
    coefficients = [0] * output.width
    for lhs, rhs in zip(request.lhs, request.rhs):
        for i, a in enumerate(lhs):
            for j, b in enumerate(rhs):
                coefficients[i + j] += a * b
    # For odd radix r, x = r*carry + digit with digit in [-(r//2), r//2].
    radix, half = output.radix, output.radix // 2
    digits, carry = [], 0
    for coefficient in coefficients:
        carry, remainder = divmod(coefficient + carry + half, radix)
        digits.append(remainder - half)
    if carry:
        raise BackendFailure('accumulator overflow')
    return EncodedResult(SCHEMA_VERSION, request.sha256, output, tuple(digits))


def run_dot(lhs, rhs, backend: DotBackend):
    """Validate, encode, execute, decode and verify one synchronous request.

    Adapters are trusted in-process code, not sandboxed or preemptible. Exceptions
    propagate; this function neither retries nor silently falls back to the oracle.
    Timings include validation overhead; there is no device transport measurement.
    """
    start = perf_counter_ns()
    caps = backend.capabilities
    if not isinstance(caps, Capabilities):
        raise ContractError('Capabilities required')
    if type(lhs) not in (tuple, list) or type(rhs) not in (tuple, list):
        raise ContractError('operands must be lists or tuples')
    if not 1 <= len(lhs) == len(rhs) <= caps.max_items:
        raise ContractError('vectors must have equal, nonzero lengths within capacity')
    lhs, rhs = tuple(lhs), tuple(rhs)
    low, high = caps.input_format.bounds
    for value in lhs + rhs:
        _integer(value, 'operand')
        if not low <= value <= high:
            raise ContractError(f'operand outside backend range [{low},{high}]')
    expected = sum(a * b for a, b in zip(lhs, rhs))
    workload_hash = _digest({'operation': 'integer_dot', 'lhs': lhs, 'rhs': rhs})
    admitted = perf_counter_ns()
    request = EncodedRequest(SCHEMA_VERSION, caps.input_format,
                             tuple(caps.input_format.encode(v) for v in lhs),
                             tuple(caps.input_format.encode(v) for v in rhs))
    _admit(request, caps)
    request_hash = request.sha256
    encoded = perf_counter_ns()
    try:
        result = backend.execute(request)
    except Exception as exc:
        raise BackendFailure(f'{caps.backend_id} execution failed: {exc}') from exc
    executed = perf_counter_ns()
    if not isinstance(result, EncodedResult):
        raise ContractError('backend did not return EncodedResult')
    _integer(result.schema_version, 'result schema_version')
    if result.schema_version != SCHEMA_VERSION or result.request_sha256 != request_hash:
        raise ContractError('result version or request identity mismatch')
    if result.format != _output_format(request):
        raise ContractError('result format mismatch')
    value = result.format.decode(result.digits)
    decoded = perf_counter_ns()
    if value != expected:
        raise ResultMismatch(f'{caps.backend_id} returned {value}; expected {expected}')
    verified = perf_counter_ns()
    return {
        'schema_version': SCHEMA_VERSION, 'status': 'VERIFIED',
        'capabilities': asdict(caps), 'workload_sha256': workload_hash,
        'request_sha256': request_hash, 'items': len(lhs), 'value': value,
        'input_range': caps.input_format.bounds, 'output_format': asdict(result.format),
        'logical_input_digits': 2 * len(lhs) * caps.input_format.width,
        'timing_ns': {
            'validation_reference': admitted - start, 'encode': encoded - admitted,
            'backend_call': executed - encoded, 'decode': decoded - executed,
            'verify': verified - decoded, 'total': verified - start,
        },
        'transport': 'NOT_MEASURED_IN_PROCESS', 'energy': 'NOT_MEASURED',
        'native_nonbinary_hardware': 'NOT_TESTED', 'motion_inference': 'NOT_PERFORMED',
        'host': {'os': platform.system(), 'machine': platform.machine(),
                 'python': platform.python_version()},
    }


def _unique_fields(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ContractError(f'duplicate JSON field: {key}')
        data[key] = value
    return data


def _read_input(path):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        raise ContractError('input exceeds 64 KiB')
    data = json.loads(raw, object_pairs_hook=_unique_fields)
    if type(data) is not dict or set(data) != {'schema_version', 'lhs', 'rhs'}:
        raise ContractError('input requires exactly schema_version, lhs and rhs')
    _integer(data['schema_version'], 'schema_version')
    if data['schema_version'] != SCHEMA_VERSION:
        raise ContractError('unsupported input schema')
    return data['lhs'], data['rhs']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('binary', 'ternary', 'septenary', 'both', 'all'),
                        default='both', help='both keeps the binary/ternary pair; all adds base 7')
    parser.add_argument('--input', help='JSON integer vectors; otherwise use a fixed fixture')
    args = parser.parse_args(argv)
    try:
        lhs, rhs = _read_input(args.input) if args.input else ([13, -7, 0, 42], [3, 11, -9, -2])
        backends = {'binary': BinaryIntegerBackend(), 'ternary': BalancedTernaryBackend(),
                    'septenary': BalancedSeptenaryBackend()}
        if args.backend == 'all':
            selected = backends.values()
        elif args.backend == 'both':
            selected = [backends['binary'], backends['ternary']]
        else:
            selected = [backends[args.backend]]
        runs = [run_dot(lhs, rhs, backend) for backend in selected]
        print(json.dumps({'schema_version': SCHEMA_VERSION, 'status': 'VERIFIED', 'runs': runs},
                         indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, RuntimeError, RecursionError) as exc:
        print(json.dumps({'schema_version': SCHEMA_VERSION, 'status': 'FAILED',
                          'error_type': type(exc).__name__, 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    sys.exit(main())
