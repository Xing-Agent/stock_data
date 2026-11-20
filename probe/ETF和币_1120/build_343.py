#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 343:23 只指数 / 行业 / 杠杆 ETF 的日线(2003 起)和 1 小时线(2015 起;2004–2014 先拿 SPY 试、过关后其余也取了)。
大白话:
  · 全部来自 Polygon(Lin 浏览器取,adjusted=false 原始价 + 分红 + 拆股记录)。
  · 日线格式和《指数ETF长历史_1120》一样:原始价、只折拆股的 *_adj、拆股加分红都折的 adjusted_close。
  · 小时线格式和《小时线_1119》全量一样:用 Polygon 原生 30 分钟线拼,每根不跨时段(盘前整点、常规从 9:30 起、盘后整点),
    半日交易日 13:00 以后算盘后,夜盘不要。折算按 Polygon 拆股记录,折到今天。
  · 今天(11-20)美股还在交易,只取到 11-19 收盘,不放半天的数据。
  · QQQ 2004-12-01 ~ 2011-03-22 那段代码是 QQQQ(同一只基金),日线、小时线都接成一条。
用法:python3 build_343.py RAW.json.gz OUT_DIR RAW_2004_2014.json.gz
"""
import csv, gzip, json, os, sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import polars as pl

ET = ZoneInfo('America/New_York')
LAST = '2026-11-19'
TICKERS = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC', 'SMH', 'KRE',
           'TQQQ', 'SQQQ', 'SOXL', 'SOXS', 'SH', 'PSQ']
# 半日交易日(13:00 收盘)。2015–2025 同《小时线_1119》;2004–2014 按 NYSE 公告;2026 到 11-19 为止没有
EARLY = {'2004-11-26', '2005-11-25', '2006-07-03', '2006-11-24', '2007-07-03', '2007-11-23', '2007-12-24', '2008-07-03', '2008-11-28',
         '2008-12-24', '2009-11-27', '2009-12-24', '2010-11-26', '2011-11-25', '2012-07-03', '2012-11-23', '2012-12-24', '2013-07-03',
         '2013-11-29', '2013-12-24', '2014-07-03', '2014-11-28', '2014-12-24',
         '2015-11-27', '2015-12-24', '2016-11-25', '2017-07-03', '2017-11-24', '2018-07-03', '2018-11-23', '2018-12-24', '2019-07-03',
         '2019-11-29', '2019-12-24', '2020-11-27', '2020-12-24', '2021-11-26', '2022-11-25', '2023-07-03', '2023-11-24', '2024-07-03',
         '2024-11-29', '2024-12-24', '2025-07-03', '2025-11-28', '2025-12-24'}


def et_day(ts): return datetime.fromtimestamp(ts / 1000, ET).date().isoformat()


def parts_of(t):
    return [('QQQ', None, '2004-11-30'), ('QQQQ', '2004-12-01', '2011-03-22'), ('QQQ', '2011-03-23', None)] if t == 'QQQ' else [(t, None, None)]


def daily(D, t):
    rows, divs, spl = {}, {}, {}
    for src, a, b in parts_of(t):
        for ts, o, h, l, c, v, n in D['d|' + src]:
            d = et_day(ts)
            if (a and d < a) or (b and d > b) or d > LAST: continue
            rows[d] = dict(date=d, open=o, high=h, low=l, close=c, volume=v, source_ticker=src)
        for ex, amt, pay, typ, fr in D['div|' + src]:
            if (a and ex < a) or (b and ex > b) or ex > LAST: continue
            divs[ex] = divs.get(ex, 0) + float(amt)
        for ex, f, to in D['spl|' + src]:
            if ex <= LAST: spl[ex] = to / f
    ds = sorted(rows)
    for d in ds:
        rows[d]['dividend_amount'] = round(divs.get(d, 0.0), 6); rows[d]['split_coefficient'] = spl.get(d, 1.0)
    for ex, amt in divs.items():   # 除息日不是交易日的(极少):挪到之后第一个交易日
        if ex not in rows and ds[0] <= ex <= ds[-1]:
            nxt = next(x for x in ds if x > ex); rows[nxt]['dividend_amount'] = round(rows[nxt]['dividend_amount'] + amt, 6)
    lost = [ex for ex in spl if ex not in rows and ds[0] <= ex <= ds[-1]]
    for ex in lost:                # 拆股生效日不是交易日的:挪到之后第一个交易日
        nxt = next(x for x in ds if x > ex); rows[nxt]['split_coefficient'] *= spl[ex]
    f_split, f_tr = 1.0, 1.0
    for i in range(len(ds) - 1, -1, -1):
        r = rows[ds[i]]
        r['adj_factor'] = f_split
        for k in ('open', 'high', 'low', 'close'): r[k + '_adj'] = round(r[k] / f_split, 6)
        r['volume_adj'] = round(r['volume'] * f_split, 2)
        r['adjusted_close'] = round(r['close'] / f_split * f_tr, 6)
        f_split *= r['split_coefficient']
        if r['dividend_amount'] and i > 0:
            f_tr *= (1 - r['dividend_amount'] / rows[ds[i - 1]]['close'])
    return rows, ds, {d: rows[d]['split_coefficient'] for d in ds if rows[d]['split_coefficient'] != 1.0}


def hourly(D, t, years, splits):
    """30 分钟线 → 不跨时段的 1 小时线;splits = {生效日: 系数},折到今天"""
    rec = []
    for src, a, b in parts_of(t):
        for y in years:
            if (b and f'{y}-01-01' > b) or (a and f'{y}-12-31' < a): continue   # 这一年不在这段代码的时间里
            for ts, o, h, l, c, v, n in D.get(f'm30|{src}|{y}', []):
                rec.append((src, a or "0000", b or "9999", int(ts), float(o), float(h), float(l), float(c), float(v), int(n)))
    if not rec: return None
    df = pl.DataFrame(rec, schema=['ticker', 'a', 'b', 'ts', 'o', 'h', 'l', 'c', 'v', 'n'], orient='row').unique(['ticker', 'ts'])
    et = pl.from_epoch('ts', time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York')
    df = df.with_columns(et.dt.strftime('%Y-%m-%d').alias('d'), (et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)).alias('mins'))
    df = df.filter((pl.col('d') >= pl.col('a')) & (pl.col('d') <= pl.col('b')) & (pl.col('d') <= LAST) & (pl.col('mins') >= 240) & (pl.col('mins') < 1200))
    close = pl.when(pl.col('d').is_in(list(EARLY))).then(780).otherwise(960)
    df = df.with_columns(pl.when(pl.col('mins') < 570).then(pl.lit('pre')).when(pl.col('mins') < close).then(pl.lit('regular')).otherwise(pl.lit('post')).alias('session'))
    df = df.with_columns(pl.when(pl.col('session') == 'regular').then(570 + ((pl.col('mins') - 570) // 60) * 60).otherwise((pl.col('mins') // 60) * 60).alias('smin'))
    df = df.with_columns((pl.col('ts') - (pl.col('mins') - pl.col('smin')) * 60_000).alias('start')).sort('ts')
    g = df.group_by(['ticker', 'start', 'session', 'd'], maintain_order=True).agg(
        pl.col('o').first().alias('open'), pl.col('h').max().alias('high'), pl.col('l').min().alias('low'), pl.col('c').last().alias('close'),
        pl.col('v').sum().alias('volume'), pl.col('n').sum().alias('trades'), (pl.len() * 30).cast(pl.Int32).alias('minutes'))
    fac = {d: 1.0 for d in g['d'].unique().to_list()}
    for d in fac:
        for e, k in splits.items():
            if d < e: fac[d] *= k
    g = g.with_columns(pl.col('d').replace_strict(fac, return_dtype=pl.Float64).alias('adj_factor'))
    g = g.with_columns(*[(pl.col(x) / pl.col('adj_factor')).alias(x + '_adj') for x in ('open', 'high', 'low', 'close')],
                       (pl.col('volume') * pl.col('adj_factor')).alias('volume_adj'),
                       pl.from_epoch('start', time_unit='ms').dt.replace_time_zone('UTC').alias('time_utc'), pl.lit(t).alias('symbol'))
    return g.select('symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume', 'open_adj', 'high_adj', 'low_adj', 'close_adj',
                    'volume_adj', 'adj_factor', 'trades', 'minutes', pl.col('ticker').alias('source_ticker'), 'd').sort('time_utc')


def check(h, rows, a0, b0):
    """每天常规时段最高价 vs 日线最高价;常规时段缺的天"""
    hi = dict(h.filter(pl.col('session') == 'regular').group_by('d').agg(pl.col('high').max()).iter_rows())
    dd = [d for d in rows if a0 <= d <= b0]
    miss = [d for d in dd if d not in hi]
    diff = [(d, rows[d]['high'], hi[d], hi[d] / rows[d]['high'] - 1) for d in dd if d in hi and rows[d]['high']]
    return miss, diff


def main(raw, out):
    D = json.load(gzip.open(raw))
    if len(sys.argv) > 3: D.update(json.load(gzip.open(sys.argv[3])))   # 2004–2014 那批 30 分钟线
    errs = [k for k, v in D.items() if v and v[-1] == 'ERR']
    assert not errs, errs
    od, oh, ot = f'{out}/日线', f'{out}/小时线_2015起', f'{out}/小时线_2004_2014'
    for p in (od, oh, ot): os.makedirs(p, exist_ok=True)
    cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividend_amount', 'split_coefficient', 'open_adj', 'high_adj', 'low_adj',
            'close_adj', 'volume_adj', 'adj_factor', 'adjusted_close', 'source_ticker']
    summ, Hs, bad = [], [], []
    for t in TICKERS:
        rows, ds, spl = daily(D, t)
        with open(f'{od}/{t}_日线.csv', 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows[d] for d in ds)
        # 日线自己:折算后单日涨跌超过 40% 的(拆股没折对会冒出来)
        jumps = []
        for i in range(1, len(ds)):
            r0, r1 = rows[ds[i - 1]], rows[ds[i]]
            x = r1['close_adj'] / r0['close_adj'] - 1
            if abs(x) > 0.4: jumps.append(f'{ds[i]}({x * 100:+.0f}%)')
        h = hourly(D, t, range(2015, 2027), spl)
        h = h.filter(pl.col('d') >= '2015-01-01')
        miss, diff = check(h, rows, max('2015-01-01', ds[0]), LAST)
        ok = sum(abs(x[3]) <= 0.01 for x in diff)
        bad += [(t, d, dh, mh, round(r * 100, 2)) for d, dh, mh, r in diff if abs(r) > 0.01]
        Hs.append(h)
        divd = [d for d in ds if rows[d]['dividend_amount']]
        summ.append(dict(代码=t, 日线起=ds[0], 日线止=ds[-1], 日线行数=len(ds), 分红次数=len(divd), 拆股=';'.join(f'{d}×{k:g}' for d, k in spl.items()),
                         折算后单日涨跌超40pct=';'.join(jumps), 小时线起=h['d'].min(), 小时线止=h['d'].max(), 小时线行数=h.height,
                         小时线常规时段缺的天数=len(miss), 缺的天=';'.join(miss[:30]), 比对天数=len(diff), 最高价差1pct以内=ok,
                         占比=f'{ok / len(diff) * 100:.2f}%' if diff else ''))
        print(summ[-1], flush=True)
    H = pl.concat(Hs)
    sizes = []
    for (y,), g in H.with_columns(pl.col('d').str.slice(0, 4).alias('y')).group_by(['y'], maintain_order=True):
        fp = f'{oh}/{y}.parquet'; g.drop('d', 'y').sort(['symbol', 'time_utc']).write_parquet(fp, compression='zstd', compression_level=9, statistics=True)
        sizes.append((y, g.height, os.path.getsize(fp) // 1000))
    print(sorted(sizes))
    with open(f'{out}/说明_每只.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)
    with open(f'{oh}/日线对不上的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['代码', '日期', '日线最高价', '小时线常规时段最高价', '差(%)']); w.writerows(bad)
    # 2004–2014:先拿 SPY 试(逐年核对),过关后其余也取了
    trial_rows, Hs2, bad2 = [], [], []
    for t in TICKERS:
        rows, ds, spl = daily(D, t)
        if ds[0] > '2014-12-31': continue
        h = hourly(D, t, range(2004, 2015), spl)
        if h is None: continue
        h = h.filter((pl.col('d') >= '2004-01-01') & (pl.col('d') <= '2014-12-31'))
        miss, diff = check(h, rows, max('2004-01-01', ds[0]), '2014-12-31')
        ok = sum(abs(x[3]) <= 0.01 for x in diff)
        bad2 += [(t, d, dh, mh, round(r * 100, 2)) for d, dh, mh, r in diff if abs(r) > 0.01]
        Hs2.append(h)
        trial_rows.append(dict(代码=t, 小时线起=h['d'].min(), 小时线止=h['d'].max(), 小时线行数=h.height, 常规时段缺的天数=len(miss),
                               缺的天=';'.join(miss[:30]) + (' …' if len(miss) > 30 else ''), 比对天数=len(diff), 最高价差1pct以内=ok,
                               占比=f'{ok / len(diff) * 100:.2f}%' if diff else ''))
        print(trial_rows[-1], flush=True)
        if t == 'SPY':
            byy = defaultdict(lambda: [0, 0, 0, 0])
            for d, dh, mh, r in diff:
                b = byy[d[:4]]; b[0] += 1; b[1] += abs(r) <= 0.01
            pre = h.filter(pl.col('session') != 'regular').group_by(pl.col('d').str.slice(0, 4).alias('y')).agg(
                pl.col('d').n_unique().alias('n1'), pl.len().alias('n2'))
            for y, nd, nb in pre.iter_rows(): byy[y][2] = nd; byy[y][3] = nb
            spy = [dict(年=y, 比对天数=v[0], 最高价差1pct以内=v[1], 占比=f'{v[1] / v[0] * 100:.2f}%', 有盘前盘后的天=v[2], 盘前盘后根数=v[3])
                   for y, v in sorted(byy.items())]
            with open(f'{ot}/SPY试取_逐年核对.csv', 'w', newline='', encoding='utf-8-sig') as fh:
                w = csv.DictWriter(fh, fieldnames=list(spy[0])); w.writeheader(); w.writerows(spy)
    H2 = pl.concat(Hs2)
    for (y,), g in H2.with_columns(pl.col('d').str.slice(0, 4).alias('y')).group_by(['y'], maintain_order=True):
        g.drop('d', 'y').sort(['symbol', 'time_utc']).write_parquet(f'{ot}/{y}.parquet', compression='zstd', compression_level=9, statistics=True)
    with open(f'{ot}/说明_每只.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(trial_rows[0])); w.writeheader(); w.writerows(trial_rows)
    with open(f'{ot}/日线对不上的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['代码', '日期', '日线最高价', '小时线常规时段最高价', '差(%)']); w.writerows(bad2)
    print('2004-2014', H2.height, 'bad', len(bad2), sum(r['常规时段缺的天数'] for r in trial_rows))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
