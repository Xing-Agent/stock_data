#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 97 · 原考卷 1,042 家:把 2016 年以前的日线补出来(接在 exam_1042 现有文件的前面)

大白话:
  · 起点就是 exam_1042 里每家「第一根 K 线」用的那个代码,从它前一个交易日往回接
  · 同一个代码连续交易(断档不超过 65 个交易日)就一路接回去,最早 2004-01-02,不早于这家在 SEC 第一次申报的前 30 天
  · 早年换过代码的:Polygon 代码表里登记在同一个 SEC 编号下的另一个代码,前一个交易日停、这一段开始、价格接得上(差 < 25%)→ 接上
  · 接缝处核一下:我们接出来的最后一根收盘 和 exam_1042 第一根开盘差 > 20% 的,写进 warnings(可能是那天有拆股 / 接错)
  · 第一根 K 线就晚于 2016-01-05 的(2016 年以后才上市)不用补,列进清单
用法:python3 plan_exam_pre2016.py exam_dir ohlcv.parquet out_plan.json
"""
import bisect, csv, glob, gzip, json, os, sys
from collections import defaultdict
from datetime import date, timedelta
import polars as pl

ROOT = '/home/claude/stock_data'


def main(exam_dir, px, out):
    S = json.load(gzip.open('/home/claude/fx/sub_all.json.gz'))
    man = list(csv.DictReader(open(os.path.join(exam_dir, 'manifest.csv'))))
    want = {r['cik'].lstrip('0') for r in man}
    tick_by_cik = defaultdict(set)
    for fp in sorted(glob.glob(f'{ROOT}/probe/fund_expand_1103/polygon_tickers_*.json.gz')) + sorted(glob.glob(f'{ROOT}/probe/universe_1107/raw/polygon_tickers_*.json.gz')):
        for r in json.load(gzip.open(fp))['rows']:
            if r[4] and r[4].lstrip('0') in want: tick_by_cik[r[4].lstrip('0')].add(r[0])
    P = pl.read_parquet(px, columns=['ticker', 'd', 'open', 'close'])
    cal = sorted(P['d'].unique().to_list()); CI = {d: i for i, d in enumerate(cal)}
    PXD = {t: (g['d'].to_list(), g['open'].to_list(), g['close'].to_list()) for (t,), g in P.sort('d').group_by(['ticker'])}
    allt = set(PXD)

    def run_start(t, end_d, lo):
        ds = PXD.get(t, ([],))[0]; k = bisect.bisect_right(ds, end_d) - 1
        if k < 0: return None
        while k > 0 and CI[ds[k]] - CI[ds[k - 1]] <= 66 and ds[k - 1] >= lo: k -= 1
        return ds[k]

    def ok_tick(T):
        if any(c.islower() for c in T) or '.' in T: return False
        return not (len(T) >= 4 and T[-1] in 'UVWR' and T[:-1] in allt)

    def link_prev(cik, t, a, a_open):
        best = None
        for T in tick_by_cik.get(cik, ()):
            if T == t or not ok_tick(T): continue
            ds, _, cs = PXD.get(T, ([], [], []))
            k = bisect.bisect_left(ds, a) - 1
            if k < 0 or not cs[k] or CI[a] - CI[ds[k]] > 5: continue
            if k + 1 < len(ds) and CI[ds[k + 1]] - CI[a] < 20: continue
            if not a_open or abs(a_open / cs[k] - 1) >= 0.25: continue
            if best is None or ds[k] > best[1]: best = (T, ds[k])
        return best

    plan, skipped = {}, []
    for r in man:
        f, cik = r['symbol'], r['cik'].lstrip('0')
        J = json.load(open(os.path.join(exam_dir, r['data_path'])))
        b0 = J['data'][0]; t0, d0 = b0['source_ticker'], b0['date']
        if d0 > '2016-01-05': skipped.append([f, cik, f'exam_1042 第一根就是 {d0}(2016 年以后才上市 / 才有行情),不用补', 'not_needed']); continue
        fs = S.get(cik, {}).get('f', [])
        lo = max('2004-01-02', (date.fromisoformat(min(x[2] for x in fs)) - timedelta(days=30)).isoformat()) if fs else '2004-01-02'
        i0 = CI.get(d0)
        if i0 is None or i0 == 0: skipped.append([f, cik, '日线库里找不到 exam 第一根那天', 'data']); continue
        prev_day = cal[i0 - 1]
        pieces, warns = [], []
        ds = PXD.get(t0, ([],))[0]
        if prev_day in set(ds[-4000:]) or (ds and bisect.bisect_left(ds, d0) > 0 and CI[d0] - CI[ds[bisect.bisect_left(ds, d0) - 1]] <= 5):
            e = ds[bisect.bisect_left(ds, d0) - 1]; s0 = run_start(t0, e, lo)
            if s0: pieces.append([t0, s0, e, 'exam_pre2016', ''])
            a, a_open, cur = s0, None, t0
        else:
            a, cur = d0, t0
        # 往前补接改过的代码(最多 6 次)
        for _ in range(6):
            start = pieces[0][1] if pieces else d0
            if start <= lo: break
            tk = pieces[0][0] if pieces else t0
            dd_, oo, _ = PXD.get(tk, ([], [], []))
            j = bisect.bisect_left(dd_, start); a_open = oo[j] if j < len(oo) and dd_[j] == start else (b0['open'] if not pieces else None)
            lk = link_prev(cik, tk, start, a_open)
            if not lk: break
            T, e = lk; s1 = run_start(T, e, lo)
            if not s1: break
            pieces.insert(0, [T, s1, e, 'polygon_cik_link', '改名(按 Polygon 同 CIK + 价格接得上补接)']); warns.append(f'早年代码按 Polygon 同 CIK、价格接得上补接:{T}→{tk}')
        if not pieces: skipped.append([f, cik, f'{t0} 在 {d0} 之前没有连得上的行情(可能 2016 年初刚换代码,前一个代码没登记在同一 SEC 编号下)', 'partial_possible']); continue
        last = pieces[-1]; dl, _, cl_ = PXD[last[0]]; k = bisect.bisect_right(dl, last[2]) - 1
        if cl_[k] and b0['open'] and abs(b0['open'] / cl_[k] - 1) > 0.2:
            warns.append(f"接缝:我们最后一根 {dl[k]} 收盘 {cl_[k]} vs exam_1042 第一根 {d0} 开盘 {b0['open']},差 {b0['open'] / cl_[k] - 1:+.1%}(那天可能有拆股 / 派现,或者接错了,请核)")
        plan[f] = {'cik': cik, 'name': r['name'], 'sic': None, 'window': [lo, d0], 'pieces': pieces, 'warnings': warns, 'exam_first_bar': d0, 'exam_first_ticker': t0}
    json.dump({'plan': plan, 'fail': skipped}, open(out, 'w'), ensure_ascii=False)
    from collections import Counter
    print('有计划', len(plan), '· 跳过', Counter(x[3] for x in skipped), '· 接缝警告', sum(1 for p in plan.values() if any('接缝' in w for w in p['warnings'])),
          '· 起点年份', sorted(Counter(min(x[1] for x in p['pieces'])[:4] for p in plan.values()).items()))


if __name__ == '__main__':
    main(*sys.argv[1:])
