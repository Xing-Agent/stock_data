#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基本面的主对标：基本面策略能买的那堆票（研发池内 large_mid 口径），全买下不动（2026-11-19）

大白话：和技术面的「同池子全买不动」同一个做法 —— 每季度第一天把当时在范围里的票等权买一遍，季内不动，下季再等权。
含分红、不扣交易成本（对标略偏高，是对我们不利的方向）。面板先按数据组的全池并股表折算，并拿掉同样那 44 只票，和策略那侧一致。
"""
import io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106")); sys.path.insert(0, HERE)
import numpy as np, pandas as pd
import 跑基本面_1106 as B
RC, _ = B.装层()
import 补分红_1107 as DIV; DIV.install()
import 按表折算_1118 as FIX; rep = FIX.install()
from engine import cache, data
hold = json.load(io.open(B.HOLD, encoding="utf-8"))
drop = set(FIX.要拿掉的票())
dev = [s for s in hold["研发池名单"] if s in cache._PANEL["close"].columns and s not in drop]
close = cache._PANEL["close"][dev].astype(float); idx = close.index
mask, diag = RC.scope_mask(dev, idx, B.SCOPE)
mask = pd.DataFrame(mask, index=idx, columns=dev)
divs = {}
for s in dev:
    d = data.dividends(s)
    if len(d): divs[s] = d[~d.index.duplicated()].reindex(idx).fillna(0.0)
dv = pd.DataFrame(divs, index=idx).reindex(columns=dev).fillna(0.0)
prev = close.shift(1)
tr = ((close - prev + dv) / prev).replace([np.inf, -np.inf], np.nan).where(close.notna(), 0.0).fillna(0.0)
perf = idx[(idx >= pd.Timestamp(data.PERF_START)) & (idx <= pd.Timestamp(data.PERF_END))]
q = pd.Series(perf.quarter, index=perf)
调 = [perf[0]] + [d for d, a, b in zip(perf[1:], q.values[1:], q.values[:-1]) if a != b]
eq = pd.Series(np.nan, index=perf); v = 1.0; 只数 = []
for k, d in enumerate(调):
    i = idx.get_loc(d)
    mem = mask.columns[mask.iloc[i - 1].to_numpy() & close.iloc[i - 1].notna().to_numpy()]
    if len(mem) == 0:   # 范围掩膜从测试期第一天才开始有值：第一季用当天的名单
        mem = mask.columns[mask.iloc[i].to_numpy() & close.iloc[i].notna().to_numpy()]
    end = 调[k + 1] if k + 1 < len(调) else None
    seg = perf[(perf >= d) & ((perf < end) if end is not None else True)]
    只数.append(len(mem))
    g = (1 + tr.loc[seg, mem]).copy(); g.iloc[0] = 1.0
    eq.loc[seg] = v * g.cumprod().mean(axis=1).values
    v = v * float((g.cumprod().iloc[-1] * (1 + tr.loc[end, mem])).mean()) if end is not None else float(eq.loc[seg].iloc[-1])
yrs = (perf[-1] - perf[0]).days / 365.25
ann = float(eq.iloc[-1]) ** (1 / yrs) - 1; dd = float((eq / eq.cummax() - 1).min())
out = {"窗口": f"{perf[0].date()} → {perf[-1].date()}", "范围": f"研发池内 {B.SCOPE} 口径，拿掉 {len(drop)} 只问题票后",
       "成分只数_最少_中位_最多": [min(只数), int(np.median(只数)), max(只数)], "复合年化pct": round(ann * 100, 2),
       "最大回撤pct": round(dd * 100, 2), "卡玛": round(ann / abs(dd), 3), "分红": "含分红", "交易成本": "没扣"}
io.open(os.path.join(HERE, "基本面主对标_1119.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
eq.to_csv(os.path.join(HERE, "基本面主对标_日净值_1119.csv"))
print(out)

# —— 自查：这个对标高得可疑（等权 1400 只票每年 13.58%，比标普还高），先当自己错了 ——
def 线(trx):
    e = pd.Series(np.nan, index=perf); v = 1.0
    for k, d in enumerate(调):
        i = idx.get_loc(d)
        mem = mask.columns[mask.iloc[i - 1].to_numpy() & close.iloc[i - 1].notna().to_numpy()]
        if len(mem) == 0:
            mem = mask.columns[mask.iloc[i].to_numpy() & close.iloc[i].notna().to_numpy()]
        end = 调[k + 1] if k + 1 < len(调) else None
        seg = perf[(perf >= d) & ((perf < end) if end is not None else True)]
        g = (1 + trx.loc[seg, mem]).copy(); g.iloc[0] = 1.0
        e.loc[seg] = v * g.cumprod().mean(axis=1).values
        v = v * float((g.cumprod().iloc[-1] * (1 + trx.loc[end, mem])).mean()) if end is not None else float(e.loc[seg].iloc[-1])
    return e
def 年化(e): return round((float(e.iloc[-1]) ** (1 / yrs) - 1) * 100, 2)
m2 = mask.reindex(perf)
大跳 = (tr.reindex(perf) > 2.0) & m2
print("范围内单日涨超 200% 的票日数", int(大跳.sum().sum()), "涉及", int(大跳.any().sum()), "只")
print("把单日涨幅封顶在 +200% 后的年化", 年化(线(tr.clip(upper=2.0))), "封顶 +100%", 年化(线(tr.clip(upper=1.0))))
print("按年", (eq.groupby(eq.index.year).last().pct_change() * 100).round(1).to_dict(), "首年", round((eq[eq.index.year == 2015].iloc[-1] - 1) * 100, 1))
x = tr.reindex(perf).where(m2).stack(); print("最大的 15 个单日收益", x.nlargest(15).round(2).to_dict())

# —— 自查二：和技术面那条对标（7.28%）差这么多，差在哪 ——
def 线2(价下限=None, 每年调=False, 额下限=None):
    vol = cache._PANEL["volume"][dev].astype(float); adv = (close * vol).rolling(20, min_periods=20).mean()
    dts = [d for k, d in enumerate(调) if (not 每年调) or k % 4 == 0]
    e = pd.Series(np.nan, index=perf); v = 1.0; ns = []
    for k, d in enumerate(dts):
        i = idx.get_loc(d)
        j = i - 1 if mask.iloc[i - 1].any() else i
        ok = mask.iloc[j].to_numpy() & close.iloc[j].notna().to_numpy()
        if 价下限: ok &= (close.iloc[j] >= 价下限).to_numpy()
        if 额下限: ok &= (adv.iloc[j] >= 额下限).fillna(False).to_numpy()
        mem = mask.columns[ok]; ns.append(len(mem))
        end = dts[k + 1] if k + 1 < len(dts) else None
        seg = perf[(perf >= d) & ((perf < end) if end is not None else True)]
        g = (1 + tr.loc[seg, mem]).copy(); g.iloc[0] = 1.0
        e.loc[seg] = v * g.cumprod().mean(axis=1).values
        v = v * float((g.cumprod().iloc[-1] * (1 + tr.loc[end, mem])).mean()) if end is not None else float(e.loc[seg].iloc[-1])
    return 年化(e), round(float((e / e.cummax() - 1).min()) * 100, 1), int(np.median(ns))
print("只留 5 美元以上", 线2(5.0)); print("只留 10 美元以上", 线2(10.0)); print("5 美元以上且日均成交额 1000 万以上", 线2(5.0, 额下限=1e7))
print("每年只调一次（不是每季）", 线2(每年调=True)); print("每年调一次 + 5 美元以上", 线2(5.0, 每年调=True))
lp = pd.read_csv(os.path.join(ROOT, "probe/流动性池_1114/机会集宽基_日净值.csv"), index_col=0, parse_dates=True)
print("技术面对标按年", (lp.iloc[:, 1].groupby(lp.index.year).last().pct_change() * 100).round(1).to_dict())
