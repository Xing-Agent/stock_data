#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""财报公布日历(第 4 条):SEC 8-K item 2.02(业绩公告)+ 外国公司的 6-K,从 2014 年起。

大白话:每家公司每次发业绩,都要交一份 8-K、勾 2.02 这一项。SEC 记下了它几点几分受理的。
  · announcement_at_utc:SEC 受理时间(UTC)
  · announcement_at_et / session:换成美东时间,并标盘前 / 盘中 / 盘后
  · effective_trade_date:市场第一次能对这条消息做反应的交易日
      盘前(< 9:30)→ 当天;盘中或盘后 → 下一个交易日
  · 一个季度里有好几份 2.02(比如先发交付量、再发正式业绩),全部保留,
    另给 is_main_release:同一财报期里,紧挨着那份 10-Q / 10-K 之前的最后一份(老规矩,1030 定的)
用法:python3 build_earn_cal.py sub.json.gz cik_list.csv calendar_dir out.csv.gz
"""
import csv, gzip, json, os, sys, bisect
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')


def main(sub_path, list_path, cal_dir, out_path):
    SUB = json.load(gzip.open(sub_path))
    cal = sorted(f[:10] for f in os.listdir(cal_dir))
    L = list(csv.DictReader(open(list_path)))
    rows = []
    for x in L:
        s = SUB.get(x['cik'])
        if not s: continue
        f = s['f']
        periodic = sorted((r[2], r[1], r[5]) for r in f if r[1].startswith(('10-Q', '10-K', '20-F', '40-F')))
        pdates = [p[0] for p in periodic]
        evs = [r for r in f if (r[1].startswith('8-K') and '2.02' in r[4]) and r[2] >= '2014-01-01']
        for r in sorted(evs, key=lambda r: r[3]):
            acc = datetime.fromisoformat(r[3].replace('Z', '+00:00')) if r[3] else None
            if acc is None: continue
            et = acc.astimezone(ET); dstr = et.date().isoformat(); hm = et.hour * 60 + et.minute
            session = 'pre' if hm < 570 else ('intraday' if hm < 960 else 'post')
            i = bisect.bisect_left(cal, dstr)
            if i < len(cal) and cal[i] == dstr and session == 'pre': eff = dstr
            else: eff = cal[bisect.bisect_right(cal, dstr)] if bisect.bisect_right(cal, dstr) < len(cal) else ''
            # 下一份 10-Q/10-K(这次业绩对应的正式报告)
            j = bisect.bisect_left(pdates, r[2])
            nxt = periodic[j] if j < len(periodic) else None
            rows.append({'cik': x['cik'], 'folder': x['folder'], 'symbols': x['symbols'], 'accession': r[0], 'form': r[1], 'items': r[4],
                         'filing_date': r[2], 'announcement_at_utc': acc.isoformat(), 'announcement_at_et': et.isoformat(),
                         'session': session, 'effective_trade_date': eff, 'report_date': r[5],
                         'next_periodic_form': nxt[1] if nxt else '', 'next_periodic_filed': nxt[0] if nxt else '',
                         'next_periodic_period': nxt[2] if nxt else '',
                         'source_url': f"https://www.sec.gov/Archives/edgar/data/{int(x['cik'])}/{r[0].replace('-', '')}/{r[6]}"})
    # 主公告:同一份「下一份定期报告」之前的最后一份 2.02
    last = {}
    for k, r in enumerate(rows):
        key = (r['cik'], r['next_periodic_filed'] or r['filing_date'])
        if key not in last or r['announcement_at_utc'] > rows[last[key]]['announcement_at_utc']: last[key] = k
    main_idx = set(last.values())
    for k, r in enumerate(rows): r['is_main_release'] = k in main_idx
    with gzip.open(out_path, 'wt', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print('事件', len(rows), '· 公司', len({r['cik'] for r in rows}), '· 主公告', len(main_idx))


if __name__ == '__main__':
    main(*sys.argv[1:])
