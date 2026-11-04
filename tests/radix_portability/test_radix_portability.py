# SPDX-License-Identifier: Apache-2.0
import dataclasses
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from motionbricks.radix_portability import (
    BINARY, TERNARY, BackendFailure, BalancedTernaryBackend, BinaryIntegerBackend,
    Capabilities, ContractError, EncodedRequest, MAX_ITEMS, ResultMismatch,
    WordFormat, run_dot,
)


class CodecTests(unittest.TestCase):
    def test_known_vectors_and_signed_boundaries(self):
        binary, ternary = WordFormat(BINARY, 4), WordFormat(TERNARY, 3)
        self.assertEqual(binary.encode(-8), (0, 0, 0, 1))
        self.assertEqual(binary.encode(-1), (1, 1, 1, 1))
        self.assertEqual(binary.encode(7), (1, 1, 1, 0))
        self.assertEqual(ternary.encode(5), (-1, -1, 1))
        self.assertEqual(ternary.encode(-5), (1, 1, -1))
        self.assertEqual(ternary.encode(13), (1, 1, 1))
        self.assertEqual(ternary.encode(-13), (-1, -1, -1))

    def test_exhaustive_small_round_trips_and_overflow(self):
        for encoding in (BINARY, TERNARY):
            for width in range(1, 7):
                fmt = WordFormat(encoding, width)
                low, high = fmt.bounds
                for value in range(low, high + 1):
                    self.assertEqual(fmt.decode(fmt.encode(value)), value)
                for value in (low - 1, high + 1, True, 1.0, '1', None):
                    with self.subTest(encoding=encoding, width=width, value=value):
                        with self.assertRaises(ContractError):
                            fmt.encode(value)

    def test_invalid_formats_and_digits(self):
        for encoding, width in [('unknown', 2), (BINARY, 0), (TERNARY, 129),
                                (BINARY, True), (TERNARY, 3.0)]:
            with self.assertRaises(ContractError):
                WordFormat(encoding, width)
        for encoding in (BINARY, TERNARY):
            for digits in [(0, 2), (True, 0), (0.0, 0), [0, 0], (0,), (0, 0, 0)]:
                with self.assertRaises(ContractError):
                    WordFormat(encoding, 2).decode(digits)
        with self.assertRaises(ContractError):
            WordFormat(BINARY, 2).decode((-1, 0))


