"""Offline tests use fake sessions explicitly: they are G0, never G1 evidence."""
import contextlib
import gc
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import weakref

import numpy as np
from motionbricks.cpu_reference import (
    CPUReference, ContractError, G1Contract, MODEL_SHA256, PrerequisiteError,
    main, synthetic_request, tensor_hash, valid_frames,
)


def outputs(count=6):
    contract = G1Contract()
    result = {name: np.zeros(s['shape'], dtype=s['dtype']) for name, s in contract.outputs.items()}
    result['pred_num_tokens'][0] = count
    result['pred_qpos'][..., 6] = 1
    return result


class FakeSession:
    def __init__(self, path, *, sess_options, providers):
        assert providers == ['CPUExecutionProvider']
        assert sess_options.intra_op_num_threads == 1
        self.values = outputs()
        self.failure = False
        self.contract = G1Contract()

    def disable_fallback(self):
        self.fallback_disabled = True

    def get_providers(self):
        return ['CPUExecutionProvider']

    def nodes(self, specs):
        return [SimpleNamespace(name=n, shape=['batch'] + s['shape'][1:],
                                type='tensor(float)' if s['dtype'] == 'float32' else 'tensor(int32)')
                for n, s in specs.items()]

    def get_inputs(self):
        return self.nodes(self.contract.inputs)

    def get_outputs(self):
        return self.nodes(self.contract.outputs)

    def run(self, names, inputs):
        if self.failure:
            raise RuntimeError('injected execution error')
        count = int(np.flatnonzero(inputs['allowed_pred_num_tokens'][0])[0]) + 6
        self.values['pred_num_tokens'][0] = count
        # Deliberately mutate the feed to test ownership of caller buffers.
        inputs['context_qpos'][:] = 99
        return [self.values[name] for name in names]


