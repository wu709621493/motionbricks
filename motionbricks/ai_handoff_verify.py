"""Independent exact oracle for the synthetic distance contract (stdlib only).

This module deliberately does not import the adapter or its conversion table.
It verifies arithmetic and evidence binding, not real-world truth or AI cognition.
"""

from fractions import Fraction
import re


def decimal_string(value: object) -> bool:
    """Bounded, non-negative, ordinary decimal; no floats, exponents or NaN."""
    return isinstance(value, str) and re.fullmatch(
        r"(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,6})?", value
    ) is not None


def verify_distance(source_value: str, source_unit: str, source_frame: str,
                    output_value: str, output_unit: str, output_frame: str) -> bool:
    if not decimal_string(source_value) or not decimal_string(output_value):
        return False
    if not source_frame or output_frame != source_frame or output_unit != "m":
        return False
    if source_unit == "cm":
        expected = Fraction(source_value) / 100
    elif source_unit == "mm":
        expected = Fraction(source_value) / 1000
    elif source_unit == "m":
        expected = Fraction(source_value)
    else:
        return False
    return Fraction(output_value) == expected
