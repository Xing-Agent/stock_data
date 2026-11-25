# -*- coding: utf-8 -*-
"""《459 拍板》第 4 条：核心位置分两档 · BTC / ETH / SOXX · 引擎外
强位置 = 第三版打分及格（A 版 5 分）且至少 3 样、跨 2 类。普通位置 = 有地基（前高前低 / 密集区 / 没补的缺口）但不够强。
扳机统一用「假突破收回」（= 扫止损后收回，右侧），止损、出场、成本沿用《437》的回放。做空开关：币用五档状态机可空（含筑底期箱顶假突破），SOXX 没有状态机，只报不加开关。
拍板里「第一目标盈亏比 ≥ 2 才做」：回放的目标是固定 2R / 3R，天然满足，没有另筛。2022–2025 封存。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
V3 = mod("v3", os.path.join(HERE, "打分器_第三版_1125.py")); SX = mod("sx", os.path.join(ROOT, "probe/核心压力位_1123/SOXX_假突破_1124.py")); V2 = SX.V; V1 = V2.V1
FL = mod("fl", os.path.join(ROOT, "probe/派发楔形_1125/反抽加过滤_1125.py"))
V2.核心 = lambda z, N: z["过"]; V2.大类 = {}
def S(x, col="R_3R"):
    if not len(x): return {"笔数": 0}
    s = V1.S(x, col); return {k: s.get(k) for k in ("笔数", "每笔净R", "胜率pct", "利润因子", "t")}
out = {}
for sym in ("BTC", "ETH", "SOXX"):
    D, H4, 币 = V3.读(sym); H = V1.小时线(sym) if 币 else SX.小时("SOXX")
    if 币: H = H[H.index < D.index[-1] + pd.Timedelta(days=1)]; 可, _ = FL.状态可空(sym)
    days = list(D.index); nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    raw = pd.read_pickle(os.path.join(HERE, "out", f"{sym}_带_A_并0.4_N5_窗60.pkl"))
    for 档名 in ("强位置", "普通位置"):
        带 = {}
        for k, v in raw.items():
            p = k - pd.Timedelta(days=1); kk = k if 币 else nxt.get(p)
            if kk is None: continue
            zs = []
            for z in v["zones"]:
                强 = bool(z["分"] >= 5 and z["几样"] >= 3 and z["几类"] >= 2); z2 = dict(z); z2["过"] = 强 if 档名 == "强位置" else (not 强); z2["有"] = z["明细"]; zs.append(z2)
            带[kk] = dict(zones=zs, atr=v["atr"], px=v["px"], 档=("可空" if (币 and bool(可.get(p, False))) else ("不可空" if 币 else "无状态机")))
        窗 = 48 if 币 else 35
        T = V2.回放(H, 带, N=0, 扳机="假突破", 窗=窗); C = pd.concat([V2.回放(H, 带, N=0, 扳机="假突破", 窗=窗, 挪=+2.5), V2.回放(H, 带, N=0, 扳机="假突破", 窗=窗, 挪=-2.5)])
        o = {}
        for nm, X in (("真位置", T), ("挪开的对照", C)):
            if not len(X): o[nm] = {"全部": {"笔数": 0}}; continue
            lock = (X.t >= "2022-01-01") & (X.t <= "2025-12-31")
            if nm == "真位置": X[lock].to_csv(os.path.join(HERE, "out", f"封存_分档_{sym}_{档名}.csv"), index=False); X[~lock].to_csv(os.path.join(HERE, "out", f"分档_{sym}_{档名}.csv"), index=False)
            X = X[~lock]; yrs = max(1, X.t.dt.year.nunique()); seg = {"全部": X}
            if 币: seg.update({"2017-2021": X[X.t < "2022-01-01"], "2026": X[X.t >= "2026-01-01"], "状态机可空": X[X["档"] == "可空"], "状态机不可空": X[X["档"] == "不可空"]})
            else: seg.update({"2005-2014": X[(X.t >= "2005-01-01") & (X.t < "2015-01-01")], "2015-2021": X[(X.t >= "2015-01-01") & (X.t < "2022-01-01")]})
            o[nm] = {a: S(g) for a, g in seg.items()}; o[nm]["一年几笔"] = round(len(X) / yrs, 1)
        out[f"{sym}·{档名}"] = o; print(f"{sym}·{档名}", json.dumps(o, ensure_ascii=False, default=str)[:1300], flush=True)
json.dump(out, open(os.path.join(HERE, "out", "分两档_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
