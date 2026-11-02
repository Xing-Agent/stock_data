# 考卷 1,042 只里的破产股:逐只按 SEC 8-K 原文定结算价,写成引擎认的格式(同 pilot_300 的 delisted_equity_outcome_review)
import json, polars as pl
U = {"AKRX": "https://www.sec.gov/Archives/edgar/data/3116/000110465920111583/tm2032215d1_8k.htm",
 "BBBY": "https://www.sec.gov/Archives/edgar/data/886158/000119312523247428/d579010d8k.htm",
 "BTU": "https://www.sec.gov/Archives/edgar/data/1064728/000106472817000022/a8k-btufebruary2017mor.htm",
 "CBL": "https://www.sec.gov/Archives/edgar/data/910612/000156459021043767/cbl-8k_20210811.htm",
 "CHK": "https://www.sec.gov/Archives/edgar/data/895126/000089512621000016/chk-20210116.htm",
 "CIE": "https://www.sec.gov/Archives/edgar/data/1471261/000119312517368742/d506127d8k.htm",
 "CREE": "https://www.sec.gov/Archives/edgar/data/895419/000119312525199310/d36059d8k.htm",
 "DO": "https://www.sec.gov/Archives/edgar/data/949039/000119312521115558/d135254d8k.htm",
 "ENDP": "https://www.sec.gov/Archives/edgar/data/1593034/000119312524075864/d813107d8k.htm",
 "ESV": "https://www.sec.gov/Archives/edgar/data/314808/000110465921032788/tm218790d1_8k.htm",
 "FTR": "https://www.sec.gov/Archives/edgar/data/20520/000114036120019176/brhc10014613_8k.htm",
 "GNC": "https://www.sec.gov/Archives/edgar/data/1502034/000119312520265653/d25873d8k.htm",
 "GPOR": "https://www.sec.gov/Archives/edgar/data/874499/000121390021023524/ea140017-8k_gulfport.htm",
 "INSY": "https://www.sec.gov/Archives/edgar/data/1516479/000156459019034903/insy-8k_20190917.htm",
 "JCP": "https://www.sec.gov/Archives/edgar/data/1166126/000119312521023867/d123081d8k.htm",
 "MNK": "https://www.sec.gov/Archives/edgar/data/1567892/000110465923108353/tm2328021d1_8k.htm",
 "NE": "https://www.sec.gov/Archives/edgar/data/1458891/000119312520205998/d85677d8k.htm",
 "RAD": "https://www.sec.gov/Archives/edgar/data/84129/000110465923109413/tm2328535d1_8ka.htm",
 "SAVE": "https://www.sec.gov/Archives/edgar/data/1498710/000095010324016405/dp220813_8k.htm",
 "SHLD": "https://www.sec.gov/Archives/edgar/data/1310067/000119312519270375/d820732d8k.htm",
 "SPN": "https://www.sec.gov/Archives/edgar/data/886835/000119312520311144/d63085d8k.htm",
 "SPWR": "https://www.sec.gov/Archives/edgar/data/867773/000086777324000086/spwr-20240802.htm",
 "WFT": "https://www.sec.gov/Archives/edgar/data/1603923/000141057819001221/tv529364_8k.htm"}
