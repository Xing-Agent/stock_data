# 9 个财务指标 · 带公布日的时点表 · 2026-11-01 · 给回测会话

> **三秒版：第 17、18 轮策略要的 10 个字段整理成了 9 个指标，300 只都取好了，每个数都带公布日。做法和 EBIT / 长期负债那次一样：一个指标试几个字段名，用的是哪个都写清楚。**
> **★ 最要紧的一条：一家公司没有某个指标，大多数情况是它本来就没有这项（不做研发、不发新股、没有短期借款），不是数据缺失。策略里要先定「没有按 0 算还是剔除」。**

位置：`probe/fundamentals_sec_1030/`

| 文件 | 内容 |
|---|---|
| `sec_fin10_pit_1101.csv.gz` | 主表，168,365 行，公布日 2014 年起 |
| `sec_fin10_coverage_1101.csv` | 每个指标的覆盖数 |
| `build_fin10.py` | 生成脚本，读 `sec_companyfacts_fin10_1101.json.gz`（SEC 原始数据，已推） |

## 一 · 9 个指标、字段名按什么顺序取

| 指标 | 字段名（按优先级） | 300 只有数 | 非金融 239 只有数 | 非金融 8 年以上年报都有 |
|---|---|---|---|---|
| ShareIssuanceProceeds 发新股收入 | ProceedsFromIssuanceOfCommonStock → ProceedsFromIssuanceOrSaleOfEquity（含优先股） | 170 | 130 | 66 |
| OptionExerciseProceeds 期权行权收入 | ProceedsFromStockOptionsExercised | 174 | 150 | 100 |
| RnD 研发 | ResearchAndDevelopmentExpense → 两个「不含收购研发」的变体 | 122 | 120 | 111 |
| Advertising 广告 | AdvertisingExpense → MarketingAndAdvertisingExpense（含营销，偏大） | 126 | 111 | 95 |
| InterestExpense 利息支出 | InterestExpense → 3 个变体 | 267 | 212 | 195 |
| AccountsReceivable 应收账款 | AccountsReceivableNetCurrent → ReceivablesNetCurrent（含其他应收） | 229 | 220 | 206 |
| ShortTermDebt 短期借款 | ShortTermBorrowings → 银行短贷 → 商业票据 → DebtCurrent（含一年内到期的长期债，偏大） | 140 | 117 | 81 |
| RetainedEarnings 留存收益 | RetainedEarningsAccumulatedDeficit | 287 | 231 | 228 |
| SharesOutstanding 股本 | 财报封面股本（dei）+ 资产负债表股本 | 279 | 223 | 219 |

- 原单里的 `ProceedsFromIssuanceOfShares` 在 SEC 没有公司用，已经并进「发新股收入」
- 每行的 `source_tag` 写着用的是哪个字段，`note` 写着这个字段偏大或口径有什么不同
- 抽查对得上：QCOM 2023 财年研发 88.18 亿；WMT 2024 财年广告 44 亿；GOOG 2023 年底留存收益 2,112.47 亿

## 二 · 怎么用（和 EBIT 那次一样）
- **`filed` = 公布日，只能用 `filed` 之前的数**。同一期会有多行（原报，加上后面财报里的对比数或重述），取「信号日之前 `filed` 最晚的那条」
- 期间数（研发、广告、利息、两个收入）有 `period_start`，按期间长度区分年度（约 12 个月）和季度（约 3 个月）；时点数（应收、短借、留存、股本）没有 `period_start`
- **用 `period_end` 判断是哪一期**，不要用 `fiscal_year`
- **股本有两种**：
  - 封面股本（`dei:`）的日期是封面日，通常在公布前几周，最适合算「公布时的市值」
  - 资产负债表股本的日期是期末
- `financial_sector = true` 的金融、地产票：应收、短借、利息的含义不一样，按策略需要排除

## 三 · ★ 没有 ≠ 缺数据
| 指标 | 没有通常是因为 | 建议 |
|---|---|---|
| 研发 | 公司不做研发（零售、公用事业、银行） | 按 0 |
| 发新股收入 / 期权行权收入 | 那年没发新股、没人行权 | 按 0 |
| 短期借款 | 没有短期借款 | 按 0 |
| 广告 | 很多公司不单独披露 | **按缺失**，不要填 0 |
| 应收、利息、留存、股本 | 大公司基本都有；没有多半是金融类或者字段名特殊 | 按缺失 |

## 四 · 范围
- 只取了老池 300 只（FRC、MTR、OCSI 不在 SEC）
- 考卷那几千只要用的话，按同一个脚本再取一次。只取财务，不碰行情和收益，不算偷看考卷
