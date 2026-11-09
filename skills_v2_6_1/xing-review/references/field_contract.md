# 持仓复检字段

最小输入：`symbol`、`exchange`、`user_question`。用户持仓细节需明示获得：`quantity`、`cost_basis`、`entry_date`、`weight`、`original_thesis`、`investment_horizon`、`risk_limit`。

证据项须含：`claim`、`source`、`period/as_of`、`status`（支持 / 削弱 / 证伪 / 未知）、`counter_evidence`。

触发条件须写明：`observable_event`、`threshold_if_any`、`verification_source`、`implication`；不得将触发条件自动变成未经授权交易动作。

若复核历史 Agent：需要 `instance_id`、`rule_version`、`run_time`、`run_status`、`actual_result`；缺失不生成绩效结论。

### 盈亏与风险边界
- `unrealized_pnl` 需实际持仓数量、有效成本、**有效估值价格及对应交易时点**，并核对费用/汇率/拆分/分红/税务是否计入；缺任一值不输出精确数额。
- “亏损 20%”来自用户描述时标注 `user_reported`，不将其写成行情核验结果。
- 反证项需包含 `verification_source`、`as_of`、`confidence`、`alternative_explanation`，不得默认技术形态可证明长期价值。
