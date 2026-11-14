# SPDX-License-Identifier: Apache-2.0
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from motionbricks import movable_type_ledger as m
from motionbricks.radix_ipc import canonical
from motionbricks.radix_portability import ContractError

A = hashlib.sha256(b'original receipt').hexdigest()
B = hashlib.sha256(b'revised receipt').hexdigest()


def record(key='test', digest=A):
    return m.entry(m.TYPE_RECORD, key, digest)


def revise(key='test', revision=1, digest=B):
    return m.entry(m.TYPE_REVISE, key, digest, expected_revision=revision)


def reference_root(leaves):
    # Independent iterative RFC 9162 2.1.2 reference; no recursive implementation.
    stack = []
    for i, leaf in enumerate(leaves):
        stack.append(hashlib.sha256(b'\x00' + leaf).digest())
        cursor = i
        while cursor & 1:
            right, left = stack.pop(), stack.pop()
            stack.append(hashlib.sha256(b'\x01' + left + right).digest())
            cursor >>= 1
    if not stack:
        return hashlib.sha256(b'').digest()
    while len(stack) > 1:
        right, left = stack.pop(), stack.pop()
        stack.append(hashlib.sha256(b'\x01' + left + right).digest())
    return stack[0]


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = m.Ledger('research-v1')

    def reject_unchanged(self, block, error=ContractError):
        before = self.ledger.snapshot(), self.ledger.state, self.ledger.tip
        with self.assertRaises(error):
            self.ledger.append(block)
        self.assertEqual(before, (self.ledger.snapshot(), self.ledger.state, self.ledger.tip))

    def test_template_reused_without_reusing_occurrence(self):
        block = self.ledger.propose([record('a'), record('b')])
        self.assertEqual(block['entries'][0]['type_id'], block['entries'][1]['type_id'])
        self.ledger.append(block)
        self.assertEqual(2, len(self.ledger.state))
        self.assertEqual(1, self.ledger.height)
        with self.assertRaises(ContractError):
            self.ledger.propose([record('a')])

    def test_separate_replica_objects_replay_same_bytes(self):
        replica = m.Ledger('research-v1')
        for items in ([record()], [revise()], [record('other')]):
            block = self.ledger.propose(items)
            self.ledger.append(block)
            replica.append(deepcopy(block))
        self.assertEqual(self.ledger.tip, replica.tip)
        self.assertEqual(self.ledger.state, replica.state)
        self.assertEqual({'artifact_sha256': B, 'revision': 2}, replica.state['test'])

    def test_key_order_does_not_change_history(self):
        other = m.Ledger('research-v1')
        item = record()
        reordered = {'args': dict(reversed(list(item['args'].items()))), 'type_id': m.TYPE_RECORD}
        self.ledger.append(self.ledger.propose([item]))
        other.append(other.propose([reordered]))
        self.assertEqual(self.ledger.tip, other.tip)

    def test_entry_order_is_committed(self):
        first = self.ledger.propose([record('a'), record('b')])
        second = self.ledger.propose([record('b'), record('a')])
        self.assertNotEqual(first['header']['entries_root'], second['header']['entries_root'])
        self.assertEqual(first['header']['state_root'], second['header']['state_root'])

    def test_caller_mutation_cannot_rewrite_stored_blocks_or_state(self):
        item = record()
        block = self.ledger.propose([item])
        tip = self.ledger.append(block)
        item['args']['key'] = 'changed'
        block['entries'][0]['args']['artifact_sha256'] = B
        self.ledger.state['test']['revision'] = 999
        self.ledger.snapshot()['blocks'].clear()
        self.assertEqual(tip, self.ledger.tip)
        self.assertEqual(1, self.ledger.state['test']['revision'])
        self.assertEqual(A, self.ledger.state['test']['artifact_sha256'])

    def test_tampered_header_fields_fail_atomically(self):
        block = self.ledger.propose([record()])
        mutations = {'format': 2, 'chain_id': 'other', 'rulebook': B,
                     'entry_count': 2, 'entries_root': B, 'state_root': B,
                     'height': 2, 'previous': B}
        for field, value in mutations.items():
            with self.subTest(field=field):
                changed = deepcopy(block)
                changed['header'][field] = value
                self.reject_unchanged(changed)

    def test_tampered_body_is_not_accepted(self):
        block = self.ledger.propose([record()])
        block['entries'][0]['args']['artifact_sha256'] = B
        self.reject_unchanged(block)

    def test_failed_second_entry_never_partially_commits_first(self):
        block = self.ledger.propose([record()])
        block['entries'].append(record())
        self.reject_unchanged(block)

    def test_replayed_block_and_sibling_fork_are_rejected(self):
        block = self.ledger.propose([record('one')])
        sibling = self.ledger.propose([record('two')])
        self.ledger.append(block)
        self.reject_unchanged(block, m.ForkError)
        self.reject_unchanged(sibling, m.ForkError)

    def test_stale_revision_and_missing_record_are_rejected(self):
        with self.assertRaises(ContractError):
            self.ledger.propose([revise()])
        self.ledger.append(self.ledger.propose([record(), revise()]))
        before = self.ledger.snapshot()
        with self.assertRaises(ContractError):
            self.ledger.propose([revise()])
        self.assertEqual(before, self.ledger.snapshot())

    def test_unknown_templates_and_invalid_values(self):
        cases = [lambda: m.entry(B, 'key', A),
                 lambda: record('space in key'), lambda: record('中文'),
                 lambda: record('x' * 97), lambda: record(digest=A.upper()),
                 lambda: record(digest='not-a-hash'),
                 lambda: revise(revision=True), lambda: revise(revision=1.0),
                 lambda: revise(revision=0), lambda: revise(revision=-1)]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ContractError):
                case()

    def test_extra_fields_and_boolean_header_numbers_fail(self):
        for section, field, value in [('header', 'format', True),
                                      ('header', 'entry_count', 1.0),
                                      ('header', 'uncommitted', 1)]:
            block = self.ledger.propose([record()])
            block[section][field] = value
            self.reject_unchanged(block)
        block = self.ledger.propose([record()])
        block['entries'][0]['args']['unknown'] = 'ignored?'
        self.reject_unchanged(block)

    def test_empty_and_excessive_blocks_rejected(self):
        for items in ([], [record(str(i)) for i in range(65)]):
            with self.assertRaises(ContractError):
                self.ledger.propose(items)

    def test_protocol_block_limit(self):
        self.ledger.append(self.ledger.propose([record()]))
        for revision in range(1, m.MAX_BLOCKS):
            self.ledger.append(self.ledger.propose([revise(revision=revision)]))
        self.assertEqual(m.MAX_BLOCKS, self.ledger.height)
        with self.assertRaises(ContractError):
            self.ledger.propose([revise(revision=m.MAX_BLOCKS)])

    def test_protocol_record_limit(self):
        for offset in range(0, m.MAX_RECORDS, m.MAX_ENTRIES):
            self.ledger.append(self.ledger.propose([record(str(i)) for i in range(offset, offset + m.MAX_ENTRIES)]))
        with self.assertRaises(ContractError):
            self.ledger.propose([record('overflow')])

    def test_snapshot_capacity_failure_does_not_mutate(self):
        block = self.ledger.propose([record()])
        with patch.object(m, 'MAX_SNAPSHOT', 100):
            self.reject_unchanged(block)


