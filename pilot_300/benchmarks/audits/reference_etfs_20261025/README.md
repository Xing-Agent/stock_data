# RSP 与 11 个板块 ETF 日线

下载区间沿用已有参考数据：2014-01-01 至 2025-12-31。仅日线，原始未复权 OHLCV；每个代码位于 `代码/daily.json`。

代码：RSP、XLB、XLC、XLE、XLF、XLI、XLK、XLP、XLRE、XLU、XLV、XLY。

XLC 返回数据从 2018-06-19 开始，XLRE 从 2015-10-08 开始；这些日期以前未返回数据，不补零、不向前填充。其余代码均从 2014-01-02 开始，终点均为 2025-12-31。

`manifest.json` 保存来源文件、实际区间、根数、状态和 SHA-256；`audit.json` 使用已有美股交易日历核对日期、OHLCV、重复记录及独立公司行动。

独立公司行动存在未解决缺口：XLP、XLRE、XLU、XLV 的分红核对为 unavailable。原始日线与这些分红记录分别保留，不将本次交付视为已完整核验的复权／总回报序列。具体原因和日期见 audit.json。

来源为现有 XING 鉴权行情接口及其配置的供应商，保留接口原始来源和缓存信息。行情历史没有供应商修订版本，本次交付不额外承诺严格 PIT 行情。


## 2026-10-29 原文件更新

11 个行业 ETF 的原 `daily.json` 已增加有效 `adj_close`，原始 OHLCV、公司行动记录保持原有结构。`sources/<SYMBOL>.json` 保存供应商来源快照；manifest 和 audit 的文件校验值已同步更新，新增复权价核验见 `adj_close_audit.json`。RSP 不属于本轮 14 ETF 更新范围，未修改。

SPY、QQQ、IWM 在 `../pilot_300/benchmarks/`，完整口径见该目录 `README_ETF.md`。供应商复权价按当前快照提供，不是严格 PIT，也不表示此前独立股息支付日核对缺口已解决。
