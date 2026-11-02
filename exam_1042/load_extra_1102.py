# 11-02:补取新接上的代码段的日线(原 exam_ohlcv 只按 company_id 取,漏了改代码后的新代码)
import glob, os, re, polars as pl
src = open('build_exam_daily_v2.py').read()
blk = src[src.index('SPECIAL = {'):src.index('# 纯改代码')]
need = set(re.findall(r"\('([A-Z.]+)', (?:START|'\d{4}-\d\d-\d\d')", blk))
have = set(pl.read_parquet('exam_ohlcv.parquet')['ticker'].unique())
tk = need  # 全部重取一遍这些代码(同一代码不同年份的段也要)
fs = sorted(f for f in glob.glob('/home/claude/pituni/day/*.csv.gz') if '2015-12-01' <= os.path.basename(f)[:10] <= '2025-12-31')
parts = []
for f in fs:
    d = pl.read_csv(f, columns=['ticker', 'open', 'high', 'low', 'close', 'volume'],
                    schema_overrides={'ticker': pl.String, 'open': pl.Float64, 'high': pl.Float64, 'low': pl.Float64, 'close': pl.Float64, 'volume': pl.Float64})
    parts.append(d.filter(pl.col('ticker').is_in(list(tk))).with_columns(pl.lit(os.path.basename(f)[:10]).alias('d')))
P = pl.concat(parts); P.write_parquet('exam_ohlcv_extra_1102.parquet')
print(P.height, sorted(tk - have))
