#!/usr/bin/env python3
# 《356》对账:修之前的小时线(OLD_DIR)和修之后的(NEW_DIR)逐根比,列出改了的;再按策略组的门槛扫一遍修完还剩下哪些大振幅
# 用法:python3 diff_356.py OLD_DIR NEW_DIR
import sys, polars as pl
old, new = sys.argv[1], sys.argv[2]
LEV = ['TQQQ', 'SQQQ', 'SOXL', 'SOXS']
k = ['symbol', 'time_utc']
out = []
for d in ['小时线_2004_2014', '小时线_2015起']:
    n = pl.read_parquet(f'{new}/{d}/*.parquet'); o = pl.read_parquet(f'{old}/{d}/*.parquet')
    j = n.join(o, on=k, how='full', suffix='_原', coalesce=True)
    ch = j.filter((pl.col('high') != pl.col('high_原')) | (pl.col('low') != pl.col('low_原')) | (pl.col('open') != pl.col('open_原')) | (pl.col('close') != pl.col('close_原')))
    ch = ch.filter(((pl.col('high') / pl.col('high_原') - 1).abs() > 0.001) | ((pl.col('low') / pl.col('low_原') - 1).abs() > 0.001)
                   | ((pl.col('open') / pl.col('open_原') - 1).abs() > 0.001) | ((pl.col('close') / pl.col('close_原') - 1).abs() > 0.001))
    out.append(ch.select(pl.lit('小时线').alias('层'), pl.col('symbol').alias('代码'), pl.col('time_utc').dt.strftime('%Y-%m-%dT%H:%MZ').alias('时间'), 'session',
                         pl.col('open_原').alias('原开'), pl.col('high_原').alias('原高'), pl.col('low_原').alias('原低'), pl.col('close_原').alias('原收'),
                         pl.col('open').alias('新开'), pl.col('high').alias('新高'), pl.col('low').alias('新低'), pl.col('close').alias('新收')))
    th = pl.when(pl.col('symbol').is_in(LEV)).then(0.25).otherwise(0.08)
    x = n.with_columns(pl.max_horizontal('open', 'close').alias('mx'), pl.min_horizontal('open', 'close').alias('mn'), th.alias('th'))
    r = x.filter((pl.col('high') > pl.col('mx') * (1 + pl.col('th'))) | (pl.col('low') < pl.col('mn') * (1 - pl.col('th'))))
    print(d, '改了', ch.height, '根;修完按 8%/25% 门槛还剩', r.height, '根')
    with pl.Config(tbl_rows=60, tbl_width_chars=220): print(r.select('symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume'))
A = pl.concat(out).sort(['代码', '时间'])
A.write_csv(f'{new}/坏点修正_小时线.csv', include_bom=True)
print('总共改了', A.height, '根小时线')
