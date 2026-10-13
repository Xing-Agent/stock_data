"""Task-local pilot orchestration. Prices use the existing fetch_market_bars.py."""
import asyncio
from collections import Counter
from datetime import UTC, datetime
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import math
import shutil
from datetime import date
from zoneinfo import ZoneInfo
from agent.tools.providers.market_data import _us_equity_session_closes

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from agent.auth_service import encode_access_token
from xing_core.db.models import User

ROOT = Path('/app/artifacts/companyfacts-audit/pilot_50')
SEED = 20261013

def save(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def fmp(client, endpoint, **params):
    r = client.get('https://financialmodelingprep.com/stable/' + endpoint,
                   params={**params, 'apikey': os.environ['FMP_API_KEY']})
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list):
        raise ValueError('FMP did not return a list: ' + endpoint)
    return data

def common(item):
    return (item.get('country') == 'US' and not item.get('isEtf') and not item.get('isFund') and not item.get('isAdr')
            and re.fullmatch('[A-Z]{1,5}', item.get('symbol', ''))
            and not re.search(r'\b(preferred|warrant|depositary|acquisition|units?|fund|ETF)\b',
                              item.get('companyName', ''), re.I))

def select_samples():
    ROOT.mkdir(parents=True, exist_ok=True)
    randomizer = random.Random(SEED)
    with httpx.Client(timeout=45) as client:
        inventories = {}
        for state, day in [('active', '2016-01-01'), ('active', '2025-12-31'), ('delisted', '2025-12-31')]:
            r = client.get('https://www.alphavantage.co/query', params={
                'function': 'LISTING_STATUS', 'date': day, 'state': state,
                'apikey': os.environ['ALPHA_VANTAGE_API_KEY']})
            r.raise_for_status()
            rows = list(csv.DictReader(io.StringIO(r.text)))
            if not rows or 'symbol' not in rows[0]:
                raise ValueError('Historical listing inventory unavailable')
            inventories[state + '_' + day] = rows
        save('selection/listing_inventories.json', inventories)
        baseline = {row['symbol']: row for row in inventories['active_2016-01-01']
                    if row['assetType'] == 'Stock' and row['exchange'] in {'NYSE', 'NASDAQ', 'AMEX'}
                    and row['ipoDate'] <= '2016-01-01'}
        survivors = {row['symbol'] for row in inventories['active_2025-12-31']}
        retired = {row['symbol']: row for row in inventories['delisted_2025-12-31']
                   if row['symbol'] in baseline and '2021-01-01' <= row['delistingDate'] <= '2025-12-31'}
        current = fmp(client, 'company-screener', country='US', isEtf='false', isFund='false', limit=10000)
        save('selection/fmp_profiles_snapshot.json', current)
        candidates = sorted((item for item in current if common(item) and item['symbol'] in baseline
                             and item['symbol'] in survivors), key=lambda item: item['symbol'])
        sectors = sorted({item['sector'] for item in candidates if item.get('sector')})
        randomizer.shuffle(candidates)
        retired_symbols = sorted(retired)
        randomizer.shuffle(retired_symbols)
        chosen, rejected, sizes, sector_counts = [], [], Counter(), Counter()
        profiles = {}
        targets = {'large': 17, 'mid': 17, 'small': 16}

        def admit(item, delisted=False):
            symbol = item['symbol']
            if 'isAdr' not in item:
                detail = fmp(client, 'profile', symbol=symbol)
                if not detail:
                    rejected.append({'symbol': symbol, 'reason': 'missing_full_profile'})
                    return False
                item = detail[0]
            profiles[symbol] = item
            if not common(item) or not item.get('sector'):
                rejected.append({'symbol': symbol, 'reason': 'ineligible_or_missing_profile'})
                return False
            if item.get('ipoDate') and item['ipoDate'] > '2016-01-01':
                rejected.append({'symbol': symbol, 'reason': 'possible_reused_symbol_new_ipo'})
                return False
            observations = fmp(client, 'historical-market-capitalization', symbol=symbol,
                               **{'from': '2015-12-31', 'to': '2015-12-31'})
            observation = next((x for x in observations if x.get('date') == '2015-12-31'
                                and isinstance(x.get('marketCap'), (int, float)) and x['marketCap'] > 0), None)
            if observation is None:
                rejected.append({'symbol': symbol, 'reason': 'missing_baseline_market_cap'})
                return False
            cap = observation['marketCap']
            size = 'large' if cap >= 10_000_000_000 else 'mid' if cap >= 2_000_000_000 else 'small'
            if sizes[size] >= targets[size]:
                rejected.append({'symbol': symbol, 'reason': 'size_quota_full', 'size': size})
                return False
            record = {'symbol': symbol, 'name': item['companyName'], 'exchange': baseline[symbol]['exchange'],
                      'ipo_date': baseline[symbol]['ipoDate'], 'market_cap_date': observation['date'],
                      'market_cap_usd': cap, 'size_group': size, 'sector': item['sector'],
                      'sector_basis': 'FMP current profile; not historical GICS', 'is_adr': item.get('isAdr'),
                      'industry': item.get('industry'), 'delisted': delisted,
                      'delisting_date': retired[symbol]['delistingDate'] if delisted else None}
            chosen.append(record)
            sizes[size] += 1
            sector_counts[item['sector']] += 1
            print(json.dumps({'selected': len(chosen), **record}), flush=True)
            return True

        for symbol in retired_symbols:
            profile = fmp(client, 'profile', symbol=symbol)
            if profile:
                admit(profile[0], True)
            else:
                rejected.append({'symbol': symbol, 'reason': 'missing_delisted_profile'})
            if len(chosen) == 3:
                break
        if len(chosen) < 3:
            raise ValueError('Cannot select three verified delisted profiles')
        # Round-robin sectors prevents a populous sector dominating the pilot.
        queues = {sector: [item for item in candidates if item.get('sector') == sector] for sector in sectors}
        while len(chosen) < 50 and any(queues.values()):
            for sector in sorted(sectors, key=lambda x: (sector_counts[x], x)):
                if queues[sector]:
                    admit(queues[sector].pop(0))
                if len(chosen) == 50:
                    break
        if len(chosen) != 50 or set(sector_counts) != set(sectors):
            raise ValueError('Pilot quotas could not be satisfied')
        manifest = {'created_at': datetime.now(UTC).isoformat(), 'seed': SEED,
                    'baseline_date': '2016-01-01', 'market_cap_date': '2015-12-31',
                    'size_counts': dict(sizes), 'sector_counts': dict(sector_counts),
                    'delisted_count': sum(x['delisted'] for x in chosen),
                    'selection_method': 'Fixed-seed randomized candidates, round-robin current FMP sectors, historical USD market-cap quotas; three delisted quota first',
                    'limitations': ['Current provider sectors are not historical GICS.',
                                    'Fixed delisted quota is for engineering coverage, not an estimate of population delisting rates.',
                                    'Unavailable profiles or baseline market caps excluded; eligibility introduces coverage bias.',
                                    'Provider historical market caps are not independently verified PIT share-count observations.',
                                    'Ticker/IPO checks do not guarantee complete permanent-security identity mapping.',
                                    'Listing API historical dates do not establish independently verified historical exchange/name/ticker metadata.'],
                    'daily_window': ['2016-01-01', '2025-12-31'],
                    'five_minute_window': ['2021-01-01', '2025-12-31'],
                    'stocks': sorted(chosen, key=lambda x: x['symbol']), 'rejected_candidates': rejected}
        save('manifest.json', manifest)
        save('selection/verified_profiles.json', profiles)

