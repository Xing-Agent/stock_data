# -*- coding: utf-8 -*-
"""《465》汇总：读 out/*_逐笔.csv，出报告用的表（out/汇总.json），并打印。"""
import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400)
R = {}
def pct(x): return round(float(np.nanmean(x)) * 100, 0) if len(x) else np.nan
# 1 形态
T = pd.read_csv(os.path.join(OUT, "形态_逐笔.csv")); T["类"] = np.where(T["sym"].isin(["BTC", "ETH"]), "币", "美股ETF")
rows = []
for (f, k, sg), x in T.groupby(["形态", "类", "段"]):
    st = x["止损第几天"].notna() & ~x["到75%"].astype(bool)
    rows.append({"形态": f, "类": k, "段": sg, "笔数": len(x), "到100%": pct(x["到100%"]), "对照100%": pct(x["对照到100%"]), "到80%": pct(x["到80%"]), "到75%": pct(x["到75%"]),
                 "对照75%": pct(x["对照到75%"]), "到70%": pct(x["到70%"]), "没到75%先打止损": pct(st), "到前低(407)": pct(x["到前低(407)"].dropna()), "对照前低": pct(x["对照到前低(407)"].dropna()),
                 "到2R(407)": pct(x["到2R(407)"]), "对照2R": pct(x["对照到2R(407)"]), "测算100%距离中位pct": round(float(x["测算100%距离pct"].median()), 1), "风险中位pct": round(float(x["风险pct"].median()), 1)})
F = pd.DataFrame(rows); print(F.to_string(index=False)); R["形态"] = F.to_dict("records")
# 2 点数图
PF = pd.read_csv(os.path.join(OUT, "点数图_逐笔.csv")); PF["类"] = np.where(PF["sym"].isin(["BTC", "ETH"]), "币", "美股ETF")
rows = []
for (q, k, sg, d), x in PF.groupby(["格值倍", "类", "段", "方向"]):
    rows.append({"格值": q, "类": k, "段": sg, "方向": "吸筹(向上)" if d > 0 else "派发(向下)", "笔数": len(x), "到近端": pct(x["到点数图近端"].dropna()), "对照近端": pct(x["对照到点数图近端"].dropna()),
                 "到远端": pct(x["到点数图远端"].dropna()), "对照远端": pct(x["对照到点数图远端"].dropna()), "近端距离中位pct": round(float(x["距离点数图近端pct"].median()), 1) if x["距离点数图近端pct"].notna().any() else None,
                 "实际落点离近端中位pct": round(float(x["实际落点离近端pct"].median()), 1), "列数中位": float(x["列数"].median())})
G = pd.DataFrame(rows); print(G.to_string(index=False)); R["点数图"] = G.to_dict("records")
# 3 波浪
WV = pd.read_csv(os.path.join(OUT, "波浪_逐笔.csv")); WV["类"] = np.where(WV["sym"].isin(["BTC", "ETH"]), "币", "美股ETF")
rows = []
for (kk, k, sg), x in WV.groupby(["拐点倍", "类", "段"]):
    r = {"拐点倍": kk, "类": k, "段": sg, "笔数": len(x)}
    for t in ("点数1倍", "点数1.618倍", "百分比1倍", "百分比1.618倍", "前低(407)", "2R(407)"):
        y = x[x[f"到{t}"].notna()]
        r[f"到{t}"] = pct(y[f"到{t}"].astype(float)); r[f"对照{t}"] = pct(y[f"对照到{t}"]); r[f"距{t}中位pct"] = round(float(y[f"距离{t}pct"].median()), 1) if len(y) else None
    rows.append(r)
W = pd.DataFrame(rows); print(W.to_string(index=False)); R["波浪"] = W.to_dict("records")
# 4 合成
CB = pd.read_csv(os.path.join(OUT, "合成_逐笔.csv")); CB["类"] = np.where(CB["sym"].isin(["BTC", "ETH"]), "币", "美股ETF")
cols = ["对照·T1平一半+保本拿T2", "T1平35%+保本拿T2", "T1平25%+保本拿T2", "T1平50%+保本拿T2", "T1平35%+吊灯3ATR", "T1平35%+吊灯2.5ATR"]
rows = []
for (并, 门, k, sg), x in CB.groupby(["合并ATR", "门槛", "类", "段"]):
    r = {"合并ATR": 并, "T1门槛": 门, "类": k, "段": sg, "笔数": len(x)}
    for c in cols:
        v = x[c]; w = v[v > 0].sum(); l = -v[v < 0].sum()
        r[c] = f"{v.mean():+.2f}R / 胜{(v > 0).mean()*100:.0f}% / PF{(w / l if l > 0 else np.nan):.2f}"
    rows.append(r)
C = pd.DataFrame(rows); print(C.to_string(index=False)); R["合成"] = C.to_dict("records")
json.dump(R, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
