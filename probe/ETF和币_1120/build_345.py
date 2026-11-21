#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 345:BTC、ETH 1 小时线,Coinbase(api.exchange.coinbase.com 公开 K 线,Lin 浏览器取),2017-01-01 起,UTC,一周 7 天。
列和 ETF 小时线一样;币没有盘前盘后,session 一律 all;没有拆股,*_adj = 原值、adj_factor = 1;Coinbase 不给成交笔数,trades 为空;
minutes = 60。Coinbase 那一小时没有成交就没有这根 —— 缺的小时逐个列在 说明 里。
用法:python3 build_345.py RAW.json.gz OUT_DIR"""
import csv, gzip, json, os, sys
import polars as pl
J = json.load(gzip.open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
parts, summ, gaps = [], [], []
for p, sym in [('BTC-USD', 'BTC'), ('ETH-USD', 'ETH')]:
    rows = [x for x in J[p] if x[0] != 'ERR']
    df = pl.DataFrame([(int(x[0]), float(x[3]), float(x[2]), float(x[1]), float(x[4]), float(x[5])) for x in rows],
                      schema=['ts', 'open', 'high', 'low', 'close', 'volume'], orient='row').unique('ts').sort('ts')
    df = df.with_columns(pl.from_epoch('ts', time_unit='s').dt.replace_time_zone('UTC').alias('time_utc'), pl.lit(sym).alias('symbol'),
                         pl.lit('all').alias('session'), pl.lit(1.0).alias('adj_factor'), pl.lit(None, dtype=pl.Int64).alias('trades'),
                         pl.lit(60, dtype=pl.Int32).alias('minutes'), pl.lit(p).alias('source_ticker'))
    df = df.with_columns(*[pl.col(c).alias(c + '_adj') for c in ('open', 'high', 'low', 'close', 'volume')])
    ts = df['ts'].to_list(); have = set(ts)
    miss = [t for t in range(ts[0], ts[-1] + 1, 3600) if t not in have]
    # 连着缺的并成一段
    seg = []
    for t in miss:
        if seg and t == seg[-1][1] + 3600: seg[-1][1] = t
        else: seg.append([t, t])
    fmt = lambda t: pl.from_epoch(pl.Series([t]), time_unit='s')[0].strftime('%Y-%m-%d %H:00')
    for a, b in seg: gaps.append(dict(币=sym, 从=fmt(a), 到=fmt(b), 缺几小时=(b - a) // 3600 + 1))
    bad = df.filter((pl.col('high') < pl.max_horizontal('open', 'close')) | (pl.col('low') > pl.min_horizontal('open', 'close')) | (pl.col('low') <= 0)).height
    summ.append(dict(币=sym, 来源=f'Coinbase {p}', 起=str(df['time_utc'][0]), 止=str(df['time_utc'][-1]), 根数=df.height, 应有根数=df.height + len(miss),
                     缺的小时=len(miss), 缺的段数=len(seg), 最长一段缺几小时=max([b['缺几小时'] for b in gaps if b['币'] == sym] or [0]), 高低价矛盾的根数=bad))
    parts.append(df)
    print(summ[-1])
A = pl.concat(parts).with_columns(pl.col('time_utc').dt.year().alias('y'))
cols = ['symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume', 'open_adj', 'high_adj', 'low_adj', 'close_adj',
        'volume_adj', 'adj_factor', 'trades', 'minutes', 'source_ticker']
for (y,), g in A.group_by(['y'], maintain_order=True):
    g.select(cols).sort(['symbol', 'time_utc']).write_parquet(f'{out}/{y}.parquet', compression='zstd', compression_level=9, statistics=True)
for name, rows in [('说明_每个币.csv', summ), ('缺的小时.csv', gaps)]:
    with open(f'{out}/{name}', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(sorted(gaps, key=lambda g: -g['缺几小时'])[:12])
