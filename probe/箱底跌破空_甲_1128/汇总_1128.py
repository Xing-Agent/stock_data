# -*- coding: utf-8 -*-
"""第四批汇总：主表（SPY/QQQ/SOXX）、扩大样本（另 13 只 ETF）、合起来；随机对照 1,000 次（出场规则和我们完全一样，含 8 根时间规则）；扣掉大盘。"""
import os, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sp = importlib.util.spec_from_file_location("b", os.path.join(HERE, "箱底跌破空_1128.py")); B = importlib.util.module_from_spec(sp); sp.loader.exec_module(B)
sp = importlib.util.spec_from_file_location("c", os.path.join(os.path.dirname(HERE), "做空组合_甲_1128/组合核心_1128.py")); C = importlib.util.module_from_spec(sp); sp.loader.exec_module(C)
池 = pd.read_pickle(os.path.join(OUT, "池.pkl")); spy = B.日线("SPY").close
档名 = [nm for nm, _ in B.档位]


def 随机(T, P, 次数=1000, 种子=0):
    rng = np.random.default_rng(种子); syms = [s for s in 池 if len(池[s][5])]; w = np.array([len(池[s][5]) for s in syms], float); w /= w.sum()
    rk = T.风险ATR.to_numpy(); out = np.empty(次数)
    for it in range(次数):
        res = []
        for q in range(len(T)):
            s = syms[rng.choice(len(syms), p=w)]; o, h, l, c, A4, ix, _ = 池[s]; i = ix[rng.integers(len(ix))] + 1
            if i >= len(c) - 1: continue
            e = o[i]; st = e + rk[rng.integers(len(rk))] * A4[i - 1]
            rr, *_ = B.出(o, h, l, c, i, e, st, P); res.append(rr - 2 * B.FEE * e / (st - e))
        out[it] = np.mean(res)
    return out


def 报(T, P, 随=True, 种子=0):
    if not len(T): return {"笔": 0}
    s = C.统计(T.R, T.pct); s["时间段"] = f"{T.t.min().date()} ~ {T.出.max().date()}"
    m0 = spy.reindex(pd.to_datetime(T.t).dt.normalize(), method="ffill").to_numpy(); m1 = spy.reindex(pd.to_datetime(T.出).dt.normalize(), method="ffill").to_numpy()
    mk = (m1 / m0 - 1) * 100; s["同期SPY每笔%"] = round(float(np.nanmean(mk)), 2); s["扣掉大盘后每笔%"] = round(float(np.nanmean(T.pct.to_numpy() + mk)), 2)
    s["怎么走"] = T.怎么走.value_counts().to_dict()
    if 随:
        r = 随机(T, P, 种子=种子); s["随机对照"] = {"随机每笔R中位": round(float(np.median(r)), 3), "5%~95%": [round(float(np.percentile(r, 5)), 3), round(float(np.percentile(r, 95)), 3)], "我们排在第几分位": C.分位(s["每笔R"], r), "过95分位": bool(s["每笔R"] > np.percentile(r, 95))}
    return s


if __name__ == "__main__":
    res = {}
    for nm, P0 in B.档位:
        P = {**B.默认, **P0}; T = pd.read_csv(os.path.join(OUT, f"逐笔_{nm}.csv"), parse_dates=["t", "出", "进箱"]) if os.path.getsize(os.path.join(OUT, f"逐笔_{nm}.csv")) > 5 else pd.DataFrame()
        if not len(T): res[nm] = {"主": {"笔": 0}}; continue
        主 = T[T.sym.isin(B.主)]; 扩 = T[~T.sym.isin(B.主)]; 随 = nm == "默认"
        res[nm] = {"主（SPY QQQ SOXX）": 报(主, P, 随, 1), "扩（另 13 只）": 报(扩, P, 随, 2), "合起来": 报(T, P, 随, 3)}
        if nm == "默认":
            res[nm]["合起来·去掉2008年"] = 报(T[(T.t < "2008-01-01") | (T.t >= "2009-01-01")], P, False)
            res[nm]["合起来·按箱子"] = {f"{s} {str(b.date())}": (int(len(g)), round(float(g.R.sum()), 2)) for (s, b), g in T.groupby(["sym", "进箱"])}
        print(nm, {k: (v.get("笔"), v.get("每笔R")) for k, v in res[nm].items() if isinstance(v, dict) and "笔" in v}, flush=True)
    box = pd.read_csv(os.path.join(OUT, "箱子.csv"), parse_dates=["进箱", "出箱"])
    res["箱子"] = {"一共": int(len(box)), "2004年以前、没有小时线": int((box.get("备注") == "没有小时线").sum()) if "备注" in box else 0,
                 "按组": box.groupby("组").size().to_dict(), "出箱方向": {f"{a}·{b}": int(v) for (a, b), v in box.groupby(["组", "出箱后"]).size().items()}}
    json.dump(res, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(res["默认"], ensure_ascii=False, default=str)[:4000]); print(res["箱子"])
