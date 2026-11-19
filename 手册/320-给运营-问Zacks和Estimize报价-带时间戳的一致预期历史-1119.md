# 320 · 给运营：去问 Zacks 和 Estimize 两家报价（2026-11-19）

**一句话：Intrinio 那两个接口不买了。请去问 Zacks 和 Estimize，我们要的是「带日期的每日一致预期历史」，最好能一次性买断。**

## 背景（大白话）

我们要回测「分析师预期上调 / 下调之后股价怎么走」。这需要知道**每一天**市场的一致预期是多少。
Intrinio 回信确认了：它的数据只告诉你财报是哪天公布的，不告诉你预期是哪天的。没有这个日期，回测会用到当时还不知道的数，结果是假的。买多少年历史都补不上，所以不买。
Intrinio 的数据源头就是 Zacks，Zacks 自己卖的版本里有这个日期。

## 要干啥

给下面两家各发一封询价邮件，用后面的模板。Lin 说了想试试**一口气买断历史**，所以两种报价都要问。

| 先后 | 找谁 | 联系方式 |
|---|---|---|
| 1（主要） | Zacks 专业服务（Zacks Professional Services） | 官网页面写的联系人：Evangeline King，eking@zacks.com，电话 800-767-3771 转 9485 |
| 2（备选） | Estimize 机构数据销售 | 官网 estimize.com/sales 的询价入口 |

## 每家都要问清的六件事

1. **有没有每天的一致预期快照**：每条记录带「观察日期」，也就是这个预期是哪一天的。这是必须项，没有就不用往下谈。
2. **历史从哪年开始**：我们至少要 2004 年到现在，季度和年度的每股收益（EPS）都要。
3. **覆盖多少只美股**，退市的公司在不在里面（我们需要包含已退市的）。
4. **字段**：均值、最高、最低、给预期的分析师人数、上调和下调的家数。营收预期有没有。
5. **价格，两种都报**：① 历史数据一次性买断多少钱；② 之后每天更新的订阅每月多少钱。两样能不能分开买。
6. **使用范围**：内部研究和回测可以吗；以后把算出来的结论（不是原始数据）展示给我们的用户可以吗，要不要另外的授权。

再顺手问一句：能不能先给几只票（比如 AAPL、NVDA、一只已退市的）的样例文件，我们核对格式。

## 邮件模板（英文，直接用，方括号里的自己填）

**Subject:** Pricing inquiry – daily consensus EPS estimate history (point-in-time)

Hi [Name],

We are XING, a fintech research platform. We are looking for **point-in-time daily consensus EPS estimates** for US equities, for internal research and backtesting.

Could you let us know:

1. Do you provide daily consensus snapshots where each record carries the observation date (the date the consensus was valid as of)?
2. How far back does the history go for quarterly and annual EPS? We need 2004 to present.
3. How many US stocks are covered, and are delisted companies included?
4. Which fields are included (mean, high, low, number of analysts, up/down revisions)? Are revenue estimates available as well?
5. Pricing for (a) a one-time purchase of the full history file, and (b) an ongoing daily update subscription. Can these be bought separately?
6. Licensing: is internal research and backtesting covered? Would displaying derived results (not raw data) to our end users need a separate license?

A small sample file (e.g. AAPL, NVDA and one delisted name) would help us verify the format.

Thank you,
[Your name]
[Title], XING

## 收到回信后

- 把两家的回信原文转给 Lin，不用自己总结。
- 第 1 条答「没有」的那家直接放弃。
- **不要当场答应购买或试用条款**，价格和授权由 Lin 定。

## 先别做的

- Intrinio 那边不用再追，礼貌回一句「这两个接口缺我们必须的字段，暂时不买，谢谢」即可。
- 不要把我们的回测结果、策略内容发给对方。
