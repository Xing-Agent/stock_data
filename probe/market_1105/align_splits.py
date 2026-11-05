# -*- coding: utf-8 -*-
"""手册 53 · 拆股对齐(2004 起,全期)—— 和 probe/splits_1101/align.py 同一套规矩,只是范围从「2015 起」放宽到「2004 起 ~ 2026-11-04」。
大白话:Polygon 记的拆股日期偶尔差一两天,所以在记录日前后 3 个交易日里,找「前收 ÷ 今开」最接近拆股比例的那天当真正的拆股日;
找不到价格跳的(比如只是多发一类股票)不用。
用法:python3 align_splits.py ohlcv.parquet out.csv"""
import bisect, gzip, json, sys
import polars as pl

ROOT = '/home/claude/stock_data'
px = pl.read_parquet(sys.argv[1]).sort('ticker', 'd')
px = px.with_columns(pl.col('close').shift(1).over('ticker').alias('pc'), pl.col('d').shift(1).over('ticker').alias('pd'))
cal = sorted(px['d'].unique().to_list()); ci = {d: i for i, d in enumerate(cal)}
px = px.with_columns(pl.col('d').replace_strict(ci, return_dtype=pl.Int32).alias('i'),
                     (pl.col('pc') / pl.col('open')).alias('jump'))
r1 = json.load(gzip.open(f'{ROOT}/probe/splits_1101/polygon_splits_1101.json.gz'))['rows']
r2 = json.load(gzip.open(f'{ROOT}/probe/market_1105/raw/polygon_splits_since_20260601.json.gz'))['rows']
ids = {r[4] for r in r1}
rows = [r for r in r1 if r[1] < '2026-06-01'] + [r for r in r2 if r[4] not in ids or r[1] >= '2026-06-01']
S = pl.DataFrame(rows, schema=['ticker', 'execution_date', 'split_from', 'split_to', 'id'], orient='row').unique('id')
S = S.with_columns(pl.col('split_from').cast(pl.Float64), pl.col('split_to').cast(pl.Float64))
S = S.filter((pl.col('execution_date') >= '2004-01-02') & (pl.col('execution_date') <= cal[-1]) & (pl.col('split_from') > 0) & (pl.col('split_to') > 0))
S = S.filter(pl.col('ticker').is_in(px['ticker'].unique().to_list())).with_columns((pl.col('split_to') / pl.col('split_from')).alias('ratio'))
S = S.with_columns(pl.col('execution_date').map_elements(lambda d: min(bisect.bisect_left(cal, d), len(cal) - 1), return_dtype=pl.Int32).alias('ei'))
J = px.filter(pl.col('jump').is_not_null() & (pl.col('jump') > 0)).select('ticker', 'd', 'i', 'jump')
cand = S.join(J, on='ticker', how='inner').filter((pl.col('i') - pl.col('ei')).abs() <= 3)
cand = cand.with_columns((pl.col('jump').log() - pl.col('ratio').log()).abs().alias('err'))
best = cand.sort('err').group_by('id').first()
S = S.join(best.select('id', pl.col('d').alias('aligned_date'), 'jump', 'err'), on='id', how='left')
S = S.with_columns(
    pl.when(pl.col('err').is_null()).then(pl.lit('无行情'))
      .when((pl.col('err') < 0.15) | ((pl.col('ratio').log().abs() >= 0.5) & (pl.col('err') < 0.4)
            & ((pl.col('jump').log() * pl.col('ratio').log()) > 0)))
      .then(pl.when(pl.col('aligned_date') == pl.col('execution_date')).then(pl.lit('确认·同日')).otherwise(pl.lit('确认·日期改')))
      .otherwise(pl.lit('价格没跳')).alias('check'))
S = S.drop('ei').sort('execution_date', 'ticker')
S.write_csv(sys.argv[2])
print(S.group_by('check').len().sort('len', descending=True))
print(S.filter(pl.col('check').str.starts_with('确认')).group_by(pl.col('execution_date').str.slice(0, 4).alias('y')).len().sort('y'))
