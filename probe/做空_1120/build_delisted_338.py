#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 338 第一样:面板里没有的退市普通股日线(Polygon,Lin 浏览器取,adjusted=false 原始价)。
大白话:
  · 名单:Polygon 参考库里 active=false、type=CS、主板在 NYSE / NASDAQ / AMEX(XNYS XNAS XASE)、退市日在 2005-01-01 ~ 2025-12-31 的,
    去掉两个面板里已有的代码。
  · Polygon 的日线是按代码取的,代码被别的公司接着用过的话会混在一起。所以每只只要「退市日以前」那段,
    再往前碰到停牌超过 60 天的空档、或者同一代码更早一家公司的退市日,就从那以后算起。
  · 拆股按 Polygon 拆股记录折(只用这只票自己那段时间里的)。列和之前的日线一样。
用法:python3 build_delisted_338.py RAW.json.gz 面板已有代码.csv OUT_DIR [标普补充 RAW_P2.json.gz] [第三步 RAW_P3.json.gz 面板CIK.json]
"""
import csv, gzip, json, os, sys
from collections import defaultdict
from datetime import date, datetime
from zoneinfo import ZoneInfo
import polars as pl

ET = ZoneInfo('America/New_York')
raw, panel_csv, out = sys.argv[1:4]
os.makedirs(out, exist_ok=True)
J = json.load(gzip.open(raw))
INA, DL, SPL = J['ina'], J['dl'], J['spl']
panel = {r['symbol'] for r in csv.DictReader(open(panel_csv))}
splits = defaultdict(list)
for t, d, f, to in SPL:
    if f and to: splits[t].append((d, to / f))
dl_by_t = defaultdict(list)          # 同一代码各家公司的退市日
for x in INA:
    if x[4]: dl_by_t[x[0]].append(x[4][:10])
EXCH = {'XNYS': 'NYSE', 'XNAS': 'NASDAQ', 'XASE': 'AMEX'}


def day(ts): return datetime.fromtimestamp(ts / 1000, ET).date().isoformat()


def frame(t, figi, cik, B, sp, tag):
    """B = [(日期, o, h, l, c, v, n)];用列直接建表,省内存"""
    ds = [b[0] for b in B]
    f = []
    for dd in ds:
        x = 1.0
        for d, k in sp:
            if dd < d: x *= k
        f.append(x)
    scd = dict(sp)
    df = pl.DataFrame({'symbol': [t] * len(B), 'polygon_composite_figi': [figi or ''] * len(B), 'cik': [cik or ''] * len(B), 'date': ds,
                       'open': [float(b[1]) for b in B], 'high': [float(b[2]) for b in B], 'low': [float(b[3]) for b in B],
                       'close': [float(b[4]) for b in B], 'volume': [float(b[5]) for b in B],
                       'split_coefficient': [scd.get(d, 1.0) for d in ds], 'adj_factor': f, 'trades': [int(b[6]) for b in B]})
    df = df.with_columns(*[(pl.col(c) / pl.col('adj_factor')).alias(c + '_adj') for c in ('open', 'high', 'low', 'close')],
                         (pl.col('volume') * pl.col('adj_factor')).alias('volume_adj'), pl.lit(t).alias('source_ticker'), pl.lit(tag).alias('退市年'))
    return df.select('symbol', 'polygon_composite_figi', 'cik', 'date', 'open', 'high', 'low', 'close', 'volume', 'split_coefficient',
                     'open_adj', 'high_adj', 'low_adj', 'close_adj', 'volume_adj', 'adj_factor', 'trades', 'source_ticker', '退市年')


summary, frames, n_panel = [], [], 0
for x in INA:
    t, name, ex, typ, dlu, figi, sfigi, cik = x[:8]
    if typ != 'CS' or ex not in EXCH or not ('2005-01-01' <= dlu[:10] < '2026-01-01'): continue
    if t in panel: n_panel += 1; continue
    dld = dlu[:10]
    bars = DL.get(f'{t}|{dld}|{figi or cik or ""}')
    rec = dict(代码=t, 公司名=name, 交易所=EXCH[ex], polygon_composite_figi=figi, polygon_share_class_figi=sfigi, cik=cik, 退市日_polygon=dld,
               数据起='', 最后交易日='', 最后收盘价='', 交易天数=0, 拆股='', 说明='')
    if bars == 'ERR' or bars is None:
        rec['说明'] = '取数出错' if bars == 'ERR' else '没取'; summary.append(rec); continue
    B = [(day(b[0]), *b[1:]) for b in bars]
    B = [b for b in B if b[0] <= dld]
    if not B:
        rec['说明'] = 'Polygon 没有这只的日线'; summary.append(rec); continue
    # 往前切:停牌超过 60 天的空档,或者同一代码更早一家公司的退市日
    cut = 0
    for i in range(len(B) - 1, 0, -1):
        if (date.fromisoformat(B[i][0]) - date.fromisoformat(B[i - 1][0])).days > 60: cut = i; break
    earlier = [d for d in dl_by_t[t] if d < dld]
    if earlier:
        e = max(earlier); j = next((i for i, b in enumerate(B) if b[0] > e), len(B)); cut = max(cut, j)
    B = B[cut:]
    if len(B) < 5:
        rec['说明'] = f'只有 {len(B)} 天,太少,没放'; summary.append(rec); continue
    a, b = B[0][0], B[-1][0]
    sp = sorted((d, k) for d, k in splits.get(t, []) if a < d <= b)
    frames.append(frame(t, figi, cik, B, sp, dld[:4]))
    DL.pop(f'{t}|{dld}|{figi or cik or ""}', None)
    gap = (date.fromisoformat(dld) - date.fromisoformat(b)).days
    rec.update(数据起=a, 最后交易日=b, 最后收盘价=B[-1][4], 交易天数=len(B), 拆股=';'.join(f'{d}×{k:g}' for d, k in sp),
               说明=('数据起点被切过(代码之前有别家用过或长期停牌)' if cut else '') + (f';最后交易日比退市日早 {gap} 天' if gap > 30 else ''))
    summary.append(rec)
# 第二步:Polygon 参考库里没有、但标普 500 历史成分里 2005–2025 调出的(贝尔斯登、WaMu、Wachovia、老 GM 这类),按代码直接取日线,
# 只要「调出日前后停止交易」的那段;调出以后还一直在交易的(改名、被并后代码还在用)不算退市,不放
if len(sys.argv) > 4:
    P2 = json.load(gzip.open(sys.argv[4]))
    for k, bars in P2.items():
        t, ex = k.split('|')
        rec = dict(代码=t, 公司名='', 交易所='', polygon_composite_figi='', polygon_share_class_figi='', cik='', 退市日_polygon='',
                   数据起='', 最后交易日='', 最后收盘价='', 交易天数=0, 拆股='', 说明=f'Polygon 参考库没有;按标普 500 调出日 {ex} 补的')
        if any(r['代码'] == t and r['交易天数'] for r in summary): continue
        if bars == 'ERR' or not bars:
            rec['说明'] += ';Polygon 没有这个代码的日线'; summary.append(rec); continue
        B = [(day(b[0]), *b[1:]) for b in bars]
        lo = (date.fromisoformat(ex).replace(year=date.fromisoformat(ex).year) - __import__('datetime').timedelta(days=60)).isoformat()
        end = None
        for i in range(1, len(B)):
            if B[i - 1][0] >= lo and (date.fromisoformat(B[i][0]) - date.fromisoformat(B[i - 1][0])).days > 30: end = i; break
        if end is None:
            last = B[-1][0]
            if (date.fromisoformat(last) - date.fromisoformat(ex)).days > 300:
                rec['说明'] += ';调出后这个代码一直在交易(改名或被并后沿用),不算退市,没放'; summary.append(rec); continue
            end = len(B)
        B = B[:end]
        cut = 0
        for i in range(len(B) - 1, 0, -1):
            if (date.fromisoformat(B[i][0]) - date.fromisoformat(B[i - 1][0])).days > 60: cut = i; break
        B = B[cut:]
        if len(B) < 5 or B[-1][0] < lo:
            rec['说明'] += ';对不上调出日,没放'; summary.append(rec); continue
        a, b = B[0][0], B[-1][0]
        sp = sorted((d, kk) for d, kk in splits.get(t, []) if a < d <= b)
        sym = t
        if t in panel:   # 面板里同一个代码是后来另一家公司(比如 WM 现在是 Waste Management),这里加后缀区分
            sym = f"{t}__{b[:7].replace('-', '')}"; rec['代码'] = sym
            rec['说明'] += f';面板里的 {t} 是后来用这个代码的另一家公司,这里写成 {sym}'
        frames.append(frame(sym, '', '', B, sp, '标普补充').with_columns(pl.lit(t).alias('source_ticker')))
        rec.update(退市日_polygon='', 数据起=a, 最后交易日=b, 最后收盘价=B[-1][4], 交易天数=len(B), 拆股=';'.join(f'{d}×{kk:g}' for d, kk in sp))
        summary.append(rec)
# 第三步(Lin 11-21 同意):Polygon 参考库漏掉的 2005–2015 年退市股(主要是纳斯达克)。
# 办法:2004-12 ~ 2017-06 每月取一天「全市场当天所有代码」(Polygon grouped daily,只含交易所上市的),
# 2005–2016-06 之间最后一次出现、之后再没出现的 1–4 个字母代码,查当时的公司名和 CIK;
# 去掉:CIK 现在还在交易的(改名)、CIK 在两个面板里的、名字像权证 / 优先股 / 基金 / ETF 的、Polygon 标了非普通股的。
if len(sys.argv) > 5:
    P3 = json.load(gzip.open(sys.argv[5]))
    pc = json.load(open(sys.argv[6]))                  # 面板 CIK → 面板代码
    have = {r['代码'] for r in summary if r['交易天数']}
    for row in P3['keep']:
        t, first, last, nmon, name, ex, typ, cik, figi = row[:9]
        c = (cik or '').lstrip('0')
        rec = dict(代码=t, 公司名=name, 交易所={'XNAS': 'NASDAQ', 'XNYS': 'NYSE', 'XASE': 'AMEX'}.get(ex, ''), polygon_composite_figi=figi,
                   polygon_share_class_figi='', cik=cik, 退市日_polygon='', 数据起='', 最后交易日='', 最后收盘价='', 交易天数=0, 拆股='',
                   说明='Polygon 参考库漏的;按每月全市场代码表找出来的')
        if c and c in pc: continue                     # 面板里有这家公司(可能换了代码)
        if t in have: continue
        bars = P3['dl'].get(t)
        if bars == 'ERR' or not bars:
            rec['说明'] += ';Polygon 没有这个代码的日线'; summary.append(rec); continue
        B = [(day(b[0]), *b[1:]) for b in bars]
        cut = 0
        for i in range(len(B) - 1, 0, -1):
            if (date.fromisoformat(B[i][0]) - date.fromisoformat(B[i - 1][0])).days > 60: cut = i; break
        B = B[cut:]
        if len(B) < 5:
            rec['说明'] += f';只有 {len(B)} 天,太少,没放'; summary.append(rec); continue
        a, b = B[0][0], B[-1][0]
        sp = sorted((d, kk) for d, kk in splits.get(t, []) if a < d <= b)
        sym = t if t not in panel else f"{t}__{b[:7].replace('-', '')}"
        if sym != t: rec['说明'] += f';面板里的 {t} 是后来用这个代码的另一家公司,这里写成 {sym}'
        frames.append(frame(sym, figi, cik, B, sp, b[:4]).with_columns(pl.lit(t).alias('source_ticker')))
        rec.update(代码=sym, 数据起=a, 最后交易日=b, 最后收盘价=B[-1][4], 交易天数=len(B), 拆股=';'.join(f'{d}×{kk:g}' for d, kk in sp))
        if not rec['交易所']: rec['说明'] += ';交易所 Polygon 没记(在 NYSE / NASDAQ / AMEX 之一上市)'
        summary.append(rec)
    p3 = [r for r in summary if '按每月全市场' in r['说明']]
    print('第三步 候选', len(P3['keep']), '进总表', len(p3), '放了', sum(1 for r in p3 if r['交易天数']))
# 省内存:原始 JSON 先丢掉,再按退市年份一年一年写
del J, INA, DL
for v in ('P2', 'P3'):
    if v in globals(): del globals()[v]
import gc; gc.collect()
byy = defaultdict(list)
for fr in frames: byy[fr['退市年'][0]].append(fr)
del frames
nrows = 0
for y in sorted(byy):
    g = pl.concat(byy[y]).drop('退市年').sort(['symbol', 'date'])
    nrows += g.height
    g.write_parquet(f'{out}/退市于{y}.parquet', compression='zstd', compression_level=9, statistics=True)
    byy[y] = None; del g; gc.collect()
summary.sort(key=lambda r: (r['退市日_polygon'] or r['最后交易日'] or '9', r['代码']))
with open(f'{out}/总表.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
ok = [r for r in summary if r['交易天数']]
print('名单(去掉面板后)', len(summary), '面板里已有', n_panel, '取到', len(ok), '取不到', len(summary) - len(ok), '行数', nrows)
from collections import Counter
print(Counter(r['说明'].split(',')[0][:12] for r in summary if not r['交易天数']))
print(sorted(Counter((r['退市日_polygon'] or r['最后交易日'])[:4] for r in ok).items()))
p2 = [r for r in summary if '按标普' in r['说明']]
print('标普补充', len(p2), '放了', sum(1 for r in p2 if r['交易天数']))
for r in p2: print(r['代码'], r['数据起'], r['最后交易日'], r['最后收盘价'], r['说明'][-30:])
