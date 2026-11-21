# -*- coding: utf-8 -*-
"""个股:过去二十年日线转跌之后怎么走的。成交最活跃的 200 只。只读面板(内存里按全池并股表折算过的),不碰引擎代码。"""
import os, io, sys, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = importlib.util.spec_from_file_location("env", os.path.join(ROOT, "probe/两段时间_1120/环境2004_1120.py")); E = importlib.util.module_from_spec(sp); sp.loader.exec_module(E)
info = E.install(只留测试期=False)
from engine import cache
P = cache._PANEL; drop = set(info["拿掉"])
P1 = os.path.join(HERE, "减仓五种并排_1121.py")
B = {"__file__": P1}; exec(compile(io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n"), "b", "exec"), B)
ind, 事件 = B["ind"], B["事件"]
c = P["close"]; dv = (P["close"] * P["volume"]).loc["2025-07-01":"2025-12-31"].mean()
alive = c.loc["2025-12-01":"2025-12-31"].notna().sum() >= 15
cand = dv[alive & ~dv.index.isin(drop)].sort_values(ascending=False).head(200).index.tolist()
rows = []; allf = []
for s in cand:
    x = pd.DataFrame({"o": P["open"][s], "h": P["high"][s], "l": P["low"][s], "c": P["close"][s], "v": P["volume"][s]}).dropna().astype(float)
    if len(x) < 600: continue
    top, bot = x[["o", "c"]].max(axis=1), x[["o", "c"]].min(axis=1)
    bh, bl = x.h > top * 1.5, x.l < bot * 0.5
    x.loc[bh, "h"] = top[bh]; x.loc[bl, "l"] = bot[bl]
    jump = (x.c / x.c.shift(1) - 1).abs() > 0.6            # 一天涨跌超 60% 的,多半是没折干净的拆股:这只票不出
    if jump.loc["2005-01-01":].any(): continue
    x["div"] = 0.0; x = ind(x)
    ev = [t for t in 事件(x) if "2005-01-01" <= str(x.index[t])[:10] <= "2025-12-31"]
    if len(ev) < 8: continue
    f60 = np.array([x.c.iloc[t + 60] / x.c.iloc[t] - 1 for t in ev]); f20 = np.array([x.c.iloc[t + 20] / x.c.iloc[t] - 1 for t in ev])
    dd = np.array([x.l.iloc[t + 1:t + 61].min() / x.c.iloc[t] - 1 for t in ev])
    yrs = np.array([x.index[t].year for t in ev]); by = pd.Series(f60, index=yrs).groupby(level=0).mean().sort_values().head(3)
    rows.append((s, str(x.index[ev[0]])[:4], len(ev), 100 * (f20 > 0).mean(), 100 * (f60 > 0).mean(), 100 * np.median(f60), 100 * (dd < -0.20).mean(), 100 * dd.min(),
                 "、".join(f"{y}（{100*v:.0f}%）" for y, v in by.items() if v < 0)))
    allf.append(pd.DataFrame({"票": s, "年": yrs, "f60": f60, "dd": dd}))
A = pd.concat(allf)
A.to_csv(os.path.join(HERE, "个股转跌_逐事件.csv"), index=False)
tot = {"只数": len(rows), "次数": len(A), "60天后涨回来pct": round(100 * (A.f60 > 0).mean(), 1), "60天后中位pct": round(100 * A.f60.median(), 1),
       "60天后跌超10pct的占比": round(100 * (A.f60 < -0.10).mean(), 1), "中途跌超20pct的占比": round(100 * (A.dd < -0.20).mean(), 1),
       "最差一成平均pct": round(100 * A.f60[A.f60 <= A.f60.quantile(0.1)].mean(), 1)}
print(tot); print(A.groupby("年").f60.agg(["count", "mean"]).round(3).T.to_string())
L = ["", "## 个股：成交最活跃的 %d 只（2026-11-21 算，数据 2005–2025）" % len(rows), "",
     "> 「转跌」的定义和上面 ETF 那张表一样。个股波动大，「中途跌超」这一列的门槛换成 20%。",
     "> 🔴 **这张表只有现在还在交易、而且成交很活跃的票**，也就是活下来并且长大了的那批，历史看上去会比真实情况好。退市的、跌没了的不在里面。讲个股历史时这句要说。",
     "> 合起来看：%d 只票一共转跌 %d 次，60 天后涨回来的占 %.0f%%，60 天后比转跌那天低 10%% 以上的占 %.0f%%，中途跌超 20%% 的占 %.0f%%；最差的一成平均是 %.0f%%。" % (
         tot["只数"], tot["次数"], tot["60天后涨回来pct"], tot["60天后跌超10pct的占比"], tot["中途跌超20pct的占比"], tot["最差一成平均pct"]), "",
     "| 代码 | 从哪年算起 | 转跌过几次 | 20 天后涨回来 | 60 天后涨回来 | 60 天后涨跌（中间那一次） | 中途跌超 20% | 中途最深跌过 | 转跌后最难看的年份（60 天平均） |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
for r in sorted(rows):
    L.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.0f}% | {r[4]:.0f}% | {r[5]:+.1f}% | {r[6]:.0f}% | {r[7]:.0f}% | {r[8] or '—'} |")
io.open(os.path.join(HERE, "个股历史表_片段.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print(len(rows), "只;片段", sum(len(z) for z in L), "字")
for r in sorted(rows):
    if r[0] in ("NVDA", "TSLA", "AAPL", "META", "INTC", "AMD", "MSFT", "COIN", "PLTR", "AMZN", "GOOG"): print(r)
