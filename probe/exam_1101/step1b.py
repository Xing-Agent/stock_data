# -*- coding: utf-8 -*-
"""考卷名单(第二段):SEC 股本 × 2015-12-31 收盘价 = 市值;按年报类型剔掉外国公司(ADR)和基金。

大白话:
  · 市值:用「2016-01-04 以前已经公布」的最近一次财报封面股本(只用当时能看到的数),乘 2015-12-31 的收盘价
  · 多类股(比如 A/B 股):封面上各类股本加总,乘这一类的价格 —— 近似,标 multi_class
  · ADR / 外国公司:2014-07 到 2016 年只交 20-F / 40-F、不交 10-K 的 → 剔
  · 基金:交 N-CSR / N-Q 的(封闭式基金)→ 剔
"""
import json, gzip, sys, polars as pl

c = pl.read_csv('cand_2016.csv', infer_schema_length=0)
S = json.load(gzip.open(sys.argv[1]))          # {cik: {sh:[[val,end,form,filed,accn]], forms:[...], ...}}
px = pl.read_csv('/home/claude/pituni/day/2015-12-31.csv.gz', columns=['ticker', 'close'],
                 schema_overrides={'ticker': pl.String, 'close': pl.Float64}).rename({'ticker': 'symbol', 'close': 'close_20151231'})

rows = []
for cik, o in S['d'].items():
    sh = [r for r in o.get('sh', []) if r[3] <= '2016-01-04' and r[1] <= '2015-12-31']
    shares, multi, sh_end, sh_form = None, False, None, None
    if sh:
        last_filed = max(r[3] for r in sh)
        cur = [r for r in sh if r[3] == last_filed]
        e = max(r[1] for r in cur)
        cur = [r for r in cur if r[1] == e]
        vals = sorted({r[0] for r in cur})
        shares, multi, sh_end, sh_form = float(sum(vals)), len(vals) > 1, e, cur[0][2]
    forms = set(o.get('forms', [])) | {r[2] for r in o.get('sh', [])}
    dom = any(f.startswith('10-K') or f.startswith('10-Q') for f in forms)
    foreign = (not dom) and any(f.startswith(('20-F', '40-F', '6-K')) for f in forms)
    fund = any(f.startswith(('N-CSR', 'N-Q')) for f in forms)
    rows.append((cik, shares, multi, sh_end, sh_form, ','.join(sorted(forms)), dom, foreign, fund, o.get('sic') or '', o.get('addr') or ''))
F = pl.DataFrame(rows, schema=['cik', 'shares', 'multi_class', 'shares_asof', 'shares_form', 'forms_2014_2016', 'files_10k',
                               'foreign_filer', 'fund_filer', 'sic', 'hq'], orient='row')
x = c.join(F, on='cik', how='left').join(px, on='symbol', how='left')
x = x.with_columns((pl.col('shares') * pl.col('close_20151231')).alias('mktcap_20151231'))
base = (pl.col('days_before_2016').cast(pl.Int64) >= 250) & pl.col('primary_exchange').is_in(['XNYS', 'XNAS']) \
       & ~(pl.col('seen_before') == 'true') & ~(pl.col('test_symbol') == 'true')
x = x.with_columns(
    pl.when(~base).then(pl.lit('不在范围(交易所/历史/老池/测试代码)'))
      .when(pl.col('cik').is_null() | (pl.col('cik') == '')).then(pl.lit('没有 CIK'))
      .when(pl.col('fund_filer')).then(pl.lit('剔:基金'))
      .when(pl.col('foreign_filer')).then(pl.lit('剔:外国公司/ADR'))
      .when(~pl.col('files_10k').fill_null(False)).then(pl.lit('剔:2014-16 没交 10-K/10-Q'))
      .when(pl.col('mktcap_20151231').is_null()).then(pl.lit('待查:没有股本或价格'))
      .when(pl.col('mktcap_20151231') >= 2e9).then(pl.lit('入选'))
      .otherwise(pl.lit('剔:市值 < 20 亿')).alias('decision'))
x.write_csv('exam_candidates_full_1101.csv')
print(x.group_by('decision').len().sort('len', descending=True))
sel = x.filter(pl.col('decision') == '入选')
sel.select('symbol', 'name', 'cik', 'company_id', 'seg_id', 'primary_exchange', 'mktcap_20151231', 'shares', 'shares_asof', 'multi_class',
           'close_20151231', 'days_before_2016', 'seg_end', 'end_type', 'renamed_to', 'sic').sort('mktcap_20151231', descending=True).write_csv('exam_list_1101.csv')
print('入选', sel.height, '· 其中后来消失/退市', sel.filter(pl.col('end_type') != '样本末尾仍在交易').height)
print(sel.group_by('end_type').len())
