import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/pyignite'))


class AdapterRefusal(unittest.TestCase):
    def test_wrong_checkpoint_cannot_be_used_as_real_weights(self):
        # The runtime package does not require safetensors. This adapter is an
        # optional offline tool, tested in the review environment.
        try:
            import safetensors
        except ImportError:
            self.skipTest('offline safetensors adapter dependency not installed')
        from g1_subset import load_g1_root_subset
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'wrong.safetensors'
            path.write_bytes(b'not a checkpoint')
            with self.assertRaisesRegex(ValueError, 'size mismatch'):
                load_g1_root_subset(path)
            # Sparse file matches the release size; its hash must still fail.
            with path.open('wb') as stream:
                stream.truncate(136510540)
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                load_g1_root_subset(path)


if __name__ == '__main__':
    unittest.main()
