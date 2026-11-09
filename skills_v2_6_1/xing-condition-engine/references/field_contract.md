# 条件表达与状态约定

**字段类型**
- `subject`: 股票代码、指数或明确业务实体
- `metric`: 可验证字段或有确定性公式的指标
- `operator`: 标准 `>`, `>=`, `<`, `<=`, `==`, `!=`, `between`, `cross_above`, `cross_below`；输入 `=` 若表示相等须规范化为 `==`。交叉运算须有至少前一期与当前一期**已完成**、连续有效数据（盘中触发需明示）
- `value`: 阈值与单位；`timeframe` / `window`: 数据频率与观察窗口
- `as_of`: 结果的真实有效时间；`source`: 证据来源
- `rule_version`: 规则版本；`input_snapshot`: 输入快照标识
- `evaluation_status`: computed / not_evaluated / blocked / error

**规则示例（仅作语义定义）**
“最近五个完整财年毛利率波动不大”不是完整规则，必须先定义波动口径（例如最大值减最小值的百分点）、阈值、是否完整五个财年、财年口径，以及特殊缺报处理。

**三值合取/析取**
- TRUE AND UNKNOWN = UNKNOWN；FALSE AND UNKNOWN = FALSE
- TRUE OR UNKNOWN = TRUE；FALSE OR UNKNOWN = UNKNOWN
- INVALID 需报规则定义错误，不继续装作有结果

**需要修正的常见问题**：数据单位混淆、采用盘中未完成 K 线判突破、区间端点不清、财报发布前后混用、未来函数、全市场股票池事后成分替代历史成分。

## 计算决策表（合法规则内）
| A | B | AND | OR |
|---|---|---|---|
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | UNKNOWN | UNKNOWN | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | UNKNOWN | FALSE | UNKNOWN |
| UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

`NOT(TRUE)=FALSE`、`NOT(FALSE)=TRUE`、`NOT(UNKNOWN)=UNKNOWN`。上述各行对 A/B 交换位置后结果不变。**任何 INVALID 子句优先导致整体规则 INVALID，不能用短路掩盖规则错误。**

## 数据与执行分层
- 规则状态：`valid` / `invalid` / `needs_clarification`。
- 执行状态：`computed` / `not_evaluated` / `blocked` / `error`；只有 `computed` 有已执行真值。
- 真值：`TRUE` / `FALSE` / `UNKNOWN`；`INVALID` 作为规则校验结果，展示时可沿用总体状态 `INVALID`。
- 快照：`rule_id`、`rule_version`、`input_snapshot`、`data_as_of`、`evaluated_at`、`source`、`fields_used`。不可用 `evaluated_at` 冒充 `data_as_of`。

`cross_below`：`left[t-1] >= right[t-1]` 且 `left[t] < right[t]`。`cross_above`：`left[t-1] <= right[t-1]` 且 `left[t] > right[t]`。`right[t]` 若为动态阈值或均线，必须依时点匹配，不得共用一个当期阈值。

`needs_clarification` 是规则描述尚不完整，不能当作可执行规则；`blocked/not_evaluated` 状态没有真值；合法表达式实际评估但字段缺失才返回 `UNKNOWN`。
