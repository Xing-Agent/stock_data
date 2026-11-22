#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 378 第 2 样:BTC、ETH
  · 现货 15 分钟线:Coinbase BTC-USD(2015-07-20 起)、ETH-USD(2016-05-18 起),UTC
  · 永续合约资金费:Binance USDT 本位永续 BTCUSDT、ETHUSDT,从上线起每次结算一条(一般 8 小时一次,2019-09 起)
  · 永续合约 15 分钟线:Binance 同一家,BTCUSDT 2019-09 起、ETHUSDT 2019-11 起
列和 ETF 小时线尽量一样;币没有盘前盘后,session 一律 all。
用法:python3 build_crypto.py RAW.json.gz OUT_DIR"""
import csv, gzip, json, os, sys
import polars as pl
J = json.load(gzip.open(sys.argv[1])); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
COLS = ['symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume', 'trades', 'source_ticker']
summ, gaps_all, bad_all = [], [], []


def gaps(df, sym, src, step):
    ts = df['ts'].to_list(); have = set(ts); miss = []
    for t in range(ts[0], ts[-1] + 1, step):
        if t not in have: miss.append(t)
    seg = []
    for t in miss:
        if seg and t == seg[-1][1] + step: seg[-1][1] = t
        else: seg.append([t, t])
    f = lambda t: pl.from_epoch(pl.Series([t]), time_unit='s')[0].strftime('%Y-%m-%d %H:%M')
    for a, b in seg: gaps_all.append(dict(品种=sym, 来源=src, 从=f(a), 到=f(b), 缺几根=(b - a) // step + 1))
    return len(miss), len(seg), max([(b - a) // step + 1 for a, b in seg] or [0])


def finish(df, sym, src, src_t, sub):
    df = df.unique('ts').sort('ts')
    now_cut = df['ts'].max()   # 最后一根可能没走完:丢掉
    df = df.filter(pl.col('ts') < now_cut)
    df = df.with_columns(pl.from_epoch('ts', time_unit='s').dt.replace_time_zone('UTC').alias('time_utc'), pl.lit(sym).alias('symbol'),
                         pl.lit('all').alias('session'), pl.lit(src_t).alias('source_ticker'))
    nm, ns, mx = gaps(df, sym, src, 900)
    b = df.filter((pl.col('high') < pl.max_horizontal('open', 'close')) | (pl.col('low') > pl.min_horizontal('open', 'close')) |
                  (pl.col('high') > pl.max_horizontal('open', 'close') * 1.15) | (pl.col('low') < pl.min_horizontal('open', 'close') * 0.85))
    for r in b.iter_rows(named=True): bad_all.append((sym, src, str(r['time_utc']), r['open'], r['high'], r['low'], r['close']))
    os.makedirs(f'{out}/{sub}', exist_ok=True)
    for (y,), g in df.with_columns(pl.col('time_utc').dt.year().alias('y')).group_by(['y'], maintain_order=True):
        g.select(COLS).write_parquet(f'{out}/{sub}/{sym}_{y}.parquet', compression='zstd', compression_level=9, statistics=True)
    summ.append(dict(品种=sym, 内容=sub, 来源=src, 起=str(df['time_utc'][0]), 止=str(df['time_utc'][-1]), 根数=df.height, 缺的根数=nm, 缺的段数=ns,
                     最长一段缺几根=mx, 高低价可疑=b.height))
    print(summ[-1])
    return df


# 现货 Coinbase:各段拼起来
spot = {}
for k, v in J['cb'].items():
    p = k.split('|')[0]; spot.setdefault(p, []).extend(v)
S = {}
for p, rows in spot.items():
    sym = p.split('-')[0]
    df = pl.DataFrame([(int(x[0]), float(x[3]), float(x[2]), float(x[1]), float(x[4]), float(x[5])) for x in rows],
                      schema=['ts', 'open', 'high', 'low', 'close', 'volume'], orient='row').with_columns(pl.lit(None, dtype=pl.Int64).alias('trades'))
    S[sym] = finish(df, sym, f'Coinbase 现货 {p}', p, '现货15分钟_Coinbase')
# 永续 Binance 15 分钟
P = {}
for sym in ('BTC', 'ETH'):
    rows = J['bn'][f'k15_{sym}USDT']
    df = pl.DataFrame([(int(x[0]) // 1000, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), int(x[8])) for x in rows],
                      schema=['ts', 'open', 'high', 'low', 'close', 'volume', 'trades'], orient='row')
    P[sym] = finish(df, sym, f'Binance USDT 永续 {sym}USDT', f'{sym}USDT', '永续15分钟_Binance')
# 资金费
os.makedirs(f'{out}/资金费_Binance', exist_ok=True)
for sym in ('BTC', 'ETH'):
    rows = J['bn'][f'fund_{sym}USDT']
    df = pl.DataFrame([(int(x['fundingTime']), float(x['fundingRate']), float(x['markPrice']) if x.get('markPrice') not in (None, '') else None) for x in rows],
                      schema=['ms', 'funding_rate', 'mark_price'], orient='row', schema_overrides={'mark_price': pl.Float64}).unique('ms').sort('ms')
    df = df.with_columns(pl.from_epoch('ms', time_unit='ms').dt.replace_time_zone('UTC').alias('time_utc'))
    iv = df['ms'].diff().drop_nulls() / 3_600_000
    from collections import Counter
    c = Counter(round(x) for x in iv.to_list())
    df.select('time_utc', 'funding_rate', 'mark_price').write_csv(f'{out}/资金费_Binance/{sym}USDT_资金费.csv')
    summ.append(dict(品种=sym, 内容='资金费_Binance', 来源=f'Binance USDT 永续 {sym}USDT /fapi/v1/fundingRate', 起=str(df['time_utc'][0]),
                     止=str(df['time_utc'][-1]), 根数=df.height, 缺的根数=sum(v for k, v in c.items() if k > 8), 缺的段数='',
                     最长一段缺几根=f'结算间隔(小时):{dict(sorted(c.items()))}', 高低价可疑=''))
    print(summ[-1])
# 现货和永续的价差(收盘价,同一根 15 分钟)
os.makedirs(f'{out}/现货与永续价差', exist_ok=True)
for sym in ('BTC', 'ETH'):
    j = S[sym].select('ts', pl.col('close').alias('现货收盘')).join(P[sym].select('ts', pl.col('close').alias('永续收盘')), on='ts')
    j = j.with_columns(((pl.col('永续收盘') / pl.col('现货收盘') - 1) * 10000).round(2).alias('价差_bp'),
                       pl.from_epoch('ts', time_unit='s').dt.replace_time_zone('UTC').alias('time_utc'))
    j.select('time_utc', '现货收盘', '永续收盘', '价差_bp').write_parquet(f'{out}/现货与永续价差/{sym}_价差_15分钟.parquet', compression='zstd')
    q = j['价差_bp']
    print(sym, '价差 bp 中位', q.median(), '1%', q.quantile(0.01), '99%', q.quantile(0.99), '绝对值超过100bp', (q.abs() > 100).sum(), j.height)
    summ.append(dict(品种=sym, 内容='现货与永续价差', 来源='Binance 永续收盘 ÷ Coinbase 现货收盘 − 1(万分之一)', 起=str(j['time_utc'].min()),
                     止=str(j['time_utc'].max()), 根数=j.height, 缺的根数='', 缺的段数='',
                     最长一段缺几根=f"中位 {q.median():.1f}bp,1%~99% 在 {q.quantile(0.01):.1f}~{q.quantile(0.99):.1f}bp,超过 ±100bp 的 {(q.abs() > 100).sum()} 根",
                     高低价可疑=''))
for name, rows, hdr in [('说明_每样.csv', summ, None), ('缺的K线.csv', gaps_all, None)]:
    with open(f'{out}/{name}', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
with open(f'{out}/高低价可疑的K线.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['品种', '来源', '时间UTC', '开', '高', '低', '收']); w.writerows(bad_all)
print('可疑', len(bad_all)); [print(b) for b in bad_all[:25]]
print('最长缺', sorted(gaps_all, key=lambda g: -g['缺几根'])[:8])
