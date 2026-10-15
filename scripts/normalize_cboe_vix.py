"""Normalize an untouched CBOE CSV snapshot; preserve the provider export separately."""

import argparse
import csv
from datetime import datetime
import hashlib
import json
import math


def normalize(path, start, end):
    bars = []
    with path.open(newline='') as source:
        for row in csv.DictReader(source):
            day = datetime.strptime(row['DATE'], '%m/%d/%Y').date().isoformat()
            if not start <= day <= end:
                continue
            bar = {'date': day, **{key: float(row[key.upper()]) for key in ('open', 'high', 'low', 'close')}}
            if any(not math.isfinite(bar[key]) or bar[key] <= 0 for key in ('open', 'high', 'low', 'close')):
                raise ValueError('Invalid CBOE index points')
            if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
                raise ValueError('Inconsistent CBOE OHLC')
            bars.append(bar)
    bars.sort(key=lambda bar: bar['date'])
    if not bars or len({bar['date'] for bar in bars}) != len(bars):
        raise ValueError('Missing or duplicate CBOE dates')
    return {'symbol': 'VIX', 'status': 'ready', 'provider': 'cboe', 'asset_type': 'index',
            'unit': 'index_points', 'adjustment': 'not_applicable',
            'source_url': 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv',
            'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'start_date': start, 'end_date': end, 'data': bars,
            'note': 'Index session calendar is not identical to equities; align SPY trading dates explicitly for the regime gate.'}


if __name__ == '__main__':
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--csv', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', default='2014-01-01')
    parser.add_argument('--end', default='2025-12-31')
    args = parser.parse_args()
    result = normalize(args.csv, args.start, args.end)
    with args.output.open('x') as target:
        json.dump(result, target, ensure_ascii=False, indent=2)
        target.write('\n')
    print(json.dumps({'symbol': 'VIX', 'provider': 'cboe', 'bars': len(result['data'])}))
