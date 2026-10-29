# 14 个 ETF 基准日线交付

需求：《给技术-1029第二版.md》第一项。全部 14 个 ETF 均读取本目录 `<SYMBOL>/daily.json`。均使用 `data` 数组，字段统一为 `date, open, high, low, close, adj_close, volume`。

本次 14 个 ETF 共 40,684 条日线，全部字段有值。请求区间为 2014-01-01 至 2025-12-31，沿用冻结股票样本的下载区间，为 2016 起的分析保留预热历史。

| 代码 | 实际首日 | 实际末日 | 根数 |
|---|---|---|---:|
| SPY、QQQ、IWM、XLK、XLF、XLE、XLV、XLI、XLY、XLP、XLU、XLB | 2014-01-02 | 2025-12-31 | 各 3,018 |
| XLRE | 2015-10-08 | 2025-12-31 | 2,573 |
| XLC | 2018-06-19 | 2025-12-31 | 1,895 |

XLRE、XLC 的首日以前本次来源没有返回数据，未补零或填充。其余代码覆盖 2014 起区间。观测范围内按现有 XNYS 日历核验，没有缺失、额外或重复交易日。

## 字段口径

- `open/high/low/close`：Alpha Vantage `TIME_SERIES_DAILY_ADJUSTED` 返回的原始 OHLC；`volume` 为原始成交量整数，未按复权因子修改。
- `adj_close`：供应商同一响应的 `5. adjusted close`，包含其拆股和现金分红调整。原值导出，未按本地股息支付日记录重新计算。原有 `adjusted_close` 与公司行动字段继续保留，新增的有效复权字段为 `adj_close`。
- 复权基准是 2026-10-29 获取的供应商快照，并未重新锚定到 2025-12-31。后续公司行动及供应商历史修订可能影响该快照的历史复权价格，因此不是严格历史修订 PIT 数据。`adj_close` 不能和原始 OHLC 当作同一价格口径混合计算；复权收益率应比较同一快照中的复权收盘价。
- 旧交付中的 `adjusted_close: null` 不构成有效复权价。本交付使用需求指定的 `adj_close` 字段，旧文件保留。

## 核验与溯源

`manifest.json` 记录代码、文件、实际首末日、条数、日历覆盖和 SHA-256。`sources/<SYMBOL>.json` 保存本次返回的区间内供应商原始行、元数据、无密钥来源地址及获取时间，可逐值核对 `adj_close`。`adj_close_audit.json` 统一记录全部 14 个 ETF 的独立字段/数值检查和旧交付比较。

13 个已有 ETF 与旧交付逐日比较，12 个 OHLCV 完全一致。SPY 仅 2015-03-06 的 open/high 与旧快照不同：旧值均为 210.46，本次为 209.42/209.94；low/close/volume 一致。原因尚未确定，按来源快照差异记录，未覆盖旧交付。QQQ 为新增交付。

## 复用导出脚本

脚本：`scripts/export_etf_benchmarks.py`。复用 optimize 后端的 Alpha Vantage 适配器及美股交易日历；在可导入后端模块、已配置 `ALPHA_VANTAGE_API_KEY` 的 Python 环境运行：

```bash
python /path/to/stock_data/scripts/export_etf_benchmarks.py --output /path/to/new_delivery
```

默认区间同本交付，可用 `--start`、`--end` 指定。已保存的来源快照会用于断点续跑；需要刷新供应商数据时使用新的输出目录。凭据不会保存到交付文件中。
