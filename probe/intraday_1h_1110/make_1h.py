#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 160 · 在存分钟线的那台机器上跑:全市场 1 分钟线 → 每年前 1,500 只的 1 小时线(常规时段,统一按拆股折算)

大白话:
  · 每年的名单:从 GitHub 拿 universe_<年>.csv.gz,取纽交所 / 纳斯达克 / 美交所的普通股和 ADR,
    按年初 60 天日均成交额取前 1,500 只(加 SPY / QQQ / IWM 当基准)
  · 1 小时线:只要常规时段 09:30–16:00(美东),从 09:30 起切,每天 7 根(最后一根 15:30–16:00 只有半小时);半日交易日到 13:00
  · 复权:分钟线分两段 —— 2021-03-26 以前(表头 ticker,t,…)下载时已按拆股折算;以后(表头 …window_start…)是原始价。
    原始价那段:凡是 K 线日期之后发生的拆股,价格除掉、成交量乘上(拆股表从 GitHub 拿),和前一段对齐
  · 接缝核对:每只票 2021-03-25 的最后收盘 vs 2021-03-26 起第一根开盘(折算后),比值写进 seam_check.csv
  · 不折分红;边界两根的官方开收价由数据组那边用日线替换,这里不做
  · 只读原始文件,结果写到桌面 xing_1h_out/,每季度一个 parquet(每个约 10MB,方便网页上传 GitHub)
