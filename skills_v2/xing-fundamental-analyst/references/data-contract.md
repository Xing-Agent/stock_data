# 双数据面、PIT、缺失与字段契约

## A. 两条数据线

- **CURRENT_DISPLAY**：只用于当前产品展示和当前研究；V1 预期工具 `collect_fundamental_snapshot`, `get_valuation_metrics`, `get_consensus_estimates`, `get_market_data`, `get_warm_document_index`, `retrieve_warm_evidence` 等，需先确认注册可用。返回当前值不能填入历史 PIT。
- **HISTORICAL_PIT**：V2 回测库中的历史财务与行情，必须记录 `published_at`, `available_at`, `retrieved_at`, `period_end`, 原始来源、重述/股本版本。只按 `as_of` 当时**实际可用**的数据回放。
- 即使同一公司 ROIC 两边都存在，定义/会计期间/时间不一致也不能把两个值当成同一次研究的两个独立证据；当前显示采用当前来源，回测采用 PIT；冲突进入工程差异审计。

## B. 时点字段

| 字段 | 含义 | 必须性 |
|---|---|---|
| `period_end` | 财报会计期间结束 | 财务报表必须 |
| `published_at` | 公开披露最早准确时间 | 财务/公告必须 |
| `available_at` | **本数据和算子首次实际可使用的时点** | 需要 PIT、事件检验时必须 |
| `retrieved_at` | 本次真实读取时间 | 任何当前数据必须 |
| `quote_as_of` | 估值使用行情截止点 | 当前估值必须 |
| `first_reaction_session` | 盘前/盘后公布后首个市场能反应的交易时段 | 财报事件研究时必须 |
| `as_of` | 本研究知识截止时点 | 所有研究必须 |

## C. 盘前/盘后：事件日 vs 当前估值

- 盘前公布：通常当天交易时段可以反应；盘后公布：通常下一交易时段反应。遇节假日、停牌、跨时区和盘中发布，必须按实际交易所日历/时区判断。**不能仅靠自然日 +1**。
- 事件反应分析使用 `first_reaction_session` 的相关行情，不强行设定为投资者当时能在那个收盘价成交。事件窗口统计可用收盘价不等于可执行交易成本。
- 当前估值总是使用当前问题的有效 `quote_as_of`，不能沿用财报首反应日的旧报价。
- 历史回测要再区分信号产生时间与实际下单可执行时点。披露后当日收盘才计算的信号，不可声称当日收盘前已知并能成交。

## D. 会计纪律

- A 股累计 Q1/Q2/Q3/Q4 与美国独立季度区别对待，不能混用。A 股 Q2=H1−Q1；Q3=9M−H1；Q4=FY−9M。重述需用对应已公开的版本。
- TTM 流量合计四个独立季度，资产负债表等存量取时点值。并购、拆分、币种、科目映射、税率、复权和总股本变动要标可比性。
- 基期为零或负数时的“增长率”默认不输出；使用绝对变化和“扭亏/转亏”等状态，不换成看似精确的增长百分比。

## E. 不确定性和缺失字段

运行时字段可用性：`VERIFIED`, `PARTIAL`, `MISSING`, `UNCHECKED`, `DISABLED_BY_POLICY`, `CONFLICT`。只有 `VERIFIED` 的字段进入确定性计算（多字段部分覆盖可单独以 PARTIAL 显示原始事实）。

老板 2026-11-02 的核查发现属于**历史调查快照**：ROIC 派生算子约 42.8% 覆盖，广告费样本中 126/300，曾核不到 `OperatingIncomeLoss`、`AssetImpairmentCharges`、`RestructuringCharges`、`NonoperatingIncomeExpense`、`IncomeTaxExpenseBenefit`、`AccountsPayableCurrent`、`PaymentsToAcquireBusinessesNetOfCashAcquired`、`ContractWithCustomerLiabilityCurrent`。这八个不能当作永远不存在；必须通过本次 `check_available_fields` 查询，查证不通过时不得运算相关公式，不用近似字段偷换。

`MISSING ≠ 0`、`未披露 ≠ 0`、`不存在于旧导出 ≠ 未在公司公开披露`、`数据库里没接入 ≠ 世界上没有数据`。

## F. 数据记录最低格式

每一条证据至少 `{id,source_id,label,field,value,unit,period_end,published_at,available_at,retrieved_at,definition,data_mode}`；未适用字段明确 null 和 `not_applicable_reason`。比较/计算都依赖证据 ID。未核验的用户材料 `USER_PROVIDED`，不得升级为已验证 FACT。
