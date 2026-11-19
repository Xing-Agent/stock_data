#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 318 · 研发池 1 小时线(试水批):Polygon 原生 30 分钟线(原始价)→ 拼成「不跨时段」的 1 小时线 + 拆股并股折算

大白话:
  · 为什么不用 Polygon 自带的小时线:它按整点切,09:00–10:00 那根把盘前半小时和开盘半小时混在一起,没法标「这根是盘前还是常规」。
    所以拿 30 分钟线自己拼,每根只属于一个时段:
      盘前 pre     04:00–05:00 … 08:00–09:00(整点),09:00–09:30(半根)
      常规 regular 09:30–10:30 … 14:30–15:30,15:30–16:00(半根)—— 一天 7 根,和《147》的接口切法一样
      盘后 post    16:00–17:00 … 19:00–20:00(整点)
    半日交易日(13:00 收盘):常规到 12:30–13:00(半根)为止,13:00 以后算盘后,按整点切。
  · 时间:time_utc 是这根的开始时间(UTC,带时区);另给 time_et(美东,带偏移)方便看。
  · 折算:用我们自己的拆股表,不用 Polygon 的 adjusted —— 研究库日线的 split_coefficient,再按「全池版并股表」补上
    是并股 / 是拆股 / 日期错位 三类。价格 ÷ 系数、成交量 × 系数,作用在生效日(美东)之前的所有 K 线上。破产重组 / 断档切开的不折。