class DotTests(unittest.TestCase):
    def test_exhaustive_signed_products(self):
        for backend in (BinaryIntegerBackend(4), BalancedTernaryBackend(3)):
            low, high = backend.capabilities.input_format.bounds
            for a in range(low, high + 1):
                for b in range(low, high + 1):
                    self.assertEqual(run_dot([a], [b], backend)['value'], a * b)

    def test_random_parity_and_workload_identity(self):
        rng = random.Random(20261104)
        for _ in range(60):
            n = rng.randint(1, 25)
            lhs = [rng.randint(-2**31, 2**31 - 1) for _ in range(n)]
            rhs = [rng.randint(-2**31, 2**31 - 1) for _ in range(n)]
            binary = run_dot(lhs, rhs, BinaryIntegerBackend())
            ternary = run_dot(lhs, rhs, BalancedTernaryBackend())
            self.assertEqual(binary['value'], ternary['value'])
            self.assertEqual(binary['workload_sha256'], ternary['workload_sha256'])
            self.assertNotEqual(binary['request_sha256'], ternary['request_sha256'])

    def test_accumulator_range_and_cancellation(self):
        for backend in (BinaryIntegerBackend(), BalancedTernaryBackend(32)):
            low, high = backend.capabilities.input_format.bounds
            for a, b in ((low, low), (low, high), (high, high)):
                result = run_dot([a] * MAX_ITEMS, [b] * MAX_ITEMS, backend)
                self.assertEqual(result['value'], MAX_ITEMS * a * b)
            self.assertEqual(run_dot([high, high], [1, -1], backend)['value'], 0)

    def test_ternary_arithmetic_does_not_decode_to_integer(self):
        backend = BalancedTernaryBackend(3)
        fmt = backend.capabilities.input_format
        request = EncodedRequest(1, fmt, (fmt.encode(5), fmt.encode(-7)),
                                  (fmt.encode(-3), fmt.encode(9)))
        with patch.object(WordFormat, 'decode', side_effect=AssertionError('integer shortcut')):
            result = backend.execute(request)
        self.assertEqual(result.format.decode(result.digits), -78)

    def test_validation_happens_before_execution(self):
        backend = BinaryIntegerBackend(4)
        cases = [([], []), ([1], []), ([True], [1]), ([1.0], [1]),
                 ([8], [1]), ([-9], [1]), ([1] * (MAX_ITEMS + 1), [1] * (MAX_ITEMS + 1)),
                 ('1', [1]), ([None], [1])]
        with patch.object(backend, 'execute', side_effect=AssertionError('must not execute')):
            for lhs, rhs in cases:
                with self.subTest(lhs=str(lhs)[:30]), self.assertRaises(ContractError):
                    run_dot(lhs, rhs, backend)

    def test_capability_and_request_admission(self):
        fmt = WordFormat(BINARY, 4)
        base = Capabilities('test', fmt, 'HOST_INTEGER_REFERENCE')
        for changes in [{'max_items': True}, {'max_items': MAX_ITEMS + 1},
                        {'schema_version': 2}, {'operation': 'float_dot'},
                        {'input_format': WordFormat(BINARY, 33)}, {'backend_id': ''},
                        {'execution': 'NATIVE_TERNARY'}]:
            with self.assertRaises(ContractError):
                dataclasses.replace(base, **changes)
        backend = BinaryIntegerBackend(4)
        request = EncodedRequest(1, fmt, (fmt.encode(1),), (fmt.encode(2),))
        for changes in [{'schema_version': 2}, {'schema_version': True},
                        {'format': WordFormat(TERNARY, 4)}, {'lhs': ()},
                        {'lhs': [fmt.encode(1)]}, {'rhs': ((0, 0, 0, 2),)}]:
            with self.assertRaises(ContractError):
                backend.execute(dataclasses.replace(request, **changes))

    def test_corrupt_stale_or_incorrect_output_never_accepted(self):
        backend = BinaryIntegerBackend()
        execute = backend.execute
        mutations = [lambda r: None,
                     lambda r: dataclasses.replace(r, schema_version=2),
                     lambda r: dataclasses.replace(r, schema_version=True),
                     lambda r: dataclasses.replace(r, request_sha256='0' * 64),
                     lambda r: dataclasses.replace(r, format=WordFormat(TERNARY, r.format.width)),
                     lambda r: dataclasses.replace(r, digits=(2,) * r.format.width),
                     lambda r: dataclasses.replace(r, digits=r.digits[:-1])]
        for mutate in mutations:
            with patch.object(backend, 'execute', side_effect=lambda req: mutate(execute(req))):
                with self.assertRaises(ContractError):
                    run_dot([2], [3], backend)
        with patch.object(backend, 'execute', side_effect=lambda req: dataclasses.replace(
                execute(req), digits=execute(req).format.encode(7))):
            with self.assertRaises(ResultMismatch):
                run_dot([2], [3], backend)

    def test_backend_failure_and_next_request(self):
        backend = BalancedTernaryBackend()
        with patch.object(backend, 'execute', side_effect=OSError('simulated device loss')):
            with self.assertRaisesRegex(BackendFailure, 'simulated device loss'):
                run_dot([2], [3], backend)
        first = run_dot([2], [3], backend)
        run_dot([-8], [9], backend)
        again = run_dot([2], [3], backend)
        self.assertEqual(first['value'], 6)
        self.assertEqual(first['request_sha256'], again['request_sha256'])
        self.assertEqual(again['value'], 6)

    def test_report_timing_and_evidence_limits(self):
        report = run_dot([13, -7, 0, 42], [3, 11, -9, -2], BalancedTernaryBackend())
        self.assertEqual(report['value'], -122)
        self.assertEqual(report['status'], 'VERIFIED')
        timings = report['timing_ns']
        self.assertEqual(timings['total'], sum(v for k, v in timings.items() if k != 'total'))
        self.assertTrue(all(type(v) is int and v >= 0 for v in timings.values()))
        self.assertEqual(report['native_nonbinary_hardware'], 'NOT_TESTED')
        self.assertEqual(report['energy'], 'NOT_MEASURED')
        self.assertEqual(report['transport'], 'NOT_MEASURED_IN_PROCESS')
        self.assertEqual(report['logical_input_digits'], 168)
        json.dumps(report, allow_nan=False)


class CLITests(unittest.TestCase):
    def cli(self, *args):
        process = subprocess.run([sys.executable, '-S', '-m', 'motionbricks.radix_portability',
                                  *args], capture_output=True, text=True, timeout=15)
        return process, json.loads(process.stdout)

    def test_dependency_free_default_and_single_backend(self):
        process, report = self.cli()
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual([r['value'] for r in report['runs']], [-122, -122])
        for backend in ('binary', 'ternary'):
            process, report = self.cli('--backend', backend)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(len(report['runs']), 1)

    def test_file_input_and_clean_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            path.write_text(json.dumps({'schema_version': 1, 'lhs': [-8, 3], 'rhs': [9, -4]}))
            process, report = self.cli('--input', str(path))
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(report['runs'][0]['value'], -84)
            bad = ['{', '[]', '{"schema_version":2,"lhs":[1],"rhs":[2]}',
                   '{"schema_version":2,"schema_version":1,"lhs":[1],"rhs":[2]}',
                   '{"schema_version":1,"lhs":[true],"rhs":[2]}',
                   '{"schema_version":1,"lhs":[1],"rhs":[2],"extra":0}',
                   ' ' * 65537, '[' * 2000 + ']' * 2000]
            for payload in bad:
                path.write_text(payload)
                process, report = self.cli('--input', str(path))
                self.assertEqual(process.returncode, 1)
                self.assertEqual(report['status'], 'FAILED')
                self.assertNotIn('runs', report)
                self.assertNotIn('Traceback', process.stderr)
            path.unlink()
            process, report = self.cli('--input', str(path))
            self.assertEqual(process.returncode, 1)


if __name__ == '__main__':
    unittest.main()
