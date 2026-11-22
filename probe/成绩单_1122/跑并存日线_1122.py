#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《376》联合回测的几条重跑一遍，这次把每天的净值、仓位、流水存下来，再套新成绩单。2015–2025，研发池，流动性池中档，含分红。
臂只留两条：A_原样（整个流动性池）、D_动量20加增长30（挑过票）。一条策略一个子进程。"""
import copy, io, json, os, subprocess, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out"); J = os.path.join(ROOT, "probe/联合_1122"); POOL = os.path.join(ROOT, "probe/流动性池_1114")
名单 = ["buy_and_hold", "trend_following", "技-1", "技-3-XING", "技-4-行业", "技-6-XING"]

def 跑一条(名):
    import yaml, numpy as np, pandas as pd, importlib.util
    sp = importlib.util.spec_from_file_location("lj", os.path.join(J, "联合回测_1122.py")); lj = importlib.util.module_from_spec(sp); sp.loader.exec_module(lj)
    sp = importlib.util.spec_from_file_location("cj", os.path.join(HERE, "成绩单_1122.py")); cj = importlib.util.module_from_spec(sp); sp.loader.exec_module(cj)
    B, FIX = lj.装()
    from engine import matrices, data, cache
    from engine_v2 import chain
    hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev); FIX.拿掉(m)
    def 膜(f): return pd.read_parquet(os.path.join(J, "out", f)).reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    liq = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet")); perf = liq.index
    liq = liq.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    base = m.universe & liq; sh = lambda a: np.vstack([np.zeros((1, a.shape[1]), bool), a[:-1]])
    臂 = {"A_原样": base, "D_动量20加增长30": base & sh(膜("掩膜_动量前20.parquet")) & sh(膜("掩膜_增长前30.parquet"))}
    C = cache._PANEL["close"].reindex(columns=list(m.symbols)).astype(float)
    res = {}
    for nm, u in 臂.items():
        m.universe = u
        r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True, pyramid=None)
        L = r.ledger
        if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
        eq = r.equity.reindex(perf).ffill(); ex = r.exposure.reindex(perf).fillna(0)
        pd.DataFrame({"eq": eq, "expo": ex}).to_parquet(os.path.join(OUT, f"日线_{名}_{nm}.parquet")); L.to_csv(os.path.join(OUT, f"流水_{名}_{nm}.csv"), index=False)
        one = {"策略": cj.成绩单(eq, L, ex), "同样仓位的标普": cj.成绩单(cj.等仓位标普(perf, ex))}
        if 名 != "buy_and_hold" and len(L):
            U = pd.DataFrame(u, index=m.index, columns=list(m.symbols))
            rs = [cj.成绩单(cj.随机进场(L, C, U, eq, 种子=k)) for k in range(10)]
            one["随机进场_10次中位"] = {k: (float(np.median([x[k] for x in rs])) if isinstance(rs[0].get(k), (int, float)) else None) for k in rs[0]}
            one["随机进场_每年赚pct_10次"] = sorted(x["每年赚pct"] for x in rs)
        res[nm] = one
        print(名, nm, {k: one["策略"][k] for k in ("每年赚pct", "最深亏损pct", "拿得住的占比pct")}, flush=True)
    json.dump({"名": 名, "臂": res}, io.open(os.path.join(OUT, f"成绩单_{名}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        try: 跑一条(sys.argv[2])
        except Exception:
            json.dump({"名": sys.argv[2], "跑失败": traceback.format_exc()[-2000:]}, io.open(os.path.join(OUT, f"成绩单_{sys.argv[2]}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        sys.exit(0)
    for n in 名单:
        if os.path.exists(os.path.join(OUT, f"成绩单_{n}.json")): continue
        t = time.time(); subprocess.run([sys.executable, __file__, "--one", n]); print("==", n, round(time.time() - t), "秒", flush=True)
    print("DONE")
