"""Export benchmark ETFs using XING's existing Alpha Vantage adapter.

Run from the backend environment (requires ALPHA_VANTAGE_API_KEY):
  python export_etf_benchmarks.py --output /path/to/new/delivery
Existing source snapshots are reused on resume; no provider key is written.
"""
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path

from agent.tools.providers.market_data import AlphaVantageMarketDataProvider, _market_failure, _us_equity_session_closes

SYMBOLS = 'SPY QQQ IWM XLK XLF XLE XLV XLI XLY XLP XLU XLB XLRE XLC'.split()
FIELDS = {'open': '1. open', 'high': '2. high', 'low': '3. low', 'close': '4. close', 'adj_close': '5. adjusted close', 'volume': '6. volume'}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)


async def main(args):
    if args.start > args.end:
        raise ValueError('Invalid date range')
    root = args.output
    provider = AlphaVantageMarketDataProvider(api_key=os.environ['ALPHA_VANTAGE_API_KEY'], timeout_seconds=45)
    sessions = {day.isoformat() for year in range(int(args.start[:4]), int(args.end[:4]) + 1)
                for day in _us_equity_session_closes(year) if args.start <= day.isoformat() <= args.end}
    manifest = {'symbols': SYMBOLS, 'requested_start': args.start, 'requested_end': args.end,
                'provider': 'alpha_vantage', 'endpoint': 'TIME_SERIES_DAILY_ADJUSTED',
                'adjustment': 'raw_ohlcv_with_vendor_adjusted_close',
                'adj_close_basis': 'vendor_snapshot_backward_adjusted_for_splits_and_dividends; not rebased to delivery_end',
                'pit_status': 'historical_vendor_snapshot_not_revision_pit', 'series': []}
    for symbol in SYMBOLS:
        source_path = root / 'sources' / f'{symbol}.json'
        if source_path.exists():
            source = json.loads(source_path.read_text())
            if source['requested_start'] != args.start or source['requested_end'] != args.end:
                raise ValueError('Resume window differs from saved snapshot')
        else:
            for attempt in range(3):
                payload = await provider._query('TIME_SERIES_DAILY_ADJUSTED', symbol, outputsize='full')
                failure = _market_failure(payload)
                if not failure and isinstance(payload, dict) and isinstance(payload.get('Time Series (Daily)'), dict):
                    break
                if attempt == 2:
                    raise RuntimeError(f'{symbol}: {failure or "missing_daily_series"}')
                await asyncio.sleep(3 * (attempt + 1))
            source = {'symbol': symbol, 'requested_start': args.start, 'requested_end': args.end,
                      'retrieved_at': datetime.now(timezone.utc).isoformat(),
                      'source_url': f'https://www.alphavantage.co/query?function=TIME_SERIES_DAILY_ADJUSTED&symbol={symbol}&outputsize=full',
                      'provider_metadata': payload.get('Meta Data'),
                      'rows': {day: row for day, row in payload['Time Series (Daily)'].items() if args.start <= day <= args.end}}
            if not source['rows']:
                raise ValueError(f'{symbol}: no rows')
            save(source_path, source)
        bars = []
        for day, row in sorted(source['rows'].items()):
            bar = {'date': day}
            for field, key in FIELDS.items():
                value = float(row[key])
                if not math.isfinite(value) or value < 0 or (field != 'volume' and value == 0):
                    raise ValueError(f'{symbol}: invalid {field} on {day}')
                if field == 'volume' and value != int(value):
                    raise ValueError(f'{symbol}: fractional volume on {day}')
                bar[field] = int(value) if field == 'volume' else value
            if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
                raise ValueError(f'{symbol}: inconsistent OHLC on {day}')
            bars.append(bar)
        actual = {bar['date'] for bar in bars}
        missing = sorted(day for day in sessions if bars[0]['date'] <= day <= bars[-1]['date'] and day not in actual)
        unexpected = sorted(actual - sessions)
        if missing or unexpected or bars[-1]['date'] != max(sessions):
            raise ValueError(f'{symbol}: session coverage mismatch: missing={missing}, unexpected={unexpected}')
        path = root / symbol / 'daily.json'
        save(path, {'status': 'ready', 'symbol': symbol, 'interval': '1d', 'timezone': 'America/New_York',
                    'provider': 'alpha_vantage', 'source_url': source['source_url'],
                    'retrieved_at': source['retrieved_at'], 'adjustment': manifest['adjustment'],
                    'adj_close_basis': manifest['adj_close_basis'], 'pit_status': manifest['pit_status'], 'data': bars})
        manifest['series'].append({'symbol': symbol, 'file': f'{symbol}/daily.json', 'bars': len(bars),
            'first': bars[0]['date'], 'last': bars[-1]['date'], 'missing_sessions_within_observed_range': missing,
            'leading_unavailable_until': bars[0]['date'] if bars[0]['date'] > min(sessions) else None,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'source_snapshot': f'sources/{symbol}.json',
            'source_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest()})
        save(root / 'manifest.json', manifest)
        print(f'{symbol}: {len(bars)} rows {bars[0]["date"]} .. {bars[-1]["date"]}; adj_close complete', flush=True)
        await asyncio.sleep(1)
    manifest['status'] = 'complete'
    manifest['created_at'] = datetime.now(timezone.utc).isoformat()
    save(root / 'manifest.json', manifest)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--start', default='2014-01-01')
    parser.add_argument('--end', default='2025-12-31')
    asyncio.run(main(parser.parse_args()))
