# 输入和结果字段

| 字段 | 说明 | 缺失处理 |
|---|---|---|
| symbol / exchange | 唯一标的及交易市场 | 先消歧 |
| as_of / timezone | 行情有效时间及所在时区 | 不认定为实时 |
| session | 盘中、正式收盘或盘前盘后 | 不称当日收盘 |
| currency | 报价币种 | 不与其他币种直接比较 |
| price / previous_close | 当前有效价及其对应上一有效常规交易日正式收盘价，可跨日期但须有明确对应基准 | 不计算涨跌幅 |
| ohlcv_window | 同周期 K 线与成交量序列 | 不判断突破/量能 |
| adjustment | 前复权、后复权或不复权 | 不跨口径比较 |
| source | 原始来源或用户提供资料 | 披露来源限制 |

字段标签：`verified` / `computed` / `inferred` / `unknown`。所有计算值可追溯到已验证输入。

### 计算前检查
- `price > 0`、`previous_close > 0`、`same_symbol=true`、`same_currency=true`、`same_adjustment=true`、`corresponding_prior_session=true`，且两者时点与交易阶段明确，方可计算简单涨跌幅。
- N 日高点：取**此前 N 个完整交易日**的 OHLCV，按明确 `high` 字段求最大值，盘中报价 `>` 该最大值只能称“盘中突破”；若需“收盘确认”，须用已完成当日收盘价比较，并声明严格 `>` 或包含相等 `>=`。
- 样本不足 N 个交易日时输出“无法判定”，不降低 N 以凑结果；同一标的名称对应多个代码时不得猜测。
