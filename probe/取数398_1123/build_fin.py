#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 398 补 2:2005–2014 面板(1,042 家)的营收、净利润和公布日期,来源 SEC XBRL(companyfacts)。
SEC 的结构化财报 2009 年才开始(大公司 2009 年中、其余 2011 年),所以最早只到 2009 年前后。
每个「期末日 × 期间长度」取第一次披露的那个数(首次公布日期 = 最早的 filed),避免用后来重述的数。
营收科目各公司不一样,按下面的次序挑:这家公司在这个期间有哪个就用哪个。
用法:python3 build_fin.py XBRL.json.gz tick2cik.json OUT_DIR"""
import csv, gzip, json, os, sys
from datetime import date
X = json.load(gzip.open(sys.argv[1])); T2C = json.load(open(sys.argv[2])); out = sys.argv[3]; os.makedirs(out, exist_ok=True)
C2T = {}
for t, c in T2C.items(): C2T.setdefault(c, []).append(t)
REV = ['Revenues', 'SalesRevenueNet', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'RevenueFromContractWithCustomerIncludingAssessedTax',
       'SalesRevenueGoodsNet', 'SalesRevenueServicesNet', 'RevenuesNetOfInterestExpense', 'RegulatedAndUnregulatedOperatingRevenue',
       'ElectricUtilityRevenue', 'OilAndGasRevenue', 'InterestAndDividendIncomeOperating']
NI = ['NetIncomeLoss', 'ProfitLoss', 'NetIncomeLossAvailableToCommonStockholdersBasic', 'IncomeLossFromContinuingOperations']


def kind(s, e):
    if not s: return None
    d = (date.fromisoformat(e) - date.fromisoformat(s)).days
    return '季' if 80 <= d <= 100 else '年' if 350 <= d <= 380 else None


def pick(facts, keys):
    """返回 {(end, 季/年): (val, filed, form, 科目)},同一期间取最早披露"""
    res = {}
    for k in keys:
        for s, e, v, fy, fp, form, filed, frame in facts.get(k, []):
            kd = kind(s, e)
            if not kd: continue
            key = (e, kd)
            if key in res and res[key][3] != k: continue   # 前面的科目已经有这一期,用前面的
            if key not in res or filed < res[key][1]: res[key] = (v, filed, form, k)
    return res


rows, cov = [], {}
for c, f in X.items():
    if not isinstance(f, dict): continue
    R, N = pick(f, REV), pick(f, NI)
    for key in sorted(set(R) | set(N)):
        e, kd = key
        if e < '2008-01-01': continue
        r, n = R.get(key), N.get(key)
        filed = min(x[1] for x in (r, n) if x)
        for t in C2T.get(c, [c]):
            rows.append(dict(代码=t, cik=c, 公司名=f.get('n', ''), 期末=e, 期间=kd, 营收=r[0] if r else '', 营收科目=r[3] if r else '',
                             净利润=n[0] if n else '', 净利润科目=n[3] if n else '', 首次公布日期=filed, 申报类型=(r or n)[2]))
            cov.setdefault(t, set()).add(e[:4])
rows.sort(key=lambda r: (r['代码'], r['期末'], r['期间']))
with open(f'{out}/营收净利润_2008至2016_SEC.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
from collections import Counter
first = Counter(min(v) for v in cov.values())
print('rows', len(rows), 'tickers with data', len(cov), 'of', len(T2C))
print('最早有数据的年份分布', sorted(first.items()))
y = Counter()
for t, v in cov.items():
    for yr in v: y[yr] += 1
print('每年有数据的票数', sorted(y.items()))
q = Counter((r['期末'][:4], r['期间']) for r in rows if r['营收'] != '')
print(sorted(q.items()))
