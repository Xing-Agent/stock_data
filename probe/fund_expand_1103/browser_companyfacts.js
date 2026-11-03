// 在 www.sec.gov 的页面里跑:逐家取 SEC companyfacts,只留下面这些标签,压成紧凑行。
// 每行 = [值, 期初, 期末, fy, fp, 表格, 申报日, 申报编号, frame]
// 结果放在 window.CF[cik] = {u: {"us-gaap:Tag|USD": [rows...]}, n: 公司名}
const TAGS = {
  'us-gaap': [
    // 原 35 个字段用到的标签
    'Revenues', 'RevenueFromContractWithCustomerExcludingAssessedTax', 'SalesRevenueNet', 'CostOfGoodsAndServicesSold', 'CostOfRevenue',
    'NetIncomeLoss', 'ProfitLoss', 'EarningsPerShareDiluted', 'AssetsCurrent', 'LiabilitiesCurrent', 'LongTermDebtNoncurrent', 'Assets',
    'StockholdersEquity', 'NetCashProvidedByUsedInOperatingActivities', 'WeightedAverageNumberOfDilutedSharesOutstanding',
    'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest', 'InterestExpense', 'InterestExpenseNonoperating',
    'IntangibleAssetsNetExcludingGoodwill', 'Goodwill', 'CashAndCashEquivalentsAtCarryingValue', 'AccountsReceivableNetCurrent', 'InventoryNet',
    'Liabilities', 'ShortTermBorrowings', 'DebtCurrent', 'LongTermDebtCurrent', 'RetainedEarningsAccumulatedDeficit', 'ResearchAndDevelopmentExpense',
    'ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost', 'PaymentsToAcquirePropertyPlantAndEquipment', 'PaymentsToAcquireProductiveAssets',
    'PaymentsOfDividends', 'PaymentsOfDividendsCommonStock', 'PaymentsForRepurchaseOfCommonStock', 'ProceedsFromIssuanceOfCommonStock',
    'DepreciationDepletionAndAmortization', 'DepreciationAmortizationAndAccretionNet',
    // 第 2 条新加
    'PropertyPlantAndEquipmentNet', 'GrossProfit', 'OperatingIncomeLoss',
    'PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization',
    'PropertyPlantAndEquipmentGross', 'PropertyPlantAndEquipmentNetIncludingFinanceLease',
    // 第 5 条 F-Score 缺口候补(以后分析用哪个补)
    'LongTermDebt', 'LongTermDebtAndCapitalLeaseObligations', 'LongTermDebtAndCapitalLeaseObligationsCurrent', 'LongTermDebtNoncurrentExcludingCurrentPortion',
    'OtherLongTermDebtNoncurrent', 'SeniorLongTermNotes', 'ConvertibleNotesPayable', 'LongTermNotesPayable', 'OperatingLeaseLiabilityNoncurrent',
    'SalesRevenueGoodsNet', 'SalesRevenueServicesNet', 'RevenuesNetOfInterestExpense', 'InterestAndDividendIncomeOperating', 'RevenueFromContractWithCustomerIncludingAssessedTax',
    'CostOfGoodsSold', 'CostOfServices', 'CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization',
    'CommonStockSharesOutstanding', 'WeightedAverageNumberOfSharesOutstandingBasic', 'EarningsPerShareBasic', 'NetIncomeLossAvailableToCommonStockholdersBasic',
    'IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments',
    'IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic', 'IncomeLossFromContinuingOperations', 'IncomeTaxExpenseBenefit',
    'InterestExpenseDebt', 'InterestPaidNet', 'StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest', 'LiabilitiesAndStockholdersEquity',
    'CommonStockDividendsPerShareDeclared', 'CommonStockDividendsPerShareCashPaid', 'SellingGeneralAndAdministrativeExpense', 'OperatingExpenses',
    'CostsAndExpenses', 'Depreciation', 'DepreciationAndAmortization', 'AmortizationOfIntangibleAssets', 'CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents',
    'Cash', 'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations',
  ],
  'ifrs-full': ['Revenue', 'ProfitLoss', 'ProfitLossAttributableToOwnersOfParent', 'Assets', 'CurrentAssets', 'CurrentLiabilities', 'Liabilities', 'Equity',
    'EquityAttributableToOwnersOfParent', 'PropertyPlantAndEquipment', 'CashFlowsFromUsedInOperatingActivities', 'GrossProfit', 'ProfitLossFromOperatingActivities',
    'DilutedEarningsLossPerShare', 'BasicEarningsLossPerShare', 'CostOfSales', 'ProfitLossBeforeTax', 'FinanceCosts', 'Goodwill',
    'IntangibleAssetsOtherThanGoodwill', 'CashAndCashEquivalents', 'NoncurrentPortionOfNoncurrentBorrowings', 'NoncurrentBorrowings',
    'PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities', 'DividendsPaidClassifiedAsFinancingActivities', 'RetainedEarnings',
    'WeightedAverageShares', 'AdjustedWeightedAverageShares', 'NumberOfSharesOutstanding'],
  'dei': ['EntityCommonStockSharesOutstanding', 'EntityPublicFloat'],
};
window.TAGS = TAGS;
window.CF = window.CF || {}; window.CFERR = window.CFERR || []; window.CFBLOBS = window.CFBLOBS || []; window.CFDONE = false;
window.runCF = async (ciks, workers = 3, flushEvery = 300) => {
  const want = new Set(); for (const [tx, ts] of Object.entries(TAGS)) for (const t of ts) want.add(tx + ':' + t);
  let i = 0, pending = {}, np = 0;
  const flush = async () => {
    const part = pending; pending = {}; np = 0;
    const s = new Blob([JSON.stringify(part)]).stream().pipeThrough(new CompressionStream('gzip'));
    const b = await new Response(s).blob(); window.CFBLOBS.push([Object.keys(part).length, b]);
  };
  const w = async () => {
    while (i < ciks.length) {
      const c = ciks[i++];
      try {
        const r = await fetch('https://data.sec.gov/api/xbrl/companyfacts/CIK' + c.padStart(10, '0') + '.json');
        if (r.status === 404) { pending[c] = { n: null, u: {}, none: 1 }; np++; window.CF[c] = 1; continue; }
        if (r.status === 429 || r.status === 403) { window.CFERR.push([c, r.status]); ciks.push(c); await new Promise(z => setTimeout(z, 5000)); continue; }
        if (!r.ok) { window.CFERR.push([c, r.status]); continue; }
        const j = await r.json(); const u = {};
        for (const [tx, tags] of Object.entries(j.facts || {})) for (const [t, o] of Object.entries(tags)) {
          if (!want.has(tx + ':' + t)) continue;
          for (const [unit, arr] of Object.entries(o.units || {}))
            u[tx + ':' + t + '|' + unit] = arr.map(x => [x.val, x.start || '', x.end, x.fy, x.fp, x.form, x.filed, x.accn, x.frame || '']);
        }
        pending[c] = { n: j.entityName, u }; np++; window.CF[c] = 1;
        if (np >= flushEvery) await flush();
      } catch (e) { window.CFERR.push([c, String(e)]); }
    }
  };
  await Promise.all(Array.from({ length: workers }, w));
  if (np) await flush();
  window.CFDONE = true;
};