def fake_ort():
    return SimpleNamespace(__version__='FAKE-NOT-INFERENCE', SessionOptions=SimpleNamespace,
                           ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL=0),
                           GraphOptimizationLevel=SimpleNamespace(ORT_DISABLE_ALL=0),
                           InferenceSession=FakeSession)


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = G1Contract()

    def test_all_lengths(self):
        for count in range(6, 17):
            request = synthetic_request(count)
            self.assertEqual(self.contract.validate_outputs(outputs(count), request), count * 4)

    def test_frame_slices_and_ownership(self):
        for count in (6, 16):
            raw = outputs(count)
            for trim in (False, True):
                sliced = valid_frames(raw, synthetic_request(count), trim_boundaries=trim)
                self.assertEqual(sliced['pred_qpos'].shape, (1, count * 4 - (6 if trim else 0), 36))
                self.assertEqual(sliced['pred_foot_contacts'].shape[1], sliced['pred_qpos'].shape[1])
                self.assertFalse(np.shares_memory(sliced['pred_qpos'], raw['pred_qpos']))

    def test_input_names_shape_dtype_and_batch(self):
        for name in self.contract.inputs:
            for change in ('missing', 'dtype', 'shape', 'batch0', 'batch2'):
                with self.subTest(name=name, change=change):
                    request = synthetic_request()
                    if change == 'missing':
                        del request[name]
                    elif change == 'dtype':
                        request[name] = request[name].astype('float64')
                    elif change == 'shape':
                        request[name] = request[name][..., :-1]
                    elif change == 'batch0':
                        request[name] = request[name][:0]
                    else:
                        request[name] = np.repeat(request[name], 2, axis=0)
                    with self.assertRaises(ContractError):
                        self.contract.validate_inputs(request)
        request = synthetic_request()
        request['extra'] = np.zeros(1)
        with self.assertRaises(ContractError):
            self.contract.validate_inputs(request)

    def test_masks(self):
        for name, spec in self.contract.inputs.items():
            if spec['dtype'] != 'int32':
                continue
            for bad in (-1, 2):
                request = synthetic_request()
                request[name][0, 0] = bad
                with self.assertRaises(ContractError):
                    self.contract.validate_inputs(request)
        request = synthetic_request()
        request['allowed_pred_num_tokens'][:] = 0
        with self.assertRaises(ContractError):
            self.contract.validate_inputs(request)
        # Conditioning masks are independent; no undocumented all-on requirement.
        for name in ('has_global_root_values', 'has_local_root_values', 'has_local_poses'):
            request = synthetic_request()
            request[name][:] = 0
            self.contract.validate_inputs(request)

    def test_nonfinite_and_masked_quaternion(self):
        for name in ('context_qpos', 'target_qpos'):
            for bad in (np.nan, np.inf, -np.inf):
                request = synthetic_request()
                request[name][0, 0, 0] = bad
                with self.assertRaises(ContractError):
                    self.contract.validate_inputs(request)
            request = synthetic_request()
            request['has_local_poses'][:] = 0
            request[name][0, 0, 3:7] = 0
            with self.assertRaises(ContractError):
                self.contract.validate_inputs(request)

    def test_invalid_outputs(self):
        for count in (5, 7, 17):
            with self.assertRaises(ContractError):
                self.contract.validate_outputs(outputs(count), synthetic_request())
        for name in self.contract.outputs:
            for change in ('missing', 'shape', 'dtype'):
                result = outputs()
                if change == 'missing':
                    del result[name]
                elif change == 'shape':
                    result[name] = result[name][:0]
                else:
                    result[name] = result[name].astype('float64')
                with self.assertRaises(ContractError):
                    self.contract.validate_outputs(result, synthetic_request())
        for name in ('pred_qpos', 'pred_foot_contacts'):
            for bad in (np.nan, np.inf, -np.inf):
                result = outputs()
                result[name][0, -1, 0] = bad  # unused padding must also be finite
                with self.assertRaises(ContractError):
                    self.contract.validate_outputs(result, synthetic_request())

    def test_hash_stable_and_content_sensitive(self):
        a = synthetic_request()
        self.assertEqual(tensor_hash(a), tensor_hash(dict(reversed(list(a.items())))))
        self.assertEqual(tensor_hash(a), 'e824c63ca2b80a570607feb58468974a88a991f133ec7db743d6edcca102347d')
        a['target_qpos'][0, 0, 0] += 1
        self.assertNotEqual(tensor_hash(a), tensor_hash(synthetic_request()))


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        tmp = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.path = Path(tmp) / 'fake.onnx'
        self.path.write_bytes(b'explicit fake session fixture')
        self.ort = fake_ort()
        self.stack.enter_context(patch.dict(sys.modules, {'onnxruntime': self.ort}))
        real_hash = __import__('motionbricks.cpu_reference', fromlist=['file_hash']).file_hash
        self.stack.enter_context(patch('motionbricks.cpu_reference.file_hash',
                                      side_effect=lambda p: MODEL_SHA256 if Path(p) == self.path else real_hash(p)))

    def test_repeat_isolation_alternation_close_and_release(self):
        ref = CPUReference(self.path)
        session_weak = weakref.ref(ref._session)
        request = synthetic_request()
        original = tensor_hash(request)
        a, _ = ref.run(request)
        ref.run(synthetic_request(16))
        b, _ = ref.run(request)
        self.assertEqual(tensor_hash(a), tensor_hash(b))
        self.assertEqual(tensor_hash(request), original)
        a['pred_qpos'][:] = 9
        self.assertFalse(np.array_equal(a['pred_qpos'], b['pred_qpos']))
        self.assertTrue(ref._session.fallback_disabled)
        ref.close()
        ref.close()
        gc.collect()
        self.assertIsNone(session_weak())
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            ref.run(request)

    def test_concurrent_requests_are_serialized(self):
        from concurrent.futures import ThreadPoolExecutor
        with CPUReference(self.path) as ref:
            active = threading.Lock()
            original = ref._session.run
            def guarded(*args):
                if not active.acquire(blocking=False):
                    raise RuntimeError('overlapping session access')
                try:
                    import time
                    time.sleep(0.005)
                    return original(*args)
                finally:
                    active.release()
            ref._session.run = guarded
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda count: ref.run(synthetic_request(count))[1]['raw_frames'],
                                        [6, 16, 6, 16]))
            self.assertEqual(results, [24, 64, 24, 64])

    def test_exception_recovery_and_context_cleanup(self):
        with CPUReference(self.path) as ref:
            ref._session.failure = True
            with self.assertRaisesRegex(RuntimeError, 'CPU inference failed'):
                ref.run(synthetic_request())
            ref._session.failure = False
            ref.run(synthetic_request())
            ref._session.values['pred_qpos'][0, 0, 0] = np.nan
            with self.assertRaises(ContractError):
                ref.run(synthetic_request())
        self.assertIsNone(ref._session)

    def test_bad_graph_metadata_and_providers(self):
        for method, value in (('get_inputs', []), ('get_providers', ['CUDAExecutionProvider'])):
            with patch.object(FakeSession, method, return_value=value):
                with self.assertRaisesRegex(RuntimeError, 'initialization failed'):
                    CPUReference(self.path)
        for attr, value in (('shape', [1, 4, 35]), ('type', 'tensor(double)')):
            nodes = FakeSession(self.path, sess_options=SimpleNamespace(intra_op_num_threads=1),
                                providers=['CPUExecutionProvider']).get_inputs()
            setattr(nodes[0], attr, value)
            with patch.object(FakeSession, 'get_inputs', return_value=nodes):
                with self.assertRaises(RuntimeError):
                    CPUReference(self.path)

    def test_missing_lfs_wrong_hash_missing_dependency(self):
        with self.assertRaises(PrerequisiteError):
            CPUReference(self.path.with_name('missing.onnx'))
        self.path.write_bytes(b'version https://git-lfs.github.com/spec/v1\n')
        with self.assertRaisesRegex(PrerequisiteError, 'LFS'):
            CPUReference(self.path)
        self.path.write_bytes(b'fake')
        with patch('motionbricks.cpu_reference.file_hash', return_value='wrong'):
            with self.assertRaisesRegex(ContractError, 'SHA-256'):
                CPUReference(self.path)
        with patch.dict(sys.modules, {'onnxruntime': None}):
            with self.assertRaisesRegex(PrerequisiteError, 'onnxruntime'):
                CPUReference(self.path)

    def test_cli_and_no_cuda_imports(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(main(['--validate-only']), 0)
        self.assertEqual(json.loads(buffer.getvalue())['evidence'], 'CONTRACT_ONLY')
        for argv, expected in ((['--model', str(self.path), '--repeat', '2'], 0),
                               (['--repeat', '0'], 1),
                               (['--model', str(self.path) + '.missing'], 2)):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv), expected)
        code = "from motionbricks.cpu_reference import synthetic_request; import sys; assert not any(x in sys.modules for x in ['warp', 'tensorrt', 'onnxruntime', 'newton'])"
        subprocess.run([sys.executable, '-c', code], check=True)


@unittest.skipUnless(os.environ.get('MOTIONBRICKS_CPU_ONNX_MODEL'),
                     'G1 BLOCKED: set MOTIONBRICKS_CPU_ONNX_MODEL to hydrated G1 FP32 ONNX to opt in')
class RealInferenceTests(unittest.TestCase):
    def test_real_lengths_repeat_and_independence(self):
        # Explicit opt-in makes missing dependencies/assets or inference errors FAIL.
        reports = []
        with CPUReference(os.environ['MOTIONBRICKS_CPU_ONNX_MODEL']) as ref:
            baseline = None
            for count in (6, 16, 6):
                arrays, report = ref.run(synthetic_request(count))
                self.assertEqual(report['raw_frames'], 4 * count)
                self.assertEqual(report['trimmed_frames'], 4 * count - 6)
                reports.append(report)
                if baseline is None:
                    baseline = arrays
                elif count == 6:
                    for name in arrays:
                        np.testing.assert_array_equal(arrays[name], baseline[name])
        print(json.dumps({'real_cpu_reports': reports, 'cross_backend_parity': 'NOT_TESTED'}))
        with self.assertRaises(RuntimeError):
            ref.run(synthetic_request())


if __name__ == '__main__':
    unittest.main()
