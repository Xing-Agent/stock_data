#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 562 第一项的 1:标普 500 成分股里收盘站在 50 日均线上面的比例(每天一个数)。
现成指数(S5FI)要付费，所以自己算。
  · 成分：fja05680/sp500(当时的名单，不是现在的往回套),1996-01-02 起。
  · 价格(两段):
      A 段 2003-11 起(主):Polygon 每日全市场行情(按拆股折算),当天名单里的代码直接对 Polygon 当天的代码。
      B 段 1996–2004(近似):Yahoo 日线。Yahoo 只剩还活着的公司，退市、被收购的大多拿不到，
         名单里每天只有约一半到六成的票有价格 —— **有幸存者偏差**,当近似看。
  · 每只票当天要有至少 50 个交易日的收盘才算;比例 = 站上 50 日线的只数 ÷ 当天算得出的只数。
  · 每天都写出「名单几只 / 算得出几只」,覆盖率低的日子自己判断。
  · 代码重复使用的防护(Polygon 段):当天那只票的成交额要在全市场前 2500 名里才用(标普成分基本都在里面)。
  · 名单里有些是公司「后来的代码」(整理者用的数据商习惯),当时 Polygon 上是旧代码，用下面这张对照表接上(只收确定的)。
用法:python3 build_breadth.py 成分原始csv polygon_grouped.json.gz yahoo_early.json.gz OUT_DIR"""
import csv, gzip, json, sys, os
from collections import defaultdict, deque
from datetime import datetime
from zoneinfo import ZoneInfo
csv.field_size_limit(10 ** 9)
MEM, PG, YE, OUT = sys.argv[1:5]; ET = ZoneInfo('America/New_York'); os.makedirs(OUT, exist_ok=True)
chg = [(r[0], set(r[1].split(','))) for r in list(csv.reader(open(MEM, encoding='utf-8-sig')))[1:]]


def members(day, _c={'i': 0}):
    # chg 按日期升序;取 <= day 的最后一行
    lo, hi = 0, len(chg) - 1
    while lo < hi:
        m = (lo + hi + 1) // 2
        if chg[m][0] <= day: lo = m
        else: hi = m - 1
    return chg[lo][1] if chg[lo][0] <= day else set()


ALIAS = {'AON': 'AOC', 'AABA': 'YHOO', 'ANDV': 'TSO', 'ANTM': 'WLP', 'ARNC': 'AA', 'BHGE': 'BHI', 'BEAM': 'FO', 'DXC': 'CSC', 'GOOGL': 'GOOG',
         'MDLZ': 'KFT', 'SPGI': 'MHP', 'TGNA': 'GCI', 'TPR': 'COH', 'VIAV': 'JDSU', 'WBA': 'WAG', 'ZBH': 'ZMH', 'MSI': 'MOT', 'LB': 'LTD',
         'LEHMQ': 'LEH', 'EKDKQ': 'EK', 'ABKFQ': 'ABK', 'BTUUQ': 'BTU', 'CITGQ': 'CIT', 'CCTYQ': 'CC', 'MTLQQ': 'GM', 'RSHCQ': 'RSH',
         'FNMA': 'FNM', 'FMCC': 'FRE', 'SUNEQ': 'WFR'}


def run(days, price_of, tag):
    hist = defaultdict(lambda: deque(maxlen=50)); out = []
    for d in days:
        px = price_of(d)
        for t, c in px.items(): hist[t].append(c)
        M = members(d); above = n = 0
        for t0 in M:
            t = t0 if t0 in px or t0 not in ALIAS else ALIAS[t0]
            h = hist.get(t)
            if t in px and h is not None and len(h) == 50:
                n += 1; above += px[t] > sum(h) / 50
        out.append((d, len(M), n, round(above / n * 100, 2) if n else None, tag))
    return out


# A 段 Polygon
G = json.load(gzip.open(PG)); gd = sorted(G)
A = run(gd, lambda d: {t: c for t, c, rk in G[d] if rk < 2500}, 'Polygon')
# B 段 Yahoo
Y = json.load(gzip.open(YE)); yp = defaultdict(dict)
for t, rows in Y.items():
    for s, c, v in rows:
        if c: yp[datetime.fromtimestamp(s, ET).date().isoformat()][t] = c
B = run(sorted(yp), lambda d: yp[d], 'Yahoo(只有活下来的公司)')
# 拼:2004-01-02 起用 A(A 段 2003-09-10 起有价格，50 天后才有数)
cut = next(d for d, m, n, p, _ in A if p is not None and n > 300)
rows = [r for r in B if r[0] < cut and r[3] is not None] + [r for r in A if r[0] >= cut]
with open(f'{OUT}/标普500_站上50日线比例.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['date', 'pct_above_50dma', 'members', 'counted', 'source']); w.writerows((d, p, m, n, s) for d, m, n, p, s in rows)
# 两段重叠期对比(B 段幸存者偏差有多大)
bA = {d: p for d, m, n, p, _ in A if p is not None}; ov = [(d, p, bA[d]) for d, m, n, p, _ in B if p is not None and d in bA]
import statistics as st
if ov:
    diff = [a - b for _, a, b in ov]
    xs, ys = [a for _, a, _ in ov], [b for _, _, b in ov]
    mx, my = st.mean(xs), st.mean(ys)
    corr = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) * sum((y - my) ** 2 for y in ys)) ** 0.5
    print('重叠', len(ov), ov[0][0], ov[-1][0], 'Yahoo-Polygon 平均差', round(st.mean(diff), 2), '绝对差中位', round(st.median([abs(x) for x in diff]), 2), '相关', round(corr, 3))
cov = defaultdict(list)
for d, m, n, p, s in rows: cov[d[:4]].append(n / m if m else 0)
print('每年平均覆盖率', {y: round(sum(v) / len(v), 2) for y, v in sorted(cov.items())})
print('起止', rows[0], rows[-1], '切换日', cut, '行数', len(rows))
for d in ('2000-03-24', '2000-09-01', '2007-10-09', '2020-02-19', '2021-12-31', '2022-01-03', '2024-07-16', '2026-11-27'):
    r = next((x for x in rows if x[0] >= d), None); print(d, r)
