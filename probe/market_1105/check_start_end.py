#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 55 · 核对起止日:「公司早就上市,我们只取到后面一段」/「还在交易,我们却提前截断」各有几只。

大白话:
  起始日:这家在 SEC 的第一份定期报告(10-K / 10-Q / 20-F / 40-F)比我们的起始日早一年以上、而且起始日晚于 2004-01-02 的,逐只查:
    · 起始那个代码在更早就有行情 → 问 Polygon「那时这个代码是哪家(CIK)」
        - 是同一家 → 真没取全 → unavailable.csv 标 partial
        - 是别家(代码被重新用过)→ 没问题,我们的起点就是这家开始用这个代码的那天
    · 起始那个代码就是从这天开始有行情 → 更早可能用别的代码、在场外交易,或者只是债券在 SEC 报告(股票后来才上市)
        → 没法逐只确认,unavailable.csv 标 partial_possible
  结束日:我们的结束日早于 2026-11-04、但最后那个代码之后 30 天以上还在交易的,问 Polygon「那时这个代码是哪家」:
    · 同一家 → 提前截断了 → partial;别家 / Polygon 没登记 → 代码被别家接走,没问题

用法:python3 check_start_end.py market_dir plan.json ohlcv.parquet polygon_startend_check_1105.json
"""
import bisect, collections, csv, glob, gzip, json, os, sys
from datetime import date, timedelta
import polars as pl

PER = ('10-K', '10-Q', '20-F', '40-F', '10-KT', '10-QT')


def main(mdir, plan_path, px_path, chk_path):
    S = json.load(gzip.open('/home/claude/fx/sub_all.json.gz'))
    P = json.load(open(plan_path))['plan']
    claims = collections.defaultdict(list)
    for f, p in P.items():
        for t, a, b, cid, et in p['pieces']: claims[t].append((a, b, f))
    O = pl.read_parquet(px_path, columns=['ticker', 'd'])
    last_by_t = {t: d for t, d in O.group_by('ticker').agg(pl.col('d').max()).iter_rows()}
    first_by_t = {t: d for t, d in O.group_by('ticker').agg(pl.col('d').min()).iter_rows()}
    C = {(r[0], r[1]): r for r in json.load(open(chk_path))['rows']}       # (early/late, 文件夹) → [.., cik, 名]
    out = []; st_cnt = collections.Counter(); en_cnt = collections.Counter()
    for fp in sorted(glob.glob(os.path.join(mdir, '*/daily.json.gz'))):
        s = fp.split('/')[-2]; j = json.load(gzip.open(fp)); cik = j['cik']
        st, en = j['start_date'], j['end_date']; t0 = j['data'][0]['source_ticker']; t1 = j['data'][-1]['source_ticker']
        per = sorted(x[2] for x in S[cik]['f'] if x[1].startswith(PER))
        # —— 起始日 ——
        if st <= '2009-12-31': st_cnt['2009 年及以前就有'] += 1
        elif not per or per[0] >= (date.fromisoformat(st) - timedelta(days=365)).isoformat(): st_cnt['2010 年以后才开始 · SEC 定期报告也是这时候才开始(上市晚)'] += 1
        else:
            ft = first_by_t.get(t0)
            if ft and ft < st:
                r = C.get(('late', s)); pc = (r[5] or '').lstrip('0') if r and r[4] == 200 else None
                if pc == cik:
                    st_cnt['2010 年以后才开始 · 真没取全(同一家早有行情)'] += 1
                    out.append([s, cik, f'部分:起始日 {st} 之前同一家(Polygon 登记同一 CIK)已用 {t0} 交易,前段没接上', 'partial'])
                else:
                    st_cnt['2010 年以后才开始 · 这个代码以前是别家的(没问题)'] += 1
            else:
                st_cnt['2010 年以后才开始 · SEC 早有定期报告、但这个代码这天才有行情(可能缺前段)'] += 1
                out.append([s, cik, f'可能缺前段:SEC 第一份定期报告 {per[0]},行情 {st} 才开始({t0} 这天才出现);'
                                    '更早可能用别的代码 / 在场外交易,也可能只是债券在 SEC 报告', 'partial_possible'])
        # —— 结束日 ——
        if en >= '2026-11-04': en_cnt['到 2026-11-04 还在交易'] += 1; continue
        lt = last_by_t.get(t1)
        other = any(f != s and a > en for a, b, f in claims[t1])
        if lt and lt > (date.fromisoformat(en) + timedelta(days=30)).isoformat() and not other:
            r = C.get(('early', s)); pc = (r[5] or '').lstrip('0') if r and r[4] == 200 else None
            if pc == cik:
                en_cnt['提前结束 · 真截断了(同一家之后还在交易)'] += 1
                out.append([s, cik, f'部分:结束日 {en} 之后同一家(Polygon 登记同一 CIK)的 {t1} 还交易到 {lt},后段没给', 'partial'])
            else:
                en_cnt['提前结束 · 之后这个代码归了别家(没问题)'] += 1
        else:
            en_cnt['提前结束 · 退市 / 被收购(代码之后不再交易,或归了本库别的文件夹)'] += 1
    with open(os.path.join(mdir, 'unavailable.csv'), 'a', newline='') as fh:
        csv.writer(fh).writerows(out)
    json.dump({'start': st_cnt, 'end': en_cnt}, open(os.path.join(mdir, '_start_end_counts.json'), 'w'), ensure_ascii=False, indent=1)
    print(dict(st_cnt)); print(dict(en_cnt)); print(collections.Counter(x[3] for x in out))


if __name__ == '__main__':
    main(*sys.argv[1:])
