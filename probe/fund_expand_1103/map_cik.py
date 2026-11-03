#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给扩池里每一行「公司 × 年份」定 SEC 公司编号(CIK)。

大白话:候选编号有三个来源 —— 考卷名单(已逐只核过)、SEC 现在的代码表、Polygon 的年度代码表。
代码会被别的公司重复使用(老 Chubb 的 CB 后来给了 ACE),而我们的「公司」是按价格连续切的,
所以同一个公司编号(company_id)在不同年份可能对应两个申报主体。这里按年定:
  候选编号在那一年(前后放宽 150 天)里必须交过年报或季报(10-K / 10-Q / 20-F / 40-F),才算对上。
对不上的列进「待补」。基本面文件按 CIK 存(一家申报主体一个文件夹)。

用法:python3 map_cik.py pool_FULL_ALL.csv sub.json.gz out_dir [polygon_yearly_dir]
"""
import csv, glob, gzip, json, os, sys
from collections import defaultdict
from datetime import date, timedelta

PERIODIC = ('10-K', '10-Q', '20-F', '40-F', '10-KT', '10-QT')
ROOT = '/home/claude/stock_data'


def main(pool_path, sub_path, out_dir, poly_dir=None):
    SUB = json.load(gzip.open(sub_path))
    pool = [r for r in csv.DictReader(open(pool_path)) if int(r['rank']) <= 2000]
    ex = {r['company_id']: r['cik'].lstrip('0') for r in csv.DictReader(open(f'{ROOT}/exam_1042/manifest.csv'))}
    ct = json.load(open(f'{ROOT}/exam_1042/reviews/sec_company_tickers_exchange_1102.json'))
    secnow = {r[2].upper().replace('-', '.'): str(r[0]) for r in ct['data']}
    poly = defaultdict(dict)                      # 代码 → {年: (cik, 名)}
    files = sorted(glob.glob(os.path.join(poly_dir or '/nonexistent', 'polygon_tickers_*.json.gz'))) + [f'{ROOT}/probe/exam_1101/polygon_tickers_20151231.json.gz']
    for f in files:
        if not os.path.exists(f): continue
        y = int(os.path.basename(f).split('_')[-1][:4]); j = json.load(gzip.open(f))
        for r in j['rows']:
            if r[4]: poly[r[0]][y] = (r[4].lstrip('0'), r[1])
    # 每个 CIK 的定期报告日期(排好序)
    per = {c: sorted(r[2] for r in s['f'] if r[1].startswith(PERIODIC)) for c, s in SUB.items()}

    def filed_in(c, lo, hi):
        return sum(1 for x in per.get(c, []) if lo <= x <= hi)

    # 先按公司收集所有来源的候选(任何年份、任何代码),再逐年用「当年交过定期报告」来核
    co_ciks = defaultdict(set)
    for r in pool:
        cid, s = r['company_id'], r['symbol']
        if cid in ex: co_ciks[cid].add(ex[cid])
        if s.upper() in secnow: co_ciks[cid].add(secnow[s.upper()])
        for c, _ in poly.get(s, {}).values(): co_ciks[cid].add(c)
    out, pend = [], []
    for r in pool:
        y, s, cid = int(r['year']), r['symbol'], r['company_id']
        lo, hi = f'{y - 1}-10-01', f'{y}-12-31'          # 当年年初排名 → 看前一年 Q4 到当年底有没有交定期报告
        cands = {}
        if cid in ex: cands[ex[cid]] = 'exam'
        if s.upper() in secnow: cands.setdefault(secnow[s.upper()], 'sec_now')
        for yy, (c, _) in sorted(poly.get(s, {}).items()):
            cands.setdefault(c, f'polygon{yy}')
        for c in co_ciks.get(cid, ()):                 # 同一家公司别的年份已经对上的编号
            cands.setdefault(c, 'same_company_other_year')
        scored = sorted(((filed_in(c, lo, hi), src == 'exam', c, src) for c, src in cands.items()), reverse=True)
        best = next((x for x in scored if x[0] > 0), None)
        base = {'year': y, 'rank': r['rank'], 'symbol': s, 'company_id': cid}
        if best:
            out.append({**base, 'cik': best[2], 'cik_source': best[3], 'periodic_filings': best[0], 'sec_name': SUB[best[2]]['n']})
        else:
            pend.append({**base, 'seg_start': r['seg_start'], 'seg_end': r['seg_end'],
                         'candidates_tried': ';'.join(f'{c}({src})' for _, _, c, src in scored),
                         'reason': 'no_candidate' if not cands else 'no_10K_10Q_filed_that_year'})
    # 文件夹:按 CIK,一家申报主体一个;用它最后一次出现在池子里的代码命名,重名加 CIK
    last = {}
    for x in sorted(out, key=lambda x: x['year']): last[x['cik']] = x['symbol']
    names = defaultdict(list)
    for c, s in last.items(): names[s].append(c)
    folder = {c: (s if len(names[s]) == 1 else f'{s}__{c}') for c, s in last.items()}
    for x in out: x['folder'] = folder[x['cik']]
    for name, data in (('pool_cik_by_year_1103.csv', out), ('cik_pending_1103.csv', pend)):
        with open(os.path.join(out_dir, name), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]) if data else ['year']); w.writeheader(); w.writerows(data)
    # 一家一行的清单(给建库用)
    agg = defaultdict(lambda: {'symbols': [], 'company_ids': set(), 'years': []})
    for x in out:
        a = agg[x['cik']]; a['years'].append(x['year']); a['company_ids'].add(x['company_id'])
        if x['symbol'] not in a['symbols']: a['symbols'].append(x['symbol'])
    with open(os.path.join(out_dir, 'cik_list_1103.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['cik', 'folder', 'company_id', 'symbols', 'y0', 'y1', 'sec_name'])
        for c, a in sorted(agg.items(), key=lambda kv: folder[kv[0]]):
            w.writerow([c, folder[c], ';'.join(sorted(a['company_ids'])), ';'.join(a['symbols']), min(a['years']), max(a['years']), SUB[c]['n']])
    cos_all = {r['company_id'] for r in pool}; cos_ok = {x['company_id'] for x in out}
    print('池子行(公司×年)', len(pool), '· 对上', len(out), '· 待补', len(pend),
          '| 公司', len(cos_all), '· 至少一年对上', len(cos_ok), '· 申报主体(CIK)', len(agg))


if __name__ == '__main__':
    main(*sys.argv[1:])
