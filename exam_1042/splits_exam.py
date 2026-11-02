# -*- coding: utf-8 -*-
"""考卷拆股表:Polygon 的拆股按「价格指纹」对到考卷的每一段,不只按代码。
大白话:Polygon 有时把拆股挂在现在的代码下(Ball 挂在 BALL、不在 BLL),有时代码写法不同(BF.B 写成 BFB)。
所以不管代码,只要「同一天前后 3 个交易日、考卷某只票的隔夜跳空正好等于这个拆股比例」就算对上;代码不一样的标出来。"""
import json, gzip, numpy as np, polars as pl
L = pl.read_csv('/home/claude/exam/exam_list_1101.csv', infer_schema_length=0)
S = pl.read_csv('/home/claude/seg/pit_company_segments.csv', infer_schema_length=0)
segs = S.filter(pl.col('company_id').is_in(L['company_id'].to_list())).select('seg_id', 'company_id', 'ticker', 'first_seen', 'last_seen')
px = pl.read_parquet('/home/claude/splits/px_2015.parquet').sort('ticker', 'd')
px = px.with_columns(pl.col('close').shift(1).over('ticker').alias('pc'), pl.col('d').shift(1).over('ticker').alias('pd'))
cal = sorted(px['d'].unique().to_list()); ci = {d: i for i, d in enumerate(cal)}
J = px.join(segs, on='ticker').filter((pl.col('d') > pl.col('first_seen')) & (pl.col('d') <= pl.col('last_seen')) & (pl.col('pd') >= pl.col('first_seen'))
       & (pl.col('d') >= '2015-06-01') & (pl.col('d') <= '2025-12-31')).with_columns((pl.col('pc') / pl.col('open')).alias('jump'),
       pl.col('d').replace_strict(ci, return_dtype=pl.Int32).alias('i'))
P = json.load(gzip.open('/home/claude/stock_data/probe/splits_1101/polygon_splits_1101.json.gz'))['rows']
P = pl.DataFrame(P, schema=['p_ticker', 'execution_date', 'split_from', 'split_to', 'id'], orient='row').with_columns(
    (pl.col('split_to') / pl.col('split_from')).alias('ratio')).filter((pl.col('execution_date') >= '2015-06-01') & (pl.col('execution_date') <= '2025-12-31') & (pl.col('ratio') != 1))
import bisect
P = P.with_columns(pl.col('execution_date').map_elements(lambda d: min(bisect.bisect_left(cal, d), len(cal) - 1), return_dtype=pl.Int32).alias('ei'))
norm = lambda t: t.replace('.', '')
P = P.with_columns(pl.col('p_ticker').str.replace_all(r'\.', '').alias('pn'))
J = J.with_columns(pl.col('ticker').str.replace_all(r'\.', '').alias('tn'))
# ① 代码对上(去掉点号)
a = P.join(J, left_on='pn', right_on='tn').filter((pl.col('i') - pl.col('ei')).abs() <= 3)
# ② 价格指纹:代码对不上,但同期跳空 ≈ 比例(容差 2%,比例必须离 1 足够远)
Jn = J.filter((pl.col('jump') > 1.15) | (pl.col('jump') < 0.87)).select('seg_id', 'company_id', 'ticker', 'd', 'i', 'jump', 'tn')
Pe = P.filter(pl.col('ratio').log().abs() > 0.13).with_columns(pl.int_ranges(pl.col('ei') - 3, pl.col('ei') + 4).alias('i')).explode('i').with_columns(pl.col('i').cast(pl.Int32))
b = Pe.join(Jn, on='i').filter((pl.col('pn') != pl.col('tn')) & ((pl.col('jump').log() - pl.col('ratio').log()).abs() < 0.02))
cols = ['company_id', 'seg_id', 'ticker', 'p_ticker', 'execution_date', 'd', 'ratio', 'jump']
m = pl.concat([a.with_columns(pl.lit('代码对上').alias('how')).select(cols + ['how']), b.with_columns(pl.lit('价格指纹(代码不同)').alias('how')).select(cols + ['how'])])
m = m.with_columns((pl.col('jump').log() - pl.col('ratio').log()).abs().alias('err')).sort('err').unique(['seg_id', 'p_ticker', 'execution_date'], keep='first')
tol = pl.when(pl.col('ratio').log().abs() >= 0.5).then(0.4).otherwise(0.15)
m = m.with_columns(pl.when((pl.col('err') < tol) & ((pl.col('jump').log() * pl.col('ratio').log()) > 0)).then(pl.lit('确认')).otherwise(pl.lit('价格没跳·不用')).alias('check'))
m = m.with_columns((pl.col('how') != '代码对上').alias('_fp')).sort('_fp', 'err').unique(['seg_id', 'd'], keep='first').drop('_fp').sort('ticker', 'd')
m.write_csv('exam_splits_1101.csv')
print(m.group_by('how', 'check').len().sort('how'))
print(m.filter(pl.col('how').str.starts_with('价格')).select('ticker', 'p_ticker', 'd', 'ratio', 'jump').rows())
