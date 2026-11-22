#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 368:SPY / QQQ / DIA / 标普 500 指数 1993 ~ 2003-09 的日线,来源 Yahoo Finance(chart 接口,Lin 浏览器取)。
Yahoo 给的开高低收已经按拆股折过(QQQ 2000-03-20 一拆二),adjclose 是拆股 + 分红都折的。
这里还原出原始价,列和《指数ETF长历史_1120》一样;再拿 2003-09-10 ~ 2004-12-31 跟我们的 Polygon 日线逐天比。
用法:python3 build_368.py RAW.json OUT_DIR POLYGON_DAILY_DIR"""
import csv, json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo
ET = ZoneInfo('America/New_York')
raw, out, pdir = sys.argv[1:4]; os.makedirs(out, exist_ok=True)
J = json.load(open(raw))
# 坏点:QQQ 这两天的最低价比开收盘低 10% 以上,但纳斯达克 100 指数当天最低只比开收盘低 0%、1.7%,是坏成交。
# 改成:开收盘较低者 × (1 − 指数当天的这个比例)。其余大振幅日子指数同样大振幅,是真行情(2000-04-04 纳指盘中跌 12.6%)
FIX_LOW = {('QQQ', '2000-06-02'): 0.000, ('QQQ', '2001-04-20'): 0.017}
NAME = {'SPY': 'SPY', 'QQQ': 'QQQ', 'DIA': 'DIA', '^GSPC': '标普500指数'}
summ, bad_all, cmp_all = [], [], []
for s, v in J.items():
    r = v['chart']['result'][0]; q = r['indicators']['quote'][0]; adj = r['indicators']['adjclose'][0]['adjclose']
    ev = r.get('events') or {}
    divs = {datetime.fromtimestamp(int(k), ET).date().isoformat(): x['amount'] for k, x in (ev.get('dividends') or {}).items()}
    spl = {datetime.fromtimestamp(int(k), ET).date().isoformat(): x['numerator'] / x['denominator'] for k, x in (ev.get('splits') or {}).items()}
    rows = []
    for i, ts in enumerate(r['timestamp']):
        d = datetime.fromtimestamp(ts, ET).date().isoformat()
        if q['close'][i] is None: continue
        rows.append(dict(date=d, o=q['open'][i], h=q['high'][i], l=q['low'][i], c=q['close'][i], v=q['volume'][i], ac=adj[i]))
    # Yahoo 价是拆股折过的:乘回「之后所有拆股」得原始价
    for x in rows:
        f = 1.0
        for e, k in spl.items():
            if x['date'] < e: f *= k
        x['f'] = f
    outrows = []
    for x in rows:
        if x['date'] > '2003-09-09': continue
        f = x['f']
        rr = dict(date=x['date'], open=round(x['o'] * f, 4), high=round(x['h'] * f, 4), low=round(x['l'] * f, 4), close=round(x['c'] * f, 4),
                  volume=(round(x['v'] / f) if x['v'] else '') if s != '^GSPC' else '', dividend_amount=divs.get(x['date'], 0.0) * f if s != '^GSPC' else '',
                  split_coefficient=spl.get(x['date'], 1.0), open_adj=round(x['o'], 4), high_adj=round(x['h'], 4), low_adj=round(x['l'], 4),
                  close_adj=round(x['c'], 4), volume_adj=(x['v'] or '') if s != '^GSPC' else '', adj_factor=f,
                  adjusted_close=round(x['ac'], 6) if s != '^GSPC' else round(x['c'], 4), source='Yahoo Finance')
        if (s, x['date']) in FIX_LOW:
            nl = round(min(rr['open'], rr['close']) * (1 - FIX_LOW[(s, x['date'])]), 4)
            bad_all.append((NAME[s], rr['date'], rr['open'], rr['high'], rr['low'], rr['close'], f"已改:最低 {rr['low']} → {nl}(纳指 100 当天没这么低)"))
            rr['low'] = nl; rr['low_adj'] = round(nl / f, 4)
        outrows.append(rr)
        mx, mn = max(rr['open'], rr['close']), min(rr['open'], rr['close'])
        if rr['high'] > mx * 1.05 or rr['low'] < mn * 0.95 or rr['high'] < mx or rr['low'] > mn:
            bad_all.append((NAME[s], rr['date'], rr['open'], rr['high'], rr['low'], rr['close'],
                            '最高低于开收盘' if rr['high'] < mx else '最低高于开收盘' if rr['low'] > mn else f"最高比开收盘高 {rr['high']/mx*100-100:.1f}% / 最低低 {100-rr['low']/mn*100:.1f}%"))
    fn = f'{out}/{NAME[s]}_日线_1993起.csv'
    with open(fn, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(outrows[0])); w.writeheader(); w.writerows(outrows)
    # 和 Polygon 重叠段比
    cm = ''
    if s != '^GSPC':
        P = {x['date']: x for x in csv.DictReader(open(f'{pdir}/{s}_日线.csv'))}
        Y = {x['date']: x for x in rows if '2003-09-10' <= x['date'] <= '2004-12-31'}
        ds = sorted(set(P) & set(Y))
        diffs = [abs(Y[d]['c'] * Y[d]['f'] / float(P[d]['close']) - 1) for d in ds]
        hd = [abs(Y[d]['h'] * Y[d]['f'] / float(P[d]['high']) - 1) for d in ds]
        # 总回报口径:两边每天涨跌幅差
        yr = [Y[ds[i]]['ac'] / Y[ds[i - 1]]['ac'] - 1 for i in range(1, len(ds))]
        pr = [float(P[ds[i]]['adjusted_close']) / float(P[ds[i - 1]]['adjusted_close']) - 1 for i in range(1, len(ds))]
        rd = [abs(a - b) for a, b in zip(yr, pr)]
        only = (len(set(P) - set(Y) & {d for d in P if d <= '2004-12-31'}), len(set(Y) - set(P)))
        cm = dict(代码=NAME[s], 重叠天数=len(ds), 收盘价最大差=f'{max(diffs)*100:.3f}%', 收盘价平均差=f'{sum(diffs)/len(diffs)*100:.4f}%',
                  收盘价差超过1分钱的天数=sum(abs(Y[d]['c'] * Y[d]['f'] - float(P[d]['close'])) > 0.011 for d in ds),
                  最高价差超过0点5pct的天数=sum(x > 0.005 for x in hd), 复权后每天涨跌幅最大差=f'{max(rd)*100:.3f}%', 只有一边有的天=f'Polygon 多 {only[0]} 天 / Yahoo 多 {only[1]} 天')
        cmp_all.append(cm); print(cm)
    summ.append(dict(代码=NAME[s], 起=outrows[0]['date'], 止=outrows[-1]['date'], 天数=len(outrows), 分红次数=sum(1 for x in outrows if x['dividend_amount']),
                     拆股=';'.join(f'{d}×{k:g}' for d, k in spl.items() if d <= '2003-09-09')))
    print(summ[-1])
for name, rows in [('说明_每只.csv', summ), ('和Polygon重叠段对比_2003-09至2004.csv', cmp_all)]:
    with open(f'{out}/{name}', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
with open(f'{out}/高低价可疑的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['代码', '日期', '开', '高', '低', '收', '哪里可疑']); w.writerows(bad_all)
print('可疑', len(bad_all)); [print(b) for b in bad_all[:40]]
