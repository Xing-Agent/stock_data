# -*- coding: utf-8 -*-
"""第五段:待人工的 148 只,用 EDGAR 按公司名重新找编号,再判。
规则(和前面一样):
  · 2014-07 ~ 2016-06 只交 20-F/40-F → 外国公司,剔
  · 交 10-K/10-Q:股本(封面 > 加权平均 > 资产负债表,2016-01-04 以前公布)× 2015-12-31 收盘价 ≥ 20 亿 → 入选
  · 多类股、SEC 汇总里取不到合计股本的美国公司:2016 年初成交额排名前 600 → 按「明显 ≥ 20 亿」入选,标出来
  · 仍然找不到的:留待人工
"""
import json, gzip, sys, polars as pl
R = json.load(gzip.open(sys.argv[1]))['d']
x = pl.read_csv('exam_candidates_full_1101.csv', infer_schema_length=0)
seen_cik = {c['cik'].lstrip('0') for c in json.load(gzip.open('/home/claude/secfund/sec_companyfacts_300_1030.json.gz'))['companies'].values()}
pri = {'EntityCommonStockSharesOutstanding': 0, 'WeightedAverageNumberOfSharesOutstandingBasic': 1, 'CommonStockSharesOutstanding': 2}
upd = []
for r in x.iter_rows(named=True):
    if r['decision'].startswith('待人工') and r['symbol'] in R:
        o = R[r['symbol']]
        forms = set(o.get('forms') or [])
        dom = any(f.startswith(('10-K', '10-Q')) for f in forms)
        foreign = (not dom) and any(f.startswith(('20-F', '40-F')) for f in forms)
        rank = int(r['rank'])
        px = float(r['close_20151231']) if r['close_20151231'] else None
        sh = None
        if o.get('shares'):
            rows = sorted(o['shares'], key=lambda s: (pri[s[0]], s[5], s[3]), reverse=False)
            best_t = min(pri[s[0]] for s in rows)
            rows = [s for s in rows if pri[s[0]] == best_t]
            last = max(s[5] for s in rows); rows = [s for s in rows if s[5] == last]
            e = max(s[3] for s in rows); rows = [s for s in rows if s[3] == e]
            sh = (sum({s[1] for s in rows}) if best_t == 0 else rows[0][1], rows[0][0], e)
        r['cik'] = (o.get('cik') or '').zfill(10) if o.get('cik') else r['cik']
        if o.get('cik') and o['cik'].lstrip('0') in seen_cik:
            r['decision'] = '剔:老池公司的另一类股'
        elif not o.get('cik'):
            r['decision'] = '待人工:EDGAR 也没找到'
        elif foreign:
            r['decision'] = '剔:外国公司/ADR'
        elif not dom:
            r['decision'] = '剔:2014-16 没交 10-K/10-Q'
        elif sh and px:
            mc = sh[0] * px
            r['shares'], r['shares_form'], r['shares_asof'], r['mktcap_20151231'] = sh[0], 'EDGAR 重找·' + sh[1], sh[2], mc
            r['decision'] = '入选' if mc >= 2e9 else '剔:市值 < 20 亿'
            if r['symbol'] == 'BRK.B': r['decision'] = '入选'
        elif rank <= 600:
            r['decision'] = '入选'; r['shares_form'] = '人工:多类股取不到合计股本,成交额排名前 600,明显 ≥ 20 亿'
        else:
            r['decision'] = '待人工:多类股取不到股本'
        r['sec_name'] = o.get('name')
    upd.append(r)
x = pl.DataFrame(upd, infer_schema_length=None)
# 同一家公司两类股,只留成交额大的(这一轮新进来的也要过一遍)
s = x.filter(pl.col('decision') == '入选').with_columns(pl.col('avg_dollar_volume_60d').cast(pl.Float64).alias('_dv'))
keep = set(s.sort('_dv', descending=True).unique('cik', keep='first')['seg_id'])
x = x.with_columns(pl.when((pl.col('decision') == '入选') & ~pl.col('seg_id').is_in(list(keep))).then(pl.lit('剔:同一公司的另一类股(留成交额大的)')).otherwise(pl.col('decision')).alias('decision'))
x.write_csv('exam_candidates_full_1101.csv')
f = x.group_by('decision').len().sort('len', descending=True); f.write_csv('exam_funnel_1101.csv'); print(f)
ch = x.filter(pl.col('symbol').is_in(list(R)))
print(ch.select('symbol', 'decision', 'sec_name', 'mktcap_20151231').sort('decision').rows())
sel = x.filter(pl.col('decision') == '入选').with_columns(pl.col('mktcap_20151231').cast(pl.Float64))
sel.select('symbol', 'name', 'cik', 'company_id', 'seg_id', 'primary_exchange', 'mktcap_20151231', 'shares', 'shares_asof', 'shares_form',
           'multi_class', 'close_20151231', 'days_before_2016', 'rank', 'tier', 'seg_end', 'end_type', 'renamed_to', 'sic'
           ).sort('mktcap_20151231', descending=True, nulls_last=False).write_csv('exam_list_1101.csv')
pend = x.filter(pl.col('decision').str.starts_with('待人工'))
pend.select('symbol', 'name', 'cik', 'decision', 'rank').write_csv('exam_pending_manual_1101.csv')
big = sel.filter((pl.col('mktcap_20151231') >= 1e10) | pl.col('shares_form').fill_null('').str.starts_with('人工'))
print('入选', sel.height, '· 大', big.height, '· 中', sel.height - big.height, '· 退市/消失', sel.filter(pl.col('end_type').str.starts_with('消失')).height,
      '· 改名', sel.filter(pl.col('end_type').str.starts_with('改名')).height, '· 仍待人工', pend.height)