class MerkleTests(unittest.TestCase):
    def test_reference_roots_and_every_leaf_for_sizes_1_to_64(self):
        self.assertEqual(reference_root([]), m.merkle_root([]))
        for count in range(1, 65):
            items = [record(str(i)) for i in range(count)]
            leaves = [canonical(item) for item in items]
            root = m.merkle_root(leaves).hex()
            self.assertEqual(reference_root(leaves).hex(), root)
            for index, item in enumerate(items):
                self.assertTrue(m.verify_inclusion(item, m.inclusion_proof(items, index), root=root, size=count))

    def test_odd_tree_is_not_duplicate_last_leaf(self):
        leaves = [canonical(record(str(i))) for i in range(3)]
        self.assertNotEqual(m.merkle_root(leaves), m.merkle_root(leaves + [leaves[-1]]))

    def test_proof_tampering_missing_extra_size_index_leaf_and_root(self):
        items = [record(str(i)) for i in range(5)]
        root = m.merkle_root([canonical(x) for x in items]).hex()
        proof = m.inclusion_proof(items, 2)
        variants = []
        for key, value in [('size', 4), ('index', 5), ('index', True),
                           ('siblings', proof['siblings'][:-1]),
                           ('siblings', proof['siblings'] + [A]),
                           ('siblings', [B] * len(proof['siblings']))]:
            changed = deepcopy(proof)
            changed[key] = value
            variants.append(changed)
        for changed in variants:
            with self.subTest(proof=changed), self.assertRaises(ContractError):
                m.verify_inclusion(items[2], changed, root=root, size=5)
        for item, claimed_root in [(record('wrong'), root), (items[2], A)]:
            with self.assertRaises(ContractError):
                m.verify_inclusion(item, proof, root=claimed_root, size=5)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'ledger.json'
        self.ledger = m.Ledger('research-v1')
        self.ledger.append(self.ledger.propose([record()]))
        self.anchor = self.ledger.save(self.path)

    def load(self, expected_tip=None):
        return m.Ledger.load(self.path, chain_id='research-v1',
                             expected_tip=self.anchor['tip'] if expected_tip is None else expected_tip)

    def test_atomic_round_trip_and_file_digest(self):
        restored = self.load()
        self.assertEqual(self.ledger.snapshot(), restored.snapshot())
        self.assertEqual(self.anchor['file_sha256'], hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_empty_chain_round_trip(self):
        empty = m.Ledger('empty')
        anchor = empty.save(self.path)
        restored = m.Ledger.load(self.path, chain_id='empty', expected_tip=anchor['tip'])
        self.assertEqual(0, restored.height)

    def test_truncation_and_valid_rewrite_fail_pinned_tip(self):
        snapshot = self.ledger.snapshot()
        snapshot['blocks'].clear()
        self.path.write_bytes(canonical(snapshot))
        with self.assertRaises(ContractError):
            self.load()
        other = m.Ledger('research-v1')
        other.append(other.propose([record(digest=B)]))
        other.save(self.path)
        with self.assertRaises(ContractError):
            self.load()
        # Demonstrates the trust boundary: accepting the attacker's own tip
        # accepts their internally valid rewrite. A hash is not authentication.
        self.assertEqual(other.tip, self.load(other.tip).tip)

    def test_wrong_chain_and_rulebook_rejected(self):
        with self.assertRaises(ContractError):
            m.Ledger.load(self.path, chain_id='other', expected_tip=self.anchor['tip'])
        snapshot = self.ledger.snapshot()
        snapshot['rulebook'] = B
        self.path.write_bytes(canonical(snapshot))
        with self.assertRaises(ContractError):
            self.load()

    def test_duplicate_keys_noncanonical_nonfinite_trailing_and_oversized(self):
        raw = self.path.read_bytes()
        variants = [raw.replace(b'"format":1', b'"format":1,"format":1', 1),
                    b' ' + raw, raw + b'\n', raw + b'{}',
                    raw.replace(b'"format":1', b'"format":NaN', 1),
                    b'x' * (m.MAX_SNAPSHOT + 1), b'{',
                    b'[' * 13 + b']' * 13]
        for bad in variants:
            self.path.write_bytes(bad)
            with self.subTest(length=len(bad)), self.assertRaises(ContractError):
                self.load()

    def test_fsync_failure_before_replace_preserves_previous_file(self):
        before = self.path.read_bytes()
        self.ledger.append(self.ledger.propose([revise()]))
        with patch.object(m.os, 'fsync', side_effect=OSError('injected fsync failure')):
            with self.assertRaises(OSError):
                self.ledger.save(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([], list(self.path.parent.glob('*.tmp')))
        self.assertEqual(self.anchor['tip'], self.load().tip)

    def test_replace_failure_preserves_previous_file_and_cleans_temp(self):
        before = self.path.read_bytes()
        self.ledger.append(self.ledger.propose([revise()]))
        with patch.object(m.os, 'replace', side_effect=OSError('injected replace failure')):
            with self.assertRaises(OSError):
                self.ledger.save(self.path)
        self.assertEqual(before, self.path.read_bytes())
        self.assertEqual([], list(self.path.parent.glob('*.tmp')))

    @unittest.skipUnless(os.name == 'posix', 'POSIX directory fsync behavior')
    def test_directory_fsync_failure_is_reported_after_replace(self):
        self.ledger.append(self.ledger.propose([revise()]))
        original = os.fsync
        calls = []

        def injected(fd):
            calls.append(fd)
            if len(calls) == 2:
                raise OSError('injected directory fsync failure')
            original(fd)

        with patch.object(m.os, 'fsync', side_effect=injected):
            with self.assertRaises(OSError):
                self.ledger.save(self.path)
        # The new bytes are visible; claiming the previous snapshot survived
        # every possible fsync failure would be incorrect.
        self.assertEqual(self.ledger.tip, self.load(self.ledger.tip).tip)


if __name__ == '__main__':
    unittest.main()
