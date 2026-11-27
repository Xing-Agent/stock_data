# -*- coding: utf-8 -*-
import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
R = {}
P = pd.read_csv(os.path.join(OUT, "第一次回踩.csv"))
g = P.groupby(["品种", "门槛", "回踩尺子"])["深度"]
A = pd.DataFrame({"事件": g.size(), "深度中位": g.median().round(2), "≤0.382占比": g.apply(lambda x: round((x <= 0.382).mean() * 100)), "≤0.5占比": g.apply(lambda x: round((x <= 0.5).mean() * 100)), ">0.618占比": g.apply(lambda x: round((x > 0.618).mean() * 100))}).reset_index()
print(A.to_string(index=False)); R["回踩"] = A.to_dict("records")
B = P[P["回踩尺子"] == 2.0].groupby(["品种", "门槛", "一年内收复大跌起点"])["深度"].agg(["size", "median", lambda x: (x <= 0.382).mean()]).round(2); print(B); R["回踩按成败"] = B.reset_index().astype(str).to_dict("records")
C = P[P["回踩尺子"] == 2.0].groupby(["品种", "门槛", "段"])["深度"].agg(["size", "median", lambda x: (x <= 0.382).mean()]).round(2); print(C)
T = pd.read_csv(os.path.join(OUT, "四种进场_逐笔.csv"))
def 表(x):
    y = x[x["有进场"] == True]
    return pd.Series({"事件": len(x), "有进场": len(y), "每笔%": round(y["收益pct"].mean(), 2) if len(y) else np.nan, "每笔R": round(y["R"].mean(), 2) if len(y) else np.nan, "赚钱%": round((y["收益pct"] > 0).mean() * 100) if len(y) else np.nan,
                      "最深亏损%": round(y["收益pct"].min(), 1) if len(y) else np.nan, "打止损%": round(y["打止损"].mean() * 100) if len(y) else np.nan, "风险中位%": round(y["风险pct"].median(), 1) if len(y) else np.nan, "进场离L中位%": round(y["进场离L涨了pct"].median(), 1) if len(y) else np.nan})
D = T[(T["参数"] == "默认")].groupby(["品种", "门槛", "拿天", "进场"]).apply(表).reset_index(); print(D.to_string(index=False)); R["进场"] = D.to_dict("records")
E2 = T[(T["参数"] == "默认") & (T["拿天"] == 60)].groupby(["品种", "门槛", "段", "进场"]).apply(表).reset_index(); print(E2.to_string(index=False)); R["进场分段"] = E2.to_dict("records")
F = T[(T["拿天"] == 60)].groupby(["品种", "门槛", "参数", "进场"]).apply(表).reset_index()[["品种", "门槛", "参数", "进场", "有进场", "每笔%", "每笔R", "赚钱%"]]
F = F[F["进场"].isin(["①", "②"])]; print(F.to_string(index=False)); R["邻点"] = F.to_dict("records")
json.dump(R, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
