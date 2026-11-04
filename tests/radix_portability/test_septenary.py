# SPDX-License-Identifier: Apache-2.0
"""Base-7 correctness, protocol rejection and legacy CLI compatibility."""
import dataclasses
import io
import itertools
import json
import random
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from motionbricks.radix_portability import (
    BINARY, TERNARY, SEPTENARY, BackendFailure, BalancedSeptenaryBackend,
    BalancedTernaryBackend, BinaryIntegerBackend, ContractError, EncodedRequest,
    MAX_ITEMS, ResultMismatch, WordFormat, main, run_dot,
)


class SeptenaryTests(unittest.TestCase):
    def test_known_digits_and_default_range(self):
        fmt = WordFormat(SEPTENARY, 3)
        self.assertEqual(fmt.radix, 7)
        for value, digits in [(0, (0, 0, 0)), (4, (-3, 1, 0)),
                              (-4, (3, -1, 0)), (13, (-1, 2, 0)),
                              (49, (0, 0, 1)), (-122, (-3, -3, -2)),
                              (171, (3, 3, 3)), (-171, (-3, -3, -3))]:
            self.assertEqual(fmt.encode(value), digits)
            self.assertEqual(fmt.decode(digits), value)
        self.assertEqual(BalancedSeptenaryBackend().capabilities.input_format.bounds,
                         (-6920643600, 6920643600))

    def test_exhaustive_words_and_unique_encoding(self):
        for width in range(1, 5):
            fmt = WordFormat(SEPTENARY, width)
            values = set()
            for digits in itertools.product(range(-3, 4), repeat=width):
                expected = sum(d * 7**i for i, d in enumerate(digits))
                self.assertEqual(fmt.decode(digits), expected)
                self.assertEqual(fmt.encode(expected), digits)
                values.add(expected)
            low, high = fmt.bounds
            self.assertEqual(values, set(range(low, high + 1)))

    def test_exhaustive_two_digit_products(self):
        backend = BalancedSeptenaryBackend(2)
        for a in range(-24, 25):
            for b in range(-24, 25):
                self.assertEqual(run_dot([a], [b], backend)['value'], a * b)

    def test_random_parity_with_binary_and_ternary(self):
        rng = random.Random(709621493)
        for _ in range(60):
            n = rng.randint(1, 25)
            lhs = [rng.randint(-2**31, 2**31 - 1) for _ in range(n)]
            rhs = [rng.randint(-2**31, 2**31 - 1) for _ in range(n)]
            reports = [run_dot(lhs, rhs, b) for b in (
                BinaryIntegerBackend(), BalancedTernaryBackend(), BalancedSeptenaryBackend())]
            self.assertEqual({r['value'] for r in reports}, {sum(a*b for a, b in zip(lhs, rhs))})
            self.assertEqual(len({r['workload_sha256'] for r in reports}), 1)
            self.assertEqual(len({r['request_sha256'] for r in reports}), 3)

    def test_wide_random_operands(self):
        rng = random.Random(7)
        for width in (1, 2, 12, 32):
            backend = BalancedSeptenaryBackend(width)
            low, high = backend.capabilities.input_format.bounds
            lhs = [rng.randint(low, high) for _ in range(31)]
            rhs = [rng.randint(low, high) for _ in range(31)]
            self.assertEqual(run_dot(lhs, rhs, backend)['value'], sum(a*b for a, b in zip(lhs, rhs)))

    def test_accumulator_capacity_carries_and_cancellation(self):
        backend = BalancedSeptenaryBackend(32)
        low, high = backend.capabilities.input_format.bounds
        for n in (1, 7, 8, 49, 50, 343, 344, MAX_ITEMS):
            for a, b in ((low, low), (low, high), (high, high)):
                report = run_dot([a] * n, [b] * n, backend)
                self.assertEqual(report['value'], n * a * b)
                width = report['output_format']['width']
                self.assertLessEqual(abs(report['value']), (7**width - 1)//2)
        self.assertEqual(run_dot([high] * MAX_ITEMS, [1, -1] * (MAX_ITEMS//2), backend)['value'], 0)
        self.assertEqual(run_dot([0] * MAX_ITEMS, [low] * MAX_ITEMS, backend)['value'], 0)
        self.assertEqual(run_dot([3, 3], [1, 1], BalancedSeptenaryBackend(1))['value'], 6)

    def test_arithmetic_never_encodes_or_decodes_whole_integers(self):
        backend = BalancedSeptenaryBackend(3)
        fmt = backend.capabilities.input_format
        request = EncodedRequest(1, fmt, (fmt.encode(13), fmt.encode(-7)),
                                  (fmt.encode(3), fmt.encode(11)))
        with patch.object(WordFormat, 'decode', side_effect=AssertionError('decode shortcut')), \
             patch.object(WordFormat, 'encode', side_effect=AssertionError('encode shortcut')):
            result = backend.execute(request)
        self.assertEqual(result.format.decode(result.digits), -38)

    def test_reject_invalid_format_digits_and_values(self):
        for width in (0, 129, True, 1.0):
            with self.assertRaises(ContractError):
                WordFormat(SEPTENARY, width)
        with self.assertRaises(ContractError):
            BalancedSeptenaryBackend(33)
        fmt = WordFormat(SEPTENARY, 2)
        for digits in ((4, 0), (-4, 0), (True, 0), (0.0, 0), (0,), [0, 0]):
            with self.assertRaises(ContractError):
                fmt.decode(digits)
        backend = BalancedSeptenaryBackend(2)
        with patch.object(backend, 'execute', side_effect=AssertionError('must not execute')):
            for lhs, rhs in [([25], [1]), ([-25], [1]), ([True], [1]), ([1.0], [1]),
                             ([], []), ([1], []), ([0] * 1025, [0] * 1025)]:
                with self.assertRaises(ContractError):
                    run_dot(lhs, rhs, backend)

    def test_reject_wrong_requests_and_cross_backend_formats(self):
        backend = BalancedSeptenaryBackend(2)
        fmt = backend.capabilities.input_format
        request = EncodedRequest(1, fmt, (fmt.encode(2),), (fmt.encode(3),))
        for changes in ({'schema_version': 2}, {'schema_version': True},
                        {'format': WordFormat(TERNARY, 2)}, {'format': WordFormat(SEPTENARY, 3)},
                        {'lhs': ()}, {'lhs': [(2, 0)]}, {'rhs': ((4, 0),)}):
            with self.assertRaises(ContractError):
                backend.execute(dataclasses.replace(request, **changes))
        for old_backend in (BinaryIntegerBackend(2), BalancedTernaryBackend(2)):
            with self.assertRaises(ContractError):
                old_backend.execute(request)

    def test_reject_corrupt_results_and_do_not_fallback(self):
        backend = BalancedSeptenaryBackend(2)
        execute = backend.execute
        for changes in ({'schema_version': 2}, {'schema_version': True},
                        {'request_sha256': '0' * 64}, {'format': WordFormat(BINARY, 4)},
                        {'digits': (4, 0, 0, 0)}, {'digits': (0, 0, 0)}):
            with patch.object(backend, 'execute', side_effect=lambda req: dataclasses.replace(
                    execute(req), **changes)):
                with self.assertRaises(ContractError):
                    run_dot([2], [3], backend)
        with patch.object(backend, 'execute', side_effect=lambda req: dataclasses.replace(
                execute(req), digits=(0, 1, 0, 0))):
            with self.assertRaises(ResultMismatch):
                run_dot([2], [3], backend)
        with patch.object(backend, 'execute', side_effect=OSError('device lost')):
            with self.assertRaises(BackendFailure):
                run_dot([2], [3], backend)
        self.assertEqual(run_dot([2], [3], backend)['value'], 6)

    def test_cli_all_septenary_and_legacy_both(self):
        for selection, encodings in [('septenary', [SEPTENARY]),
                                     ('all', [BINARY, TERNARY, SEPTENARY]),
                                     ('both', [BINARY, TERNARY])]:
            process = subprocess.run([sys.executable, '-S', '-m', 'motionbricks.radix_portability',
                                      '--backend', selection], capture_output=True, text=True, timeout=15)
            self.assertEqual(process.returncode, 0, process.stderr)
            report = json.loads(process.stdout)
            self.assertEqual([r['capabilities']['input_format']['encoding'] for r in report['runs']], encodings)
            self.assertEqual([r['value'] for r in report['runs']], [-122] * len(encodings))
            if selection == 'septenary':
                run = report['runs'][0]
                self.assertEqual(run['capabilities']['execution'], 'HOST_SEPTENARY_SIMULATION')
                self.assertEqual(run['logical_input_digits'], 96)
                self.assertEqual(run['energy'], 'NOT_MEASURED')
                self.assertEqual(run['native_nonbinary_hardware'], 'NOT_TESTED')

    def test_cli_no_partial_report_on_septenary_failure(self):
        output = io.StringIO()
        with patch.object(BalancedSeptenaryBackend, 'execute', side_effect=OSError('injected')), \
             redirect_stdout(output):
            self.assertEqual(main(['--backend', 'all']), 1)
        report = json.loads(output.getvalue())
        self.assertEqual(report['status'], 'FAILED')
        self.assertNotIn('runs', report)

    def test_cli_file_input_range_and_shared_range(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            high = BalancedSeptenaryBackend().capabilities.input_format.bounds[1]
            for value, selection, status in ((high, 'septenary', 0), (high + 1, 'septenary', 1),
                                              (high, 'all', 1)):
                path.write_text(json.dumps({'schema_version': 1, 'lhs': [value], 'rhs': [1]}))
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['--input', str(path), '--backend', selection]), status)
                report = json.loads(output.getvalue())
                if status:
                    self.assertEqual(report['status'], 'FAILED')
                    self.assertNotIn('runs', report)
                else:
                    self.assertEqual(report['runs'][0]['value'], high)


if __name__ == '__main__':
    unittest.main()