用法:python3 make_1h.py "/Users/a1/Desktop/美股历史数据/minute"
"""
import gzip, io, os, re, sys, time, urllib.request
from collections import defaultdict
import polars as pl

GH = 'https://raw.githubusercontent.com/Xing-Agent/stock_data/main'
TOPN = 1500
BENCH = {'SPY', 'QQQ', 'IWM'}
OUT = os.path.expanduser('~/Desktop/xing_1h_out')
PAT = re.compile(r'(\d{4})-(\d{2})-(\d{2})\.csv(\.gz)?$')


def fetch(path):
    with urllib.request.urlopen(f'{GH}/{path}', timeout=120) as r: return r.read()


def main(root):
    os.makedirs(OUT, exist_ok=True)
    log = open(os.path.join(OUT, 'log.txt'), 'a')
    def say(*a):
        s = ' '.join(str(x) for x in a); print(s); log.write(s + '\n'); log.flush()
    # ① 找全部分钟线文件,同一天有多份时取第一份(主目录优先,然后「最新/stocks_minute」)
    files = {}
    for dp, dn, fn in sorted(os.walk(root), key=lambda x: (('最新' in x[0]), ('us_stocks_sip/minute_aggs_v1' in x[0] and 'stocks_minute' not in x[0]), x[0])):
        dn.sort()
        for f in sorted(fn):
            m = PAT.match(f)
            if m and f[:10] not in files: files[f[:10]] = os.path.join(dp, f)
    days = sorted(files); say('分钟线文件', len(days), '天', days[0], '~', days[-1])
    # ② 名单 + 拆股表
    uni = {}
    for y in sorted({d[:4] for d in days}):
        u = pl.read_csv(io.BytesIO(gzip.decompress(fetch(f'universe_1107/universe_{y}.csv.gz'))), infer_schema_length=0)
        u = u.filter(pl.col('type').is_in(['CS', 'ADRC']) & (pl.col('is_otc_or_other') == '0')).with_columns(
            pl.col('avg_dollar_volume_60d_close').cast(pl.Float64, strict=False).fill_null(0)).sort('avg_dollar_volume_60d_close', descending=True)
        uni[y] = set(u['ticker'].head(TOPN).to_list()) | BENCH
    sp = pl.read_csv(io.BytesIO(fetch('probe/market_1105/polygon_splits_aligned_1107.csv')), infer_schema_length=0).filter(pl.col('check').str.starts_with('确认'))
    splits = defaultdict(list)
    for t, d, r in sp.select('ticker', 'aligned_date', 'ratio').iter_rows(): splits[t].append((d, float(r)))
    def factor(t, day):          # 这一天之后发生的拆股累计倍数
        f = 1.0
        for d, r in splits.get(t, ()):
            if d > day: f *= r
        return f
    say('名单', {y: len(s) for y, s in uni.items()}, '· 拆股记录', sp.height)
    # ③ 逐天处理
    buf = defaultdict(list); seam = {}
    t0 = time.time()
    for i, day in enumerate(days):
        p = files[day]; keep = uni[day[:4]]
        try: df = pl.read_csv(p, infer_schema_length=0)
        except Exception as e: say('读不了', p, e); continue
        if 'window_start' in df.columns:
            raw = True
            df = df.select(pl.col('ticker'), (pl.col('window_start').cast(pl.Int64) // 1_000_000).alias('ms'),
                           *[pl.col(c).cast(pl.Float64).alias(c[0]) for c in ('open', 'high', 'low', 'close')], pl.col('volume').cast(pl.Float64).alias('v'))
        else:
            raw = False
            df = df.select(pl.col('ticker'), pl.col('t').cast(pl.Int64).alias('ms'), *[pl.col(c).cast(pl.Float64) for c in ('o', 'h', 'l', 'c')], pl.col('v').cast(pl.Float64))
        df = df.filter(pl.col('ticker').is_in(list(keep)))
        if df.is_empty(): continue
        et = pl.from_epoch(pl.col('ms'), time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York')
        df = df.with_columns(et.alias('ts')).with_columns((pl.col('ts').dt.hour().cast(pl.Int32) * 60 + pl.col('ts').dt.minute().cast(pl.Int32) - 570).alias('m')).filter((pl.col('m') >= 0) & (pl.col('m') < 390))
        df = df.filter(pl.col('ts').dt.date().cast(pl.String) == day)
        if df.is_empty(): continue
        h = df.sort('ms').group_by(['ticker', (pl.col('m') // 60).alias('k')]).agg(
            pl.col('o').first(), pl.col('h').max(), pl.col('l').min(), pl.col('c').last(), pl.col('v').sum(), pl.len().alias('n_min'))
        if raw:
            fac = {t: factor(t, day) for t in h['ticker'].unique().to_list()}
            h = h.with_columns(pl.col('ticker').replace_strict(fac, default=1.0, return_dtype=pl.Float64).alias('f'))
            h = h.with_columns(*[(pl.col(c) / pl.col('f')) for c in ('o', 'h', 'l', 'c')], (pl.col('v') * pl.col('f'))).drop('f')
        h = h.with_columns(pl.lit(day).alias('date'), pl.lit('raw→split_adjusted' if raw else 'split_adjusted_at_download').alias('src'))
        buf[(day[:4], f'Q{(int(day[5:7]) - 1) // 3 + 1}')].append(h)
        # 接缝:记 2021-03-25 最后收盘、2021-03-26 起第一根开盘
        if '2021-03-20' <= day <= '2021-04-02':
            for t, k, o, c in h.select('ticker', 'k', 'o', 'c').iter_rows():
                s = seam.setdefault(t, {})
                if not raw: s['rest_last'] = (day, c) if k == h.filter(pl.col('ticker') == t)['k'].max() else s.get('rest_last')
                elif 'raw_first' not in s and k == 0: s['raw_first'] = (day, o)
        if (i + 1) % 50 == 0: say(f'{i + 1}/{len(days)} 天 {day} · 用时 {time.time() - t0:.0f}s')
    # ④ 写出
    for (y, half), parts in sorted(buf.items()):
        df = pl.concat(parts).rename({'o': 'open', 'h': 'high', 'l': 'low', 'c': 'close', 'v': 'volume', 'k': 'bar_index'}).sort('ticker', 'date', 'bar_index')
        f = os.path.join(OUT, f'hourly_{y}_{half}.parquet'); df.write_parquet(f, compression='zstd', compression_level=19)
        say('写出', f, df.height, '行', f'{os.path.getsize(f) / 1e6:.1f} MB')
    with open(os.path.join(OUT, 'seam_check.csv'), 'w') as fh:
        fh.write('ticker,rest_last_day,rest_last_close,raw_first_day,raw_first_open_adjusted,ratio\n')
        for t, s in sorted(seam.items()):
            if s.get('rest_last') and s.get('raw_first'):
                fh.write(f"{t},{s['rest_last'][0]},{s['rest_last'][1]},{s['raw_first'][0]},{s['raw_first'][1]},{s['raw_first'][1] / s['rest_last'][1]:.4f}\n")
    say('完成 · 总用时', f'{time.time() - t0:.0f}s')


if __name__ == '__main__':
    main(sys.argv[1])
