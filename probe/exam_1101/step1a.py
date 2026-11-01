# -*- coding: utf-8 -*-
"""考卷候选(第一段):2016 年初就在交易的普通股 → 对上 Polygon 当天名单拿交易所和 CIK。"""
import json, gzip, os, polars as pl, bisect, glob
pool = pl.read_csv('/home/claude/seg/pool_FULL_ALL.csv', infer_schema_length=0).filter(pl.col('year') == '2016')
hist = pl.read_csv('/home/claude/hist/pit_history_start_1030.csv', infer_schema_length=0).select('seg_id', 'company_history_start', 'company_start_censored')
cal = sorted(os.path.basename(f)[:10] for f in glob.glob('/home/claude/pituni/day/*.csv.gz'))
td = lambda a, b: bisect.bisect_right(cal, b) - bisect.bisect_left(cal, a)
c = pool.join(hist, on='seg_id', how='left').with_columns(
    pl.struct('company_history_start').map_elements(lambda s: td(s['company_history_start'], '2015-12-31'), return_dtype=pl.Int64).alias('days_before_2016'))
P = json.load(gzip.open('/home/claude/stock_data/probe/exam_1101/polygon_tickers_20151231.json.gz'))
T = pl.DataFrame(P['rows'], schema=P['fields'], orient='row', infer_schema_length=None).rename({'ticker': 'symbol'})
# 同一代码可能有多条(活着的 + 已退市的),优先取活着那天是 2015 年的那条:delisted 在 2016 以后或为空
T = T.with_columns(((pl.col('delisted_utc') == '') | (pl.col('delisted_utc') >= '2016-01-01')).alias('ok_date')).sort('ok_date', descending=True).unique('symbol', keep='first')
c = c.join(T.select('symbol', 'name', 'type', 'primary_exchange', 'cik', 'ok_date'), on='symbol', how='left')
seen = set(pl.read_csv('/home/claude/sd5/pilot_300/manifest.csv', infer_schema_length=0)['symbol']) | {'GNSS', 'MORN', 'XOM', 'KO', 'NVDA', 'PLTR'}
seen_co = set(c.filter(pl.col('symbol').is_in(list(seen)))['company_id'])
# 已看过的公司:按公司剔(改了名的也算);老池里 2016 年还不在交易的,按代码再挡一次
c = c.with_columns(pl.col('company_id').is_in(list(seen_co)).alias('seen_before'))
c = c.with_columns(pl.col('symbol').str.contains(r'^Z[A-Z]ZZT$|^ZVV$|^NTEST|^ATEST|^CTEST|^PTEST').alias('test_symbol'))
c.write_csv('cand_2016.csv')
print('2016 年初全量池', c.height)
print('  历史 ≥250 天', c.filter(pl.col('days_before_2016') >= 250).height)
print('  对上 Polygon', c.filter(pl.col('primary_exchange').is_not_null()).height)
print(c.group_by('primary_exchange').len().sort('len', descending=True))
print('  已看过的公司', c.filter(pl.col('seen_before')).height, '· 测试代码', c.filter(pl.col('test_symbol')).height)
k = c.filter((pl.col('days_before_2016') >= 250) & pl.col('primary_exchange').is_in(['XNYS', 'XNAS']) & ~pl.col('seen_before') & ~pl.col('test_symbol') & (pl.col('cik') != '') & pl.col('cik').is_not_null())
print('→ 要去 SEC 查股本和年报类型的:', k.height, '家 · CIK 去重', k['cik'].n_unique())
open('ciks.txt', 'w').write(','.join(sorted(set(k['cik'].to_list()))))
print('没有 CIK 的(XNYS/XNAS、历史够):', c.filter((pl.col('days_before_2016') >= 250) & pl.col('primary_exchange').is_in(['XNYS', 'XNAS']) & ((pl.col('cik') == '') | pl.col('cik').is_null())).height)
