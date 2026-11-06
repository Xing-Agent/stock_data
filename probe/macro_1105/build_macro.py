#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 64 · VIX + 3 个月期美债收益率 → market_macro_1105/<序列>/daily.json.gz

大白话:
  · VIX:CBOE 官方日线(cdn-api.cboe.com 的 _VIX.json,开高低收),2008-01-02 起;用 FRED 的 VIXCLS(只有收盘)逐日对一遍
  · DTB3:FRED 原样(3 个月期国债二级市场利率,贴现口径,年化百分数);FRED 节假日那一行是空的 → 直接不要这一行,不补
  · 都不复权、不拆股、不分红:adjustment = "none";volume / adjusted_close / dividend_amount / split_coefficient 一律 null
用法:python3 build_macro.py raw_dir ohlcv.parquet out_dir"""
import csv, gzip, hashlib, json, os, sys
from datetime import datetime, timezone
import polars as pl

START, END = '2004-01-01', '2026-11-04'   # 1106:从 2008 放宽到 2004,和行情库起点对齐(手册 81 B1)


def write(out_dir, sid, doc):
    p = os.path.join(out_dir, sid); os.makedirs(p, exist_ok=True)
    f = os.path.join(p, 'daily.json.gz')
    with open(f, 'wb') as fh:
        with gzip.GzipFile(fileobj=fh, mode='wb', mtime=0, filename='') as z:
            z.write(json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode())
    return hashlib.sha256(open(f, 'rb').read()).hexdigest(), f'{sid}/daily.json.gz'


def coverage(dates, cal):
    c = [d for d in cal if dates[0] <= d <= dates[-1]]; have = set(dates)
    miss = [d for d in c if d not in have]; extra = [d for d in dates if d not in set(c)]
    return {'status': 'complete' if not miss else 'partial', 'calendar': 'XNYS (按我们日线库里出现过的交易日)', 'timezone': 'America/New_York',
            'session': 'regular', 'expected_bars': len(c), 'observed_bars': len(dates), 'missing_bars': len(miss), 'missing_examples': miss[:20],
            'extra_bars_not_in_calendar': len(extra), 'extra_examples': extra[:20]}


def bar(d, o, h, l, c, tk, prov):
    return {'date': d, 'open': o, 'high': h, 'low': l, 'close': c, 'volume': None, 'price': c, 'adjusted_close': None,
            'dividend_amount': None, 'split_coefficient': None, 'source_ticker': tk, 'provider': prov}


def main(raw, px, out):
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cal = sorted(pl.read_parquet(px, columns=['d'])['d'].unique().to_list())
    os.makedirs(out, exist_ok=True); shas, man = [], []
    # —— VIX ——
    J = json.load(open(os.path.join(raw, 'cboe_VIX_historical_20261105.json')))
    rows = [r for r in J['data'] if START <= r['date'] <= END]
    fred = {}
    for r in csv.DictReader(open(os.path.join(raw, 'fred_VIXCLS_fredgraph_20261106.csv'))):
        if r['VIXCLS'] not in ('', '.'): fred[r['observation_date']] = float(r['VIXCLS'])
    data = [bar(r['date'], float(r['open']), float(r['high']), float(r['low']), float(r['close']), J.get('symbol') or '_VIX', 'cboe') for r in rows]
    # 2022 年起 CBOE 在美股休市日(阵亡将士纪念日、独立日……)也发 VIX(用盘前盘后 / 全球交易时段的期权算的)——
    # 是真值不是补的,但那天股票不交易;单独放进 holiday_rows,不进 data,免得和股票日线对不齐
    calset = set(cal)
    hol = [b for b in data if b['date'] not in calset]
    data = [b for b in data if b['date'] in calset]
    diff = [(b['date'], b['close'], fred.get(b['date'])) for b in data if b['date'] in fred and abs(b['close'] - fred[b['date']]) > 0.011]
    only_fred = [d for d in fred if START <= d <= END and d not in {r['date'] for r in rows}]   # 和 CBOE 全部行比(含休市日那 33 行)
    flat3 = sum(1 for a, b, c in zip(data, data[1:], data[2:]) if a['close'] == b['close'] == c['close'])
    ohlc_eq = sum(1 for b in data if b['open'] == b['high'] == b['low'] == b['close'])
    dates = [b['date'] for b in data]
    warns = []
    if diff: warns.append(f'和 FRED VIXCLS 收盘差 > 0.01 的 {len(diff)} 天,例:{diff[:5]}')
    if only_fred: warns.append(f'FRED 有、CBOE 没有的日子 {len(only_fred)} 天:{only_fred[:10]}')
    doc = {'status': 'ready', 'symbol': 'VIX', 'series_id': 'VIX', 'interval': '1d', 'timezone': 'America/New_York', 'adjustment': 'none',
           'unit': 'index_points', 'provider': 'cboe', 'source_url': 'https://cdn-api.cboe.com/api/global/delayed_quotes/charts/historical/_VIX.json',
           'cross_check': 'FRED VIXCLS(只有收盘)https://fred.stlouisfed.org/graph/fredgraph.csv?id=VIXCLS',
           'retrieved_at': now, 'source_timestamp': J.get('timestamp'), 'start_date': dates[0], 'end_date': dates[-1], 'warnings': warns,
           'qa': {'fred_close_mismatch_days': len(diff), 'fred_only_days': len(only_fred), 'three_identical_closes_in_a_row': flat3,
                  'bars_open_eq_high_eq_low_eq_close': ohlc_eq, 'max_close_2008_10_to_2008_11': max(b['close'] for b in data if '2008-10' <= b['date'] < '2008-12')},
           'holiday_rows_not_in_xnys': hol,
           'market_coverage': coverage(dates, cal), 'data': data}
    if hol: doc['warnings'].append(f'CBOE 在 {len(hol)} 个美股休市日也发了 VIX({hol[0]["date"]} 起),是真值、不是补的;没放进 data,放在 holiday_rows_not_in_xnys')
    shas.append(write(out, 'VIX', doc))
    man.append(['VIX', J.get('symbol') or '_VIX', 'cboe', 'index_points', dates[0], dates[-1], len(data), 'none',
                f'CBOE 官方开高低收;FRED VIXCLS 逐日对收盘,差 > 0.01 的 {len(diff)} 天;美股休市日 CBOE 也发的 {len(hol)} 天另放,不在 data 里'])
    print('VIX', len(data), doc['qa'], doc['market_coverage']['missing_bars'], doc['market_coverage']['extra_bars_not_in_calendar'])
    # —— DTB3 ——
    rows, blank = [], []
    for r in csv.DictReader(open(os.path.join(raw, 'fred_DTB3_fredgraph_20261106.csv'))):
        d, v = r['observation_date'], r['DTB3']
        if not START <= d <= END: continue
        if v in ('', '.'): blank.append(d); continue
        rows.append((d, float(v)))
    data = [bar(d, None, None, None, v, 'DTB3', 'fred') for d, v in rows]
    dates = [b['date'] for b in data]
    cov = coverage(dates, cal)
    flat3 = sum(1 for a, b, c in zip(data, data[1:], data[2:]) if a['close'] == b['close'] == c['close'])
    doc = {'status': 'ready', 'symbol': 'DTB3', 'series_id': 'DTB3', 'interval': '1d', 'timezone': 'America/New_York', 'adjustment': 'none',
           'unit': 'percent_annualized', 'quote_basis': 'discount basis(贴现口径,不是票息等价 / 债券等价收益率)',
           'provider': 'fred', 'source_url': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3',
           'source_title': '3-Month Treasury Bill Secondary Market Rate, Discount Basis (DTB3), Board of Governors of the Federal Reserve System (H.15)',
           'retrieved_at': now, 'start_date': dates[0], 'end_date': dates[-1],
           'warnings': [f'FRED 在这些日子给的是空值(节假日 / 债市休市),**这一行直接没有**,没有用前值补:共 {len(blank)} 天'],
           'blank_days_dropped': blank,
           'qa': {'three_identical_values_in_a_row': flat3, 'mean_2021': round(sum(v for d, v in rows if d[:4] == '2021') / max(1, sum(1 for d, v in rows if d[:4] == '2021')), 4)},
           'note': 'open/high/low 为 null:FRED 只发一个日值,放在 close / price', 'market_coverage': cov, 'data': data}
    shas.append(write(out, 'DTB3', doc))
    man.append(['DTB3', 'DTB3', 'fred', 'percent_annualized', dates[0], dates[-1], len(data), 'none',
                f'贴现口径;FRED 空值的 {len(blank)} 天(节假日 / 债市休市)不出行,没有补;到 {dates[-1]}'])
    print('DTB3', len(data), 'blank', len(blank), doc['qa'], cov['missing_bars'], cov['extra_bars_not_in_calendar'], cov['extra_examples'][:5])
    with open(os.path.join(out, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['series_id', 'source_ticker', 'provider', 'unit', 'first_date', 'last_date', 'n_rows', 'adjustment', 'notes']); w.writerows(man)
    with open(os.path.join(out, 'SHA256SUMS.txt'), 'w') as fh:
        for h, n in shas: fh.write(f'{h}  {n}\n')


if __name__ == '__main__':
    main(*sys.argv[1:])
