#!/usr/bin/env python3
"""Flag persistent extreme daily close jumps for corporate-action review.

This is a review aid, not a split detector: it never edits source bars or
asserts that a flagged move is a split. Provider adjustment metadata should
be checked alongside issuer/exchange evidence.
"""
from __future__ import annotations
import argparse
import json
import statistics
from pathlib import Path


def load_rows(path: Path):
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    rows = payload.get('data', []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            date, close = str(row['date']), float(row['close'])
        except (KeyError, TypeError, ValueError):
            continue
        if close > 0:
            out.append((date, close))
    return sorted(out)


def scan(root: Path, threshold: float = 3.0, lookahead: int = 5):
    candidates = []
    for path in sorted(root.rglob('daily.json')):
        rows = load_rows(path)
        payload = json.loads(path.read_text())
        for i in range(1, len(rows)):
            prior_date, prior = rows[i - 1]
            event_date, event_close = rows[i]
            ratio = event_close / prior
            if ratio >= threshold or ratio <= 1 / threshold:
                future = rows[i + 1:i + 1 + lookahead]
                if len(future) < lookahead:
                    continue
                median_ratio = statistics.median(v for _, v in future) / prior
                persistence = ('persistent_level_shift_candidate'
                               if median_ratio >= threshold or median_ratio <= 1 / threshold
                               else 'reverted_or_not_persistent')
                if persistence != 'persistent_level_shift_candidate':
                    continue
                candidates.append({
                    'symbol': payload.get('symbol') or path.parent.name,
                    'prior_date': prior_date,
                    'event_date': event_date,
                    'prior_close': prior,
                    'event_close': event_close,
                    'close_ratio': ratio,
                    'lookahead_sessions': len(future),
                    'lookahead_median_close_over_prior': median_ratio,
                    'candidate_status': persistence,
                    'data_file': str(path.relative_to(root)),
                    'provider': payload.get('provider'),
                    'adjustment': payload.get('adjustment'),
                    'review_required': True,
                    'interpretation': 'price-discontinuity candidate only; verify split/dividend/security identity and source adjustment semantics',
                })
    return candidates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent,
                        help='data root containing ticker/daily.json files (default: parent pilot_300 directory)')
    parser.add_argument('--output', type=Path, help='optional JSON output path; stdout by default')
    parser.add_argument('--threshold', type=float, default=3.0)
    parser.add_argument('--lookahead', type=int, default=5)
    args = parser.parse_args()
    result = {'method': {'absolute_close_jump_threshold': args.threshold,
                         'subsequent_sessions': args.lookahead,
                         'persistence_rule': 'median of next N closes remains >= threshold or <= 1/threshold versus prior close',
                         'automatic_correction': False},
              'candidate_count': 0, 'candidates': []}
    result['candidates'] = scan(args.root, args.threshold, args.lookahead)
    result['candidate_count'] = len(result['candidates'])
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        args.output.write_text(rendered)
    else:
        print(rendered, end='')

if __name__ == '__main__':
    main()
