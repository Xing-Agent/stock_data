# -*- coding: utf-8 -*-
"""第四段:核对 CIK 对不对。
大白话:Polygon 给的公司编号(CIK),对被收购的公司有时填成了收购方的(PNK 填成了 Legg Mason,
LVLT 填成了 Expeditors)。编号错了,股本就是别家的,市值全错。
核对办法:SEC 里这个编号的现名 + 所有曾用名,跟 Polygon 的公司名比,像不像。不像的 → 待人工。"""
import json, gzip, sys, re, difflib, polars as pl
V = json.load(gzip.open(sys.argv[1]))['d']
x = pl.read_csv('exam_candidates_full_1101.csv', infer_schema_length=0)
STOP = {'INC', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'LTD', 'PLC', 'THE', 'HOLDINGS', 'HLDGS', 'HLDG', 'GROUP', 'COM', 'STK', 'CL',
        'CLASS', 'A', 'B', 'C', 'NEW', 'DE', 'SHS', 'COMMON', 'STOCK', 'LP', 'L', 'P', 'TRUST', 'N', 'V', 'NV', 'SA', 'AG', 'ORD', 'INTL',
        'INTERNATIONAL', 'LIMITED', 'LLC', 'TR', 'SBI', 'REIT', 'HOLDING', 'MD', 'IN', 'OF', 'AND', 'SER', 'UNITS', 'PARTNERS'}
def toks(s):
    s = re.sub(r'\(.*?\)', ' ', (s or '').upper()); s = re.sub(r'[^A-Z0-9 ]', ' ', s)
    return [w for w in s.split() if w not in STOP]
def sim(a, b):
    ta, tb = toks(a), toks(b)
    if not ta or not tb: return 0.0
    r = difflib.SequenceMatcher(None, ' '.join(ta), ' '.join(tb)).ratio()
    ov = len(set(ta) & set(tb)) / min(len(set(ta)), len(set(tb)))
    return max(r, ov)
def best(r):
    v = V.get(r['cik'])
    if not v: return -1.0
    names = [v['name']] + [f[0] for f in v['former']]
    return max(sim(r['name'], n) for n in names)
x = x.with_columns(pl.struct('cik', 'name').map_elements(best, return_dtype=pl.Float64).alias('cik_name_match'))
chk = pl.col('decision').is_in(['入选', '剔:同一公司的另一类股(留成交额大的)', '剔:老池公司的另一类股']) | \
      ((pl.col('decision') == '剔:市值 < 20 亿') & (pl.col('rank').cast(pl.Int32) <= 2000))
bad = chk & (pl.col('cik_name_match') >= 0) & (pl.col('cik_name_match') < 0.5)
x = x.with_columns(pl.when(bad).then(pl.lit('待人工:CIK 可能指向别家公司')).otherwise(pl.col('decision')).alias('decision'))
x.write_csv('exam_candidates_full_1101.csv')
print(x.filter(pl.col('decision') == '待人工:CIK 可能指向别家公司').select('symbol', 'name', 'cik', 'cik_name_match').sort('cik_name_match').rows())
print(x.group_by('decision').len().sort('len', descending=True))
sel = x.filter(pl.col('decision') == '入选').with_columns(pl.col('mktcap_20151231').cast(pl.Float64))
sel.select('symbol', 'name', 'cik', 'company_id', 'seg_id', 'primary_exchange', 'mktcap_20151231', 'shares', 'shares_asof', 'shares_form',
           'multi_class', 'close_20151231', 'days_before_2016', 'rank', 'tier', 'seg_end', 'end_type', 'renamed_to', 'sic', 'cik_name_match'
           ).sort('mktcap_20151231', descending=True).write_csv('exam_list_1101.csv')
pend = x.filter(pl.col('decision').str.starts_with('待人工'))
pend.select('symbol', 'name', 'cik', 'decision', 'rank', 'mktcap_20151231', 'close_20151231', 'forms_2014_2016').sort(pl.col('rank').cast(pl.Int32)).write_csv('exam_pending_manual_1101.csv')
print('入选', sel.height, '大', sel.filter(pl.col('mktcap_20151231') >= 1e10).height, '中', sel.filter(pl.col('mktcap_20151231') < 1e10).height,
      '消失', sel.filter(pl.col('end_type').str.starts_with('消失')).height, '改名', sel.filter(pl.col('end_type').str.starts_with('改名')).height,
      '待人工', pend.height)
