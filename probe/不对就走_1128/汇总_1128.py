# -*- coding: utf-8 -*-
import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); pd.set_option("display.width", 280); pd.set_option("display.max_rows", 500); pd.set_option("display.max_columns", 30)
T = pd.concat([pd.read_csv(os.path.join(OUT, f"逐笔_{k}.csv")) for k in ("4小时", "箱顶", "反抽")], ignore_index=True)
T["年"] = T.日.str[:4].astype(int); T["d"] = pd.to_datetime(T.日)
封 = T.批.isin(["急拉后高位派发区", "派发楔形"]) | ((T.批 == "反抽20日线没过再空") & (T.类 == "币"))
T["照原样"] = ~(封 & T.年.between(2022, 2025))
T["是BTC2026九十月"] = (T.sym == "BTC") & (T.d >= "2026-09-01") & (T.d <= "2026-10-31")
def 组(r):
    if r.批 == "急拉后高位派发区": return "派发区·" + r.类
    if r.批 == "派发楔形": return "派发楔形（三种合）"
    if r.批 == "反抽20日线没过再空": return "反抽·" + r.类
    return "箱顶假突破"
T["组"] = T.apply(组, axis=1)
def 段(r):
    if r.组.startswith("派发") or r.组 == "反抽·币": return "2017–2021" if r.年 <= 2021 else "2022–2026"
    if r.组 == "反抽·SOXX": return "2003–2011" if r.年 <= 2011 else "2012–2021"
    if r.组 == "反抽·个股": return "2015–2018" if r.年 <= 2018 else "2019–2021"
    return "币" if r.sym in ("BTC", "ETH") else "美股"
T["段"] = T.apply(段, axis=1)
主 = {"4小时": ("缓冲0.0", "N12·1.0R", "缓冲0.0·N12·1.0R"), "日线": ("缓冲0.0", "N5·1.0R", "缓冲0.0·N5·1.0R")}
def 统(x):
    if not len(x): return {}
    w = x.R[x.R > 0].sum(); lo = -x.R[x.R < 0].sum(); 早 = x[x.走法.isin(["甲", "乙"])]
    return dict(笔=len(x), 每笔R=round(x.R.mean(), 2), 赚钱=f"{(x.R > 0).mean():.0%}", 利润因子=round(w / lo, 2) if lo > 0 else None, 最深R=round(x.R.min(), 2), 亏的平均亏R=round(x.R[x.R < 0].mean(), 2) if (x.R < 0).any() else None,
                提前平=len(早), 其中本来会赚=int((早.原来R > 0).sum()))
def 四列(x, 周期):
    a, b, c = 主[周期]; out = {"原来": 统(x[x.出场 == "原来"]), "只加甲": 统(x[(x.出场 == "只加甲") & (x.档 == a)]), "只加乙": 统(x[(x.出场 == "只加乙") & (x.档 == b)]), "甲乙都加": 统(x[(x.出场 == "甲乙都加") & (x.档 == c)])}
    return out
R = {}; 周期of = lambda g: "日线" if g == "箱顶假突破" else "4小时"
样本 = {"照原样": T[T.照原样], "含2022–2025（币）": T}
for g in T.组.unique():
    for nm, S in 样本.items():
        if nm != "照原样" and not (g.startswith("派发") or g == "反抽·币"): continue
        x = S[S.组 == g]; R[f"{g}｜{nm}"] = 四列(x, 周期of(g))
        if x.是BTC2026九十月.any(): R[f"{g}｜{nm}｜去掉BTC2026年9~10月"] = 四列(x[~x.是BTC2026九十月], 周期of(g))
for k, v in R.items():
    print("\n##", k); print(pd.DataFrame(v).T.to_string())
# 邻点：每组的 每笔R
rows = []
for g in T.组.unique():
    x = T[T.照原样 & (T.组 == g)]
    for (e, d), y in x.groupby(["出场", "档"]): rows.append(dict(组=g, 出场=e, 档=d, 笔=len(y), 每笔R=round(y.R.mean(), 2), 亏的平均亏R=round(y.R[y.R < 0].mean(), 2) if (y.R < 0).any() else None, 提前平=int(y.走法.isin(["甲", "乙"]).sum()), 本来会赚=int((y.走法.isin(["甲", "乙"]) & (y.原来R > 0)).sum())))
N = pd.DataFrame(rows); N.to_csv(os.path.join(OUT, "邻点.csv"), index=False)
print("\n## 邻点"); print(N[N.出场 != "甲乙都加"].to_string(index=False))
# 两段
rows = []
for (g, s), x in T[T.照原样].groupby(["组", "段"]):
    v = 四列(x, 周期of(g)); rows.append(dict(组=g, 段=s, **{k: f"{d.get('笔', 0)}笔 {d.get('每笔R')}" for k, d in v.items()}))
P = pd.DataFrame(rows); print("\n## 两段"); print(P.to_string(index=False))
# 快不快
o = T[T.照原样 & (T.出场 == "原来")].copy(); o["结果"] = np.where(o.R > 0, "最后赚", "最后亏")
Q = o.groupby(["组", "结果"])[["第1根浮盈R", "第3根浮盈R", "第5根浮盈R"]].agg(["mean", "count"]).round(2); print("\n## 快不快"); print(Q.to_string())
Q2 = o.groupby(["结果"])[["第1根浮盈R", "第3根浮盈R", "第5根浮盈R"]].mean().round(2); print(Q2)
# 牛熊
美 = T[T.照原样 & (T.牛熊.fillna("") != "")]
rows = []
for (g, b), x in 美.groupby(["组", "牛熊"]):
    v = 四列(x, 周期of(g)); rows.append(dict(组=g, 当时=b, **{k: f"{d.get('笔', 0)}笔 {d.get('每笔R')}" for k, d in v.items()}))
B = pd.DataFrame(rows); print("\n## 牛熊"); print(B.to_string(index=False))
json.dump(dict(主表={k: v for k, v in R.items()}, 两段=P.to_dict("records"), 牛熊=B.to_dict("records")), open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
