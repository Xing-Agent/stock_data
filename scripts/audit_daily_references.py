"""Audit exported benchmark daily files without treating VIX as an equity."""

import argparse
from datetime import date
import hashlib
import json
import math
from pathlib import Path


def audit(path, sessions):
    payload = json.loads(path.read_text())
    symbol = path.parent.name
    bars = payload.get('data', [])
    days = [bar.get('date', '') for bar in bars]
    issues = []
    if not bars:
        issues.append('no_bars')
    if days != sorted(set(days)):
        issues.append('dates_not_unique_and_sorted')
    index = symbol == 'VIX'
    if payload.get('adjustment') != ('not_applicable' if index else 'raw'):
        issues.append('unexpected_price_basis')
    if index and payload.get('unit') != 'index_points':
        issues.append('unexpected_index_unit')
    fields = ('open', 'high', 'low', 'close') if index else ('open', 'high', 'low', 'close', 'volume')
    for bar in bars:
        if any(isinstance(bar.get(key), bool) or not isinstance(bar.get(key), (int, float))
               or not math.isfinite(bar[key]) or bar[key] < 0 for key in fields):
            issues.append('invalid_numeric_values')
            break
        if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
            issues.append('inconsistent_ohlc')
            break
    start, end = payload['start_date'], payload['end_date']
    for day in days:
        try:
            parsed = date.fromisoformat(day)
            if not start <= day <= end or parsed.isoformat() != day:
                raise ValueError('Invalid date')
        except ValueError:
            issues.append('invalid_or_out_of_range_date')
            break
    expected = {day for day in sessions if start <= day <= end}
    actions = payload.get('corporate_actions', {})
    if not index and actions.get('status') != 'ready':
        issues.append('corporate_actions_not_ready')
    return {'symbol': symbol, 'file': path.name, 'status': payload.get('status'), 'bars': len(bars),
            'first': days[0] if days else None, 'last': days[-1] if days else None,
            'structural_validation_passed': not issues, 'issues': issues,
            'missing_us_equity_sessions': sorted(expected - set(days)),
            'dates_outside_us_equity_calendar': sorted(set(days) - expected),
            'calendar_note': 'Equity calendar comparison only; VIX index-session differences require source review.',
            'actions_status': None if index else actions.get('status'),
            'actions_warnings': [] if index else actions.get('warnings', []),
            'payment_date_issues': [] if index else actions.get('payment_date_issues', []),
            'missing_payment_dates': [] if index else actions.get('missing_payment_dates', []),
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'ohlcv_sha256': hashlib.sha256(json.dumps([
                {key: bar.get(key) for key in ('date', *fields)} for bar in bars
            ], sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--calendar', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    sessions = json.loads(args.calendar.read_text())['session_dates']
    report = {'files': [audit(path, sessions) for path in sorted(args.root.glob('*/daily*.json'))],
              'calendar_sha256': hashlib.sha256(args.calendar.read_bytes()).hexdigest()}
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(report, ensure_ascii=False))


if __name__ == '__main__':
    main()
