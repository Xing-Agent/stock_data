"""Freeze the approved stock identities and bounded requests, not data availability."""

import argparse
import copy
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def freeze(root, accept_alternative_baseline):
    directory = root / 'pilot_300'
    draft_path = directory / 'manifest.draft.json'
    result = copy.deepcopy(json.loads(draft_path.read_text()))
    if result['status'] != 'draft_requires_user_review_not_frozen' or not accept_alternative_baseline:
        raise ValueError('Explicit alternative-baseline approval is required')
    for name, digest in result['source_sha256'].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Source changed since draft: {name}')
    cutoff_path = directory / 'selection/download_cutoffs.json'
    cutoffs = {row['symbol']: row for row in json.loads(cutoff_path.read_text())['stocks']}
    ledger = {row['symbol']: row for row in json.loads((directory / 'selection/retirement_event_review.json').read_text())['events']}
    for row in result['stocks']:
        symbol = row['symbol']
        row['download_start_date'] = '2016-01-01'
        row['download_end_date'] = '2025-12-31'
        row['review_flags'] = [flag for flag in row.get('review_flags', [])
                               if flag != 'alternative_baseline_evidence_requires_approval']
        if symbol in result['alternative_baseline_candidates_requiring_approval']:
            row['baseline_listing_basis'] = row['baseline_listing_basis'].replace('approval required', 'alternative evidence accepted; not strict PIT')
            row['review_flags'].append('alternative_baseline_accepted_not_strict_pit')
        if row['origin'] == 'pilot_50':
            data_path = root / 'pilot_50' / symbol / 'daily.json'
            row['data_path'] = f'../pilot_50/{symbol}/daily.json'
            row['source_data_sha256'] = hashlib.sha256(data_path.read_bytes()).hexdigest()
            row['download_end_date'] = min(row['delisting_date'] or '2025-12-31', '2025-12-31')
            continue
        row['data_path'] = f'{symbol}/daily.json'
        if symbol in cutoffs:
            row['download_cutoff'] = cutoffs[symbol]
            row['download_end_date'] = cutoffs[symbol]['download_end_date']
            if not cutoffs[symbol]['cutoff_event_confirmed']:
                row['review_flags'].append('announced_cutoff_requires_review')
        elif row['delisted']:
            event = ledger[symbol]
            bounds = [day for day in (row['delisting_date'], event['event_date']) if day]
            if not bounds:
                raise ValueError(f'Missing retirement download bound: {symbol}')
            row['download_end_date'] = min(bounds)
            row['download_cutoff'] = {'basis': 'earliest_provider_delisting_or_official_merger_completion',
                'source_url': event['source_url'], 'last_trade_independently_verified': False}
        if row['download_end_date'] < row['download_start_date']:
            raise ValueError(f'Invalid download window: {symbol}')
    if len(result['stocks']) != 300 or len({row['symbol'] for row in result['stocks']}) != 300:
        raise ValueError('Expected 300 unique stock identities')
    result.update(status='frozen_sample_and_download_windows',
                  frozen_at=datetime.now(timezone.utc).isoformat(),
                  alternative_baseline_approval='User explicitly accepted the 13 alternatives in this chat',
                  frozen_from_draft_sha256=hashlib.sha256(draft_path.read_bytes()).hexdigest())
    result['source_sha256'][str(cutoff_path.relative_to(root))] = hashlib.sha256(cutoff_path.read_bytes()).hexdigest()
    result['limitations'] = [note for note in result['limitations'] if not note.startswith('This is not a download authorization')]
    result['limitations'].append('Frozen membership does not imply complete price coverage or verified terminal proceeds. Announced cutoff warnings remain unresolved.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--accept-alternative-baseline', action='store_true')
    args = parser.parse_args()
    result = freeze(args.root, args.accept_alternative_baseline)
    directory = args.root / 'pilot_300'
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    for name in ('manifest.json', 'manifest.csv', 'manifest.sha256'):
        if (directory / name).exists():
            raise FileExistsError(f'Frozen artifact already exists: {name}')
    with (directory / 'manifest.json').open('x') as output: output.write(encoded)
    with (directory / 'manifest.sha256').open('x') as output:
        output.write(hashlib.sha256(encoded.encode()).hexdigest() + '  manifest.json\n')
    with (directory / 'manifest.csv').open('x', newline='') as output:
        fields = ['symbol','name','origin','size_group','sector','delisted','retirement_category',
                  'download_start_date','download_end_date','data_path','baseline_listing_basis']
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader();writer.writerows(result['stocks'])
    print(json.dumps({'status': result['status'], 'stocks': len(result['stocks'])}))
