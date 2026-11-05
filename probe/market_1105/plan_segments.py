#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 53 · 行情扩面:给每个文件夹(= 一个 SEC 申报主体 CIK)定「哪段时间用哪个代码」。

大白话:
  · 我们的「公司」是按价格连续切出来的(company_id),一个公司可能先后用过几个代码
  · 一个 CIK 在选股池里对应若干 (年份, company_id);把这些 company_id 的代码段都拿来
  · 再按这个 CIK 自己「交过定期报告的时间」裁剪:前后各放宽 400 天
    —— 防止代码被别家重新用了以后,把别家的价格接到这家头上(老 Chubb / ACE 那种)
  · 判不准的(没有代码段、或裁完是空的)进「取不到的清单」,不硬塞

用法:python3 plan_segments.py list.txt out_plan.json
"""
import csv, gzip, json, sys
from collections import defaultdict
from datetime import date, timedelta

ROOT = '/home/claude/stock_data'
PERIODIC = ('10-K', '10-Q', '20-F', '40-F', '10-KT', '10-QT')


def main(list_path, out_path):
    L = [l.strip() for l in open(list_path) if l.strip()]
    cl = {r['folder']: r for r in csv.DictReader(open(f'{ROOT}/probe/fund_expand_1103/cik_list_1103.csv'))}
    by_cik_year = defaultdict(set)
    for r in csv.DictReader(open(f'{ROOT}/probe/fund_expand_1103/pool_cik_by_year_1103.csv')):
        by_cik_year[r['cik']].add((int(r['year']), r['company_id'], r['symbol']))
    seg = defaultdict(list)
    for r in csv.DictReader(open('/home/claude/seg/pit_company_segments.csv')):
        seg[r['company_id']].append((r['ticker'], r['first_seen'], r['last_seen'], r['end_type']))
    SUB = json.load(gzip.open('/home/claude/fx/sub_all.json.gz'))
    # 同一个 company_id(价格连续的一串)在不同年份可能归不同 CIK(代码被收购方接走)。
    # 按选股池逐年的归属切时间:第一年之前归第一年的主人,最后一年之后归最后一年的主人;
    # 主人换了的那一年,切在旧主人的「结束日」(退市申报 +10 天 / 最后定期报告 +120 天),和下一年年底取早的那个
    def end_of(s_):
        # 这家在 SEC 的「结束日」:
        #   · 最后一份定期报告之后交过退市申报(25 / 15)→ 那天 +10 天
        #   · 没有退市申报、但最近半年还在向 SEC 交东西(任何表格)→ 还活着,不设结束日
        #   · 否则:最后一份定期报告 +120 天;只交年报的外国公司(20-F / 40-F)+400 天
        #   (1105 修:以前一律 +120 天,只交年报的外国公司还活着也被提前截断,ABEV、ASML 这类)
        per = sorted((x[2], x[1]) for x in s_.get('f', []) if x[1].startswith(PERIODIC))
        if not per: return None
        # 最近半年还交过「退市 / 注销」以外的东西 → 还活着(注意 25 也可能只是某只债券或优先股退市,AZN 2026 年就是)
        if any(x[2] >= '2026-05-01' and not x[1].startswith(('25', '15')) for x in s_['f']): return '2100-01-01'
        tail = [x[2] for x in s_.get('f', []) if x[1].startswith(('25', '15')) and x[2] >= per[-1][0]]
        if tail: return (date.fromisoformat(min(tail)) + timedelta(days=10)).isoformat()
        g = 400 if per[-1][1].startswith(('20-F', '40-F')) else 120
        return (date.fromisoformat(per[-1][0]) + timedelta(days=g)).isoformat()
    def bounds(c):
        return end_of(SUB.get(c, {}))
    cid_years = defaultdict(dict)
    for r in csv.DictReader(open(f'{ROOT}/probe/fund_expand_1103/pool_cik_by_year_1103.csv')):
        cid_years[r['company_id']][int(r['year'])] = r['cik']
    def first_of(c, periodic_only):
        fs_ = [x[2] for x in SUB.get(c, {}).get('f', []) if (not periodic_only or x[1].startswith(PERIODIC))]
        return min(fs_) if fs_ else None
    def dd(x, n): return (date.fromisoformat(x) + timedelta(days=n)).isoformat()
    own_cache, gap_warn = {}, defaultdict(list)
    def owned(cid, cik):
        # 1105 改:主人换手那一年怎么切
        #   · 旧主人已经没了(退市申报 +10 天 / 最后定期报告 +120 天 早于新主人入池那年 1 月 1 日)→ 切在旧主人结束日
        #   · 旧主人还活着(典型:分拆后母公司改代码、子公司接走老代码,像 2016 年 Alcoa → AA)→ 只给有把握的:
        #       旧主人拿到「新主人第一次向 SEC 申报」的前一天;新主人从「它第一份定期报告」或入池那年 1 月 1 日(取早)开始
        #       中间那段两边都不给,写进 warnings
        if cid not in own_cache:
            ys = sorted(cid_years[cid].items()); spans = []
            start = '1900-01-01'
            for i, (y, c) in enumerate(ys):
                nxt = ys[i + 1] if i + 1 < len(ys) else None
                if nxt and nxt[1] != c:
                    y1, n = nxt; b_old = bounds(c)
                    if b_old and b_old <= f'{y1}-01-01':
                        spans.append((c, start, b_old)); start = dd(b_old, 1)
                    else:
                        fe, fp = first_of(n, False), first_of(n, True)
                        oe = max(f'{y}-01-01', dd(fe, -1) if fe else f'{y}-01-01'); oe = min(oe, f'{y1}-01-01')
                        ns = min(f'{y1}-01-01', fp) if fp and fp > oe else f'{y1}-01-01'
                        spans.append((c, start, oe)); start = ns
                        if dd(oe, 1) < ns:
                            for who in (c, n): gap_warn[(cid, who)].append((dd(oe, 1), dd(ns, -1), c, n))
            spans.append((ys[-1][1], start, '2100-01-01'))
            own_cache[cid] = spans
        return [(a, b) for c, a, b in own_cache[cid] if c == cik]
    # 2013 年以前:价格连续切段是从 2013-01-02 开始做的,所以最早一段往前接 —— 只要同一个代码在全量日线里连续交易
    # (中间断档不超过 30 个交易日;1105 从 10 放宽,flat files 偶有整段缺)、而且还在这家 SEC 存续区间里,就一路接回 2004-01-02
    import polars as pl, glob as _g, bisect
    # 往前接(1105 改):
    #   ① 同一个代码:最早一段从 2013-01-02 开始(切段的样本起点)的,只要这个代码在全量日线里连续交易
    #      (断档不超过 65 个交易日 —— flat files 偶有整段缺,如 AEIS 2005 年 5~7 月),就一路接回 2004-01-02
    #   ② 换过代码、但切段时没接上的(CECE → CECO 这种):Polygon 年度代码表里登记在同一个 CIK 下的另一个代码,
    #      前一个交易日(最多差 5 天)停牌、这一段开始,而且价格接得上(前收和今开差 < 25%)→ 接到前面;再对它做 ①
    want = {cl[f]['cik'] for f in L}
    tick_by_cik = defaultdict(set)
    for fp in sorted(_g.glob(f'{ROOT}/probe/fund_expand_1103/polygon_tickers_*.json.gz')) + [f'{ROOT}/probe/exam_1101/polygon_tickers_20151231.json.gz']:
        for r in json.load(gzip.open(fp))['rows']:
            if r[4] and r[4].lstrip('0') in want: tick_by_cik[r[4].lstrip('0')].add(r[0])
    need = {t for c in want for t in tick_by_cik[c]} | {t for cid in seg for t, *_ in seg[cid]}
    PX = pl.read_parquet('/home/claude/mkt/ohlcv.parquet', columns=['ticker', 'd', 'open', 'close'])
    CAL = sorted(PX['d'].unique().to_list()); CI = {d: i for i, d in enumerate(CAL)}
    PXD = {t: (g['d'].to_list(), g['open'].to_list(), g['close'].to_list()) for (t,), g in PX.filter(pl.col('ticker').is_in(list(need))).sort('d').group_by(['ticker'])}
    all_ticks = set(PX['ticker'].unique().to_list())
    del PX
    def run_start(t, end_d, lo):
        """代码 t 在 end_d(含)往前连续交易到哪天(断档 ≤ 65 个交易日,不早于 lo)"""
        ds = PXD.get(t, ([], [], []))[0]
        k = bisect.bisect_right(ds, end_d) - 1
        if k < 0: return None
        while k > 0 and CI[ds[k]] - CI[ds[k - 1]] <= 66 and ds[k - 1] >= lo: k -= 1
        return ds[k]
    def back_start(t, lo):
        return run_start(t, '2013-01-02', lo)
    def ok_tick(T):
        # 不接:发行前交易(…w)、单位(…U)、权证 / 认股权(…W / …R)、优先股(…p…)、带点的特殊类别、…V(发行中)
        if any(ch.islower() for ch in T) or '.' in T: return False
        if len(T) >= 4 and T[-1] in 'UVWR' and T[:-1] in all_ticks: return False
        return True
    def link_prev(cik, t, a):
        da, oa_, _ = PXD.get(t, ([], [], []))
        i = bisect.bisect_left(da, a)
        if i >= len(da) or da[i] != a or not oa_[i]: return None
        best = None
        for T in tick_by_cik.get(cik, ()):
            if T == t or not ok_tick(T): continue
            ds, _, cs = PXD.get(T, ([], [], []))
            k = bisect.bisect_left(ds, a) - 1
            if k < 0 or not cs[k]: continue
            if CI[a] - CI[ds[k]] > 5: continue
            if k + 1 < len(ds) and CI[ds[k + 1]] - CI[a] < 20: continue      # 这个代码之后还在交易 → 不是改名
            if abs(oa_[i] / cs[k] - 1) >= 0.25: continue
            if best is None or ds[k] > best[1]: best = (T, ds[k])
        return best
    plan, fail = {}, []
    for f in L:
        cik = cl[f]['cik']
        s = SUB.get(cik, {})
        per = sorted(x[2] for x in s.get('f', []) if x[1].startswith(PERIODIC))
        if not per:
            fail.append((f, cik, 'SEC 里没有这家的定期报告,判不了存续区间')); continue
        allf = sorted(x[2] for x in s.get('f', []))
        # 开始:这家最早的一份申报(上市文件 S-1 / 10-12B 也算)前 30 天
        lo = (date.fromisoformat(allf[0]) - timedelta(days=30)).isoformat()
        # 结束:最后一份定期报告之后,有退市申报(25 / 15)就用它 +10 天,没有就 +120 天
        hi = end_of(s)
        pieces = []
        for cid in sorted({c for _, c, _ in by_cik_year[cik]}):
            for (oa, ob) in owned(cid, cik):
                for t, a, b, et in seg[cid]:
                    a2, b2 = max(a, lo, oa, '2004-01-01'), min(b, hi, ob)
                    if a2 <= b2: pieces.append([t, a2, b2, cid, et])
        pieces.sort(key=lambda x: x[1])
        lo4 = max(lo, '2004-01-02'); linked = []
        for _ in range(6):
            if not pieces: break
            if pieces[0][1] == '2013-01-02':
                b0 = back_start(pieces[0][0], lo4)
                if b0 and b0 < pieces[0][1]: pieces[0][1] = b0
            if pieces[0][1] <= lo4: break
            lk = link_prev(cik, pieces[0][0], pieces[0][1])
            if not lk: break
            T, e = lk; st0 = run_start(T, e, lo4)
            if not st0: break
            pieces.insert(0, [T, st0, e, 'polygon_cik_link', '改名(按 Polygon 同 CIK + 价格接得上补接)']); linked.append(f'{T}→{pieces[1][0]}')
        warns = [f'早年代码按 Polygon 同 CIK、价格接得上补接:{x}' for x in linked] + [f'代码段 {a}~{b} 是 CIK {c} 和 {n} 换手的那段,哪天换的判不准,两边都没给' for cid in sorted({c for _, c, _ in by_cik_year[cik]}) for a, b, c, n in gap_warn.get((cid, cik), [])]
        # 同一天两段重叠的,后一段从前一段结束后一天开始
        clean = []
        for p in pieces:
            if clean and p[1] <= clean[-1][2]:
                p[1] = (date.fromisoformat(clean[-1][2]) + timedelta(days=1)).isoformat()
                if p[1] > p[2]: continue
            clean.append(p)
        if not clean:
            fail.append((f, cik, '没有落在这家存续区间里的代码段')); continue
        plan[f] = {'cik': cik, 'name': s.get('n'), 'sic': s.get('sic'), 'window': [lo, hi], 'pieces': clean,
                   'pool_symbols': sorted({sym for _, _, sym in by_cik_year[cik]}), 'warnings': warns}
    # 全局查冲突:同一个代码、同一段日子被两个文件夹认领 → 两边都在重叠段上裁掉,记进 warnings
    claims = defaultdict(list)
    for f, p_ in plan.items():
        for i, (t, a, b, cid, et) in enumerate(p_['pieces']): claims[t].append((a, b, f, i))
    conflicts = []
    for t, cs in claims.items():
        cs.sort()
        for x in range(len(cs)):
            for y in range(x + 1, len(cs)):
                a1, b1, f1, i1 = cs[x]; a2, b2, f2, i2 = cs[y]
                if f1 != f2 and a2 <= b1:
                    conflicts.append((t, f1, f2, a2, min(b1, b2)))
    # 判归属:重叠那一年,选股池里这个代码对应的是哪个 CIK,就给哪一家;池子里两家都没有(或都有)→ 两边都不给
    pool_owner = defaultdict(set)
    for r in csv.DictReader(open(f'{ROOT}/probe/fund_expand_1103/pool_cik_by_year_1103.csv')):
        pool_owner[(r['symbol'], int(r['year']))].add(r['cik'])
    def cut(f, t, a, b):
        new = []
        for pc in plan[f]['pieces']:
            if pc[0] != t or pc[2] < a or pc[1] > b: new.append(pc); continue
            if pc[1] < a: new.append([pc[0], pc[1], (date.fromisoformat(a) - timedelta(days=1)).isoformat(), pc[3], pc[4]])
            if pc[2] > b: new.append([pc[0], (date.fromisoformat(b) + timedelta(days=1)).isoformat(), pc[2], pc[3], pc[4]])
        plan[f]['pieces'] = sorted(new, key=lambda x: x[1])
    resolved = []
    for t, f1, f2, a, b in conflicts:
        y = int(a[:4]); own = pool_owner.get((t, y), set()) | pool_owner.get((t, y + 1), set()) if a[5:] >= '07' else pool_owner.get((t, y), set())
        c1, c2 = plan[f1]['cik'] in own, plan[f2]['cik'] in own
        if c1 and not c2: losers, note = [f2], f'给 {f1}'
        elif c2 and not c1: losers, note = [f1], f'给 {f2}'
        else: losers, note = [f1, f2], '两边都不给'
        for f in losers: cut(f, t, a, b)
        for f in (f1, f2):
            plan[f].setdefault('warnings', []).append(f'代码 {t} 在 {a}~{b} 被 {f1} 和 {f2} 同时认领,按选股池当年归属:{note}')
        resolved.append((t, f1, f2, a, b, note))
    json.dump(resolved, open(out_path.replace('.json', '_conflicts.json'), 'w'), ensure_ascii=False)
    for f in [f for f, p_ in plan.items() if not p_['pieces']]:
        fail.append((f, plan[f]['cik'], '代码段全部和别家重叠,判不准')); del plan[f]
    print('冲突', len(conflicts))
    json.dump({'plan': plan, 'fail': fail}, open(out_path, 'w'), ensure_ascii=False)
    print('有计划', len(plan), '· 取不到', len(fail))


if __name__ == '__main__':
    main(*sys.argv[1:])
