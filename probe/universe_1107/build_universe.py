#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 94 · 4.4 + 4.5:每年年初的全市场股票名单 + 每只年初回看 60 个交易日的日均成交额

大白话:
  · 名单:Polygon 代码表在「上一年最后一天」那一刻还挂牌的股票(active = true),所以包含后来当年退市的
  · 只留股票类:普通股 CS、ADR(ADRC)、外国普通股(OS)、纽约登记股(NYRS)、GDR;不要 ETF / 优先股 / 权证 / 单位 / 基金
  · 2016 年以前 Polygon 代码表里很多票没标类型(多半是纳斯达克的),这些也留着,type 写 unknown —— 里面可能混着少量 ETF / 优先股
    —— type 原样给,ADR 要不要剔你们自己定
  · 日均成交额:当年第一个交易日之前 60 个交易日,每天 成交量 × 当天成交均价(vwap),没交易的日子算 0,再取平均;
    同时给「60 天里真交易了几天」和「用收盘价算的版本」
  · 不排名、不筛(手册 94 4.3),交易所也原样给(场外 OTC 的也在,`is_otc` 标出来)
用法:python3 build_universe.py snapshots_dir day_dir out_dir
"""
import csv, glob, gzip, json, os, sys
import polars as pl

KEEP = {'CS', 'ADRC', 'OS', 'NYRS', 'GDR'}
MAJOR = {'XNYS', 'XNAS', 'XASE', 'ARCX', 'BATS'}


def main(snap_dir, day_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    days = sorted(os.path.basename(f)[:10] for f in glob.glob(os.path.join(day_dir, '*.csv.gz')))
    snaps = {}
    for f in glob.glob(os.path.join(snap_dir, 'polygon_tickers_*.json.gz')):
        d = os.path.basename(f).split('_')[-1][:8]; snaps[f'{d[:4]}-{d[4:6]}-{d[6:]}'] = f
    # 早年没标类型的,先按「同一个 FIGI / 同一个代码在 2016 年以后的代码表里标的是什么」补(type_inferred),
    # 再按名字里有没有 ETF / FUND / TRUST / iShares / SPDR 之类标 fund_like —— 补的都写在 type_source 里,原始 type 不改
    import re
    later_by_figi, later_by_tk = {}, {}
    for d, f in sorted(snaps.items()):
        if d < '2016-12-01': continue
        J2 = json.load(gzip.open(f)); F2 = {k: i for i, k in enumerate(J2['fields'])}
        for r in J2['rows']:
            t_ = r[F2['type']]
            if not t_: continue
            if r[F2['composite_figi']]: later_by_figi[r[F2['composite_figi']]] = t_
            later_by_tk.setdefault(r[F2['ticker']], t_)
    FUNDY = re.compile(r'\b(ETF|ETN|FUND|ISHARES|SPDR|PROSHARES|POWERSHARES|INDEX|NOTES?|PREFERRED|PFD|WARRANTS?|RIGHTS?|UNITS?)\b', re.I)
    def infer(r, F):
        if r[F['type']]: return r[F['type']], 'polygon'
        t_ = later_by_figi.get(r[F['composite_figi']])
        if t_: return t_, 'inferred_from_later_list_by_figi'
        if FUNDY.search(r[F['name']] or ''): return 'fund_like', 'inferred_from_name'
        t_ = later_by_tk.get(r[F['ticker']])
        if t_: return t_ + '?', 'inferred_from_later_list_by_ticker(弱)'
        return 'unknown', 'none'
    summary = []
    for y in range(2004, 2027):
        prev = [d for d in snaps if d[:4] == str(y - 1)]
        if not prev: print('没有', y - 1, '年底的代码表'); continue
        sd = max(prev); J = json.load(gzip.open(snaps[sd])); F = {k: i for i, k in enumerate(J['fields'])}
        rows = {}
        for r in J['rows']:
            act = r[F['active']]
            if act not in (True, 'true', 'True'): continue
            if r[F['type']] not in KEEP and r[F['type']] != '': continue        # 早年(2016 以前)Polygon 很多代码没标类型 → 留着,type 写 unknown
            rows[r[F['ticker']]] = r
        first = [d for d in days if d >= f'{y}-01-01']
        if not first: continue
        base = first[0]; i = days.index(base); win = days[max(0, i - 60):i]
        parts = []; novwap = set()
        for d in win:
            t = pl.read_csv(os.path.join(day_dir, d + '.csv.gz'), infer_schema_length=0)
            if 'volume_weighted_average_price' in t.columns: t = t.rename({'volume_weighted_average_price': 'volume_weighted_average'})   # 早年的 flat files 列名不一样
            if 'volume_weighted_average' not in t.columns:                      # 有的日子 flat files 根本没给 vwap → 那天用收盘价代替,记下来
                t = t.with_columns(pl.col('close').alias('volume_weighted_average')); novwap.add(d)
            t = t.select(pl.col('ticker'), *[pl.col(c).cast(pl.Float64, strict=False) for c in ('volume', 'volume_weighted_average', 'close')])
            parts.append(t.filter(pl.col('ticker').is_in(list(rows))))
        if not parts:                                   # 2004 年:日线库从 2004-01-02 才开始,年初往前没有 60 天 → 名单照给,成交额留空
            A = {}
        else:
            P = pl.concat(parts)
            agg = P.group_by('ticker').agg((pl.col('volume') * pl.col('volume_weighted_average')).sum().alias('dv_vwap'),
                                       (pl.col('volume') * pl.col('close')).sum().alias('dv_close'), pl.len().alias('n'))
            A = {t: (a, b, n) for t, a, b, n in agg.iter_rows()}
        out = []
        for t, r in sorted(rows.items()):
            a, b, n = A.get(t, (0.0, 0.0, 0))
            ex = r[F['primary_exchange']] or ''
            ty, tsrc = infer(r, F)
            out.append([y, base, sd, t, r[F['name']], ty, tsrc, ex, int(ex not in MAJOR), (r[F['cik']] or '').lstrip('0'), r[F['composite_figi']],
                        round(a / len(win), 2) if win else '', round(b / len(win), 2) if win else '', n, len(win)])
        with gzip.open(os.path.join(out_dir, f'universe_{y}.csv.gz'), 'wt', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['year', 'base_date', 'list_as_of', 'ticker', 'name', 'type', 'type_source', 'primary_exchange', 'is_otc_or_other', 'cik', 'composite_figi',
                        'avg_dollar_volume_60d_vwap', 'avg_dollar_volume_60d_close', 'days_traded_in_window', 'window_days'])
            w.writerows(out)
        cs_major = sum(1 for x in out if x[5] == 'CS' and not x[8])
        summary.append([y, base, sd, len(out), cs_major, sum(1 for x in out if x[5] == 'ADRC'), sum(1 for x in out if x[5] in ('unknown', 'fund_like') or x[5].endswith('?')),
                        sum(1 for x in out if x[13] == 0), len(novwap)])
        print(summary[-1])
    with open(os.path.join(out_dir, 'summary.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['year', 'base_date', 'list_as_of', 'n_all', 'n_common_stock_major_exchange', 'n_adr', 'n_type_unsure', 'n_no_trade_in_window', 'days_without_vwap_used_close']); w.writerows(summary)


if __name__ == '__main__':
    main(*sys.argv[1:])
