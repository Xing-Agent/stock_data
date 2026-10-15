"""Prepare, but do not freeze, the daily-only expansion from preserved snapshots."""

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re


DISTRESS_REVIEW = {
    'BBBY': 'Bed Bath & Beyond (old common stock)',
    'REV': 'Revlon', 'ENDP': 'Endo International',
    'SRNE': 'Sorrento Therapeutics', 'TUP': 'Tupperware Brands',
    'YELL': 'Yellow Corporation', 'PRTY': 'Party City Holdco',
    'EXPR': 'Express', 'WPG': 'Washington Prime Group',
    'SQBG': 'Sequential Brands Group', 'DBD': 'Diebold Nixdorf (old common stock)',
    'WW': 'WW International (old common stock)',
    'FRC': 'First Republic Bank', 'SIVB': 'SVB Financial Group',
    'SBNY': 'Signature Bank',
}


def eligible_profile(row, allow_unknown=False):
    return (row.get('country') == 'US'
            and all(row.get(key) is False or (allow_unknown and row.get(key) is None)
                    for key in ('isEtf', 'isFund', 'isAdr'))
            and re.fullmatch(r'[A-Z]{1,5}', row.get('symbol', '')) is not None
            and not re.search(r'\b(preferred|warrant|depositary|acquisition|units?|fund|ETF)\b',
                              row.get('companyName', ''), re.I))


def listing_groups(rows):
    groups = defaultdict(list)
    for row in rows:
        if (row.get('assetType') == 'Stock'
                and row.get('exchange') in {'NYSE', 'NASDAQ', 'AMEX'}
                and row.get('ipoDate', '9999') <= '2016-01-01'):
            groups[row['symbol']].append(row)
    return groups


def ambiguous(rows):
    return len({(row.get('name'), row.get('ipoDate'), row.get('exchange'))
                for row in rows}) > 1


def prepare(root):
    pilot = root / 'pilot_50'
    paths = [pilot / 'manifest.json', pilot / 'selection/listing_inventories.json',
             pilot / 'selection/fmp_profiles_snapshot.json']
    original, inventory, profiles = [json.loads(path.read_text()) for path in paths]
    stocks = original['stocks']
    if len(stocks) != 50 or len({x['symbol'] for x in stocks}) != 50:
        raise ValueError('Expected the unchanged original 50 unique stocks')
    excluded = {x['symbol'] for x in stocks}
    baseline = listing_groups(inventory['active_2016-01-01'])
    retired = listing_groups(inventory['delisted_2025-12-31'])
    active = listing_groups(inventory['active_2025-12-31'])
    pool, rejected = [], []
    seen = set()
    for profile in sorted(profiles, key=lambda x: x.get('symbol', '')):
        symbol = profile.get('symbol')
        if symbol in excluded or symbol in seen or symbol not in baseline or symbol not in active:
            continue
        seen.add(symbol)
        if symbol in DISTRESS_REVIEW:
            rejected.append({'symbol': symbol, 'reason': 'distress_security_requires_identity_review'})
        elif ambiguous(baseline[symbol]) or ambiguous(active[symbol]):
            rejected.append({'symbol': symbol, 'reason': 'ambiguous_listing_identity'})
        elif not eligible_profile(profile, allow_unknown=True) or not profile.get('sector'):
            rejected.append({'symbol': symbol, 'reason': 'ineligible_or_unverified_profile'})
        elif profile.get('ipoDate') and profile['ipoDate'] > '2016-01-01':
            rejected.append({'symbol': symbol, 'reason': 'possible_new_security_or_reused_ticker'})
        else:
            pool.append({'symbol': symbol, 'name': profile.get('companyName'),
                         'sector': profile['sector'], 'ipo_date': baseline[symbol][0]['ipoDate'],
                         'historical_market_cap_status': 'not_checked',
                         'full_profile_status': 'not_checked',
                         'security_identity_status': 'provider_screen_only_not_verified_pit'})
    random.Random(20261015).shuffle(pool)
    retired_pool = []
    for symbol, rows in sorted(retired.items()):
        if symbol in excluded or symbol not in baseline or not re.fullmatch('[A-Z]{1,5}', symbol):
            continue
        if ambiguous(rows) or ambiguous(baseline[symbol]):
            rejected.append({'symbol': symbol, 'reason': 'ambiguous_retired_identity'})
            continue
        row = rows[0]
        if '2021-01-01' <= row['delistingDate'] <= '2025-12-31':
            retired_pool.append({**row, 'reason_status': 'unverified',
                                 'historical_market_cap_status': 'not_checked'})
    review = [{'historical_symbol': symbol, 'expected_company': name,
               'in_baseline_snapshot': symbol in baseline,
               'in_retired_snapshot': symbol in retired,
               'in_active_snapshot': symbol in active,
               'reason_status': 'unverified', 'counts_toward_quota': False}
              for symbol, name in DISTRESS_REVIEW.items()]
    sizes = Counter(x['size_group'] for x in stocks)
    report = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'candidate_review_not_frozen',
        'source_sha256': {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in paths},
        'original_count': 50, 'new_required': 250, 'target_count': 300,
        'target_size_counts': {'large': 100, 'mid': 100, 'small': 100},
        'new_size_required': {key: 100 - sizes[key] for key in ('large', 'mid', 'small')},
        'daily_window': ['2016-01-01', '2025-12-31'],
        'new_five_minute_downloads': 0,
        'retired_target': 30, 'distress_minimum': 10,
        'survivor_candidate_count': len(pool), 'retired_candidate_count': len(retired_pool),
        'survivor_candidates': pool, 'retired_candidates': retired_pool,
        'distress_identity_review': review, 'rejected_candidates': rejected,
        'freeze_blockers': ['Verify historical market caps before assigning size groups.',
                            'Verify 27 additional retirement reasons, including at least 10 distress exits.',
                            'Resolve old-security identities missing from provider snapshots.',
                            'Review final 250 additions before freezing; do not select by download success.'],
        'limitations': original['limitations'],
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as output:
        json.dump(report, output, ensure_ascii=False, indent=2)
        output.write('\n')
    print(json.dumps({key: report[key] for key in ('status', 'original_count',
        'new_required', 'survivor_candidate_count', 'retired_candidate_count', 'new_size_required')}))


if __name__ == '__main__':
    main()
