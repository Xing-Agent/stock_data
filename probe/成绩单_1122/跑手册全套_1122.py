#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册技术面全部版本套新成绩单（Lin 11-22 21:09 同意排在最前）。两段时间：2015–2025、2005–2014。研发池、流动性池中档、含分红、不挂任何挂件（原样）。
每条存每天净值、仓位、流水；出：策略 / 同样仓位的标普 / 随机进场（5 次中位）。一条策略一个时间段一个子进程，可断点续跑。"""
import copy, io, json, os, subprocess, sys, time, traceback, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out_手册")
W2 = os.path.join(ROOT, "probe/两段时间_1120"); J = os.path.join(ROOT, "probe/联合_1122"); POOL = os.path.join(ROOT, "probe/流动性池_1114")
def mod(name, path):
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m

def 跑一条(名, 段):
    import yaml, numpy as np, pandas as pd
    cj = mod("cj", os.path.join(HERE, "成绩单_1122.py"))
    if 段 == "一":
        lj = mod("lj", os.path.join(J, "联合回测_1122.py")); B, FIX = lj.装()
        from engine import matrices, data, cache
        from engine_v2 import chain
        hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev, hs = hold["研发池名单"], set(hold["留出池名单"])
        raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
        m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev); FIX.拿掉(m)
        mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet")); s, e = data.PERF_START, data.PERF_END
    else:
        sys.path.insert(0, W2); sys.path.insert(0, ROOT)
        import 环境2004_1120 as ENV
        env = ENV.install(只留测试期=True); hs = env["留出池"]
        from engine import cache
        has = cache._PANEL["close"].loc[:ENV.END].notna().any(); dev = [x for x in env["dev"] if bool(has.get(x, False))]
        from engine import matrices, data
        from engine_v2 import chain
        raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
        m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
        mk = pd.read_parquet(os.path.join(W2, "流动性池掩膜2004_中.parquet")); s, e = ENV.START, ENV.END
    perf = mk.index; u = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool); m.universe = u
    r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, s, e, m=m, total_return=True, pyramid=None)
    L = r.ledger
    if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
    eq = r.equity.reindex(perf).ffill(); ex = r.exposure.reindex(perf).fillna(0)
    pd.DataFrame({"eq": eq, "expo": ex}).to_parquet(os.path.join(OUT, f"日线_{段}_{名}.parquet")); L.to_csv(os.path.join(OUT, f"流水_{段}_{名}.csv"), index=False)
    one = {"策略": cj.成绩单(eq, L, ex), "同样仓位的标普": cj.成绩单(cj.等仓位标普(perf, ex)), "不算连亏的拿得住pct": cj.生存率(eq, None)[0]}
    if len(L) and 名 != "buy_and_hold":
        C = cache._PANEL["close"].reindex(columns=list(m.symbols)).astype(float); U = pd.DataFrame(u, index=m.index, columns=list(m.symbols))
        rs = [cj.成绩单(cj.随机进场(L, C, U, eq, 种子=k)) for k in range(5)]
        one["随机进场_5次中位"] = {k: float(np.median([x[k] for x in rs])) for k in ("每年赚pct", "最深亏损pct", "每年赚除以最深亏损", "溃疡绩效", "最差一年pct", "拿得住的占比pct")}
        one["随机进场_每年赚pct_5次"] = sorted(x["每年赚pct"] for x in rs)
    return {"名": 名, "段": 段, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "结果": one}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 3 and sys.argv[1] == "--one":
        名, 段 = sys.argv[2], sys.argv[3]; t = time.time()
        try: rec = 跑一条(名, 段)
        except Exception as ex_: rec = {"名": 名, "段": 段, "跑失败": f"{type(ex_).__name__}: {ex_}", "traceback": traceback.format_exc()[-2000:]}
        rec["秒"] = round(time.time() - t, 1)
        json.dump(rec, io.open(os.path.join(OUT, f"成绩单_{段}_{名}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(("FAIL " if "跑失败" in rec else "ok   ") + 段, 名, rec["秒"], flush=True); sys.exit(0)
    names = ["buy_and_hold"] + mod("w2", os.path.join(W2, "跑第二段_1120.py")).名单()
    for 段 in ("一", "二"):
        for n in names:
            if os.path.exists(os.path.join(OUT, f"成绩单_{段}_{n}.json")): continue
            subprocess.run([sys.executable, __file__, "--one", n, 段])
    print("DONE")
