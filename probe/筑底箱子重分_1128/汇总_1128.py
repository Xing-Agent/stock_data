# -*- coding: utf-8 -*-
import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); R = {}
T0 = pd.read_csv(os.path.join(OUT, "全部箱子.csv")); T = T0[T0.方向 != "还在箱里"].copy(); 币 = T.品种.isin(["BTC", "ETH"])
def g(col_c, col_u): return pd.Series(np.where(T.品种.isin(["BTC", "ETH"]), T[col_c], T[col_u]), index=T.index).astype(bool)
rules = {"不加（全算筑底）": pd.Series(True, index=T.index), "离顶门槛 低档（币150/美股90）": g("过门槛150", "过门槛90"), "离顶门槛 默认（币180/美股120）": g("过门槛180", "过门槛120"),
         "离顶门槛 高档（币210/美股150）": g("过门槛210", "过门槛150"), "量能萎缩 0.35": T["量缩0.35"].astype(bool), "量能萎缩 0.45": T["量缩0.45"].astype(bool), "量能萎缩 0.55": T["量缩0.55"].astype(bool),
         "首箱豁免": ~T["首箱"].astype(bool)}
rows = []
for k, p in rules.items():
    ok = (p & (T.方向 == "向上")) | (~p & (T.方向 == "破位")); up = T.方向 == "向上"
    rows.append(dict(规则=k, 判对=f"{ok.sum()}/{len(T)}", 向上的箱子判对=f"{(ok & up).sum()}/{up.sum()}", 破位的箱子判对=f"{(ok & ~up).sum()}/{(~up).sum()}", 币=f"{ok[币].sum()}/{币.sum()}", 美股=f"{ok[~币].sum()}/{(~币).sum()}",
                     判错的=", ".join(T[~ok].apply(lambda r: f"{r.品种} {r.进箱[:7]}（{r.方向}）", axis=1))))
A = pd.DataFrame(rows); print(A.to_string(index=False)); R["分类"] = A.to_dict("records")
P = pd.read_csv(os.path.join(OUT, "再派发四档.csv")); P = P[P.方向 != "还在箱里"]
rows = []
for k, x in P.groupby("再派发档", sort=False):
    up = x[x.方向 == "向上"]; dn = x[x.方向 == "破位"]
    b18 = x[(x.品种 == "BTC") & (x.进箱 == "2018-04-02")]
    rows.append(dict(档=k, 向上箱子被错判=f"{(up.派天 > 0).sum()}/{len(up)}", 错判天数=int(up.派天.sum()), 破位箱子认出=f"{(dn.派天 > 0).sum()}/{len(dn)}", 破位箱子认出天数=int(dn.派天.sum()),
                     BTC2018_6月8日到11月16日认出天数=int(b18.派日_2018_06_08到11_16.iloc[0]) if len(b18) else None, 错判的=", ".join(up[up.派天 > 0].apply(lambda r: f"{r.品种} {r.进箱[:7]} {r.派天}天", axis=1))))
B = pd.DataFrame(rows); print(B.to_string(index=False)); R["再派发"] = B.to_dict("records")
Q = pd.read_csv(os.path.join(OUT, "再派发四档.csv")); print(Q[Q.方向 == "还在箱里"].to_string(index=False))
X = pd.read_csv(os.path.join(OUT, "均线退路A_逐笔.csv"))
def 统(x):
    if not len(x): return pd.Series({"笔": 0})
    s = (x.R < 0).astype(int).to_numpy(); mx = cur = 0
    for v in s: cur = cur + 1 if v else 0; mx = max(mx, cur)
    return pd.Series({"笔": len(x), "赚钱笔": f"{(x.R > 0).sum()}/{len(x)}", "合计R": round(x.R.sum(), 1), "每笔R": round(x.R.mean(), 2), "最大连亏": mx, "最深%": round(x.收益pct.min(), 1)})
X["箱型"] = np.where(X.箱子方向 == "向上", "真筑底（最后向上）", np.where(X.箱子方向 == "破位", "熊市中段（最后破位）", "还在箱里（BTC 2026）"))
X["币"] = np.where(X.品种.isin(["BTC", "ETH"]), "币", "美股")
C = X.groupby(["参数", "箱型", "币"]).apply(统).reset_index(); print(C.to_string(index=False)); R["退路A"] = C.to_dict("records")
C2 = X.groupby(["参数", "箱型"]).apply(统).reset_index(); print(C2.to_string(index=False)); R["退路A合"] = C2.to_dict("records")
y = X[(X.参数 == "默认") & (X.品种 == "BTC") & (X.日.str[:4] == "2018")]; print("BTC 2018 A 版默认:", len(y), round(y.R.sum(), 1))
json.dump(R, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
