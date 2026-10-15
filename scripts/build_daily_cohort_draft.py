"""Build a review-only 300-stock draft; alternative listing evidence requires approval."""

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


DISTRESS = ['AMRS', 'CLVS', 'ACOR', 'PRTY', 'REV', 'TUP', 'EXPR',
            'SQBG', 'WPG', 'SIVB', 'GTT', 'FRC', 'GNCA']
STRICT_DISTRESS = set(DISTRESS) - {'GTT', 'FRC', 'GNCA'}


def build(root):
    selection = root / 'pilot_300/selection'
    original_path = root / 'pilot_50/manifest.json'
    original = json.loads(original_path.read_text())
    review_path = selection / 'candidate_review.json'
    review = json.loads(review_path.read_text())
    ledger_path = selection / 'retirement_event_review.json'
    events = {row['symbol']: row for row in json.loads(ledger_path.read_text())['events']}
    retired = {row['symbol']: row for row in review['retired_candidates']}
    stocks = [{**row, 'origin': 'pilot_50',
               'retirement_category': events.get(row['symbol'], {}).get('category'),
               'retirement_source_url': events.get(row['symbol'], {}).get('source_url')}
              for row in original['stocks']]
    evidence_files = [original_path, review_path, ledger_path]

    def record(symbol, path, external=False):
        meta = json.loads(path.read_text())
        if meta['status'] != 'metadata_available_not_pit_identity_verified':
            raise ValueError(f'Metadata not available for {symbol}')
        profile = meta['profiles'][0]
        event = events.get(symbol, {})
        if event.get('expected_cik') and str(profile.get('cik', '')).lstrip('0') != event['expected_cik'].lstrip('0'):
            raise ValueError(f'Issuer CIK mismatch for {symbol}')
        evidence_files.append(path)
        return {'symbol': symbol, 'name': profile['companyName'],
                'size_group': meta['size_group'], 'sector': profile['sector'],
                'market_cap_date': '2015-12-31', 'market_cap_usd': next(
                    row['marketCap'] for row in meta['historical_cap_rows']
                    if row['date'] == '2015-12-31' and row['symbol'] == symbol),
                'ipo_date': profile['ipoDate'], 'cik': profile.get('cik'), 'origin': 'expansion_250',
                'delisted': bool(event), 'delisting_date': retired.get(symbol, {}).get('delistingDate'),
                'retirement_category': event.get('category'),
                'retirement_source_url': event.get('source_url'),
                'baseline_listing_basis': 'FMP IPO and baseline cap; missing AV listing; approval required'
                    if external else 'AV historical listing plus FMP profile and baseline cap',
                'review_flags': ['alternative_baseline_evidence_requires_approval', 'verify_last_trading_date']
                    if external else (['verify_last_trading_date'] if event else []),
                'sector_basis': 'FMP current profile; not historical GICS'}

    for path in sorted((selection / 'metadata_retired').glob('*.json')):
        symbol = path.stem
        meta = json.loads(path.read_text())
        if meta['status'] == 'metadata_available_not_pit_identity_verified':
            if symbol not in retired or events.get(symbol, {}).get('category') != 'acquisition_or_merger':
                raise ValueError(f'Unverified acquisition candidate {symbol}')
            stocks.append(record(symbol, path))
    if len(stocks) != 64:
        raise ValueError('Expected 14 reviewed acquisition metadata records plus the original 50')
    for symbol in DISTRESS:
        stocks.append(record(symbol, selection / 'metadata_distress' / (symbol + '.json'), external=True))
    sizes = Counter(row['size_group'] for row in stocks)
    sectors = Counter(row['sector'] for row in stocks)
    queues = defaultdict(list)
    excluded = {row['symbol'] for row in stocks}
    supplemental_path = root / 'pilot_50/supplemental/manifest.json'
    excluded.update(row['symbol'] for row in json.loads(supplemental_path.read_text())['stocks'])
    evidence_files.append(supplemental_path)
    for candidate in review['survivor_candidates']:
        path = selection / 'metadata' / (candidate['symbol'] + '.json')
        if candidate['symbol'] in excluded or not path.exists():
            continue
        meta = json.loads(path.read_text())
        if meta['status'] == 'metadata_available_not_pit_identity_verified':
            queues[meta['profiles'][0]['sector']].append((candidate['symbol'], path, meta['size_group']))
    while len(stocks) < 300 and any(queues.values()):
        for sector in sorted(queues, key=lambda key: (sectors[key], key)):
            while queues[sector]:
                symbol, path, group = queues[sector].pop(0)
                if sizes[group] < 100:
                    stocks.append(record(symbol, path));sizes[group] += 1;sectors[sector] += 1
                    break
            if len(stocks) == 300:
                break
    if len(stocks) != 300 or any(sizes[group] != 100 for group in ('large', 'mid', 'small')):
        raise ValueError(f'Metadata pool still insufficient: stocks={len(stocks)}, sizes={dict(sizes)}')
    if len({row['symbol'] for row in stocks}) != 300:
        raise ValueError('Duplicate stock identity in draft')
    return {'status': 'draft_requires_user_review_not_frozen',
            'created_at': datetime.now(timezone.utc).isoformat(), 'stocks': stocks,
            'size_counts': dict(sizes), 'sector_counts': dict(sectors),
            'retired_count': sum(row['delisted'] for row in stocks),
            'strict_distress_event_candidates': sorted(STRICT_DISTRESS),
            'alternative_baseline_candidates_requiring_approval': DISTRESS,
            'daily_window': ['2016-01-01', '2025-12-31'], 'new_intraday_downloads': 0,
            'source_sha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in evidence_files},
            'limitations': original['limitations'] + [
                'Thirteen candidates are missing from AV historical listings; FMP IPO/cap and primary event evidence are an explicitly proposed alternative, not verified PIT listings.',
                'CIK validates issuer identity only, not permanent security-class continuity.',
                'Metadata availability, current sectors, and survival-conditioned sampling introduce coverage bias.',
                'No final trading cutoff or delisting settlement is inferred from a bankruptcy or merger date.',
                'This is not a download authorization manifest; review the alternative baseline evidence before freezing.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build(args.root)
    with args.output.open('x') as output:
        json.dump(result, output, ensure_ascii=False, indent=2);output.write('\n')
    csv_path = args.output.with_suffix('.csv')
    with csv_path.open('x', newline='') as output:
        fields = ['symbol', 'name', 'size_group', 'market_cap_usd', 'sector', 'origin',
                  'delisted', 'retirement_category', 'baseline_listing_basis']
        writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore')
        writer.writeheader();writer.writerows(result['stocks'])
    print(json.dumps({key: result[key] for key in ('status', 'size_counts', 'retired_count')}))
