# 筛选数据契约

输入字段：`universe_id`、`universe_as_of`、`exchange`、`symbol[]`、`rules[]`、`logic`、`market_as_of`、`financial_period`、`data_source`。

单规则结构：`metric`、`operator`、`threshold`、`unit`、`lookback`、`adjustment`、`missing_policy`、`rule_version`。

结果含义：`match` 已满足、`no_match` 已确认不满足、`unknown` 缺数据或时点不齐、`invalid` 规则无法执行。不得将 unknown 记为 no_match。

汇总字段：`universe_count`、`excluded_count`、`eligible_count`、`matched_count`、`not_matched_count`、`unknown_count`、`unprocessed_count`、`processed_count`、`evaluable_count`。只有取得真实股票池和判定结果才能填写。必须满足：
- `universe_count = excluded_count + eligible_count`
- `eligible_count = processed_count + unprocessed_count`
- `processed_count = matched_count + not_matched_count + unknown_count`
- `evaluable_count = matched_count + not_matched_count`
整体规则 `INVALID` 时先返回规则错误，不把它计入未命中或未知，不生成统计假象。只有当 `unprocessed_count = 0` 且股票池与批次数据对应时，才可声称完整筛选；部分处理时只展示真实已处理和未处理数。

覆盖披露：股票池来源、构成时间、剔除范围、价格与财务指标的最新时点、是否存在幸存者偏差。

唯一标识：`security_key = (exchange, canonical_symbol)`；不同证券市场或不同股种不按名称合并。`excluded_count` 是依据已定义母体规则明确排除的证券，不包含仅因数据缺失而无法判断的证券。
