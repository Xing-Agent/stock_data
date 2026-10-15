"""Cache full profiles and baseline caps; never download bars or freeze a cohort."""

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
import json
import math
import os
from pathlib import Path
import time

from prepare_daily_expansion import eligible_profile


def group_for_cap(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError('Invalid historical market cap')
    return 'large' if value >= 10_000_000_000 else 'mid' if value >= 2_000_000_000 else 'small'


def load_symbol(symbol, output, api_key):
    import httpx

    path = output / (symbol + '.json')
    previous = None
    if path.exists():
        previous = json.loads(path.read_text())
        if previous.get('reason') not in {'ConnectError', 'ConnectTimeout', 'ReadTimeout', 'RemoteProtocolError'}:
            return previous
    record = {'symbol': symbol, 'status': 'unavailable', 'market_cap_date': '2015-12-31'}
    try:
        with httpx.Client(timeout=40) as client:
            def get(endpoint, **params):
                for attempt in range(3):
                    try:
                        response = client.get('https://financialmodelingprep.com/stable/' + endpoint,
                                              params={**params, 'symbol': symbol, 'apikey': api_key})
                        if response.status_code not in (429, 502, 503, 504) or attempt == 2:
                            break
                    except httpx.RequestError:
                        if attempt == 2:
                            raise
                    time.sleep(attempt + 1)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, list):
                    raise ValueError('Provider returned a non-list')
                return data
            profiles = get('profile')
            record['profiles'] = profiles
            if len(profiles) != 1 or profiles[0].get('symbol') != symbol:
                record['reason'] = 'missing_or_ambiguous_profile'
            elif not eligible_profile(profiles[0]) or not profiles[0].get('sector'):
                record['reason'] = 'ineligible_profile'
            elif not profiles[0].get('ipoDate') or profiles[0]['ipoDate'] > '2016-01-01':
                record['reason'] = 'new_or_unknown_security_ipo'
            else:
                rows = get('historical-market-capitalization', **{'from': '2015-12-31', 'to': '2015-12-31'})
                record['historical_cap_rows'] = rows
                observations = [row for row in rows if row.get('date') == '2015-12-31' and row.get('symbol') == symbol]
                if len(observations) != 1:
                    record['reason'] = 'missing_or_ambiguous_baseline_cap'
                else:
                    record['size_group'] = group_for_cap(observations[0].get('marketCap'))
                    record['status'] = 'metadata_available_not_pit_identity_verified'
    except (httpx.HTTPError, ValueError) as exc:
        record['status'] = 'fetch_failed_not_missing_data'
        record['reason'] = type(exc).__name__  # Do not log URLs containing API keys.
    record['retrieved_at_unix'] = time.time()
    if previous:
        attempts = previous.pop('previous_attempts', [])
        record['previous_attempts'] = [*attempts, previous]
    with path.open('w' if previous else 'x') as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--limit', type=int, default=400)
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error('--limit must be positive')
    key = os.getenv('FMP_API_KEY')
    if not key:
        parser.error('FMP_API_KEY is required; never store it in reports')
    review = json.loads(args.review.read_text())
    if review['status'] != 'candidate_review_not_frozen':
        parser.error('Expected an unfrozen candidate review')
    args.output.mkdir(parents=True, exist_ok=True)
    # Preserve the prepared randomized order. This does not select by bar availability.
    symbols = [row['symbol'] for row in review['survivor_candidates'][:args.limit]]
    counts = Counter()
    with ThreadPoolExecutor(max_workers=2) as workers:
        for index, start in enumerate(range(0, len(symbols), 2)):
            all_cached = all((args.output / (symbol + '.json')).exists() for symbol in symbols[start:start + 2])
            futures = [workers.submit(load_symbol, symbol, args.output, key) for symbol in symbols[start:start + 2]]
            for future in futures:
                result = future.result()
                counts[result.get('size_group', 'unavailable')] += 1
            if index % 10 == 0 or start + 2 >= len(symbols):
                print(json.dumps({'processed': min(start + 2, len(symbols)), 'counts': dict(counts)}), flush=True)
            if all(counts[group] >= needed for group, needed in review['new_size_required'].items()):
                print(json.dumps({'metadata_pool_covers_size_quotas': True, 'counts': dict(counts)}), flush=True)
                break
            if not all_cached:
                time.sleep(0.5)


if __name__ == '__main__':
    main()
