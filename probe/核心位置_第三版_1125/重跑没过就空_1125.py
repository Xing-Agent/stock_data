# -*- coding: utf-8 -*-
"""用第三版核心带重跑「反弹到带里没过就空」和「假突破收回再空」· BTC / ETH / SOXX · 引擎外
扳机、止损、出场、成本、对照（带整体挪 ±2.5 日 ATR）都沿用《437》第二版的回放，一个字没改；只换了「哪些带算核心」。
核心 = 第三版打分及格（B 版 8 分 / A 版 5 分）且至少 3 样、跨 2 类（《411》）。另报：加《442》「30 周线向上不开空」前后。
2022–2025 的单子单独存 out/封存_*.csv，不打印、不进统计。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
V3 = mod("v3", os.path.join(HERE, "打分器_第三版_1125.py")); SX = mod("sx", os.path.join(ROOT, "probe/核心压力位_1123/SOXX_假突破_1124.py")); V2 = SX.V; V1 = V2.V1
V2.核心 = lambda z, N: z["过"]; V2.大类 = {}
def S(x, col):
    s = V1.S(x, col); return {k: s.get(k) for k in ("笔数", "每笔净R", "胜率pct", "利润因子", "去掉最赚3笔后每笔", "t")}
out = {}
for sym in ("BTC", "ETH", "SOXX"):
    D, H4, 币 = V3.读(sym); H = V1.小时线(sym) if 币 else SX.小时("SOXX")
    if 币: H = H[H.index < D.index[-1] + pd.Timedelta(days=1)]
    wk = 7 if 币 else 5; m30 = D.close.rolling(30 * wk).mean(); 向上 = (m30 > m30.shift(4 * wk)); days = list(D.index); nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
    for 版, 及格, tag in (("B", 8, "B_并0.25_N5_窗60"), ("A", 5, "A_并0.4_N5_窗60")):
        带 = pd.read_pickle(os.path.join(HERE, "out", f"{sym}_带_{tag}.pkl")); 带2 = {}
        for k, v in 带.items():
            p = k - pd.Timedelta(days=1); kk = k if 币 else nxt.get(p)
            if kk is None: continue
            for z in v["zones"]: z["过"] = bool(z["分"] >= 及格 and z["几样"] >= 3 and z["几类"] >= 2); z["有"] = z["明细"]
            v["档"] = "30周线向上" if bool(向上.get(p, False)) else "30周线不向上"; 带2[kk] = v
        for trg, 窗 in (("没过", 48), ("假突破", 48 if 币 else 35)):
            T = V2.回放(H, 带2, N=0, 扳机=trg, 窗=窗); C = pd.concat([V2.回放(H, 带2, N=0, 扳机=trg, 窗=窗, 挪=+2.5), V2.回放(H, 带2, N=0, 扳机=trg, 窗=窗, 挪=-2.5)])
            key = f"{sym}·{版}版·{trg}"; o = {}
            for nm, X in (("真位置", T), ("挪开的对照", C)):
                if not len(X): o[nm] = {"全部": {"笔数": 0}}; continue
                lock = (X.t >= "2022-01-01") & (X.t <= "2025-12-31")
                if nm == "真位置": X[lock].to_csv(os.path.join(HERE, "out", f"封存_{key}.csv"), index=False); X[~lock].to_csv(os.path.join(HERE, "out", f"单子_{key}.csv"), index=False)
                X = X[~lock]; segs = {"全部": X}
                if 币: segs.update({"2017-2021": X[X.t < "2022-01-01"], "2026": X[X.t >= "2026-01-01"]})
                else: segs.update({"2005-2014": X[(X.t >= "2005-01-01") & (X.t < "2015-01-01")], "2015-2021": X[(X.t >= "2015-01-01") & (X.t < "2022-01-01")], "2026": X[X.t >= "2026-01-01"]})
                segs["30周线不向上"] = X[X["档"] == "30周线不向上"]; segs["30周线向上"] = X[X["档"] == "30周线向上"]
                o[nm] = {a: {"3R": S(g, "R_3R"), "2R": S(g, "R_2R")} for a, g in segs.items()}
            out[key] = o; print(key, json.dumps(o, ensure_ascii=False, default=str)[:1500], flush=True)
json.dump(out, open(os.path.join(HERE, "out", "重跑_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
