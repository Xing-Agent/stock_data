#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基本面扩池:SEC companyfacts + submissions → 每家一个 fundamentals.json.gz(格式同 pilot_300/<票>/fundamentals.json)。

大白话:
  · 字段和 pilot_300 那 250 只完全一样的 35 个,再加 3 个新的(PP&E 净值、毛利、营业利润),
    另外把 F-Score 补缺口用的候补标签原样留在 raw_tags 里(第 5 条再用)
  · 时点信息:每条带 filed_at(申报日)、accepted_at(SEC 受理时间,来自 submissions 里同一个申报编号)、
    acceptance_verified、source_tag、period_start / period_end、filing_accession
  · 受理时间对不上申报编号的,acceptance_verified = false、pit_status = degraded,不删
  · EBIT = 税前利润 + 利息费用;无形+商誉 = 商誉 + 无形资产 —— 和 250 只一样,只在同一份申报、同一期都有时才算

用法:python3 build_fund_ext.py <cf_dir> <sub_json.gz> <mapping.csv> <out_dir>
"""
import gzip, json, os, sys, glob
from datetime import date, timedelta
from decimal import Decimal

METRIC_TAGS = {
    'Revenue': ['Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet'],
    'CostOfRevenue': ['CostOfGoodsAndServicesSold', 'CostOfRevenue'],
    'NetIncome': ['NetIncomeLoss', 'ProfitLoss'],
    'DilutedEPS': ['EarningsPerShareDiluted'],
    'CurrentAssets': ['AssetsCurrent'],
    'CurrentLiabilities': ['LiabilitiesCurrent'],
    'LongTermDebt': ['LongTermDebtNoncurrent'],
    'TotalAssets': ['Assets'],
    'StockholdersEquity': ['StockholdersEquity'],
    'OperatingCashFlow': ['NetCashProvidedByUsedInOperatingActivities'],
    'WeightedAverageDilutedShares': ['WeightedAverageNumberOfDilutedSharesOutstanding'],
    'IncomeBeforeTax': ['IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest'],
    'InterestExpense': ['InterestExpense', 'InterestExpenseNonoperating'],
    'IntangibleAssetsNetExcludingGoodwill': ['IntangibleAssetsNetExcludingGoodwill'],
    'Goodwill': ['Goodwill'],
}
RAW_METRICS = ['CashAndCashEquivalentsAtCarryingValue', 'AccountsReceivableNetCurrent', 'InventoryNet', 'Liabilities', 'ShortTermBorrowings',
               'DebtCurrent', 'LongTermDebtCurrent', 'RetainedEarningsAccumulatedDeficit', 'ResearchAndDevelopmentExpense',
               'PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsOfDividends', 'PaymentsOfDividendsCommonStock',
               'PaymentsForRepurchaseOfCommonStock', 'ProceedsFromIssuanceOfCommonStock', 'DepreciationDepletionAndAmortization',
               'DepreciationAmortizationAndAccretionNet', 'PaymentsToAcquireProductiveAssets', 'ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost',
               # ★ 1103 新加(第 2 条)
               'PropertyPlantAndEquipmentNet', 'GrossProfit', 'OperatingIncomeLoss']
FORMS_OK = ('10-K', '10-Q', '10-K/A', '10-Q/A', '10-KT', '10-QT', '10-KT/A', '20-F', '20-F/A', '40-F', '40-F/A', '8-K', '6-K')


def d(s): return date.fromisoformat(s)


def econ_period(start, end, fye_mmdd):
    """按公司财年末(MMDD)算「经济期」:财年、FY/Q1-Q4/YTD。拿不准的返回 (None, None)。"""
    if not fye_mmdd or len(fye_mmdd) != 4:
        return None, None
    m, dd_ = int(fye_mmdd[:2]), int(fye_mmdd[2:])
    e = d(end)
    fy_end = None
    for y in (e.year - 1, e.year, e.year + 1):
        try: cand = date(y, m, min(dd_, 28) if m == 2 else dd_)
        except ValueError: cand = date(y, m, 28)
        if cand >= e - timedelta(days=10):          # 52/53 周财年:允许差几天
            fy_end = cand; break
    if fy_end is None:
        return None, None
    fy = fy_end.year
    if not start:
        months = round((fy_end - e).days / 30.44)
        q = {0: 'FY', 3: 'Q3', 6: 'Q2', 9: 'Q1'}.get(months)
        return fy, q
    days = (e - d(start)).days + 1
    months_left = round((fy_end - e).days / 30.44)
    if 340 <= days <= 380: return fy, 'FY'
    qn = {9: 'Q1', 6: 'Q2', 3: 'Q3', 0: 'Q4'}.get(months_left)
    if 80 <= days <= 100: return fy, qn
    if 170 <= days <= 280: return fy, qn          # 半年 / 9 个月累计:和 250 只的口径一样,标所在季度
    return fy, None


def main(cf_dir, sub_path, map_path, out_dir):
    import csv
    SUB = json.load(gzip.open(sub_path))
    mp = list(csv.DictReader(open(map_path)))
    os.makedirs(out_dir, exist_ok=True)
    stats = []
    by_cik = {r['cik']: r for r in mp}
    seen = set()
    # 一批一批读(全读进内存太大)
    for fpath in sorted(glob.glob(os.path.join(cf_dir, 'cf_*.json.gz'))):
      CF = json.load(gzip.open(fpath))
      for cik in [c for c in CF if c in by_cik]:
        row = by_cik[cik]; folder = row['folder']; seen.add(cik)
        cf, sub = CF.get(cik), SUB.get(cik)
        if not cf or not sub or not cf.get('u'):
            stats.append({'folder': folder, 'cik': cik, 'status': 'no_companyfacts' if not (cf and cf.get('u')) else 'no_submissions'}); continue
        acc = {r[0]: r for r in sub['f']}            # accn → [accn, form, filingDate, acceptanceDateTime, items, reportDate, doc]
        fye = sub.get('fye')
        cik_i = str(int(cik))

        def recs(tag, metric, stype):
            out = []
            for key, rows in cf['u'].items():
                tx_t, unit = key.split('|', 1)
                tx, t = tx_t.split(':', 1)
                if tx != 'us-gaap' or t != tag: continue
                for val, st, en, fy, fp, form, filed, accn, frame in rows:
                    if form not in FORMS_OK: continue
                    a = acc.get(accn)
                    accepted = None
                    if a and a[3]:
                        accepted = a[3].replace('.000Z', '+00:00').replace('Z', '+00:00')
                    efy, efp = econ_period(st or None, en, fye)
                    url = f'https://www.sec.gov/Archives/edgar/data/{cik_i}/{accn.replace("-", "")}/{accn}-index.htm'
                    ok = accepted is not None
                    reasons = [] if ok else ['acceptance_time_not_found_in_submissions']
                    if efp is None: reasons.append('unverified_economic_period')
                    out.append({
                        'metric': metric, 'value': format(Decimal(str(val)), 'f'), 'unit': unit,
                        'fiscal_year': efy, 'fiscal_period': efp, 'source_url': url, 'source_type': stype,
                        'source_form': form, 'source_tag': t, 'taxonomy': 'us-gaap', 'filed_at': filed, 'accepted_at': accepted,
                        'period_start': st or None, 'period_end': en, 'filing_accession': accn, 'acceptance_verified': ok,
                        'period_verified': efp is not None, 'reported_fiscal_year': fy, 'reported_fiscal_period': fp, 'frame': frame or None,
                        'form': form, 'pit_eligible': ok, 'pit_status': 'strict' if not reasons else 'degraded', 'pit_reasons': reasons,
                        'sec_filed_date': filed, 'filing_date': accepted or filed, 'available_at': accepted or filed,
                    })
            return out

        fv = {}
        for m, tags in METRIC_TAGS.items():
            fv[m] = [r for t in tags for r in recs(t, m, 'sec_companyfacts')]
        for t in RAW_METRICS:
            fv[t] = recs(t, t, 'sec_companyfacts_raw')

        def derive(left, right, formula, name, instant, nonneg_right=False):
            def key(r): return (r['filing_accession'], r['period_start'], r['period_end'], r['unit'])
            L, R = {}, {}
            for r in fv[left]:
                if (r['period_start'] is None) == instant and r['pit_status'] == 'strict': L.setdefault(key(r), []).append(r)
            for r in fv[right]:
                if (r['period_start'] is None) == instant and r['pit_status'] == 'strict': R.setdefault(key(r), []).append(r)
            out = []
            for k in sorted(L.keys() & R.keys(), key=str):
                lv = {Decimal(x['value']) for x in L[k]}; rv = {Decimal(x['value']) for x in R[k]}
                if len(lv) != 1 or len(rv) != 1: continue
                a_, b_ = next(iter(lv)), next(iter(rv))
                if nonneg_right and b_ < 0: continue
                base = dict(L[k][0]); base.pop('source_tag', None); base.pop('taxonomy', None)
                base.update({'metric': name, 'value': format(a_ + b_, 'f'), 'source_type': 'derived_from_sec_pit_facts',
                             'derivation': {'formula': formula, 'input_metrics': [left, right], 'filing_accession': k[0],
                                            'period_start': k[1], 'period_end': k[2], 'accepted_at': base['accepted_at']}})
                out.append(base)
            return out
        # ── 第 5 条:F-Score 缺口 —— 主标签没有的那一期,按顺序用备选标签补;每条标明用的哪条规则 ──
        def raw_recs(tag):
            r_ = recs(tag, '_', 'sec_companyfacts_fallback'); return r_
        def key(r): return (r['filing_accession'], r['period_start'], r['period_end'], r['unit'])
        def fill(metric, rules):
            have = {(r['filing_accession'], r['period_start'], r['period_end']) for r in fv[metric]}
            added = 0
            for rule_name, getter in rules:
                for r in getter():
                    k3 = (r['filing_accession'], r['period_start'], r['period_end'])
                    if k3 in have: continue
                    r = dict(r); r['metric'] = metric; r['source_type'] = 'sec_companyfacts_fallback'; r['fallback_rule'] = rule_name
                    fv[metric].append(r); have.add(k3); added += 1
            return added
        def diff(a_tag, b_tag, name):
            def g():
                A = {key(r): r for r in raw_recs(a_tag)}; B = {key(r): r for r in raw_recs(b_tag)}
                out_ = []
                for k in A.keys() & B.keys():
                    r = dict(A[k]); r['value'] = format(Decimal(A[k]['value']) - Decimal(B[k]['value']), 'f'); r['source_tag'] = name
                    out_.append(r)
                return out_
            return g
        def tag_in(t):
            def g():
                out_ = []
                for key_, rows in cf['u'].items():
                    if key_.split('|')[0] == 'us-gaap:' + t: break
                else:
                    return []
                return raw_recs(t)
            return g
        fb = {}
        fb['LongTermDebt'] = fill('LongTermDebt', [
            ('LongTermDebtAndCapitalLeaseObligations', tag_in('LongTermDebtAndCapitalLeaseObligations')),
            ('LongTermDebt - LongTermDebtCurrent', diff('LongTermDebt', 'LongTermDebtCurrent', 'LongTermDebt-LongTermDebtCurrent')),
            ('LongTermDebtNoncurrentExcludingCurrentPortion', tag_in('LongTermDebtNoncurrentExcludingCurrentPortion')),
            ('LongTermNotesPayable', tag_in('LongTermNotesPayable')),
            ('OtherLongTermDebtNoncurrent', tag_in('OtherLongTermDebtNoncurrent'))])
        fb['CostOfRevenue'] = fill('CostOfRevenue', [
            ('CostOfGoodsSold', tag_in('CostOfGoodsSold')),
            ('CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization', tag_in('CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization')),
            ('CostOfServices', tag_in('CostOfServices')),
            ('Revenues - GrossProfit', diff('Revenues', 'GrossProfit', 'Revenues-GrossProfit')),
            ('RevenueFromContractWithCustomerExcludingAssessedTax - GrossProfit', diff('RevenueFromContractWithCustomerExcludingAssessedTax', 'GrossProfit', 'RevenueFromContract-GrossProfit'))])
        # 2019 年新租赁准则以后,很多公司把「固定资产净值」改报成「固定资产 + 融资租赁使用权资产 净值」(UNP、CVX、DAL 都是)
        fb['PropertyPlantAndEquipmentNet'] = fill('PropertyPlantAndEquipmentNet', [
            ('PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization',
             tag_in('PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization')),
            ('PropertyPlantAndEquipmentNetIncludingFinanceLease', tag_in('PropertyPlantAndEquipmentNetIncludingFinanceLease'))])
        fb['Revenue'] = fill('Revenue', [
            ('SalesRevenueGoodsNet', tag_in('SalesRevenueGoodsNet')),
            ('RevenueFromContractWithCustomerIncludingAssessedTax', tag_in('RevenueFromContractWithCustomerIncludingAssessedTax')),
            ('RevenuesNetOfInterestExpense', tag_in('RevenuesNetOfInterestExpense'))])

        fv['EBIT'] = derive('IncomeBeforeTax', 'InterestExpense', 'IncomeBeforeTax + InterestExpense', 'EBIT', False, True)
        fv['IntangiblesAndGoodwill'] = derive('Goodwill', 'IntangibleAssetsNetExcludingGoodwill', 'Goodwill + IntangibleAssetsNetExcludingGoodwill', 'IntangiblesAndGoodwill', True)

        # F-Score 候补和 IFRS(外国公司)标签:原样留下,不进 financial_versions(第 5 条再定怎么用)
        used = {t for ts in METRIC_TAGS.values() for t in ts} | set(RAW_METRICS)
        raw_tags = {k: v for k, v in cf['u'].items() if k.split('|')[0].split(':', 1)[1] not in used or not k.startswith('us-gaap:')}

        doc = {'symbol': folder, 'cik': cik, 'company_id': row['company_id'], 'sec_name': sub.get('n'),
               'cohort': {'origin': 'fund_expand_1103', 'pool_symbols': row['symbols'].split(';'), 'pool_years': [row['y0'], row['y1']]},
               'meta': {'retrieved_at': row.get('retrieved_at') or '2026-11-03', 'sources': ['SEC CompanyFacts', 'SEC submissions (acceptanceDateTime)'],
                        'pit_status': 'partial', 'adjustment': 'not_applicable',
                        'filing_date_semantics': 'filing_date and available_at use SEC acceptance time (UTC) from submissions for the same accession; sec_filed_date is the SEC filing date.',
                        'fiscal_period_semantics': 'fiscal_year/fiscal_period = economic period from period dates and the company fiscal-year end; reported_fiscal_* = the fy/fp of the filing as given by SEC.',
                        'builder': 'probe/fund_expand_1103/build_fund_ext.py'},
               'financial_versions': fv, 'raw_tags_fields': ['val', 'start', 'end', 'fy', 'fp', 'form', 'filed', 'accn', 'frame'], 'raw_tags': raw_tags}
        p = os.path.join(out_dir, folder); os.makedirs(p, exist_ok=True)
        with gzip.open(os.path.join(p, 'fundamentals.json.gz'), 'wt', encoding='utf-8') as fh:
            json.dump(doc, fh, ensure_ascii=False, separators=(',', ':'))
        n = {m: len(v) for m, v in fv.items()}
        strict = sum(1 for v in fv.values() for r in v if r['pit_status'] == 'strict')
        stats.append({'folder': folder, 'cik': cik, 'status': 'ok', 'records': sum(n.values()), 'strict': strict, **{f'fallback_{m}': c for m, c in fb.items()},
                      **{f'n_{m}': c for m, c in n.items()}})
      del CF
    for cik, row in by_cik.items():
        if cik not in seen: stats.append({'folder': row['folder'], 'cik': cik, 'status': 'no_companyfacts_fetched'})
    json.dump(stats, open(os.path.join(out_dir, '_build_stats.json'), 'w'), ensure_ascii=False)
    print(len(stats), sum(1 for s in stats if s['status'] == 'ok'))


if __name__ == '__main__':
    main(*sys.argv[1:5])
