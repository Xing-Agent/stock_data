# -*- coding: utf-8 -*-
"""《475》汇总：读 out/五类形态_逐笔.csv（不含封存），出 out/汇总_五类.json 并打印。2026 年单子单列、不进结论。"""
import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
pd.set_option("display.width", 300); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 40)
T = pd.read_csv(os.path.join(OUT, "五类形态_逐笔.csv")); T = T[T["段"] != "2026"]
def pc(x): x = x.dropna(); return round(float(x.astype(float).mean()) * 100) if len(x) else None
主 = {"双顶": ["100%"], "旗": ["100%", "61.8%", "50%"], "三角": ["100%"], "楔": ["宽度100%", "回到起点"]}
R = {}
# 1 默认参数、每种形态一行
d = T[T["参数"] == "默认"]; rows = []
for (类, f, k, sg), x in d.groupby(["类别", "形态", "品种类", "段"]):
    r = {"类别": 类, "形态": f, "品种": k, "段": sg, "笔数": len(x), "样本": "太少" if len(x) < 10 else ""}
    for t in (["100%", "80%", "75%", "61.8%", "50%"] if 类 != "楔" else ["回到起点", "宽度100%", "宽度80%", "宽度75%"]):
        if f"到{t}" in x and x[f"到{t}"].notna().any(): r[f"到{t}"] = pc(x[f"到{t}"]); r[f"对照{t}"] = pc(x[f"对照到{t}"])
    r["先打止损"] = pc(x["没到75%先打止损"]); r["到前低"] = pc(x["到前低(407)"]); r["对照前低"] = pc(x["对照到前低(407)"]); r["到2R"] = pc(x["到2R(407)"]); r["对照2R"] = pc(x["对照到2R(407)"])
    r["主目标距离中位pct"] = round(float(x["主目标距离pct"].median()), 1); rows.append(r)
F = pd.DataFrame(rows); print(F.to_string(index=False)); R["逐形态"] = F.to_dict("records")
# 2 每一类合并（不分形态），主目标 − 对照，看两段是不是都为正
def 差(x, t):
    y = x[x[f"到{t}"].notna()]; return (len(y), pc(y[f"到{t}"]), pc(y[f"对照到{t}"]))
rows = []
for (类, 参, k, sg), x in T.groupby(["类别", "参数", "品种类", "段"]):
    for t in 主[类]:
        n, a, b = 差(x, t); rows.append({"类别": 类, "参数": 参, "品种": k, "段": sg, "目标": t, "笔数": n, "到": a, "对照": b, "差": (a - b) if a is not None and b is not None else None})
G = pd.DataFrame(rows); R["分类合并"] = G.to_dict("records")
print(G[G["参数"] == "默认"].to_string(index=False))
# 3 邻点：方向变没变（差的正负）
base = G[G["参数"] == "默认"].set_index(["类别", "品种", "段", "目标"])["差"]
rows = []
for (类, 参), x in G[G["参数"] != "默认"].groupby(["类别", "参数"]):
    x = x.set_index(["类别", "品种", "段", "目标"]); s = []
    for key, r in x.iterrows():
        b = base.get(key); s.append(f"{key[1]}{key[2][:4]}{key[3]}:{'+' if (r['差'] or 0) > 0 else '-' if (r['差'] or 0) < 0 else '0'}{'' if b is None or np.sign(b) == np.sign(r['差'] or 0) else '(变)'}({r['笔数']})")
    rows.append({"类别": 类, "参数": 参, "各格": "  ".join(s)})
N = pd.DataFrame(rows); print(N.to_string(index=False)); R["邻点"] = N.to_dict("records")
json.dump(R, open(os.path.join(OUT, "汇总_五类.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
