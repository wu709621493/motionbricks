"""Opt-in zero-error handling for finite real scalars and vectors (CPU only).

Zero remains valid data. No epsilon substitution, exception retry, or global
patching. A fallback is a caller decision, never a mathematically valid answer.
"""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class NumericResult:
    value: float | tuple[float, ...] | None
    status: str  # OK, UNDEFINED, FALLBACK
    operation: str
    reason: str | None = None


class ZeroDomainError(ValueError):
    """The requested operation has no result in this API's real domain."""


def _real(value):
    if type(value) not in (int, float):
        raise TypeError('expected a built-in real int or float, excluding bool')
    try:
        result = float(value)
    except OverflowError as exc:
        raise ValueError('input outside finite float range') from exc
    if not math.isfinite(result):
        raise ValueError('input must be finite')
    return result


def _options(policy, fallback):
    if policy not in ('raise', 'undefined', 'fallback'):
        raise ValueError('policy must be raise, undefined, or fallback')
    if policy == 'fallback':
        if fallback is None:
            raise ValueError('fallback policy requires an explicit fallback')
    elif fallback is not None:
        raise ValueError('fallback supplied without fallback policy')


def _failure(operation, reason, policy, fallback):
    if policy == 'raise':
        raise ZeroDomainError(f'{operation}: {reason}')
    return NumericResult(fallback if policy == 'fallback' else None,
                         'FALLBACK' if policy == 'fallback' else 'UNDEFINED',
                         operation, reason)


def divide(numerator, denominator, *, policy='raise', fallback=None):
    """Exact zero denominator guard; tiny nonzero denominators are not clamped."""
    _options(policy, fallback)
    fallback = _real(fallback) if fallback is not None else None
    a, b = _real(numerator), _real(denominator)
    if b == 0:
        return _failure('divide', 'zero_denominator', policy, fallback)
    value = a / b
    if not math.isfinite(value):
        raise OverflowError('divide result outside finite float range')
    return NumericResult(value, 'OK', 'divide')


def log(value, *, policy='raise', fallback=None):
    """Natural logarithm; negative inputs are errors, not zero recovery cases."""
    _options(policy, fallback)
    fallback = _real(fallback) if fallback is not None else None
    value = _real(value)
    if value < 0:
        raise ValueError('log requires a nonnegative real input')
    if value == 0:
        return _failure('log', 'zero_argument', policy, fallback)
    return NumericResult(math.log(value), 'OK', 'log')


def normalize(values, *, policy='raise', fallback=None):
    """Unit L2 vector using scaling to avoid norm overflow/underflow.

    Fallback must match the input dimension but need not be a unit vector:
    e.g. a zero hold command is explicitly labelled FALLBACK, never OK.
    Empty vectors and nonfinite inputs are always rejected.
    """
    _options(policy, fallback)
    values = tuple(_real(v) for v in values)
    if not values:
        raise ValueError('cannot normalize an empty vector')
    if fallback is not None:
        fallback = tuple(_real(v) for v in fallback)
        if len(fallback) != len(values):
            raise ValueError('fallback dimension must match input')
    scale = max(abs(v) for v in values)
    if scale == 0:
        return _failure('normalize', 'zero_norm', policy, fallback)
    scaled = tuple(v / scale for v in values)
    norm = math.sqrt(math.fsum(v * v for v in scaled))
    return NumericResult(tuple(v / norm for v in scaled), 'OK', 'normalize')
