#!/usr/bin/env python3
"""Read-only inventory of committed Git blobs for PRODUCT-V1 cleanup planning.

No deletion or ref mutation is performed. The only write is an optional JSON
report at --json. Counts are based on `git ls-tree` and represent logical
path sizes, not git object store disk consumption.
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
from pathlib import Path

CANDIDATE_ROOT = 'docs/R5_4_2/autonomous_2026_10_07/'
CATEGORIES = (
    'checkpoint_history/',
    'normative_build_candidate/',
    'build_schema_fixtures/',
    'golden_build_candidate/',
    'build_time_candidate/',
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', default='.', help='Git working tree path')
    parser.add_argument('--ref', default='HEAD', help='Local ref to inventory')
    parser.add_argument('--json', dest='json_output', help='Optional JSON output file (no other file writes)')
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    if not (root / '.git').exists():
        # A linked git worktree stores .git as a file, which also passes exists().
        raise SystemExit('Not a Git worktree root: ' + str(root))
    proc = subprocess.run(
        ['git', '-C', str(root), 'ls-tree', '-r', '-l', '-z', args.ref],
        capture_output=True, check=True,
    )
    summary = collections.defaultdict(lambda: {'files': 0, 'logical_bytes': 0})
    identity = collections.defaultdict(list)
    total = 0
    for rec in proc.stdout.split(b'\0'):
        if not rec:
            continue
        meta, raw_path = rec.split(b'\t', 1)
        mode, typ, sha, raw_size = meta.split()
        if typ != b'blob' or raw_size == b'-':
            continue
        path = raw_path.decode('utf-8', errors='surrogateescape')
        size = int(raw_size)
        total += size
        if path.startswith(CANDIDATE_ROOT):
            rel = path[len(CANDIDATE_ROOT):]
            category = next((c.rstrip('/') for c in CATEGORIES if rel.startswith(c)), 'other_r5_4_2_autonomous')
        elif path.startswith('src/'):
            category = 'PROTECT_src'
        elif path.startswith('tests/'):
            category = 'PROTECT_tests'
        elif path.startswith('docs/'):
            category = 'other_docs_REVIEW'
        else:
            category = 'other_root_REVIEW'
        summary[category]['files'] += 1
        summary[category]['logical_bytes'] += size
        identity[sha.decode('ascii')].append({'path': path, 'size': size, 'category': category})
    duplicates = [{
        'blob_sha': sha,
        'count': len(entries),
        'logical_repeat_bytes': (len(entries) - 1) * entries[0]['size'],
        'examples': [x['path'] for x in entries[:5]],
    } for sha, entries in identity.items() if len(entries) > 1]
    duplicates.sort(key=lambda row: (-row['logical_repeat_bytes'], row['blob_sha']))
    report = {
        'kind': 'READ_ONLY_GIT_TREE_INVENTORY',
        'ref': args.ref,
        'candidate_paths_are_not_approved_for_deletion': True,
        'total_logical_bytes': total,
        'distinct_blob_ids': len(identity),
        'categories': dict(sorted(summary.items())),
        'repeated_identical_blob_logical_bytes': sum(x['logical_repeat_bytes'] for x in duplicates),
        'duplicate_groups': len(duplicates),
        'largest_duplicate_groups': duplicates[:20],
        'warning': 'Deleting paths does not remove committed blobs from Git history.',
    }
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    print(encoded)
    if args.json_output:
        dest = Path(args.json_output)
        if not dest.is_absolute():
            dest = root / dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(encoded, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
