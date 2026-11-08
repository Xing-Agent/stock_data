# 确定性计算与条件估值

所有公式都是**算子规格**，不是让模型在自然语言里自行口算。仅当字段、口径、日期均验证后才调用；每条计算必须带 `calculation_version`、`input_evidence_ids`、舍入、失败码。

| 指标 | 参考公式 | 例外 |
|---|---|---|
| 收入同比 | 当期收入/去年同季收入 - 1 | 基期 ≤0 / 不可比：停止百分比 |
| 毛利率 | (Revenue - CostOfRevenue)/Revenue | 收入为 0 停止，字段定义核对 |
| ROIC | NOPAT / AverageInvestedCapital | 投入资本 ≤0 或范围不稳：停止 |
| ROE | NetIncome attributable to equity / avg attributable equity | 杠杆和股权变更需说明 |
| 现金转换率 | CFO/NetIncome | 利润 ≤0 或现金/利润口径不一致暂停比率 |
| FCF | CFO - cash CapEx | 不推定 CapEx 全是维护性支出 |
| EV | market_cap + debt + preferred + minority - cash - nonoperating_adjustments | 少数股东/优先/非经营资产不可直接忽略 |
| PE | price/EPS | EPS ≤0 不适用；明确 TTM/forward 口径 |
| TTM | 4 个独立季度流量相加 | 存量不允许相加 |
| 反向增速 | 解 `ModelValue(g, margin, reinvestment, discount, horizon, terminal)=ObservedEV` | 缺参数或未运行求根算子，不输出具体 g |

## 估值纪律

1. 同一批正盈利公司用**同一个正数折现率**计算某个纯分子/分母模型时，比较**那个模型值**的排序不变。这不等于不同公司 WACC 相同，更不等于真实 DCF 都可删去。
2. 老板 2026-11-03 已明确默认停用“零增长下公允价值”及绝对目标价。**此禁令不因本参考文档解释数学局限就自动解除**。
3. 在 CORE 中：只可输出已验证的倍数、历史可比区间和**定性/条件性**的兑现要求；任何明确“现价隐含未来年增速 X%”需要经过参数验证的反向求解算子。
4. 如启用 `RESEARCH_PLUS`（必须有产品、策略、合规批准且共用边界同步更新）：三情景的增长率、利润率、资本开支、折现率、终值等都以 `ASSUMPTION` 注记，给来源/区间/敏感性；场景不是预测命中概率，更不是无条件目标价。
5. 未来量化区间若缺足够来源或模型算子未通过测试，输出“关键变量与必要条件”，**不要按字面漂亮地补几个数**。

## 方法适配

- 银行：P/B、ROE、净息差、不良和资本充足，不套工业 FCF/净债务；
- 保险：新业务价值/赔付/准备金/偿付能力；
- 券商：资本、ROE、周期性收入；
- REIT：NOI/FFO/AFFO/LTV（不存在数据就暂不估值）；
- SaaS：ARR/NRR/单位经济模型/股权激励/现金消耗，不能单靠库存周转；
- 医药临床：现金跑道、阶段概率研究须有可信公开来源，不对未上市产品强用 PE；
- 周期：正常化盈利不可机械用历史中位数代表未来必回归。
