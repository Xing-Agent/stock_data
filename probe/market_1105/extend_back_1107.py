#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1107 · 研究行情库补前段:SEC 编号换过、但同一个代码价格一直连着的,往前接

大白话:
  原来按「这家 SEC 编号第一次申报前 30 天」截断起点。控股公司重组(Google → Alphabet、BlackRock、Cigna……)、
  外国公司晚交申报、上市后才补交申报的,都会被截掉一段 —— 但同一个代码在交易所一直连着交易,价格也连着。
  这里对每个文件夹的「第一段」:同一个代码在起点前 5 个交易日内还在交易、而且那段时间没有被别的文件夹认领
  (研究库 + 原考卷,原考卷含 2016 年以前那段),就一路往前接(断档 ≤ 65 个交易日,最早 2004-01-02);
  碰到别的文件夹认领的日子就停。每处都写进 warnings。
  另:GOOG / GOOGL 2014-04-03 的 C 类股派发(每 1 股 A 送 1 股 C)当作 1 拆 2,手工补一条拆股记录。
用法:python3 extend_back_1107.py plan.json exam_dir exam_pre2016_plan.json ohlcv.parquet out_plan.json
"""
import bisect, glob, json, os, sys
from collections import defaultdict
import polars as pl


def main(plan_path, exam_dir, exam_pre, px, out):
    P = json.load(open(plan_path)); plan = P['plan']
    claims = defaultdict(list)
    for f, p in plan.items():
        for t, a, b, *_ in p['pieces']: claims[t].append((a, b, f))
    for fp in glob.glob(os.path.join(exam_dir, '*/daily.json')):
        f = 'exam:' + fp.split('/')[-2]
        for s in json.load(open(fp)).get('company_segments') or []:
            claims[s['ticker']].append((s['from'], s['to'], f))
    for f, p in json.load(open(exam_pre))['plan'].items():
        for t, a, b, *_ in p['pieces']: claims[t].append((a, b, 'exam:' + f))
    O = pl.read_parquet(px, columns=['ticker', 'd'])
    cal = sorted(O['d'].unique().to_list()); ci = lambda d: bisect.bisect_left(cal, d)
    D = {t: g['d'].sort().to_list() for (t,), g in O.group_by(['ticker'])}
    O2 = pl.read_parquet(px, columns=['ticker', 'd', 'open', 'close']).sort('d')
    first_t = {p['pieces'][0][0] for p in plan.values()}
    PXc = {t: (g['d'].to_list(), g['open'].to_list(), g['close'].to_list()) for (t,), g in O2.filter(pl.col('ticker').is_in(list(first_t))).group_by(['ticker'])}
    import csv as _csv
    SPL = {(r['ticker'], r['aligned_date']) for r in _csv.DictReader(open(os.environ.get('SPLITS_CSV') or '/home/claude/stock_data/probe/market_1105/polygon_splits_aligned_1105.csv')) if r['check'].startswith('确认')}
    # 护栏:只在「按价格连续切出来的同一家公司」(company_id)那一段里往前接 —— 切段时已经把代码被别家重用的地方切开了
    #   (旧 IGT 2015 年被收购、新 IGT plc 接着用 IGT;旧 BAM 2022 年改名 BN、新 BAM 接着用 BAM,都属于这种);
    #   切段数据从 2013-01-02 开始,所以第一段从 2013-01-02 开始的,才允许再往 2013 年以前接
    import csv
    seg_first = {}
    for r in csv.DictReader(open('/home/claude/seg/pit_company_segments.csv')):
        k_ = (r['company_id'], r['ticker']); seg_first[k_] = min(seg_first.get(k_, '9999'), r['first_seen'])
    # 第二道护栏:Polygon 年底代码表里,这个代码在那些年登记的是哪个 SEC 编号
    #   · 和我们是同一个编号(上市后才补交申报、外国公司晚交)→ 接
    #   · 是别的编号:只有我们这家交过「继承发行人」申报(8-K12B / 8-K12G3,控股公司重组时交的),
    #     或者在下面这张手工核过的重组名单里,才接;否则停在换编号那年,写 warnings
    import gzip
    owner = defaultdict(dict)      # 代码 → {快照日: cik}
    for fp in glob.glob('/home/claude/stock_data/probe/universe_1107/raw/polygon_tickers_*.json.gz') + glob.glob('/home/claude/stock_data/probe/fund_expand_1103/polygon_tickers_*.json.gz'):
        dd = os.path.basename(fp).split('_')[-1][:8]; dd = f'{dd[:4]}-{dd[4:6]}-{dd[6:]}'
        for r in json.load(gzip.open(fp))['rows']:
            if r[4] and r[5] in (True, 'true', 'True'): owner[r[0]][dd] = r[4].lstrip('0')
    SUB = json.load(gzip.open('/home/claude/fx/sub_all.json.gz'))
    MANUAL_REORG = {'1652044': 'Google Inc → Alphabet(2015-10 控股公司重组)', '2012383': 'BlackRock 2024-10 控股公司重组(并购 GIP)'}
    def successor(c): return c in MANUAL_REORG or any(x[1].startswith(('8-K12B', '8-K12G3')) for x in SUB.get(c, {}).get('f', []))
    n = 0; log = []; stopped = []
    for f, p in plan.items():
        t, a = p['pieces'][0][0], p['pieces'][0][1]
        cid = p['pieces'][0][3]
        fs = seg_first.get((cid, t))
        floor = '2004-01-02' if (fs is None or fs <= '2013-01-02') else fs
        if a <= '2004-01-05': continue
        ds = D.get(t, []); k = bisect.bisect_left(ds, a) - 1
        if k < 0 or ci(a) - ci(ds[k]) > 5: continue
        others = [(x0, x1) for x0, x1, g in claims[t] if g != f]
        def taken(d): return any(x0 <= d <= x1 for x0, x1 in others)
        if taken(ds[k]): continue
        j = k
        while j > 0 and ci(ds[j]) - ci(ds[j - 1]) <= 66 and not taken(ds[j - 1]) and ds[j - 1] >= floor: j -= 1
        new = ds[j]
        cik = p['cik']
        diff = sorted(d for d, c in owner.get(t, {}).items() if new <= d < a and c != cik)
        if diff and not successor(cik):
            stopped.append((f, t, diff[-1], owner[t][diff[-1]]))
            p['warnings'].append(f'{diff[-1]} 以前代码 {t} 在 Polygon 登记的是另一个 SEC 编号 {owner[t][diff[-1]]}({SUB.get(owner[t][diff[-1]], {}).get("n", "?")}),'
                                 f'可能是同一家重组,也可能是别家用过这个代码 —— 没往前接')
            new = a                                     # 年底快照只能定到年,换手具体哪天不知道 → 干脆不接
        # 第三道护栏:往前接的那段里,没有拆股记录却隔夜跳 25% 以上的,停在跳之后(防 BAM 2022 年那种:同一个代码,换了一只新股)
        if new < a:
            PXo = PXc.get(t)
            if PXo:
                dl, op, cl = PXo; i1 = bisect.bisect_left(dl, a) - 1; i0 = bisect.bisect_left(dl, new)
                for i in range(i1, i0, -1):
                    # 看前后各 5 天的收盘中位数,单日坏价(GOOG 2008-09-30 收 322.99 那种)不算
                    import statistics
                    pre = [x for x in cl[max(0, i - 5):i] if x]; post = [x for x in cl[i:i + 5] if x]
                    if pre and post and abs(statistics.median(post) / statistics.median(pre) - 1) > 0.25 and not any((t, dl[k_]) in SPL for k_ in range(max(0, i - 5), min(len(dl), i + 6))):
                        new = dl[i]; p['warnings'].append(f'往前接时在 {dl[i]} 碰到价位断层(前后 5 天收盘中位数差 {statistics.median(post) / statistics.median(pre) - 1:+.0%},没有拆股记录),停在这天'); break
        if new < a:
            p['pieces'][0][1] = new; n += 1
            p['warnings'].append(f'起点从 {a} 往前接到 {new}:同一代码 {t} 价格一直连着(多半是控股公司重组换了 SEC 编号,或上市后才补交申报)')
            log.append((f, t, a, new))
    json.dump(P, open(out, 'w'), ensure_ascii=False)
    print('往前接了', n, '· 碰到换编号停下的', len(stopped)); print(log[:30]); print(stopped[:30])


if __name__ == '__main__':
    main(*sys.argv[1:])
