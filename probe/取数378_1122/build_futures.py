#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 378 第 3 样:ES、NQ(顺手 YM、RTY)连续合约日线,来源 Yahoo Finance 的 ES=F / NQ=F 连续合约。
Yahoo 的连续合约是「近月合约直接拼」:不做价差调整,换月那天会有一个跳(近月和次月的价差)。
这里原样给出,另标出每个季月(3/6/9/12 月)第三个周五前后的换月窗口,并估一下每次换月的跳空。
用法:python3 build_futures.py RAW.json OUT_DIR"""
import csv, json, os, sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
ET = ZoneInfo('America/New_York')
J = json.load(open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
NAME = {'ES=F': 'ES_标普500', 'NQ=F': 'NQ_纳指100', 'YM=F': 'YM_道指', 'RTY=F': 'RTY_罗素2000'}


def third_friday(y, m):
    d = date(y, m, 15)
    while d.weekday() != 4: d += timedelta(days=1)
    return d


summ, bad = [], []
IDX = {'ES=F': '^GSPC', 'NQ=F': '^NDX', 'YM=F': '^DJI', 'RTY=F': '^RUT'}
ICLOSE = {}
for ix in set(IDX.values()):
    r = J[ix]['chart']['result'][0]; q = r['indicators']['quote'][0]
    ICLOSE[ix] = {datetime.fromtimestamp(t, ET).date().isoformat(): q['close'][i] for i, t in enumerate(r['timestamp']) if q['close'][i]}
ROLLS = []
for s, v in J.items():
    if s not in NAME: continue
    r = v['chart']['result'][0]; q = r['indicators']['quote'][0]
    rows = []
    for i, ts in enumerate(r['timestamp']):
        if q['close'][i] is None or q['open'][i] is None: continue
        # Yahoo 期货日线的时间戳是当天开盘(美东前一晚 18:00)那一刻,所以按 UTC+? 取交易日:用 ET 时间加 7 小时再取日期
        d = (datetime.fromtimestamp(ts, ET) + timedelta(hours=7)).date().isoformat()
        rows.append(dict(date=d, open=round(q['open'][i], 2), high=round(q['high'][i], 2), low=round(q['low'][i], 2), close=round(q['close'][i], 2),
                         volume=q['volume'][i] or 0))
    # 同一天出现两次的(极少)留后一条
    dd = {}
    for x in rows: dd[x['date']] = x
    rows = [dd[k] for k in sorted(dd)]
    if s in ('ES=F', 'NQ=F'): rows = [x for x in rows if x['date'] >= '2004-01-01'] if False else rows
    rolls = []
    for y in range(int(rows[0]['date'][:4]), int(rows[-1]['date'][:4]) + 1):
        for m in (3, 6, 9, 12):
            tf = third_friday(y, m)
            if rows[0]['date'] <= tf.isoformat() <= rows[-1]['date']: rolls.append(tf)
    for x in rows:
        dt = date.fromisoformat(x['date'])
        x['换月窗口'] = 1 if any(timedelta(days=-9) <= dt - tf <= timedelta(days=1) for tf in rolls) else 0
        mx, mn = max(x['open'], x['close']), min(x['open'], x['close'])
        if x['high'] > mx * 1.05 or x['low'] < mn * 0.95 or x['high'] < mx - 1e-6 or x['low'] > mn + 1e-6:
            o, h, l, c = x['open'], x['high'], x['low'], x['close']
            kind = '收盘不在当天高低之间' if (c > h + 1e-6 or c < l - 1e-6) else '开盘不在当天高低之间' if (o > h + 1e-6 or o < l - 1e-6) else '大振幅(高或低离开收盘超过 5%)'
            exp = '是' if x['换月窗口'] and any(date.fromisoformat(x['date']) == tf for tf in rolls) else ''
            bad.append((NAME[s], x['date'], o, h, l, c, kind, exp))
    # 换月跳空估算:期货收盘 ÷ 现货指数收盘,这个比值在换月那天会突然变一截(近月换成次月的价差);
    # 每个季月第三个周五前 3 个到后 3 个交易日里,比值变得最多的那天当换月日,变动超过 0.3% 才算
    ic = ICLOSE[IDX[s]]; pos = {x['date']: i for i, x in enumerate(rows)}
    roll_days = {}
    for tf in rolls:
        cand = [i for i, x in enumerate(rows) if abs((date.fromisoformat(x['date']) - tf).days) <= 5 and i > 0]
        best = None
        for i in cand:
            d0, d1 = rows[i - 1]['date'], rows[i]['date']
            if d0 in ic and d1 in ic:
                ch = (rows[i]['close'] / ic[d1]) / (rows[i - 1]['close'] / ic[d0])
                if best is None or abs(ch - 1) > abs(best[1] - 1): best = (i, ch)
        if best and abs(best[1] - 1) > 0.003:
            roll_days[best[0]] = best[1]; ROLLS.append((NAME[s], tf.isoformat(), rows[best[0]]['date'], round((best[1] - 1) * 100, 3)))
    f = 1.0
    for i in range(len(rows) - 1, -1, -1):
        x = rows[i]
        for k in ('open', 'high', 'low', 'close'): x[k + '_adj'] = round(x[k] * f, 2)
        x['adj_factor'] = round(f, 6)
        if i in roll_days: f *= roll_days[i]
    fn = f'{out}/{NAME[s]}_连续合约_日线.csv'
    with open(fn, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['date', 'open', 'high', 'low', 'close', 'volume', '换月窗口', 'open_adj', 'high_adj', 'low_adj', 'close_adj', 'adj_factor']); w.writeheader(); w.writerows(rows)
    gaps = 0
    for i in range(1, len(rows)):
        if (date.fromisoformat(rows[i]['date']) - date.fromisoformat(rows[i - 1]['date'])).days > 5: gaps += 1
    summ.append(dict(代码=NAME[s], Yahoo代码=s, 估出的换月次数=len(roll_days), 季月个数=len(rolls), 起=rows[0]['date'], 止=rows[-1]['date'], 天数=len(rows), 中间断档超过5天=gaps, 高低价可疑=sum(1 for b in bad if b[0] == NAME[s])))
    print(summ[-1])
with open(f'{out}/说明_每个.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)
with open(f'{out}/高低价可疑的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['代码', '日期', '开', '高', '低', '收', '哪里可疑', '是不是交割日(季月第三个周五)']); w.writerows(bad)
with open(f'{out}/换月记录_估算.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['代码', '交割日(季月第三个周五)', '估出的换月日', '换月跳空(%)']); w.writerows(ROLLS)
from collections import Counter
print(Counter(r[0] for r in ROLLS)); print(ROLLS[-6:])
