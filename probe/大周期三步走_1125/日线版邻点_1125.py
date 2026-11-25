# -*- coding: utf-8 -*-
"""《457》· 日线对照版相邻三点（标普、道指、纳指、SOXX）+ 漏掉的真顶卡在哪 + 每个真顶确认时离顶 + BTC 改写主版本相邻三点。
一次只挪一个数，其余照基准。SOXX 的基准本来就不同（45 天箱底、破位 3%、急跌 15%），它的相邻点按自己的基准上下挪（我补的）。
评分、封存照 改写版_1125.py。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("G", os.path.join(HERE, "改写版_1125.py")); G = importlib.util.module_from_spec(sp); sp.loader.exec_module(G)

指数基准 = dict(箱=65, 破=0.015, 急=0.10, 前提天=10, 慢天=15)
指数邻点 = {"箱": (45, 90), "破": (0.01, 0.02), "急": (0.08, 0.12), "前提天": (5, 15), "慢天": (10, 20)}
SOXX基准 = dict(箱=45, 破=0.03, 急=0.15, 前提天=10, 慢天=15)
SOXX邻点 = {"箱": (30, 65), "破": (0.02, 0.04), "急": (0.12, 0.18), "前提天": (5, 15), "慢天": (10, 20)}


def 卡在哪(D, a, tb, 箱=65, 破=0.015, 急=0.10, 急天=10, 前提天=10, 慢天=15):
    """漏掉的真顶：在「顶 → 熊底」之间逐天看，前提有没有成立过、破位有没有、急跌条件有没有、慢熊为什么没确认。"""
    c = D.close.to_numpy(float); idx = D.index; ma = pd.Series(c).rolling(200, min_periods=200).mean().to_numpy(); sw = G.摆动低(c)
    i0, i1 = a, idx.get_loc(tb); 前提过 = 破过 = 急过 = 0; 慢原因 = []
    for t in range(max(i0, 230), i1 + 1):
        lows = [c[j] for j in range(max(0, t - 箱), t - 3) if sw[j]]
        if not lows: continue
        底 = float(np.median(lows))
        前提 = ma[t] - ma[t - 20] <= 0 and all(c[t - k] < ma[t - k] for k in range(前提天))
        前提过 += 前提
        if c[t] < 底 and c[t] < ma[t] and c[t] / c[t - 急天] - 1 < -急: 急过 += 1
        if 前提 and c[t] < 底 * (1 - 破):
            破过 += 1
    最大10天跌 = float(min(c[t] / c[t - 急天] - 1 for t in range(max(i0, 急天), i1 + 1))) if i1 > i0 else np.nan
    return {"前提成立的天数": int(前提过), "前提下破位的天数": int(破过), "急跌条件成立的天数": int(急过), "这段里最大10天跌幅pct": round(最大10天跌 * 100, 1)}


if __name__ == "__main__":
    out = {"日线版邻点": {}, "漏掉的真顶": {}, "每个真顶": {}, "BTC主版本邻点": {}}
    for nm, D in (("标普500指数", G.L.读("标普500指数")), ("道琼斯工业指数", G.L.读("道琼斯工业指数")), ("纳斯达克综合指数", G.L.读("纳斯达克综合指数")), ("SOXX", G.SC.soxx())):
        基, 邻 = (SOXX基准, SOXX邻点) if nm == "SOXX" else (指数基准, 指数邻点)
        原严 = G.原来(D, 要ST或UT=True, BC严=True)
        rows = {}
        S, T, F = G.评(D, G.日线版(D, **基), 原=原严); rows["基准"] = (S["认出"], S["真大顶"], S["其中虚惊"])
        out["每个真顶"][nm] = T.to_dict("records")
        漏 = []
        for _, r in T[T["认出"] == "没认出"].iterrows():
            a = D.index.get_loc(pd.Timestamp(r["顶"])); 漏.append({"顶": r["顶"], "整轮跌幅pct": r["整轮跌幅pct"], **卡在哪(D, a, pd.Timestamp(r["熊底"]), **{k: v for k, v in 基.items()})})
        out["漏掉的真顶"][nm] = 漏
        for k, vs in 邻.items():
            for v in vs:
                p = dict(基); p[k] = v; S, _, _ = G.评(D, G.日线版(D, **p), 原=原严); rows[f"{k}={v}"] = (S["认出"], S["真大顶"], S["其中虚惊"])
        for 解 in (False,):
            S2, T2, F2 = G.评(D, G.日线版(D, **基, 解除要箱底=False), 原=原严); rows["解除不要求收回箱底"] = (S2["认出"], S2["真大顶"], S2["其中虚惊"])
            out["每个真顶·解除不要求收回箱底"] = out.get("每个真顶·解除不要求收回箱底", {}); out["每个真顶·解除不要求收回箱底"][nm] = T2.to_dict("records")
            for k, vs in 邻.items():
                for v in vs:
                    p = dict(基); p[k] = v; S3, _, _ = G.评(D, G.日线版(D, **p, 解除要箱底=False), 原=原严); rows[f"解除不要箱底·{k}={v}"] = (S3["认出"], S3["真大顶"], S3["其中虚惊"])
            if nm != "SOXX":
                W = G.周线(D); S4, _, _ = G.评(D, G.主版(W, 量起=pd.Timestamp("1950-01-01"), 解除要箱底=False), 原=原严); rows["周线主版本·解除不要求收回箱底"] = (S4["认出"], S4["真大顶"], S4["其中虚惊"])
                S5, _, _ = G.评(D, G.主版(W, 量起=pd.Timestamp("1950-01-01"), 解除要箱底=False, 涨=0.0), 原=原严); rows["周线主版本·解除不要箱底·去掉35%前提"] = (S5["认出"], S5["真大顶"], S5["其中虚惊"])
        out["日线版邻点"][nm] = rows
        print("==", nm, rows, flush=True)
    # BTC 改写主版本邻点
    D = G.M4.币日线("BTC"); B = D[["close", "volume"]]
    基 = dict(破=0.05, 急=0.12, 观=12)
    def btc(**kw):
        p = dict(基); p.update(kw)
        ev = G.主版(B, 两根跌=0.045, 均线=120, 年=365, 盒小=28, 盒大=84, 两年=730, **p)
        return [(str(e["确认"].date()), e["路"]) for e in ev]
    out["BTC主版本邻点"]["基准(破5%急12%观察12天)"] = btc()
    for k, vs in (("破", (0.04, 0.06)), ("急", (0.10, 0.15)), ("观", (5, 8))):
        for v in vs: out["BTC主版本邻点"][f"{k}={v}"] = btc(**{k: v})
    for k, v in out["BTC主版本邻点"].items(): print("BTC", k, v)
    json.dump(out, open(os.path.join(HERE, "out", "日线版邻点_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE")
