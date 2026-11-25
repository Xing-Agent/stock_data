# -*- coding: utf-8 -*-
"""按每次报警对号评三步走（替代 三步走_1125.py 里沿用《429》的「顶到第一段底之间」那把尺子 —— 三步走要等 3~10 根确认，
确认时第一段多半已经跌完，那把尺子会把晚到的确认都算成「没认出」，不公平）。
对号：原来哪次报警认出了哪个真顶 / 哪次是别的转空（虚惊与否），三步走后这次报警有没有被确认、确认时离顶多少天、离顶跌了多少、离这轮熊市最低还有多少。
「这轮熊市最低」= 顶之后、收盘重新站上顶之前的最低收盘（比《429》的「第一段底」长）。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("S", os.path.join(HERE, "三步走_1125.py")); S = importlib.util.module_from_spec(sp); sp.loader.exec_module(S)

def 熊底(c, a):
    top = c.iloc[a]; after = c.iloc[a:]; back = after[after > top].index[:1]
    seg = after.loc[:back[0]] if len(back) else after
    return seg.idxmin(), float(seg.min())

def 对号(D, R, 候, res):
    c = D.close; idx = D.index; tops = S.L.真顶(c); rows = []
    for e, r in zip(候, res):
        t = e["日期"]; 归 = None
        for a, b in tops:
            if idx[a] <= t <= idx[b]: 归 = a; break
        row = {"报警": str(t.date()), "事": e["事"], "认的是真顶": str(idx[归].date()) if 归 is not None else "", "三步走": r["结果"]}
        if 归 is None: row["原来_之后最多再跌pct"] = S.虚惊之后跌(D, R, t, float(c.loc[t]))
        if r["结果"] == "确认":
            tc = r["确认日"]; px = float(c.loc[:tc].iloc[-1]); row["确认日"] = str(tc.date())
            if 归 is not None:
                bt, bv = 熊底(c, 归); row.update({"原来离顶天": int((t - idx[归]).days), "原来离顶pct": round((float(c.loc[t]) / c.iloc[归] - 1) * 100, 1),
                    "确认离顶天": int((tc - idx[归]).days), "确认离顶pct": round((px / c.iloc[归] - 1) * 100, 1), "比原来晚天": int((tc - t).days),
                    "确认时离这轮熊市最低还有pct": round((bv / px - 1) * 100, 1) if tc <= bt else "已过最低", "这轮熊市最低": str(bt.date())})
            else: row["确认后_之后最多再跌pct"] = S.虚惊之后跌(D, R, tc, px)
        rows.append(row)
    return pd.DataFrame(rows)

def 概(X, a, b):
    X = X[(X["报警"] >= a) & (X["报警"] < b)]; 真 = X[X["认的是真顶"] != ""]; 别 = X[X["认的是真顶"] == ""]
    顶们 = sorted(set(真["认的是真顶"])); 认 = [tp for tp in 顶们 if (真[(真["认的是真顶"] == tp)]["三步走"] == "确认").any()]
    确 = 真[真["三步走"] == "确认"].sort_values("确认日").groupby("认的是真顶").head(1)
    别确 = 别[别["三步走"] == "确认"]
    return {"原来认出的真顶": len(顶们), "三步走还认得出": len(认), "晚了多少天中位(比原报警)": float(确["比原来晚天"].median()) if len(确) else None,
            "确认时离顶pct中位": float(确["确认离顶pct"].median()) if len(确) else None, "原来离顶pct中位": float(真.sort_values("报警").groupby("认的是真顶").head(1)["原来_之后最多再跌pct"].median()) if False else None,
            "原来别的转空": int(len(别)), "原来其中虚惊": int((别["原来_之后最多再跌pct"] > -10).sum()),
            "三步走后别的转空还剩": int(len(别确)), "其中虚惊还剩": int((别确["确认后_之后最多再跌pct"] > -10).sum()) if len(别确) else 0}

if __name__ == "__main__":
    out = {}
    for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
        D = S.L.读(nm); 候, R = S.候选(D, "三层一版"); 候 = [x for x in 候 if str(x["日期"].date()) < S.封存]
        for tf, tfn in (("M", "月线"), ("W", "周线")):
            for (实体, 量, N) in ((1.2, 1.3, 2), (1.2, 1.3, 1), (1.2, 1.3, 3), (0.9, 1.3, 2), (0.6, 1.0, 2), (0.0, 1.0, 2)):
                res = S.三步(D, tf, 候, N=N, 窗=1, 实体=实体, 量=量); X = 对号(D, R, 候, res)
                k = f"{nm}｜{tfn}｜实体{实体}｜量{量}｜连续{N}根"
                out[k] = {s: 概(X, a, b) for s, (a, b) in (("1928–1992", ("1900", "1993")), ("1993–2021", ("1993", S.封存)))}
                if (实体, 量, N) in ((1.2, 1.3, 2), (0.0, 1.0, 2)): X.to_csv(os.path.join(HERE, "out", f"对号_{nm}_{tfn}_实体{实体}_量{量}.csv"), index=False)
                print(k, json.dumps(out[k], ensure_ascii=False), flush=True)
    json.dump(out, open(os.path.join(HERE, "out", "对号_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
