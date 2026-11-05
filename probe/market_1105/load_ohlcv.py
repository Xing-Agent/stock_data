#!/usr/bin/env python3
"""把需要的代码的日线从全量库(Polygon flat files,原始价)抽出来,再接上 Polygon 2026-08-04 以后的日线。
用法:python3 load_ohlcv.py plan.json grouped_daily.json.gz out.parquet"""
import glob, gzip, json, os, sys
import polars as pl

plan = json.load(open(sys.argv[1]))['plan']
tk = sorted({p[0] for v in plan.values() for p in v['pieces']})
fs = sorted(glob.glob('/home/claude/pituni/day/*.csv.gz'))
parts = []
for f in fs:
    d = pl.read_csv(f, columns=['ticker', 'open', 'high', 'low', 'close', 'volume'],
                    schema_overrides={'ticker': pl.String, 'open': pl.Float64, 'high': pl.Float64, 'low': pl.Float64, 'close': pl.Float64, 'volume': pl.Float64})
    parts.append(d.filter(pl.col('ticker').is_in(tk)).with_columns(pl.lit(os.path.basename(f)[:10]).alias('d')))
P = pl.concat(parts)
G = json.load(gzip.open(sys.argv[2]))
TK = set(tk)
rows = []
for d, rs in G['days'].items():
    for T, o, h, l, c, v, vw, n in rs:
        if T in TK and None not in (o, h, l, c, v): rows.append((T, float(o), float(h), float(l), float(c), float(v), d))
if rows:
    N = pl.DataFrame(rows, schema=['ticker', 'open', 'high', 'low', 'close', 'volume', 'd'], orient='row')
    P = pl.concat([P, N.filter(pl.col('d') > P['d'].max())])
P.write_parquet(sys.argv[3])
print(P.height, P['ticker'].n_unique(), P['d'].min(), P['d'].max())
