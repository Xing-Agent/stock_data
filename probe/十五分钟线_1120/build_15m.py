#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 327 · 15 分钟线。列和切法跟《小时线_1119》全量一致,只是每根 15 分钟。
大白话:
  · 第一组(SOXL TQQQ KORU QQQ SOXX SPY,2020-01-01 ~ 2026-05-31):Polygon 原生 15 分钟线(adjusted=false 原始价),
    在 Lin 浏览器里取。15 分钟的格子本来就从整点、9:30 对齐,不会跨时段,所以直接用,只标 session。
    这 6 只不在研究库,拆股按 Polygon 拆股记录折(折到今天,窗口之后生效的也折)。
  · 第二组(最活跃 200 只,2021-01-01 ~ 2025-12-31):Lin 电脑上的分钟线库,用 agg15.py 拼成 15 分钟。
    2021-01-01 ~ 2021-03-25 那段分钟线已按拆股折到下载那天,先用《小时线_1119》同一套办法还原成原始价;
    折算用研究库拆股系数 + 全池版并股表修正,和小时线一样。
  · 每根标 pre / regular / post;半日交易日 13:00 以后算盘后;20:00 ~ 次日 04:00 不要。
用法:python3 build_15m.py 1|2 OUT_DIR
"""
import csv, gzip, json, os, sys
from collections import defaultdict
import numpy as np, polars as pl

R = '/home/claude/stock_data'
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, f'{R}/probe/小时线_1119')
import assemble_full as A   # read_year(), unadjust(), daily()
import build_1h as B        # EARLY, split_events()

UP = '/mnt/user-data/uploads/Downloads'
COLS = ['symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume', 'open_adj', 'high_adj', 'low_adj', 'close_adj',
        'volume_adj', 'adj_factor', 'trades', 'minutes', 'source_ticker']
G1 = ['SOXL', 'TQQQ', 'KORU', 'QQQ', 'SOXX', 'SPY']


def et_cols(df, ts='start'):
    et = pl.from_epoch(ts, time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York')
    return df.with_columns(et.dt.strftime('%Y-%m-%d').alias('d'),
                           (et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)).alias('mins'))


def fold(df, events):
    """events: {symbol: [(生效日, 系数 new/old)]};生效日之前的 K 线 价÷系数、量×系数"""
    rows = []
    for f, d in df.select('folder', 'd').unique().iter_rows():
        c = 1.0
        for e, k in events.get(f, []):
            if d < e: c *= k
        rows.append((f, d, c))
    F = pl.DataFrame(rows, schema=['folder', 'd', 'adj_factor'], orient='row')
    df = df.join(F, on=['folder', 'd'], how='left')
    return df.with_columns(*[(pl.col(x) / pl.col('adj_factor')).alias(x + '_adj') for x in ('open', 'high', 'low', 'close')],
                           (pl.col('volume') * pl.col('adj_factor')).alias('volume_adj'))


def finish(df):
    df = df.with_columns(pl.from_epoch('start', time_unit='ms').dt.replace_time_zone('UTC').alias('time_utc'))
    return df.select(pl.col('folder').alias('symbol'), 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume',
                     'open_adj', 'high_adj', 'low_adj', 'close_adj', 'volume_adj', 'adj_factor', pl.col('n').alias('trades'),
                     pl.col('m').alias('minutes'), pl.col('ticker').alias('source_ticker'), 'd').sort(['symbol', 'time_utc'])


def group1():
    J = json.load(gzip.open(f'{HERE}/raw15m_第一组_1120.json.gz'))
    rows = []
    for k, v in J.items():
        if k.startswith('splits|'): continue
        t, y = k.split('|')
        rows += [(t, t, int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5]), int(x[6])) for x in v]
    df = pl.DataFrame(rows, schema=['folder', 'ticker', 'start', 'o', 'h', 'l', 'c', 'v', 'n'], orient='row').unique(['folder', 'start'])
    df = et_cols(df).filter((pl.col('d') >= '2020-01-01') & (pl.col('d') <= '2026-05-31') & (pl.col('mins') >= 240) & (pl.col('mins') < 1200))
    close = pl.when(pl.col('d').is_in(list(B.EARLY))).then(780).otherwise(960)
    df = df.with_columns(pl.when(pl.col('mins') < 570).then(pl.lit('pre')).when(pl.col('mins') < close).then(pl.lit('regular'))
                         .otherwise(pl.lit('post')).alias('session'), pl.lit(None, dtype=pl.Int32).alias('m'))
    df = df.rename({'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume'})
    ev = {t: sorted((e, b / a) for e, a, b in J[f'splits|{t}'] if e >= '2020-01-01') for t in G1}   # 窗口之后的拆股也折,和研究库日线、《147》拆股折算日线一致
    later = {t: [(e, b / a) for e, a, b in J[f'splits|{t}'] if e > '2026-05-31'] for t in G1}
    df = finish(fold(df, ev))
    # 日线(Polygon adjusted=false)用来核对
    Dj = json.load(gzip.open(f'{HERE}/daily_第一组_1120.json.gz'))
    daily = {}
    for t, v in Dj.items():
        dd = pl.DataFrame([(int(x[0]), float(x[2])) for x in v], schema=['ts', 'high'], orient='row')
        dd = dd.with_columns(pl.from_epoch('ts', time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York').dt.strftime('%Y-%m-%d').alias('d'))
        daily[t] = dict(zip(dd['d'].to_list(), dd['high'].to_list()))
    return df, ev, later, daily, {}


def group2():
    seg = json.load(open(f'{HERE}/seg15.json'))
    parts, notes = [], defaultdict(set)
    for y in range(2021, 2026):
        df = A.read_year(f'{UP}/xing_15m/years/{y}.csv.gz')
        if y == 2021:
            df, nt = A.unadjust(df)
            for f, lv in nt.items(): notes[f].update(lv)
        else:
            df = df.with_columns(pl.lit(1.0).alias('rest_mult'))
        df = df.with_columns((pl.col('o') * pl.col('rest_mult')).alias('open'), (pl.col('h') * pl.col('rest_mult')).alias('high'),
                             (pl.col('l') * pl.col('rest_mult')).alias('low'), (pl.col('c') * pl.col('rest_mult')).alias('close'),
                             (pl.col('v') / pl.col('rest_mult')).round(0).alias('volume'))
        df = et_cols(df).filter((pl.col('d') >= '2021-01-01') & (pl.col('d') <= '2025-12-31'))
        parts.append(df.select('folder', 'ticker', 'start', 'session', 'open', 'high', 'low', 'close', 'volume', 'n', 'm', 'd'))
        print(y, df.height, flush=True)
    df = pl.concat(parts)
    ev = {f: B.split_events(f)[0] for f in seg}
    df = finish(fold(df, ev))
    daily = {f: {d: v['high'] for d, v in A.daily(f).items() if '2021-01-01' <= d <= '2025-12-31'} for f in seg}
    return df, ev, {}, daily, notes


def check(df, daily, ev, later, notes, a0, b0):
    """每只票:起止、常规时段缺的天、每天常规时段最高价 vs 日线最高价(原始价)"""
    hi = df.filter(pl.col('session') == 'regular').group_by(['symbol', 'd']).agg(pl.col('high').max().alias('mh'))
    H = defaultdict(dict)
    for s, d, m in hi.iter_rows(): H[s][d] = m
    st = {s: (a, b, n) for s, a, b, n in df.group_by('symbol').agg(pl.col('d').min(), pl.col('d').max().alias('b'), pl.len()).iter_rows()}
    rows, bad = [], []
    for s in sorted(daily):
        D = {d: h for d, h in daily[s].items() if a0 <= d <= b0 and h}
        miss = sorted(d for d in D if d not in H[s])
        both = [(d, D[d], H[s][d]) for d in sorted(D) if d in H[s]]
        diff = [(d, dh, mh, mh / dh - 1) for d, dh, mh in both]
        ok = sum(abs(x[3]) <= 0.01 for x in diff)
        bad += [(s, d, dh, mh, round(r * 100, 2)) for d, dh, mh, r in diff if abs(r) > 0.01]
        a, b, n = st.get(s, ('', '', 0))
        evs = ';'.join(f'{e}×{k:g}' for e, k in ev.get(s, []) if a0 <= e <= '2026-12-31')
        rows.append(dict(代码=s, 日线起=min(D) if D else '', 日线止=max(D) if D else '', 十五分钟线起=a, 十五分钟线止=b, 行数=n,
                         常规时段缺的天数=len(miss), 缺的天=';'.join(miss[:30]) + (' …' if len(miss) > 30 else ''),
                         比对天数=len(diff), 最高价差1pct以内的天数=ok, 占比=f'{ok / len(diff) * 100:.2f}%' if diff else '',
                         拆股折算=evs, 其中窗口之后生效的=';'.join(f'{e}×{k:g}' for e, k in later.get(s, [])),
                         还原倍数_2021年1至3月=';'.join(f'{x:g}' for x in sorted(notes.get(s, [])))))
    return rows, bad


def write(df, out, by_half):
    os.makedirs(out, exist_ok=True)
    df = df.with_columns(pl.col('d').str.slice(0, 4).alias('y'), pl.when(pl.col('d').str.slice(5, 2) <= '06').then(pl.lit('H1')).otherwise(pl.lit('H2')).alias('h'))
    sizes = []
    keys = ['y', 'h'] if by_half else ['y']
    for k, g in df.group_by(keys, maintain_order=True):
        name = '_'.join(k) if by_half else k[0]
        fp = f'{out}/{name}.parquet'
        g.select(COLS).write_parquet(fp, compression='zstd', compression_level=9, statistics=True)
        sizes.append((name, g.height, os.path.getsize(fp)))
    return sorted(sizes)


if __name__ == '__main__':
    which, out = sys.argv[1], sys.argv[2]
    if which == '1':
        df, ev, later, daily, notes = group1(); a0, b0 = '2020-01-01', '2026-05-31'
    else:
        df, ev, later, daily, notes = group2(); a0, b0 = '2021-01-01', '2025-12-31'
    rows, bad = check(df, daily, ev, later, notes, a0, b0)
    sizes = write(df, out, by_half=False)   # 每年一个文件,最大的也不到 60MB
    with open(f'{out}/说明_每只票.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    with open(f'{out}/日线对不上的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['代码', '日期', '日线最高价', '15分钟线常规时段最高价', '差(%)']); w.writerows(bad)
    tot = sum(r['比对天数'] for r in rows); ok = sum(r['最高价差1pct以内的天数'] for r in rows)
    print('files', [(n, h, s // 1_000_000) for n, h, s in sizes])
    print('rows', df.height, 'tickers', df['symbol'].n_unique(), 'days_compared', tot, 'within1%', f'{ok / tot * 100:.3f}%', 'bad', len(bad),
          'gt5%', sum(abs(b[4]) > 5 for b in bad), 'miss_total', sum(r['常规时段缺的天数'] for r in rows))
    print(df.group_by('session').len().sort('session'))
