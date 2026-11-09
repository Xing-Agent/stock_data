# 规则定义契约

- 基础：`rule_name` / `goal` / `asset_universe` / `rule_version` / `owner` / `created_at`
- 数据：`sources` / `fields` / `lookback` / `as_of_policy` / `reporting_lag` / `missing_policy`
- 条件：`clauses[]` / `logic_tree` / `thresholds` / `unit` / `comparison_baseline`
- 验证：`positive_case` / `negative_case` / `boundary_case` / `missing_case` / `lookahead_check` / `version_regression`
- 状态：`draft` → `pending_validation` → `validated` → `published`，只在具备真实证据/回执时升级；文本生成只能表示 draft。`validated` 指规则计算与状态判定按指定验证样本可复核，不构成策略盈利承诺。

不得把“可读草稿”视为已保存、“静态格式检查”视为回测、“历史拟合”视为未来确定结果。

### 规则发布门槛
`rule_version` 单调更新且变更摘要可追溯；静态可读不等于通过数值校验；数值校验不等于策略已实盘验证；平台保存回执与平台启用回执必须是两件不同的证据。

历史回看需要 `universe_as_of` / `source_publication_time` / `adjustment` / `delisted_handling`，避免幸存者偏差、未来函数和价格复权混用。