用法:python3 build_1h.py raw.json.gz out_dir
"""
import csv, gzip, json, math, os, sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta, time, date
from zoneinfo import ZoneInfo
import pandas as pd

ET = ZoneInfo('America/New_York'); UTC = timezone.utc
R = '/home/claude/stock_data'
EARLY = {'2015-11-27', '2015-12-24', '2016-11-25', '2017-07-03', '2017-11-24', '2018-07-03', '2018-11-23', '2018-12-24', '2019-07-03',
         '2019-11-29', '2019-12-24', '2020-11-27', '2020-12-24', '2021-11-26', '2022-11-25', '2023-07-03', '2023-11-24', '2024-07-03',
         '2024-11-29', '2024-12-24', '2025-07-03', '2025-11-28', '2025-12-24'}


def bucket(dt):
    """美东时间 → (这根 1h 的开始, 时段)"""
    d = dt.date().isoformat(); close = time(13, 0) if d in EARLY else time(16, 0)
    t = dt.time()
    if t < time(9, 30):
        st = dt.replace(minute=0, second=0, microsecond=0); return st, 'pre'
    if t < close:
        o = datetime.combine(dt.date(), time(9, 30), ET); k = int((dt - o).total_seconds() // 3600)
        return o + timedelta(hours=k), 'regular'
    st = dt.replace(minute=0, second=0, microsecond=0)
    return st, 'post'


def split_events(folder):
    """返回 [(生效日, 系数 new/old)]:研究库日线系数 + 全池并股表修正"""
    fp = f'{R}/market_ext_1105/{folder}/daily.json.gz'
    if not os.path.exists(fp): fp = f'{R}/market_etf_1106/{folder}/daily.json.gz'
    D = json.load(gzip.open(fp))['data']
    ev = {x['date']: float(x['split_coefficient']) for x in D if x.get('split_coefficient') not in (None, 1, 1.0)}
    note = []
    for r in TABLE.get(folder, []):
        k = r['结论']; ratio = r['比例(新股数:旧股数)']
        if k in ('是并股', '是拆股') and ratio:
            a, b = [float(x) for x in ratio.split(':')]
            if r['生效日'] not in ev: ev[r['生效日']] = a / b; note.append(f"按并股表补 {r['生效日']} {ratio}")
        elif k == '有系数但日期错位' and ratio:
            a, b = [float(x) for x in ratio.split(':')]; c = a / b
            for d0 in list(ev):
                if abs(math.log(ev[d0] / c)) < 0.01 and abs((date.fromisoformat(d0) - date.fromisoformat(r['生效日'])).days) <= 15:
                    ev.pop(d0); note.append(f'系数从 {d0} 挪到 {r["生效日"]}')
            ev[r['生效日']] = c
    return sorted(ev.items()), note


def load_table():
    T = defaultdict(list)
    for r in csv.DictReader(open(f'{R}/market_ext_1105/并股事件表_第二来源_全池_1118.csv', encoding='utf-8-sig')):
        T[r['代码']].append(r)
    return T


TABLE = load_table()


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    J = json.load(gzip.open(raw)); H = J['data']
    by = defaultdict(list)
    for k, rows in H.items():
        f, t, a, b = k.split('|'); by[f].append((t, a, b, rows))
    summary = []
    for f, parts in sorted(by.items()):
        recs = []
        for t, a, b, rows in parts:
            for ts, o, h, l, c, v, n in rows:
                dt = datetime.fromtimestamp(ts / 1000, ET)
                if not (a <= dt.date().isoformat() <= b): continue
                if not (time(4, 0) <= dt.time() < time(20, 0)): continue   # 只要 04:00–20:00(夜盘不要)
                st, ses = bucket(dt)
                recs.append((st, ses, ts, o, h, l, c, v, n, t))
        if not recs:
            summary.append(dict(代码=f, 起='', 止='', 行数=0, 有K线的交易日=0, 常规时段缺整天='', 拆股折算='', 说明='取不到:Polygon 这段时间没有这只票的 30 分钟线')); continue
        df = pd.DataFrame(recs, columns=['start', 'session', 'ts', 'o', 'h', 'l', 'c', 'v', 'n', 'ticker']).sort_values('ts')
        g = df.groupby(['start', 'session'], sort=True)
        bars = g.agg(open=('o', 'first'), high=('h', 'max'), low=('l', 'min'), close=('c', 'last'), volume=('v', 'sum'),
                     trades=('n', 'sum'), source_ticker=('ticker', 'last'), n30=('o', 'size')).reset_index()
        bars['time_utc'] = pd.to_datetime([s.astimezone(UTC) for s in bars['start']], utc=True)
        bars['time_et'] = [s.isoformat() for s in bars['start']]
        bars['date_et'] = [s.date().isoformat() for s in bars['start']]
        ev, note = split_events(f)
        fac = []
        for d in bars['date_et']:
            c = 1.0
            for e, k in ev:
                if d < e: c *= k
            fac.append(c)
        bars['adj_factor'] = fac   # 折算价 = 原始价 ÷ adj_factor;折算量 = 原始量 × adj_factor
        for col in ('open', 'high', 'low', 'close'):
            bars[col + '_adj'] = bars[col] / bars['adj_factor']
        bars['volume_adj'] = bars['volume'] * bars['adj_factor']
        cols = ['time_utc', 'time_et', 'session', 'open', 'high', 'low', 'close', 'volume', 'open_adj', 'high_adj', 'low_adj', 'close_adj',
                'volume_adj', 'adj_factor', 'trades', 'source_ticker']
        bars = bars[cols].sort_values('time_utc').reset_index(drop=True)
        bars.to_parquet(os.path.join(out, f'{f}.parquet'), index=False)
        # 缺天:常规时段对照 SPY 日历
        days = set(bars.loc[bars.session == 'regular', 'time_et'].str[:10])
        lo, hi = min(days), max(days)
        miss = [d for d in CAL if lo <= d <= hi and d not in days]
        summary.append(dict(代码=f, 起=bars['time_et'].iloc[0][:10], 止=bars['time_et'].iloc[-1][:10], 行数=len(bars), 有K线的交易日=len(days),
                            常规时段缺整天=';'.join(miss[:20]) + (f' …共{len(miss)}天' if len(miss) > 20 else ''),
                            拆股折算=';'.join(f'{e}×{k:g}' for e, k in ev if lo <= e <= '2026-12-31' and e > lo) + (('|' + ';'.join(note)) if note else ''),
                            说明='代码改过:' + '→'.join(dict.fromkeys(p[0] for p in parts)) if len({p[0] for p in parts}) > 1 else ''))
        print(f, len(bars), len(miss))
    return summary


if __name__ == '__main__':
    spy = json.load(gzip.open(f'{R}/market_etf_1106/SPY/daily.json.gz'))['data']
    CAL = [x['date'] for x in spy]
    s = main(sys.argv[1], sys.argv[2])
    with open(os.path.join(sys.argv[2], '说明_每只票.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(s[0])); w.writeheader(); w.writerows(s)