async def access_token():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    try:
        async with async_sessionmaker(engine)() as session:
            user = await session.scalar(select(User).where(User.email.like('earnings-smoke-%@example.com'), User.status == 'active'))
            if user is None:
                raise ValueError('Existing test account unavailable')
            return encode_access_token(user.id)
    finally:
        await engine.dispose()

def download():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    token = asyncio.run(access_token())
    results = []
    partition = int(sys.argv[2]) if len(sys.argv) > 2 else None
    report_name = 'download_report.json' if partition is None else f'download_report_{partition}.json'
    stocks = [item for i, item in enumerate(manifest['stocks']) if partition is None or i % 3 == partition]
    for item in stocks:
        for interval, name, start in [('1d', 'daily.json', '2016-01-01'), ('5min', '5min.json', '2021-01-01')]:
            destination = ROOT / item['symbol'] / name
            # Stop at source-listed delisting; do not invent post-delisting bars.
            end = min('2025-12-31', item['delisting_date'] or '2025-12-31')
            if not destination.exists():
                run = subprocess.run([sys.executable, 'scripts/fetch_market_bars.py', item['symbol'],
                    '--base-url', 'http://127.0.0.1:8000', '--interval', interval,
                    '--start-date', start, '--end-date', end, '--include-actions',
                    '--timeout', '1200', '--output', str(destination)],
                    env={**os.environ, 'XING_BEARER_TOKEN': token}, capture_output=True, text=True)
                if run.returncode not in (0, 2):
                    result = {'symbol': item['symbol'], 'interval': interval, 'exit_code': run.returncode,
                              'error': run.stderr[-600:].replace(token, '[REDACTED]')}
                    results.append(result)
                    print(json.dumps(result), flush=True)
                    save(report_name, results)
                    continue
            data = json.loads(destination.read_text())
            bars = data.get('data', [])
            actions = data.get('corporate_actions', {})
            time_field = 'date' if interval == '1d' else 'time'
            times = [bar[time_field] for bar in bars]
            valid = (bool(bars) and data.get('adjustment') == 'raw' and times == sorted(set(times))
                     and all(start <= str(t)[:10] <= end for t in times)
                     and all(bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high'] for bar in bars))
            result = {'symbol': item['symbol'], 'interval': interval, 'status': data.get('status'),
                      'bars': len(bars), 'first': times[0] if times else None, 'last': times[-1] if times else None,
                      'requested_end': end, 'validation_passed': valid, 'actions_status': actions.get('status'),
                      'actions_count': len(actions.get('events', [])),
                      'missing_payment_dates': actions.get('missing_payment_dates', []),
                      'missing_months': data.get('missing_months', []),
                      'sha256': hashlib.sha256(destination.read_bytes()).hexdigest()}
            results.append(result)
            save(report_name, results)
            print(json.dumps(result), flush=True)

def audit():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    reports = []
    for stock in manifest['stocks']:
        for interval, filename, start in [('1d', 'daily.json', '2016-01-01'), ('5min', '5min.json', '2021-01-01')]:
            path = ROOT / stock['symbol'] / filename
            if not path.exists():
                reports.append({'symbol': stock['symbol'], 'interval': interval, 'status': 'file_missing', 'validation_passed': False})
                continue
            data = json.loads(path.read_text())
            bars, actions = data.get('data', []), data.get('corporate_actions', {})
            key = 'date' if interval == '1d' else 'time'
            times = [bar[key] for bar in bars]
            end = min('2025-12-31', stock['delisting_date'] or '2025-12-31')
            session_closes = {day: close for year in range(int(start[:4]), int(end[:4]) + 1)
                              for day, close in _us_equity_session_closes(year).items()
                              if start <= day.isoformat() <= end}
            expected = len(session_closes) if interval == '1d' else sum(
                ((close.hour * 60 + close.minute) - (9 * 60 + 30)) // 5 for close in session_closes.values())
            issues = []
            if not bars: issues.append('no_bars')
            if data.get('adjustment') != 'raw': issues.append('not_raw')
            if times != sorted(set(times)): issues.append('timestamps_not_unique_and_sorted')
            if any(not start <= t[:10] <= end for t in times): issues.append('outside_requested_range')
            if any(not all(isinstance(bar.get(k), (float, int)) and math.isfinite(bar[k]) and bar[k] >= 0
                           for k in ('open', 'high', 'low', 'close', 'volume')) for bar in bars):
                issues.append('invalid_ohlcv')
            if any(not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high'] for bar in bars):
                issues.append('inconsistent_ohlc_bounds')
            if interval == '5min':
                for timestamp in times:
                    instant = datetime.fromisoformat(timestamp)
                    local = instant.astimezone(ZoneInfo('America/New_York'))
                    close = session_closes.get(local.date())
                    if (instant.utcoffset() != local.utcoffset() or close is None or
                        not (9, 30) <= (local.hour, local.minute) < (close.hour, close.minute)
                        or local.minute % 5 or local.second):
                        issues.append('invalid_regular_session_timestamp')
                        break
            elif any(date.fromisoformat(timestamp) not in session_closes for timestamp in times):
                issues.append('non_trading_day_bar')
            reports.append({'symbol': stock['symbol'], 'interval': interval, 'status': data.get('status'),
                'bars': len(bars), 'first': times[0] if times else None, 'last': times[-1] if times else None,
                'requested_end': end, 'validation_passed': not issues, 'validation_issues': issues,
                'calendar_expected_bars': expected, 'absent_calendar_bars': max(0, expected - len(bars)),
                'calendar_note': 'Absent bars include illiquid no-trade intervals and vendor gaps; not synthesized.',
                'actions_status': actions.get('status'), 'actions_count': len(actions.get('events', [])),
                'missing_payment_dates': actions.get('missing_payment_dates', []),
                'missing_months': data.get('missing_months', []),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'ohlcv_sha256': hashlib.sha256(json.dumps([
                    {k: bar[k] for k in (key, 'open', 'high', 'low', 'close', 'volume')} for bar in bars
                ], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(),
                'corporate_actions_sha256': hashlib.sha256(json.dumps(actions.get('events', []),
                    sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()})
    save('download_report.json', reports)
    summary = {'stocks': len(manifest['stocks']), 'files': len(reports),
               'status_counts': dict(Counter(x['status'] for x in reports)),
               'validated_files': sum(x['validation_passed'] for x in reports),
               'issues': [x for x in reports if not x['validation_passed'] or x['status'] != 'ready' or x.get('actions_status') != 'ready'],
               'supplier_missing_payment_dates': {x['symbol'] + ':' + x['interval']: x['missing_payment_dates'] for x in reports if x.get('missing_payment_dates')}}
    save('acceptance_summary.json', summary)
    with (ROOT / 'manifest.csv').open('w') as out:
        fields = ['symbol', 'name', 'exchange', 'size_group', 'market_cap_usd', 'market_cap_date', 'sector', 'sector_basis', 'delisted', 'delisting_date']
        writer = csv.DictWriter(out, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(manifest['stocks'])
    print(json.dumps({key: value for key, value in summary.items() if key != 'issues'}), flush=True)

def retry():
    manifest = json.loads((ROOT / 'manifest.json').read_text())
    token = asyncio.run(access_token())
    attempt = int(sys.argv[2])
    partition = int(sys.argv[3]) if len(sys.argv) > 3 else None
    report_name = 'selection/retry_attempts.json' if partition is None else f'selection/retry_attempts_{attempt}_{partition}.json'
    attempts_path = ROOT / report_name
    attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else []
    with httpx.Client(timeout=40) as client:
        stocks = [item for i, item in enumerate(manifest['stocks']) if partition is None or i % 3 == partition]
        for item in stocks:
            for interval, name, start in [('1d', 'daily.json', '2016-01-01'), ('5min', '5min.json', '2021-01-01')]:
                path = ROOT / item['symbol'] / name
                if not path.exists(): continue
                old = json.loads(path.read_text())
                if old.get('status') == 'ready' and old.get('corporate_actions', {}).get('status') == 'ready': continue
                missing = old.get('missing_months', [])
                first_month = old['data'][0]['time'][:7] if interval == '5min' and old.get('data') else None
                unsupported_prefix = bool(first_month and missing and all(month < first_month for month in missing))
                if interval == '5min' and ((item['delisted'] and not old.get('data')) or unsupported_prefix):
                    try:
                        r = client.get('https://www.alphavantage.co/query', params={
                            'function': 'TIME_SERIES_INTRADAY', 'symbol': item['symbol'], 'interval': '5min',
                            'month': missing[0] if missing else '2021-01', 'outputsize': 'full', 'extended_hours': 'false', 'adjusted': 'false',
                            'apikey': os.environ['ALPHA_VANTAGE_API_KEY']})
                        diagnostic = r.json()
                    except (httpx.RequestError, ValueError) as error:
                        attempts.append({'symbol': item['symbol'], 'interval': interval, 'attempt': attempt,
                                         'probe_error_type': type(error).__name__, 'probe_month': '2021-01'})
                        save(report_name, attempts)
                        print(json.dumps(attempts[-1]), flush=True)
                        continue
                    if diagnostic.get('Error Message'):
                        attempts.append({'symbol': item['symbol'], 'interval': interval, 'attempt': attempt,
                                         'supplier_error': diagnostic['Error Message'], 'probe_month': '2021-01'})
                        save(report_name, attempts)
                        print(json.dumps(attempts[-1]), flush=True)
                        continue
                end = min('2025-12-31', item['delisting_date'] or '2025-12-31')
                target = ROOT.parent / 'pilot_50_retries' / item['symbol'] / f'{interval}_{attempt}.json'
                run = subprocess.run([sys.executable, 'scripts/fetch_market_bars.py', item['symbol'],
                    '--base-url', 'http://127.0.0.1:8000', '--interval', interval,
                    '--start-date', start, '--end-date', end, '--include-actions', '--timeout', '1200', '--output', str(target)],
                    env={**os.environ, 'XING_BEARER_TOKEN': token}, capture_output=True, text=True)
                if not target.exists():
                    attempts.append({'symbol': item['symbol'], 'interval': interval, 'attempt': attempt,
                                     'exit_code': run.returncode, 'error': run.stderr[-600:].replace(token, '[REDACTED]')})
                else:
                    new = json.loads(target.read_text())
                    def rank(data):
                        return (data.get('status') == 'ready', len(data.get('data', [])),
                                data.get('corporate_actions', {}).get('status') == 'ready')
                    improved = rank(new) > rank(old)
                    if improved: shutil.copyfile(target, path)
                    attempts.append({'symbol': item['symbol'], 'interval': interval, 'attempt': attempt,
                        'previous_status': old.get('status'), 'status': new.get('status'),
                        'bars': len(new.get('data', [])), 'missing_months': new.get('missing_months', []),
                        'actions_status': new.get('corporate_actions', {}).get('status'), 'adopted': improved,
                        'retry_payload_sha256': hashlib.sha256(target.read_bytes()).hexdigest()})
                save(report_name, attempts)
                print(json.dumps(attempts[-1]), flush=True)

if sys.argv[1] == 'select':
    select_samples()
elif sys.argv[1] == 'download':
    download()
elif sys.argv[1] == 'audit':
    audit()
elif sys.argv[1] == 'retry':
    retry()
