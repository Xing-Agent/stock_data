#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 398:
  · BTC、ETH USDT 永续的持仓量等衍生品指标:Binance 公开数据下载站 data.binance.vision 的 futures/um/daily/metrics,每天一个文件,5 分钟一条
  · SOL 行情:Coinbase SOL-USD 1 小时线和日线
用法:python3 build_oi_sol.py METRICS.json.gz SOL.json.gz OUT_DIR"""
import csv, gzip, json, os, sys
import polars as pl
M = json.load(gzip.open(sys.argv[1])); S = json.load(gzip.open(sys.argv[2])); out = sys.argv[3]
os.makedirs(f'{out}/持仓量_Binance_5分钟', exist_ok=True); os.makedirs(f'{out}/持仓量_Binance_1小时', exist_ok=True)
summ, gaps = [], []
COLS = ['open_interest_coin', 'open_interest_usdt', 'top_trader_account_long_short', 'top_trader_position_long_short', 'all_account_long_short', 'taker_buy_sell_vol_ratio']
for sym, days in M['oi'].items():
    rows = []
    for d, txt in days.items():
        for ln in txt.split('\n'):
            p = ln.split(',')
            if len(p) != 7: continue
            rows.append([p[0]] + [float(x.strip('"')) if x.strip('"') not in ('', 'nan') else None for x in p[1:]])
    df = pl.DataFrame(rows, schema=['t'] + COLS, orient='row').unique('t').sort('t')
    df = df.with_columns(pl.col('t').str.to_datetime('%Y-%m-%d %H:%M:%S').dt.replace_time_zone('UTC').alias('time_utc')).drop('t')
    df = df.select(['time_utc'] + COLS).with_columns(pl.lit(sym).alias('symbol'))
    # 缺口:5 分钟网格
    ts = df['time_utc'].dt.epoch('s').to_list(); have = set(ts); miss = [t for t in range(ts[0], ts[-1] + 1, 300) if t not in have]
    seg = []
    for t in miss:
        if seg and t == seg[-1][1] + 300: seg[-1][1] = t
        else: seg.append([t, t])
    f = lambda t: pl.from_epoch(pl.Series([t]), time_unit='s')[0].strftime('%Y-%m-%d %H:%M')
    for a, b in seg: gaps.append(dict(品种=sym, 从=f(a), 到=f(b), 缺几条=(b - a) // 300 + 1))
    big = [g for g in gaps if g['品种'] == sym and g['缺几条'] >= 12]
    for (y,), g in df.with_columns(pl.col('time_utc').dt.year().alias('y')).group_by(['y'], maintain_order=True):
        g.drop('y').write_parquet(f'{out}/持仓量_Binance_5分钟/{sym}_{y}.parquet', compression='zstd')
    h = df.group_by_dynamic('time_utc', every='1h', closed='right', label='right').agg(*[pl.col(c).last() for c in COLS]).with_columns(pl.lit(sym).alias('symbol'))
    h.write_parquet(f'{out}/持仓量_Binance_1小时/{sym}_1小时.parquet', compression='zstd')
    summ.append(dict(内容=f'{sym} 持仓量等(5 分钟)', 来源='Binance data.binance.vision futures/um/daily/metrics', 起=str(df['time_utc'][0]), 止=str(df['time_utc'][-1]),
                     条数=df.height, 缺的条数=len(miss), 缺一小时以上的段数=len(big), 说明=f"缺的天文件:{len(M['miss'][sym])} 个"))
    print(summ[-1])
# SOL
os.makedirs(f'{out}/SOL_Coinbase', exist_ok=True)
for key, step, name in [('h1', 3600, '1小时'), ('d1', 86400, '日线')]:
    rows = S['sol'][key]
    df = pl.DataFrame([(int(x[0]), float(x[3]), float(x[2]), float(x[1]), float(x[4]), float(x[5])) for x in rows],
                      schema=['ts', 'open', 'high', 'low', 'close', 'volume'], orient='row').unique('ts').sort('ts')
    df = df.filter(pl.col('ts') < df['ts'].max())  # 最后一根没走完
    ts = df['ts'].to_list(); have = set(ts); miss = [t for t in range(ts[0], ts[-1] + 1, step) if t not in have]
    df = df.with_columns(pl.from_epoch('ts', time_unit='s').dt.replace_time_zone('UTC').alias('time_utc'), pl.lit('SOL').alias('symbol'),
                         pl.lit('all').alias('session'), pl.lit('SOL-USD').alias('source_ticker')).select('symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume', 'source_ticker')
    bad = df.filter((pl.col('high') > pl.max_horizontal('open', 'close') * 1.2) | (pl.col('low') < pl.min_horizontal('open', 'close') * 0.8)).height
    df.write_parquet(f'{out}/SOL_Coinbase/SOL_{name}.parquet', compression='zstd')
    summ.append(dict(内容=f'SOL {name}', 来源='Coinbase SOL-USD', 起=str(df['time_utc'][0]), 止=str(df['time_utc'][-1]), 条数=df.height, 缺的条数=len(miss),
                     缺一小时以上的段数='', 说明=f'高低价离开收盘 20% 以上的 {bad} 根'))
    print(summ[-1])
with open(f'{out}/说明_每样.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)
with open(f'{out}/持仓量缺的段.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=['品种', '从', '到', '缺几条']); w.writeheader(); w.writerows(gaps)
print(sorted(gaps, key=lambda g: -g['缺几条'])[:8])