# (结论, 原文要点)  zero = 计划明确写了普通股注销、不分配
Z = {
 "AKRX": "Effective-date 8-K: all common stock outstanding immediately prior to the Effective Date cancelled and discharged.",
 "BBBY": "Confirmed plan effective: all equity interests (common and Series A preferred) cancelled; no recovery.",
 "BTU": "Plan: current equity cancelled and extinguished; holders will not receive or retain any property.",
 "CHK": "Confirmed plan: Existing Equity Interests (Class 10) cancelled; holders receive no distribution.",
 "ENDP": "Plan: existing equity interests cancelled, extinguished and discharged; holders receive no distribution.",
 "FTR": "Confirmed plan: all equity interests including common stock cancelled; holders receive no distribution.",
 "GNC": "Plan: all outstanding common and preferred stock cancelled, shareholders receive no distributions (asset sale to Harbin Pharmaceutical).",
 "GPOR": "Confirmed plan: common stock cancelled; holders receive no distribution.",
 "INSY": "Liquidating plan: common stock cancelled for no consideration; company dissolved into liquidating trusts.",
 "JCP": "Plan effective: all equity interests cancelled without consideration and have no value (Old Copper Company).",
 "MNK": "2023 plan: holders of existing equity interests receive no distribution; ordinary shares cancelled.",
 "RAD": "Plan: all Existing Equity Interests cancelled and extinguished; holders receive no recovery.",
 "SAVE": "Plan: existing common stock and equity interests cancelled without any distribution.",
 "SHLD": "Confirmed liquidating plan: common stock and warrants cancelled, of no further force or effect; no distribution to equity.",
 "SPN": "Plan: existing equity discharged and terminated without any distribution or retained property (NYSE delisting preceded the Dec-2020 filing).",
}
N = {  # 部分回收(认股权证 / 新股百分比)或找不到原文 —— 不许当 0
 "CBL": ("bankruptcy", "partial_recovery_new_equity", "Plan: existing REIT common stock cancelled; holders receive pro rata share of the Existing Common Equity Recovery Pool (a slice of new common stock). Per-share value not fixed."),
 "DO": ("bankruptcy", "partial_recovery_warrants", "Plan: common stock cancelled; holders of existing parent equity receive pro rata share of New Warrants."),
 "ESV": ("bankruptcy", "partial_recovery_warrants", "Exam series = Ensco (ESV) → Valaris (VAL, 1:1 rename 2019-07-31). Valaris plan: existing interests (Class 13) receive pro rata share of New Warrants."),
 "NE": ("bankruptcy", "partial_recovery_warrants", "Plan: existing ordinary shares receive pro rata Tranche 3 Warrants (if plan not submitted to equity) or nothing (if equity class rejects)."),
 "WFT": ("bankruptcy", "partial_recovery_new_equity_and_warrants", "Plan: noteholders receive 99% of new common stock; existing shareholders receive 1% of new equity plus warrants."),
 "CREE": ("bankruptcy", "partial_recovery_new_equity", "Exam series = Cree → Wolfspeed (WOLF, 1:1 rename 2021-10-04). 2025 plan: common stock cancelled; existing holders receive pro rata 3.0% or 5.0% of new equity. Series cut at 2025-09-26, the last day of old shares (new shares began trading 2025-09-29)."),
 "CIE": ("bankruptcy", "no_SEC_text_found", "Chapter 11 liquidation (assets sold); no SEC filing found stating the equity treatment. Likely zero but not verified."),
 "SPWR": ("bankruptcy", "no_SEC_text_found", "Chapter 11 with sale of assets to Complete Solaria; no SEC filing found stating the equity treatment. Likely zero but not verified."),
}
m = pl.read_csv('/home/claude/stock_data/exam_1042/manifest.csv', infer_schema_length=0)
dd = dict(zip(m['symbol'], m['delisting_date']))
recs = []
for s, note in sorted(Z.items()):
    recs.append({"symbol": s, "retirement_category": "bankruptcy", "disposition": "bankruptcy", "transaction_consideration_type": None,
                 "cash_component_per_old_share": None, "stock_or_other_component": None, "verified_source": U[s],
                 "status": "plan_no_recovery_verified_primary_SEC", "note": note + " Numeric zero is the plan recovery, not the last exchange close.",
                 "delisting_date_in_exam_data": dd[s], "delisting_settlement_price": 0.0,
                 "settlement_price_basis": "confirmed_plan_no_distribution_to_common_equity"})
for s, (cat, st, note) in sorted(N.items()):
    recs.append({"symbol": s, "retirement_category": cat, "disposition": "bankruptcy", "transaction_consideration_type": None,
                 "cash_component_per_old_share": None, "stock_or_other_component": ("warrants/new equity" if st.startswith('partial') else None),
                 "verified_source": U[s], "status": st, "note": note, "delisting_date_in_exam_data": dd[s],
                 "delisting_settlement_price": None,
                 "settlement_price_basis": "null = no fixed per-share amount established; use last close and track separately; NOT zero"})
doc = {"generated_at": "2026-11-02",
       "scope": "Exam universe (1,042). Bankruptcy-related delistings only (23 names): every delisted exam name was scanned on SEC submissions for 8-K Item 1.03 within [delisting-730d, delisting+400d] plus later chain segments; each hit read in the plan/effective-date 8-K. delisting_settlement_price = 0.0 only where the SEC text explicitly says common equity is cancelled with no distribution; null otherwise (null is NOT zero). Acquisitions are not covered here: engine default (last close) applies; stock-merger cuts are flagged ACQUISITION_STOCK in manifest.csv.",
       "records": recs}
json.dump(doc, open('/home/claude/stock_data/exam_1042/reviews/delisted_equity_outcome_review_exam_1102.json', 'w'), ensure_ascii=False, indent=1)
# manifest:破产的标 bankruptcy
cat = {s: 'bankruptcy' for s in list(Z) + list(N)}
m = m.with_columns(pl.col('symbol').map_elements(lambda s: cat.get(s, ''), return_dtype=pl.String).alias('_bk'))
m = m.with_columns(pl.when(pl.col('_bk') != '').then(pl.col('_bk')).otherwise(pl.col('retirement_category')).alias('retirement_category')).drop('_bk')
m.write_csv('/home/claude/stock_data/exam_1042/manifest.csv')
print(len(Z), len(N), m.group_by('retirement_category').len().rows(), m.filter(pl.col('retirement_category') == 'bankruptcy')['delisted'].unique().to_list())
