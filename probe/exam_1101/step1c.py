# -*- coding: utf-8 -*-
"""第三段:多类股公司(FB、V、MA、F……)封面股本是按类分开报的,SEC 的汇总接口里取不到。
改用「基本加权平均股数」(利润表上,所有类合计),只用 2016-01-04 以前公布的。"""
import json, gzip, sys, polars as pl
x = pl.read_csv('exam_candidates_full_1101.csv', infer_schema_length=0)
FB = json.load(gzip.open(sys.argv[1]))['d']
fix = {}
for cik, o in FB.items():
    forms = set()
    best = None
    for tag in ('WeightedAverageNumberOfSharesOutstandingBasic', 'CommonStockSharesOutstanding'):
        rows = o.get(tag, [])
        forms |= {r[3] for r in rows}
        ok = [r for r in rows if r[4] <= '2016-01-04' and r[2] <= '2015-12-31']
        if ok and best is None:
            # 最新一期;同一期多条取期间最短(季度优先)
            e = max(r[2] for r in ok)
            cand = sorted([r for r in ok if r[2] == e], key=lambda r: (r[1] or '0000') , reverse=True)
            best = (float(cand[0][0]), e, cand[0][3], tag)
    dom = any(f.startswith(('10-K', '10-Q')) for f in forms)
    fix[cik] = (best, dom)
upd = []
for r in x.iter_rows(named=True):
    if r['decision'] in ('剔:2014-16 没交 10-K/10-Q', '待查:没有股本或价格') and r['cik'] in fix:
        best, dom = fix[r['cik']]
        px = float(r['close_20151231']) if r['close_20151231'] else None
        if best and px:
            mc = best[0] * px
            r['shares'], r['shares_asof'], r['shares_form'], r['mktcap_20151231'] = best[0], best[1], best[2] + '·' + best[3], mc
            r['files_10k'] = 'true' if dom else r['files_10k']
            if r['symbol'] in ('BRK.B', 'BRK.A'):
                r['decision'] = '入选' ; r['shares_form'] += '·手工:BRK 加权股数按 A 股折算,市值远超 20 亿'
            elif not dom:
                r['decision'] = '剔:2014-16 没交 10-K/10-Q'
            else:
                r['decision'] = '入选' if mc >= 2e9 else '剔:市值 < 20 亿'
            r['multi_class'] = 'fallback_weighted_basic'
    upd.append(r)
x = pl.DataFrame(upd, infer_schema_length=None)
x.write_csv('exam_candidates_full_1101.csv')
print(x.group_by('decision').len().sort('len', descending=True))
sel = x.filter(pl.col('decision') == '入选').with_columns(pl.col('mktcap_20151231').cast(pl.Float64))
sel.select('symbol', 'name', 'cik', 'company_id', 'seg_id', 'primary_exchange', 'mktcap_20151231', 'shares', 'shares_asof', 'shares_form',
           'multi_class', 'close_20151231', 'days_before_2016', 'rank', 'tier', 'seg_end', 'end_type', 'renamed_to', 'sic'
           ).sort('mktcap_20151231', descending=True).write_csv('exam_list_1101.csv')
print('入选', sel.height, '· 大(≥100亿)', sel.filter(pl.col('mktcap_20151231') >= 1e10).height, '· 中(20–100亿)', sel.filter(pl.col('mktcap_20151231') < 1e10).height)
print(sel.group_by('end_type').len())
print('成交额排名(2016 年初)在前 2000 名以外的:', sel.filter(pl.col('rank').cast(pl.Int32) > 2000).height)
