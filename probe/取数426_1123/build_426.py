#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 426:标普 500、道琼斯工业、纳斯达克综合三个指数尽量长的日线。
大白话:
  · 标普 500(^GSPC):Yahoo,1927-12-30 起。1962 年以前 Yahoo 只有收盘价(开高低和收盘写成同一个数),这里把开高低留空。
  · 道指:Yahoo 只有 1992 起(带开高低收量);1928–1991 用 MeasuringWorth 的每日收盘(只有收盘)。1992 全年两边逐天比对。
  · 纳指(^IXIC):Yahoo,1971-02-05 起;1984-10-11 以前只有收盘。
  · 指数不用复权:*_adj 和 adjusted_close 就等于原值,列和《指数ETF_1993起_1122》一样,末尾多一列「数据完整度」。
  · 「开盘=前一天收盘」:Yahoo 的标普 1962–2011 很多天开盘价其实是照抄前一天收盘(当年没记开盘),最高最低是真的;这些天在「数据完整度」里标出来。
  · 1952 年以前纽交所周六也开市:MeasuringWorth 的道指有周六,Yahoo 的标普没有周六(Yahoo 本身就没收)。
  · 取到 2026-11-20(上周五)收盘。
用法:python3 build_426.py YAHOO.json.gz MW_DJA.csv.gz OUT_DIR"""
import csv, gzip, json, os, sys
from datetime import datetime, date
from zoneinfo import ZoneInfo
from collections import Counter
ET = ZoneInfo('America/New_York'); LAST = '2026-11-20'
Y = json.load(gzip.open(sys.argv[1])); MW = gzip.open(sys.argv[2], 'rt').read().splitlines(); OUT = sys.argv[3]; os.makedirs(OUT, exist_ok=True)
COLS = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividend_amount', 'split_coefficient', 'open_adj', 'high_adj', 'low_adj',
        'close_adj', 'volume_adj', 'adj_factor', 'adjusted_close', 'source', '数据完整度']
R2 = lambda x: None if x is None else round(x, 2)


def yahoo(sym):
    R = Y[sym]['chart']['result'][0]; q = R['indicators']['quote'][0]; out = []
    for i, t in enumerate(R['timestamp']):
        d = datetime.fromtimestamp(t, ET).date().isoformat()
        if d > LAST or q['close'][i] is None: continue
        out.append(dict(date=d, o=R2(q['open'][i]), h=R2(q['high'][i]), l=R2(q['low'][i]), c=R2(q['close'][i]), v=q['volume'][i] or None, src='Yahoo Finance'))
    return out


def row(x, prev_c):
    o, h, l, c = x['o'], x['h'], x['l'], x['c']
    if o is None or (o == h == l == c): o = h = l = None; q = '只有收盘'
    elif prev_c is not None and o == prev_c: q = '开盘=前一天收盘(当年没记开盘,高低收是真的)'
    else: q = '完整'
    return dict(date=x['date'], open=o, high=h, low=l, close=c, volume=x['v'], dividend_amount='', split_coefficient=1.0,
                open_adj=o, high_adj=h, low_adj=l, close_adj=c, volume_adj=x['v'], adj_factor=1.0, adjusted_close=c, source=x['src'], 数据完整度=q)


def write(name, xs):
    rows, pc = [], None
    for x in xs: rows.append(row(x, pc)); pc = x['c']
    with open(f'{OUT}/{name}_日线.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=COLS); w.writeheader(); w.writerows(rows)
    seg, cur = [], None   # 按完整度分段
    for r in rows:
        k = r['数据完整度']
        if cur and cur[0] == k: cur[2] = r['date']; cur[3] += 1
        else: cur = [k, r['date'], r['date'], 1]; seg.append(cur)
    big = [(r['date'], round(r['close'] / rows[i - 1]['close'] - 1, 4)) for i, r in enumerate(rows) if i and abs(r['close'] / rows[i - 1]['close'] - 1) > 0.10]
    vol0 = next((r['date'] for r in rows if r['volume']), '')
    return dict(指数=name, 起=rows[0]['date'], 止=rows[-1]['date'], 行数=len(rows), 成交量起=vol0,
                各段完整度=';'.join(f'{a}~{b} {k}({n}天,主要)' if n > 200 else '' for k, a, b, n in seg if n > 200).strip(';'),
                完整度天数=';'.join(f'{k}:{n}' for k, n in Counter(r['数据完整度'] for r in rows).most_common()),
                周六天数=sum(date.fromisoformat(r['date']).weekday() == 5 for r in rows),
                单日涨跌超10pct=';'.join(f'{d}({x * 100:+.1f}%)' for d, x in big)), rows


summ = []
s, _ = write('标普500指数', yahoo('^GSPC')); summ.append(s)
s, _ = write('纳斯达克综合指数', yahoo('^IXIC')); summ.append(s)
# 道指:MW 1927-12-31 ~ 1991-12-31 + Yahoo 1992 起;1992 全年比对
mw = {}
for line in MW[1:]:
    d, c = line.split(','); m, dd, y = d.split('/'); mw[f'{y}-{int(m):02d}-{int(dd):02d}'] = float(c)
dj = yahoo('^DJI'); yd = {x['date']: x['c'] for x in dj}
cmp = [(d, mw[d], yd[d], round(yd[d] / mw[d] - 1, 5)) for d in sorted(mw) if d in yd]
only_mw = [d for d in mw if d.startswith('1992') and d not in yd]; only_y = [d for d in yd if d.startswith('1992') and d not in mw]
print('道指 1992 比对', len(cmp), '最大差', max(abs(x[3]) for x in cmp), '差超0.1%', sum(abs(x[3]) > 0.001 for x in cmp), '只MW有', only_mw, '只Y有', only_y)
with open(f'{OUT}/道指_1992年两个来源比对.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['日期', 'MeasuringWorth收盘', 'Yahoo收盘', '差']); w.writerows(cmp)
early = [dict(date=d, o=None, h=None, l=None, c=mw[d], v=None, src='MeasuringWorth') for d in sorted(mw) if d < '1992-01-01']
s, _ = write('道琼斯工业指数', early + dj); summ.append(s)
s['接缝'] = f"1991-12-31 MW {mw['1991-12-31']} → 1992-01-02 Yahoo {yd['1992-01-02']};1992 年 {len(cmp)} 天两边最大差 {max(abs(x[3]) for x in cmp) * 100:.3f}%"
with open(f'{OUT}/说明_每只.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    keys = list(dict.fromkeys(k for x in summ for k in x)); w = csv.DictWriter(fh, fieldnames=keys); w.writeheader(); w.writerows(summ)
for x in summ: print(x)
