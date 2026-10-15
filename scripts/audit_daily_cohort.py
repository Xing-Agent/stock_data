"""Audit the frozen 300-stock sample, separating prices, actions and identity limits."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from audit_daily_references import audit


def inspect(root):
    directory = root / 'pilot_300'
    manifest_path = directory / 'manifest.json'
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if digest != (directory / 'manifest.sha256').read_text().split()[0]:
        raise ValueError('Frozen manifest digest mismatch')
    manifest = json.loads(manifest_path.read_text())
    findings_path = directory / 'selection/post_download_findings.json'
    findings = {row['symbol']: row for row in json.loads(findings_path.read_text())['stocks']} if findings_path.exists() else {}
    sessions = json.loads((directory / 'selection/us_equity_sessions_2014_2025.json').read_text())['session_dates']
    rows = []
    for stock in manifest['stocks']:
        path = directory / stock['data_path']
        row = {'symbol': stock['symbol'], 'origin': stock['origin'], 'data_path': stock['data_path'],
               'size_group': stock['size_group'], 'sector': stock['sector'],
               'review_flags': stock.get('review_flags', []), 'retired': stock['delisted']}
        if not path.exists():
            row.update(status='missing_file', price_validation_passed=False, actions_status=None)
        else:
            row.update(audit(path, sessions))
            payload = json.loads(path.read_text())
            issues = [issue for issue in row['issues'] if issue != 'corporate_actions_not_ready']
            if payload.get('symbol') != stock['symbol'] or payload.get('interval') != '1d':
                issues.append('symbol_or_interval_mismatch')
            if stock['origin'] != 'pilot_50' and (payload['start_date'], payload['end_date']) != (stock['download_start_date'], stock['download_end_date']):
                issues.append('frozen_window_mismatch')
            if stock['origin'] == 'pilot_50' and row['sha256'] != stock['source_data_sha256']:
                issues.append('original_file_changed')
            if any(bar.get(key, 0) <= 0 for bar in payload.get('data', []) for key in ('open', 'high', 'low', 'close')):
                issues.append('nonpositive_price')
            if stock['symbol'] in findings:
                row['post_download_finding'] = findings[stock['symbol']]
                cutoff = findings[stock['symbol']].get('verified_last_trading_date')
                if cutoff and any(bar['date'] > cutoff for bar in payload['data']):
                    issues.append('provider_prices_after_verified_last_trade')
            row.update(price_issues=issues, price_validation_passed=not issues,
                       warnings=payload.get('warnings', []),
                       provider=payload.get('provider'),
                       zero_volume_dates=[bar['date'] for bar in payload.get('data', []) if bar.get('volume') == 0],
                       expected_sessions=row['bars'] + len(row['missing_us_equity_sessions']) - len(row['dates_outside_us_equity_calendar']),
                       actions_sha256=hashlib.sha256(json.dumps(payload.get('corporate_actions', {}), sort_keys=True, separators=(',', ':')).encode()).hexdigest())
            if payload.get('source_snapshot'):
                source = directory / payload['source_snapshot']
                row['source_snapshot'] = payload['source_snapshot']
                row['source_snapshot_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
                if row['source_snapshot_sha256'] != payload['source_snapshot_sha256']:
                    issues.append('source_snapshot_changed')
                    row['price_validation_passed'] = False
        rows.append(row)
    benchmark = directory / 'benchmarks/manifest.json'
    control = directory / 'selection/fmp_raw_probe/TSLA_split_control.json'
    return {'created_at': datetime.now(timezone.utc).isoformat(), 'manifest_sha256': digest,
            'analysis_window': manifest.get('daily_window'),
            'new_intraday_downloads': manifest.get('new_intraday_downloads'),
            'benchmark_manifest': 'benchmarks/manifest.json' if benchmark.exists() else None,
            'benchmark_manifest_sha256': hashlib.sha256(benchmark.read_bytes()).hexdigest() if benchmark.exists() else None,
            'split_scale_control_sha256': hashlib.sha256(control.read_bytes()).hexdigest() if control.exists() else None,
            'stocks': len(rows), 'files_present': sum(row['status'] != 'missing_file' for row in rows),
            'selected_size_counts': dict(Counter(row['size_group'] for row in rows)),
            'selected_retired_count': sum(row['retired'] for row in rows),
            'additional_retired_findings': [symbol for symbol, finding in findings.items() if finding.get('retired') and not next(stock['delisted'] for stock in manifest['stocks'] if stock['symbol'] == symbol)],
            'post_download_findings_sha256': hashlib.sha256(findings_path.read_bytes()).hexdigest() if findings_path.exists() else None,
            'with_prices_size_counts': dict(Counter(row['size_group'] for row in rows if row.get('bars', 0))),
            'with_prices_retired_count': sum(row['retired'] and row.get('bars', 0) > 0 for row in rows),
            'strict_distress_with_prices': [row['symbol'] for row in rows if row['symbol'] in manifest.get('strict_distress_event_candidates', []) and row.get('bars', 0) > 0],
            'price_status_counts': dict(Counter(row['status'] for row in rows)),
            'provider_counts': dict(Counter(row.get('provider') for row in rows)),
            'price_validation_passed': sum(row['price_validation_passed'] for row in rows),
            'actions_status_counts': dict(Counter(row['actions_status'] for row in rows)),
            'complete_equity_calendar': sum(row.get('bars', 0) > 0 and not row.get('missing_us_equity_sessions') and not row.get('dates_outside_us_equity_calendar') for row in rows),
            'fully_ready': sum(row['status'] == 'ready' and row['price_validation_passed'] and row['actions_status'] == 'ready' and not row.get('missing_us_equity_sessions') and not row.get('dates_outside_us_equity_calendar') for row in rows),
            'limitations': ['Price readiness is not strict PIT identity verification or terminal return readiness.',
                            'Retired securities may stop trading before request bounds; missing sessions are reported, not fabricated.',
                            'GNCA and WPG announced cutoffs still require review. No liquidation proceeds or borrow availability supplied.',
                            'Zero-volume source rows are retained, not assumed executable trades. FMP supplements are whole-series, with original API exports preserved.'],
            'files': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = inspect(args.root)
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({key: value for key, value in report.items() if key not in ('files', 'limitations')}))
