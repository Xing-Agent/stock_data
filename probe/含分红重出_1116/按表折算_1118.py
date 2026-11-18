#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按数据组的《并股事件表_第二来源_全池_1118》（19:42 到的全池版，替掉下午那张；下午那张里 SPI/CRIS/MLGO/PRFX/DCIX 五处判错，已不再折）在内存里折算面板（2026-11-18）

大白话：公司并股（比如 10 股并 1 股）时股价一夜变成 10 倍。数据没折算，回测就以为它一天涨了 10 倍。
       这里按数据组核过 SEC 公告的那张表，把并股生效日之前的价格乘上倍数、成交量除以同一个倍数，前后就接上了。
只改内存里的面板（engine.cache._PANEL），源头文件和 engine/ 都不动。数据组说好了：我们按表跑完之前，它不改源头，免得折两次。

怎么用：先 B.装层()，再 import 按表折算_1118 as FIX; 报告 = FIX.install()
处理规则：
  是并股            生效日前后 3 根里面板上确实有跳变（收盘 ÷ 前一根收盘 >= max(1.4, 倍数的三成)；并股当天常同时大跌，所以不要求跳满）才折算；没有跳变的说明面板里已经折算过，跳过并记下来
  有系数但日期错位  （HOLO、JAGX）整只票拿掉 —— 面板里的系数标错了日子，折算前要先把错的那次撤掉，这里先不冒险
  破产重组          （BAS、CHRD、CIVI、EGLE、SGY、TDW、WLL）整只票拿掉 —— 新老股是两只不同的证券，不能折算；
                    ⚠ 这会同时拿掉老股最后归零的那段亏损，对便宜货类策略是偏好看的方向，结果里要写明
  查不到            整只票拿掉
  是拆股            （正向，1 拆 2 这种）同样折，方向相反
  不用折算          不动
  代码中间断档      读《代码中间断档_全池_1118》：断档接上的日子落在 2014 年以后的票整只拿掉（不管是哪一类断档，最保守的做法）
没处理的：除息金额没有跟着折算（并股前的每股分红应该同样乘上倍数）；影响很小，写在这里备查。
"""
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
表 = os.path.join(ROOT, "market_ext_1105/并股事件表_第二来源_全池_1118.csv")
破产重组 = ["BAS", "CHRD", "OAS", "CIVI", "EGLE", "SGY", "TDW", "WLL"]
断档表 = os.path.join(ROOT, "market_ext_1105/代码中间断档_全池_1118.csv")
窗口起 = "2014-01-01"    # 断档接上的日子在这之后的票整只拿掉（跑 2004–2014 时把它改成 2003-01-01）


def 断档票():
    g = pd.read_csv(断档表)
    return sorted(set(g.loc[g["接上的第一天"] >= 窗口起, "代码"].astype(str)))


def 要拿掉的票():
    d = pd.read_csv(表)
    out = set(d.loc[d["结论"].isin(["查不到", "有系数但日期错位"]) & (d["生效日"] >= 窗口起), "代码"].astype(str))   # 只管落在测试窗口里的
    return sorted(out | set(破产重组) | set(断档票()))


def install():
    from engine import cache
    P = cache._PANEL
    idx = P["close"].index
    d = pd.read_csv(表)
    d = d[d["结论"].isin(["是并股", "是拆股"])].copy()
    报告 = {"折算了": [], "跳过_面板上没有跳变": [], "跳过_不在面板或日期在面板之外": []}
    for _, r in d.sort_values(["代码", "生效日"]).iterrows():
        s = str(r["代码"])
        try:
            new, old = str(r["比例(新股数:旧股数)"]).split(":")
            倍 = float(old) / float(new)
        except Exception:
            报告["跳过_不在面板或日期在面板之外"].append((s, str(r["生效日"]), "比例读不出"))
            continue
        day = pd.Timestamp(r["生效日"])
        if s not in P["close"].columns or day <= idx[0] or day > idx[-1]:
            报告["跳过_不在面板或日期在面板之外"].append((s, str(day.date()), 倍))
            continue
        t = int(idx.searchsorted(day))
        c = P["close"][s].to_numpy(dtype=float)
        # 生效日附近（前后各 3 根）找最大的那次跳变，停牌断档时生效日可能差一两根
        best, bt = None, None
        for u in range(max(1, t - 3), min(len(c), t + 4)):
            prev = c[:u][np.isfinite(c[:u])]
            if len(prev) and np.isfinite(c[u]) and prev[-1] > 0:
                ratio = c[u] / prev[-1]
                if best is None or (ratio > best if 倍 > 1 else ratio < best):
                    best, bt = ratio, u
        # 并股（倍 > 1）：要往上跳到 max(1.4, 倍数三成)；拆股（倍 < 1）：要往下跳到 min(0.72, 倍数开方)
        够 = best is not None and (best >= max(1.4, 0.3 * 倍) if 倍 > 1 else best <= min(0.72, 倍 ** 0.5))
        if not 够:
            报告["跳过_面板上没有跳变"].append((s, str(day.date()), 倍, None if best is None else round(best, 2)))
            continue
        cut = idx[bt]
        for k in ("open", "high", "low", "close"):
            if k in P:
                col = P[k][s].to_numpy(dtype=float).copy()
                col[:bt] = col[:bt] * 倍
                P[k][s] = col
        if "volume" in P:
            col = P["volume"][s].to_numpy(dtype=float).copy()
            col[:bt] = col[:bt] / 倍
            P["volume"][s] = col
        报告["折算了"].append((s, str(cut.date()), 倍, round(best, 2)))
    return 报告


def 拿掉(m):
    """把要拿掉的票从选股范围里去掉（m 是 matrices.build 出来的对象）。返回拿掉了几只。"""
    n = 0
    for s in 要拿掉的票():
        if s in m.col:
            m.universe[:, m.col[s]] = False
            n += 1
    return n
