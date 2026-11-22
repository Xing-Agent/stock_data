#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 326 第二样:SPY / RSP / QQQ / IWM 2003 起日线(Polygon 原始价 + 分红 + 拆股),一只一个 CSV。
折算口径和研究库日线一样:
  · split_coefficient = 新股数/旧股数(生效日那一行),close_adj 等 = 只折拆股(价 ÷ 之后所有系数之积,量 × 之)
  · adjusted_close = 拆股 + 分红都折(总回报口径):除息日前的价 × (1 − 分红/前收),再按拆股折
  · QQQ:2004-12-01 ~ 2011-03-22 那段代码是 QQQQ(同一只基金),接成一条,source_ticker 标明"""
import csv, gzip, json, os, sys
from datetime import datetime
from zoneinfo import ZoneInfo


def _near(divs, ex, amt):
    """Polygon 在前后 10 天内已经记了一笔差不多的(金额差 5% 以内),就是同一次分红、日期记得不一样,不重复补"""
    from datetime import date as _d
    e = _d.fromisoformat(ex)
    return any(abs((_d.fromisoformat(d) - e).days) <= 10 and abs(a - amt) <= 0.05 * max(a, amt) for d, a in divs.items())
ET = ZoneInfo('America/New_York')
J = json.load(gzip.open(sys.argv[1])); D = J['data']; out = sys.argv[2]
os.makedirs(out, exist_ok=True)
summ = []
ADD = []
for t in ['SPY', 'RSP', 'QQQ', 'IWM']:
    rows = {}
    parts = [('QQQ', None, '2004-11-30'), ('QQQQ', '2004-12-01', '2011-03-22'), ('QQQ', '2011-03-23', None)] if t == 'QQQ' else [(t, None, None)]
    divs, spl = {}, {}
    for src, a, b in parts:
        for ts, o, h, l, c, v in D['d_' + src]:
            d = datetime.fromtimestamp(ts / 1000, ET).date().isoformat()
            if (a and d < a) or (b and d > b) or d > '2025-12-31': continue
            rows[d] = dict(date=d, open=o, high=h, low=l, close=c, volume=v, source_ticker=src)
        for ex, amt, pay, typ, fr in D['div_' + src]:
            if (a and ex < a) or (b and ex > b): continue
            divs[ex] = divs.get(ex, 0) + float(amt)
        for ex, f, to in D['spl_' + src]: spl[ex] = to / f
    # 11-22(《368》后补):Polygon 分红记录大多从 2007-03 才开始,之前的用 Yahoo 补;Yahoo 的金额按之后的拆股折过,先换回原始每股金额
    if len(sys.argv) > 3:
        Y = json.load(open(sys.argv[3])).get(t, {'div': [], 'spl': []})
        ysp = [(datetime.fromtimestamp(x, ET).date().isoformat(), n / dn) for x, n, dn in Y['spl']]
        for x, amt in Y['div']:
            ex = datetime.fromtimestamp(x, ET).date().isoformat(); f = 1.0
            for e, k in ysp:
                if ex < e: f *= k
            if ex not in divs and ex <= '2025-12-31' and rows and ex >= min(rows) and not _near(divs, ex, amt * f): divs[ex] = round(amt * f, 6); ADD.append((t, ex, round(amt * f, 6)))
    ds = sorted(rows)
    for d in ds:
        rows[d]['dividend_amount'] = round(divs.get(d, 0.0), 6); rows[d]['split_coefficient'] = spl.get(d, 1.0)
    # 分红日不是交易日的(极少):挪到之后第一个交易日
    for ex, amt in divs.items():
        if ex not in rows and ds[0] <= ex <= ds[-1]:
            nxt = next(x for x in ds if x > ex); rows[nxt]['dividend_amount'] = round(rows[nxt]['dividend_amount'] + amt, 6)
    # 折算
    f_split, f_tr = 1.0, 1.0
    for i in range(len(ds) - 1, -1, -1):
        r = rows[ds[i]]
        r['adj_factor'] = f_split
        for k in ('open', 'high', 'low', 'close'): r[k + '_adj'] = round(r[k] / f_split, 6)
        r['volume_adj'] = round(r['volume'] * f_split, 2)
        r['adjusted_close'] = round(r['close'] / f_split * f_tr, 6)
        # 往前一天走:今天的拆股/分红作用在昨天及以前
        f_split *= r['split_coefficient']
        if r['dividend_amount'] and i > 0:
            pc = rows[ds[i - 1]]['close']
            f_tr *= (1 - r['dividend_amount'] / pc)
    cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividend_amount', 'split_coefficient', 'open_adj', 'high_adj', 'low_adj', 'close_adj',
            'volume_adj', 'adj_factor', 'adjusted_close', 'source_ticker']
    with open(f'{out}/{t}_日线.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows[d] for d in ds)
    divd = sorted(d for d in ds if rows[d]['dividend_amount'])
    summ.append(dict(代码=t, 起=ds[0], 止=ds[-1], 行数=len(ds), 分红次数=len(divd), 分红最早=divd[0] if divd else '', 拆股=';'.join(f'{d}×{spl[d]:g}' for d in sorted(spl))))
    print(summ[-1])
with open(f'{out}/说明_每只.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)

with open(f'{out}/分红补自Yahoo.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['代码', '除息日', '每股分红(原始股数)']); w.writerows(sorted(ADD))
print('Yahoo 补分红', len(ADD))
