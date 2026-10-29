"""Download only the frozen expansion through the existing authenticated exporter."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--exporter', type=Path, required=True)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--symbols', nargs='+')
    parser.add_argument('--retry-unavailable', action='store_true', help='One additional export, retaining the first result and retry artifact')
    args = parser.parse_args()
    directory = args.root / 'pilot_300'
    manifest_path = directory / 'manifest.json'
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if digest != (directory / 'manifest.sha256').read_text().split()[0]:
        raise ValueError('Frozen manifest digest mismatch')
    manifest = json.loads(manifest_path.read_text())
    if manifest['status'] != 'frozen_sample_and_download_windows':
        raise ValueError('Expected a frozen manifest')
    rows = [row for row in manifest['stocks'] if row['origin'] != 'pilot_50']
    if args.symbols:
        if not set(args.symbols) <= {row['symbol'] for row in rows}:
            raise ValueError('Requested symbol is not in the frozen expansion')
        rows = [row for row in rows if row['symbol'] in args.symbols]
    for row in rows:
        output = directory / row['data_path']
        if output.resolve().parent.parent != directory.resolve() or output.name != 'daily.json':
            raise ValueError('Unsafe export path')
        canonical = output
        previous = json.loads(output.read_text()) if output.exists() else None
        if args.retry_unavailable:
            transient_actions = {'connection_error', 'timeout', 'rate_limited', 'request_failed'}
            if previous is None or (previous.get('data') and not transient_actions.intersection(previous.get('corporate_actions', {}).get('warnings', []))):
                continue
            output = canonical.with_name('daily.retry-01.json')
        code, detail = None, 'existing_file_preserved'
        if not output.exists():
            command = [sys.executable, str(args.exporter), row['symbol'], '--base-url', args.base_url,
                       '--interval', '1d', '--start-date', row['download_start_date'],
                       '--end-date', row['download_end_date'], '--include-actions', '--output', str(output)]
            for attempt in range(3):
                try:
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=1250)
                    code = completed.returncode
                    # Exporter diagnostics contain no credentials; do not print arbitrary API payloads.
                    detail = completed.stderr[-2000:]
                except subprocess.TimeoutExpired:
                    code, detail = 1, 'exporter_timeout'
                if 'HTTP 401' in detail or 'HTTP 403' in detail:
                    raise RuntimeError('API authentication/authorization failed; batch stopped')
                if output.exists() or code == 0:
                    break
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        record = {'symbol': row['symbol'], 'at': datetime.now(timezone.utc).isoformat(),
                  'manifest_sha256': digest, 'exit_code': code, 'detail': detail}
        if output.exists():
            payload = json.loads(output.read_text())
            if args.retry_unavailable:
                record['retry_sha256'] = hashlib.sha256(output.read_bytes()).hexdigest()
                record['retry_status'] = payload.get('status')
                if len(payload.get('data', [])) > len(previous.get('data', [])) or (payload.get('data') == previous.get('data') and payload.get('corporate_actions', {}).get('status') == 'ready' and previous.get('corporate_actions', {}).get('status') != 'ready'):
                    initial = canonical.with_name('daily.initial.json')
                    if not initial.exists():
                        shutil.copyfile(canonical, initial)
                    # Retain both original and retry evidence before promoting an improved result.
                    temporary = canonical.with_name('daily.promoting.json')
                    shutil.copyfile(output, temporary)
                    temporary.replace(canonical)
                    record['promoted_improvement'] = True
            record.update(status=payload.get('status'), bars=len(payload.get('data', [])),
                          actions_status=payload.get('corporate_actions', {}).get('status'),
                          sha256=hashlib.sha256(output.read_bytes()).hexdigest())
        else:
            record['status'] = 'export_failed_no_file'
        with (directory / 'download_attempts.jsonl').open('a') as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        print(json.dumps({key: record.get(key) for key in ('symbol', 'status', 'bars', 'actions_status')}), flush=True)
        time.sleep(1)

    # Refresh a non-blocking corporate-action review after the batch. The audit
    # never edits bars and does not classify price gaps as splits.
    checker = Path(__file__).resolve().with_name('check_extreme_split_candidates.py')
    if not checker.exists():
        raise FileNotFoundError(f'Missing price-gap review tool: {checker}')
    audit_path = directory / 'reviews/corporate_actions_2026-10/extreme_split_candidates_latest.json'
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_audit = audit_path.with_name(audit_path.name + '.tmp')
    completed = subprocess.run(
        [sys.executable, str(checker), '--root', str(directory), '--output', str(temporary_audit)],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f'Post-download price-gap review failed: {completed.stderr[-1000:]}')
    audit = json.loads(temporary_audit.read_text())
    temporary_audit.replace(audit_path)
    print(json.dumps({'type': 'post_download_price_gap_review',
                      'candidate_count': audit['candidate_count'],
                      'report': str(audit_path)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
