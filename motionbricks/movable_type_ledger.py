# SPDX-License-Identifier: Apache-2.0
"""Movable-type evidence ledger: a deterministic blockchain core experiment.

Single trusted writer; no signatures, peer transport, or distributed consensus.
Reuse radix IPC's bounded canonical codec, not its worker as a consensus oracle.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import struct
import tempfile
from types import MappingProxyType

from .radix_ipc import canonical, fields, integer, unpack
from .radix_portability import ContractError

MAX_BLOCKS = 256
MAX_ENTRIES = 64
MAX_RECORDS = 4096
MAX_SNAPSHOT = 2 * 1024 * 1024
MAX_BLOCK_BYTES = 32 * 1024
KEY = re.compile(r'[A-Za-z0-9._:-]{1,96}\Z')
HEX = re.compile(r'[0-9a-f]{64}\Z')

# Descriptors identify fixed, audited semantics. They never load executable code.
_SPECS = (
    {'name': 'evidence.record', 'version': 1,
     'args': ['key', 'artifact_sha256'], 'effect': 'create-at-revision-1'},
    {'name': 'evidence.revise', 'version': 1,
     'args': ['key', 'artifact_sha256', 'expected_revision'],
     'effect': 'compare-revision-then-replace-and-increment'},
)


def _hash(tag: bytes, raw: bytes) -> str:
    return hashlib.sha256(b'motionbricks.movable-type.v1\0' + tag + b'\0' + raw).hexdigest()


TYPE_RECORD, TYPE_REVISE = (_hash(b'type', canonical(s)) for s in _SPECS)
TYPES = MappingProxyType({TYPE_RECORD: canonical(_SPECS[0]),
                          TYPE_REVISE: canonical(_SPECS[1])})
RULEBOOK = _hash(b'rulebook', canonical({'format': 1, 'types': sorted(TYPES),
                                      'max_blocks': MAX_BLOCKS,
                                      'max_entries': MAX_ENTRIES,
                                      'max_records': MAX_RECORDS,
                                      'max_snapshot_bytes': MAX_SNAPSHOT,
                                      'max_block_bytes': MAX_BLOCK_BYTES}))


class ForkError(ContractError):
    """Not an extension of the pinned local head; no fork is silently chosen."""


def _key(value):
    if type(value) is not str or not KEY.fullmatch(value):
        raise ContractError('invalid ASCII key or chain ID')
    return value


def _hex(value):
    if type(value) is not str or not HEX.fullmatch(value):
        raise ContractError('expected lowercase SHA-256')
    return value


def _decode(raw: bytes, limit=MAX_SNAPSHOT):
    if type(raw) is not bytes or not 0 < len(raw) <= limit:
        raise ContractError('encoded object outside byte limit')
    return unpack(struct.pack('!I', len(raw)) + raw, limit)


def _copy(value, limit=MAX_BLOCK_BYTES):
    try:
        return _decode(canonical(value), limit)
    except (TypeError, ValueError, UnicodeError, RecursionError) as exc:
        raise ContractError('invalid or oversized canonical object') from exc


def entry(type_id, key, artifact_sha256, *, expected_revision=None):
    """Create one occurrence of an immutable template. Validate again on append."""
    args = {'key': key, 'artifact_sha256': artifact_sha256}
    if expected_revision is not None:
        args['expected_revision'] = expected_revision
    result = {'type_id': type_id, 'args': args}
    _validate_entry(result)
    return result


def _validate_entry(item):
    fields(item, 'type_id args')
    type_id = _hex(item['type_id'])
    if type_id not in TYPES:
        raise ContractError('unknown type/version; explicit rulebook upgrade required')
    args = item['args']
    names = 'key artifact_sha256'
    if type_id == TYPE_REVISE:
        names += ' expected_revision'
    fields(args, names)
    _key(args['key'])
    _hex(args['artifact_sha256'])
    if type_id == TYPE_REVISE:
        integer(args['expected_revision'], 1, MAX_BLOCKS * MAX_ENTRIES)


def _entries(items):
    if type(items) is not list or not 1 <= len(items) <= MAX_ENTRIES:
        raise ContractError('block requires 1..64 ordered entries')
    for item in items:
        _validate_entry(item)
    return _copy(items)


def _reduce(state, items):
    result = {k: dict(v) for k, v in state.items()}
    for item in items:
        args = item['args']
        key = args['key']
        old = result.get(key)
        if item['type_id'] == TYPE_RECORD:
            if old is not None:
                raise ContractError('record already exists; replay rejected')
            if len(result) >= MAX_RECORDS:
                raise ContractError('record limit reached')
            revision = 1
        else:
            if old is None or old['revision'] != args['expected_revision']:
                raise ContractError('missing record or stale revision; replay rejected')
            revision = old['revision'] + 1
        result[key] = {'artifact_sha256': args['artifact_sha256'], 'revision': revision}
    return result


def merkle_root(leaves):
    """RFC 9162 section 2.1 tree shape, SHA-256, including empty and odd trees."""
    if type(leaves) is not list or len(leaves) > MAX_ENTRIES or any(type(x) is not bytes for x in leaves):
        raise ContractError('bounded list of byte leaves required')
    if not leaves:
        return hashlib.sha256(b'').digest()
    if len(leaves) == 1:
        return hashlib.sha256(b'\x00' + leaves[0]).digest()
    split = 1 << ((len(leaves) - 1).bit_length() - 1)
    return hashlib.sha256(b'\x01' + merkle_root(leaves[:split]) + merkle_root(leaves[split:])).digest()


def inclusion_proof(items, index):
    items = _entries(items)
    integer(index, 0, len(items) - 1)
    leaves = [canonical(x) for x in items]

    def path(part, i):
        if len(part) == 1:
            return []
        split = 1 << ((len(part) - 1).bit_length() - 1)
        if i < split:
            return path(part[:split], i) + [merkle_root(part[split:]).hex()]
        return path(part[split:], i - split) + [merkle_root(part[:split]).hex()]

    return {'index': index, 'size': len(items), 'siblings': path(leaves, index)}


def verify_inclusion(item, proof, *, root, size):
    """Root AND size must come from an independently trusted block header."""
    _validate_entry(item)
    fields(proof, 'index size siblings')
    integer(size, 1, MAX_ENTRIES)
    integer(proof['size'], 1, MAX_ENTRIES)
    integer(proof['index'], 0, size - 1)
    _hex(root)
    siblings = proof['siblings']
    if proof['size'] != size or type(siblings) is not list or len(siblings) > 6:
        raise ContractError('invalid proof shape or tree size')
    for sibling in siblings:
        _hex(sibling)
    used = 0

    def rebuild(i, n):
        nonlocal used
        if n == 1:
            return hashlib.sha256(b'\x00' + canonical(item)).digest()
        split = 1 << ((n - 1).bit_length() - 1)
        child = rebuild(i, split) if i < split else rebuild(i - split, n - split)
        if used >= len(siblings):
            raise ContractError('truncated proof')
        sibling = bytes.fromhex(siblings[used])
        used += 1
        left, right = (child, sibling) if i < split else (sibling, child)
        return hashlib.sha256(b'\x01' + left + right).digest()

    computed = rebuild(proof['index'], size)
    if used != len(siblings) or computed.hex() != root:
        raise ContractError('inclusion proof mismatch')
    return True


class Ledger:
    """Serial, bounded evidence state machine with an append-only public API.

    A local writer may forge an internally consistent history. Retain a trusted
    tip separately. Matching hashes prove byte/history consistency, not truth.
    """
    def __init__(self, chain_id):
        self._chain_id = _key(chain_id)
        self._genesis = _hash(b'genesis', canonical({'chain_id': chain_id,
                                                  'format': 1, 'rulebook': RULEBOOK}))
        self._blocks = []  # canonical bytes: caller mutation cannot change history
        self._state = {}

    @property
    def height(self):
        return len(self._blocks)

    @property
    def tip(self):
        if not self._blocks:
            return self._genesis
        return _hash(b'header', canonical(_decode(self._blocks[-1])['header']))

    @property
    def state(self):
        return {key: dict(value) for key, value in self._state.items()}

    def _header(self, items, state):
        return {'format': 1, 'chain_id': self._chain_id, 'rulebook': RULEBOOK,
                'height': self.height + 1, 'previous': self.tip,
                'entry_count': len(items),
                'entries_root': merkle_root([canonical(x) for x in items]).hex(),
                'state_root': _hash(b'state', canonical(state))}

    def propose(self, items):
        if self.height >= MAX_BLOCKS:
            raise ContractError('block limit reached')
        items = _entries(items)
        state = _reduce(self._state, items)
        block = {'header': self._header(items, state), 'entries': items}
        return _copy(block)

    def append(self, block):
        # Validate every field and the complete transition before changing memory.
        fields(block, 'header entries')
        fields(block['header'], 'format chain_id rulebook height previous entry_count entries_root state_root')
        header = block['header']
        for name in ('format', 'height', 'entry_count'):
            integer(header[name], 1)
        _key(header['chain_id'])
        for name in ('rulebook', 'previous', 'entries_root', 'state_root'):
            _hex(header[name])
        if header['height'] != self.height + 1 or header['previous'] != self.tip:
            raise ForkError('block does not extend the pinned head')
        candidate = self.propose(block['entries'])
        if canonical(header) != canonical(candidate['header']):
            raise ContractError('header, rulebook, entries, or resulting state mismatch')
        raw = canonical(candidate)
        # Do not create an in-memory chain that cannot be snapshotted under v1.
        size = len(canonical(self._snapshot(extra=candidate)))
        if size > MAX_SNAPSHOT:
            raise ContractError('snapshot byte limit reached')
        state = _reduce(self._state, candidate['entries'])
        self._blocks.append(raw)
        self._state = state
        return self.tip

    def _snapshot(self, extra=None):
        blocks = [_decode(raw) for raw in self._blocks]
        if extra is not None:
            blocks.append(extra)
        return {'format': 1, 'chain_id': self._chain_id, 'rulebook': RULEBOOK, 'blocks': blocks}

    def snapshot(self):
        return self._snapshot()

    def save(self, path):
        """Atomic replace for a single trusted writer; no concurrent writer lock.

        A directory-fsync error after replace means durability is uncertain even
        though the new file may already be visible. Never report that as success.
        """
        path = Path(path)
        raw = canonical(self._snapshot())
        if len(raw) > MAX_SNAPSHOT:
            raise ContractError('snapshot too large')
        name = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + '.',
                                             suffix='.tmp', delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            name = None
            if os.name == 'posix':
                descriptor = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            if name is not None:
                Path(name).unlink(missing_ok=True)
        return {'height': self.height, 'tip': self.tip,
                'file_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    @classmethod
    def load(cls, path, *, chain_id, expected_tip):
        """Replay from pinned chain identity and an OUT-OF-BAND trusted tip."""
        _hex(expected_tip)
        with Path(path).open('rb') as stream:
            raw = stream.read(MAX_SNAPSHOT + 1)
        data = _decode(raw)
        fields(data, 'format chain_id rulebook blocks')
        integer(data['format'], 1, 1)
        if data['chain_id'] != chain_id or data['rulebook'] != RULEBOOK:
            raise ContractError('snapshot chain identity or rulebook mismatch')
        if type(data['blocks']) is not list or len(data['blocks']) > MAX_BLOCKS:
            raise ContractError('snapshot block count invalid')
        ledger = cls(chain_id)
        for block in data['blocks']:
            ledger.append(block)
        if ledger.tip != expected_tip:
            raise ContractError('trusted tip mismatch: truncation, fork, or rewrite')
        return ledger
