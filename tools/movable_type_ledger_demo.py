# SPDX-License-Identifier: Apache-2.0
"""Run from a repository checkout; no GPU or third-party packages required."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motionbricks.movable_type_ledger import (  # noqa: E402
    Ledger, TYPE_RECORD, TYPE_REVISE, entry, inclusion_proof, verify_inclusion,
)
from motionbricks.radix_ipc import canonical, run_mixed_dot  # noqa: E402
from motionbricks.radix_portability import (  # noqa: E402
    BinaryIntegerBackend, BalancedTernaryBackend, BalancedSeptenaryBackend, run_dot,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--ipc', action='store_true', help='also run bounded POSIX binary/ternary workers')
    args = parser.parse_args(argv)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    # Do not overwrite the user's earlier experiment or its external anchor.
    if any(args.out_dir.iterdir()):
        parser.error('--out-dir must be empty')

    lhs, rhs = [7, -11, 5, 2], [-3, 9, 0, -1]
    results = [run_dot(lhs, rhs, backend) for backend in
               (BinaryIntegerBackend(), BalancedTernaryBackend(), BalancedSeptenaryBackend())]
    expected = sum(a * b for a, b in zip(lhs, rhs))
    if expected != -122 or any(result['value'] != expected for result in results):
        raise RuntimeError('integer reference mismatch')
    receipt = {'experiment': 'integer-dot', 'lhs': lhs, 'rhs': rhs,
               'value': expected, 'local_backends': results,
               'ipc': run_mixed_dot(lhs, rhs, timeout_s=5, total_timeout_s=10) if args.ipc else None}
    raw = canonical(receipt)
    (args.out_dir / 'radix-receipt.json').write_bytes(raw)
    artifact = hashlib.sha256(raw).hexdigest()

    ledger, replica = Ledger('motionbricks-evidence-v1'), Ledger('motionbricks-evidence-v1')
    first = ledger.propose([entry(TYPE_RECORD, 'radix:dot', artifact),
                            entry(TYPE_RECORD, 'demo:fixture', hashlib.sha256(b'fixture-v1').hexdigest())])
    ledger.append(first)
    replica.append(first)
    revised = ledger.propose([entry(TYPE_REVISE, 'demo:fixture',
                                    hashlib.sha256(b'fixture-v2').hexdigest(), expected_revision=1)])
    ledger.append(revised)
    replica.append(revised)
    proof = inclusion_proof(first['entries'], 0)
    verify_inclusion(first['entries'][0], proof, root=first['header']['entries_root'],
                     size=first['header']['entry_count'])
    anchor = ledger.save(args.out_dir / 'ledger.json')
    restored = Ledger.load(args.out_dir / 'ledger.json', chain_id='motionbricks-evidence-v1',
                           expected_tip=anchor['tip'])
    if replica.tip != ledger.tip or restored.state != ledger.state:
        raise RuntimeError('replica replay or checkpoint restore mismatch')
    report = {'scope': 'single-writer research prototype; no signatures or distributed consensus',
              'artifact_sha256': artifact, 'anchor': anchor,
              'replica_tip_matches': replica.tip == ledger.tip,
              'restored_state_matches': restored.state == ledger.state,
              'inclusion_proof': proof, 'integer_value': expected,
              'ipc_executed': args.ipc, 'state': ledger.state}
    # Co-located anchor is a demonstration, not an independent trust service.
    (args.out_dir / 'report.json').write_bytes(canonical(report))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
