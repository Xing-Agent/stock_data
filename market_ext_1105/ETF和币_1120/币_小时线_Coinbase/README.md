# BTC、ETH 1 小时线 · Coinbase · 数据组 · 2026-11-21(回手册 345)

> **三秒版：两个币都取到了，2017-01-01 00:00 到 2026-11-21 07:00（UTC），一周 7 天，一共 8.7 万根。**
> - BTC 缺 53 个小时，ETH 缺 38 个小时，占不到万分之七。最长一段是 BTC 2018-08-10 01:00–15:00 缺 15 小时，其余每段都不超过 5 小时，是 Coinbase 停机或那小时没成交。
> - 每天的最高价和仓库里的 Coinbase 日线（`market_tech_exam_1118/`）逐天对过：3,608 天，**一天不差**。

## 文件
- `2017.parquet` … `2026.parquet`：每年一个，两个币合在一起。
- `说明_每个币.csv`：起止、根数、缺几小时。
- `缺的小时.csv`：每一段缺的从哪到哪。

## 列（和 ETF 小时线一样）
| 列 | 说明 |
|---|---|
| `symbol` | BTC / ETH |
| `time_utc` | 这根开始的时间，UTC |
| `session` | 一律 `all` |
| `open high low close volume` | 原价；成交量单位是币的个数 |
| `*_adj` | 和原价一样（币没有拆股） |
| `adj_factor` | 1 |
| `trades` | 空，Coinbase 不给成交笔数 |
| `minutes` | 60 |
| `source_ticker` | BTC-USD / ETH-USD |

**缺的小时没有补**：没有那一根，不填前值。今天这根还没走完，所以不放。

脚本 `probe/ETF和币_1120/build_345.py`，原始数据 `raw_345_币1小时线_Coinbase_1121.json.gz`。来源是 Coinbase 公开行情接口。
