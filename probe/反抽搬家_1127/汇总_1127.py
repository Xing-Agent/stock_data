import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
def 统(x):
    if not len(x): return pd.Series({"笔": 0})
    w = x.R[x.R > 0].sum(); lo = -x.R[x.R < 0].sum()
    return pd.Series({"笔": len(x), "每笔R": round(x.R.mean(), 2), "每笔%": round(x.收益pct.mean(), 2), "赚钱%": round((x.R > 0).mean() * 100), "利润因子": round(w / lo, 2) if lo > 0 else None, "最深%": round(x.收益pct.min(), 1), "风险中位%": round(x.风险pct.median(), 1)})
R = {}
S = pd.read_csv(os.path.join(OUT, "SOXX_逐笔.csv")); S["段"] = np.where(pd.to_datetime(S.t).dt.year < 2008, "2003–2007", "2008–2021")
A = S.groupby(["开关", "过滤"]).apply(统).reset_index(); print(A.to_string(index=False)); R["SOXX"] = A.to_dict("records")
A2 = S.groupby(["开关", "过滤", "段"]).apply(统).reset_index(); print(A2[A2.过滤 == "过滤0.8"].to_string(index=False)); R["SOXX分段"] = A2.to_dict("records")
f = os.path.join(OUT, "个股_逐笔.csv")
if os.path.exists(f):
    G = pd.read_csv(f); G["年"] = pd.to_datetime(G.t).dt.year
    B = G.groupby(["开关", "过滤"]).apply(统).reset_index(); print(B.to_string(index=False)); R["个股"] = B.to_dict("records")
    C = G[G.过滤 == "过滤0.8"].groupby(["开关", "年"]).apply(统).reset_index(); print(C.to_string(index=False)); R["个股按年"] = C.to_dict("records")
    x = G[(G.开关 == "均线") & (G.过滤 == "过滤0.8")]; print("票数", x.sym.nunique(), "前 5 笔占总 R", round(x.R.nlargest(5).sum() / x.R.sum(), 2) if x.R.sum() else None, "最多的票", x.sym.value_counts().head(5).to_dict())
json.dump(R, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
