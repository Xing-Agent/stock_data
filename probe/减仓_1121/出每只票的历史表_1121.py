# -*- coding: utf-8 -*-
"""每只 ETF:过去二十年日线转跌之后怎么走的。给技术面大师卡当参考表。只读日线,不碰引擎。"""
import os, io, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
P1 = os.path.join(HERE, "减仓五种并排_1121.py")
B = {"__file__": P1}; exec(compile(io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n"), "b", "exec"), B)
load, ind, 事件 = B["load"], B["ind"], B["事件"]
名 = {"SPY": "标普 500", "QQQ": "纳指 100", "IWM": "罗素 2000 小盘", "DIA": "道指", "XLK": "科技", "SMH": "半导体", "XLF": "金融", "KRE": "地区银行",
      "XLE": "能源", "XLV": "医疗", "XLI": "工业", "XLY": "可选消费", "XLP": "必需消费", "XLU": "公用事业", "XLB": "材料", "XLRE": "房地产", "XLC": "通信",
      "TQQQ": "三倍做多纳指", "SOXL": "三倍做多半导体"}
rows = []
for s, cn in 名.items():
    x = ind(load(s)); ev = [t for t in 事件(x) if "2005-01-01" <= str(x.index[t])[:10] <= "2025-12-31"]
    if not ev: continue
    f60 = np.array([x.c.iloc[t + 60] / x.c.iloc[t] - 1 for t in ev]); f20 = np.array([x.c.iloc[t + 20] / x.c.iloc[t] - 1 for t in ev])
    dd = np.array([x.l.iloc[t + 1:t + 61].min() / x.c.iloc[t] - 1 for t in ev])
    yrs = pd.Series([x.index[t].year for t in ev]); bad = pd.Series(f60, index=yrs.values)
    worst_y = bad.groupby(level=0).mean().sort_values().head(3)
    rows.append((s, cn, str(x.index[ev[0]])[:4], len(ev), 100 * (f20 > 0).mean(), 100 * (f60 > 0).mean(), 100 * np.median(f60),
                 100 * (dd < -0.10).mean(), 100 * dd.min(), "、".join(f"{y}（{100*v:.0f}%）" for y, v in worst_y.items() if v < 0)))
L = ["# 日线转跌之后，过去二十年是怎么走的（每只 ETF 一行）", "",
     "> 给技术面大师卡「行情在跌时」那一节用。2026-11-21 算的，数据到 2025 年底。",
     "> **转跌** = 前一天还在 20 日线和 50 日线上方，当天收盘放量跌破 20 日线（超过 0.3 倍日均波幅），或收盘跌破前 10 天最低点。同一只票 20 个交易日内只算一次。",
     "> **怎么读**：「60 天后涨回来」= 转跌那天收盘之后 60 个交易日，收盘价高于转跌那天的次数占比。「中途跌超 10%」= 这 60 天里最低曾经比转跌那天收盘低 10% 以上的次数占比。",
     "> 🔴 这是历史上发生过的情况，**不代表这一次**。2005–2025 美股整体是上涨的，所以多数转跌之后是涨回来的；转跌之后没涨回来的年份集中在 2008、2022 这种跌得久的年份。", "",
     "| 代码 | 是什么 | 从哪年算起 | 转跌过几次 | 20 天后涨回来 | 60 天后涨回来 | 60 天后涨跌（中间那一次） | 中途跌超 10% | 中途最深跌过 | 转跌后最难看的年份（60 天平均） |",
     "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
for r in rows:
    L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]:.0f}% | {r[5]:.0f}% | {r[6]:+.1f}% | {r[7]:.0f}% | {r[8]:.0f}% | {r[9] or '—'} |")
L += ["", "**用法**", "- 用户问的票在表里 → 把那一行的数讲给他：转跌过几次、多少次涨回来、最深跌过多少、哪几年最难看。",
      "- 不在表里（个股、别的 ETF）→ 直说「这只票我们没有扫过转跌之后的历史」，可以讲它对应的指数或行业 ETF 那一行，并说明是拿它当参照。🔴 不许编一个数。",
      "- 讲完历史，必须接两句：「过去不代表这一次」「最后还是看这一次盘面走得强还是弱」。", ""]
out = os.path.join(ROOT, "skills_v2/xing-ta-master/references/after_daily_breakdown_history.md")
io.open(out, "w", encoding="utf-8").write("\n".join(L)); print("\n".join(L[7:]))
