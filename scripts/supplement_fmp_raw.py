"""Supplement missing daily history with explicitly non-split-adjusted FMP snapshots."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import time

ENDPOINT = 'https://financialmodelingprep.com/stable/historical-price-eod/non-split-adjusted'
DOCUMENTATION = 'https://site.financialmodelingprep.com/developer/docs/stable/historical-price-eod-non-split-adjusted'
FIELDS = dict(open='adjOpen', high='adjHigh', low='adjLow', close='adjClose', volume='volume')


def normalize(record, stock):
    if record.get('endpoint') != ENDPOINT or record.get('http_status') != 200 or not isinstance(record.get('payload'), list) or not record['payload']:
        raise ValueError('No usable raw price snapshot')
    bars = []
    for row in record['payload']:
        day = row['date']
        if row.get('symbol') != stock['symbol'] or not stock['download_start_date'] <= day <= stock['download_end_date']:
            raise ValueError('Symbol or date outside frozen request')
        if datetime.strptime(day, '%Y-%m-%d').date().isoformat() != day:
            raise ValueError('Invalid date')
        bar = {'date': day, **{key: row[source] for key, source in FIELDS.items()}}
        if any(isinstance(bar[key], bool) or not isinstance(bar[key], (float, int)) or not math.isfinite(bar[key]) or bar[key] < 0 for key in FIELDS):
            raise ValueError('Invalid numeric value')
        if min(bar[key] for key in ('open', 'high', 'low', 'close')) <= 0 or not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
            raise ValueError('Invalid OHLC')
        bars.append(bar)
    bars.sort(key=lambda row: row['date'])
    if len({row['date'] for row in bars}) != len(bars):
        raise ValueError('Duplicate dates')
    return bars


def main():
    import httpx
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory
    manifest_path = directory / 'manifest.json'
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != (directory / 'manifest.sha256').read_text().split()[0]:
        raise ValueError('Frozen manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text())
    snapshots = directory / 'selection/fmp_raw_probe'
    snapshots.mkdir(parents=True, exist_ok=True)
    control = json.loads((snapshots / 'TSLA_split_control.json').read_text())
    alpha = {row['date']: row for row in json.loads((directory / 'TSLA/daily.json').read_text())['data']}
    if control.get('http_status') != 200 or {row['date'] for row in control['payload']} != {'2020-08-28', '2020-08-31'}:
        raise ValueError('Missing split-scale control')
    for row in control['payload']:
        if any(abs(row[source] / alpha[row['date']][key] - 1) > 0.001 for key, source in FIELDS.items() if key != 'volume'):
            raise ValueError('Raw split-scale control disagrees')
    with httpx.Client(timeout=60) as client:
        for stock in manifest['stocks']:
            if stock['origin'] == 'pilot_50': continue
            canonical = directory / stock['data_path']
            if not canonical.exists(): continue
            prior = json.loads(canonical.read_text())
            if len(prior.get('data', [])) > 1: continue
            record = None
            for attempt in range(3):
                suffix = '' if attempt == 0 else f'.retry-{attempt:02d}'
                source = snapshots / (stock['symbol'] + suffix + '.json')
                if source.exists():
                    record = json.loads(source.read_text())
                else:
                    record = {'symbol': stock['symbol'], 'endpoint': ENDPOINT,
                              'from': stock['download_start_date'], 'to': stock['download_end_date'],
                              'retrieved_at': datetime.now(timezone.utc).isoformat()}
                    try:
                        response = client.get(ENDPOINT, params={'symbol': stock['symbol'], 'from': record['from'], 'to': record['to'], 'apikey': os.environ['FMP_API_KEY']})
                        record.update(http_status=response.status_code, payload=response.json())
                    except (httpx.HTTPError, ValueError) as error:
                        record['error_class'] = type(error).__name__
                    with source.open('x') as stream: json.dump(record, stream, ensure_ascii=False, indent=2)
                if record.get('http_status') == 200: break
                time.sleep(attempt + 1)
            try:
                bars = normalize(record, stock)
            except (ValueError, KeyError, TypeError) as error:
                print(json.dumps({'symbol': stock['symbol'], 'status': 'supplement_unavailable', 'reason': type(error).__name__}), flush=True)
                continue
            if len(bars) <= len(prior.get('data', [])): continue
            output = {**prior, 'provider': 'fmp_non_split_adjusted', 'adjustment': 'raw',
                      'status': 'ready', 'source_url': ENDPOINT, 'data': bars, 'warnings': [],
                      'source_documentation': DOCUMENTATION, 'source_snapshot': str(source.relative_to(directory)),
                      'source_snapshot_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                      'retrieved_at': record.get('retrieved_at'),
                      'source_note': 'Whole-series fallback, no per-day splice. FMP adjOpen/adjHigh/adjLow/adjClose are mapped only for its documented non-split-adjusted endpoint. Actions retain their independent original provenance.'}
            output.pop('market_coverage', None)  # Old coverage describes the replaced series; audit recomputes it.
            target = canonical.with_name('daily.fmp-raw.json')
            with target.open('x') as stream: json.dump(output, stream, ensure_ascii=False, indent=2)
            snapshot = canonical.with_name('daily.before-fmp.json')
            if not snapshot.exists(): shutil.copyfile(canonical, snapshot)
            temporary = canonical.with_name('daily.promoting.json')
            shutil.copyfile(target, temporary)
            temporary.replace(canonical)
            print(json.dumps({'symbol': stock['symbol'], 'status': 'supplemented', 'bars': len(bars)}), flush=True)
            time.sleep(1)


if __name__ == '__main__':
    main()
