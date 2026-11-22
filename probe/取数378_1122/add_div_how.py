#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 378 第 1 样(在《338》退市股日线上加两样):
  · 分红:Polygon 分红记录(/v3/reference/dividends 全量),按代码 + 这只票自己那段时间对上;加 dividend_amount 和 adjusted_close(拆股分红都折)
  · 怎么退的:classify_delist.py 的结果并进总表
用法:python3 add_div_how.py POLYGON_DIV.json.gz 怎么退的.csv 退市股目录"""
import csv, gzip, json, os, sys, glob
import polars as pl

divf, howf, d = sys.argv[1:4]
DV = pl.DataFrame(json.load(gzip.open(divf)), schema=['source_ticker', 'date', 'amt', 'typ'], orient='row',
                  schema_overrides={'amt': pl.Float64}).filter(pl.col('amt') > 0)
DV = DV.unique(['source_ticker', 'date', 'amt']).group_by(['source_ticker', 'date']).agg(pl.col('amt').sum().alias('dividend_amount'))
n_div, n_sym = 0, set()
for fp in sorted(glob.glob(f'{d}/退市于*.parquet')):
    df = pl.read_parquet(fp)
    if 'dividend_amount' in df.columns: df = df.drop('dividend_amount', 'adjusted_close')
    df = df.join(DV, on=['source_ticker', 'date'], how='left').with_columns(pl.col('dividend_amount').fill_null(0.0))
    # 总回报系数:除息日那天,之前的价格乘 (1 − 分红 ÷ 前一天收盘)
    df = df.sort(['symbol', 'date']).with_columns(pl.col('close').shift(1).over('symbol').alias('pc'))
    df = df.with_columns(pl.when((pl.col('dividend_amount') > 0) & pl.col('pc').is_not_null() & (pl.col('dividend_amount') < pl.col('pc')))
                         .then(1 - pl.col('dividend_amount') / pl.col('pc')).otherwise(1.0).alias('k'))
    # 某天之前的累计系数 = 之后所有除息日 k 的乘积
    df = df.with_columns(pl.col('k').log().reverse().cum_sum().reverse().over('symbol').alias('lk'))
    df = df.with_columns((pl.col('lk') - pl.col('k').log()).exp().alias('tr'))
    df = df.with_columns((pl.col('close_adj') * pl.col('tr')).alias('adjusted_close')).drop('pc', 'k', 'lk', 'tr')
    n_div += df.filter(pl.col('dividend_amount') > 0).height
    n_sym |= set(df.filter(pl.col('dividend_amount') > 0)['symbol'].unique().to_list())
    df.write_parquet(fp, compression='zstd', compression_level=9, statistics=True)
print('分红条数', n_div, '有分红的票', len(n_sym))
# 怎么退的并进总表
H = {r['代码']: r for r in csv.DictReader(open(howf, encoding='utf-8-sig'))}
T = list(csv.DictReader(open(f'{d}/总表.csv', encoding='utf-8-sig')))
for r in T:
    h = H.get(r['代码'])
    r['怎么退的'] = h['怎么退的'] if h else ''
    r['怎么退的_依据'] = h['依据'] if h else ''
    r['怎么退的_来源'] = h['来源'] if h else ''
    r['怎么退的_备注'] = h['备注'] if h else ''
    r['分红次数'] = ''
cnt = {}
for fp in sorted(glob.glob(f'{d}/退市于*.parquet')):
    for s, n in pl.read_parquet(fp, columns=['symbol', 'dividend_amount']).filter(pl.col('dividend_amount') > 0).group_by('symbol').len().iter_rows():
        cnt[s] = n
for r in T:
    if r['交易天数'] not in ('', '0'): r['分红次数'] = cnt.get(r['代码'], 0)
with open(f'{d}/总表.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(T[0])); w.writeheader(); w.writerows(T)
