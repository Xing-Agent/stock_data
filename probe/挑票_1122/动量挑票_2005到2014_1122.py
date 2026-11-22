#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""挑票的另一个十年：动量挑票在 2005–2014 再验（《376》只验过 2015–2025；增长数据这一段没有，只验动量）。引擎外、研发池、流动性池中档、含分红。
动量的算法和《376》一样：过去 12 个月涨幅（跳过最近 1 个月）在流动性池里排前 20%（另跑 10% / 30%）；收盘定、第二天才用。
每条存每天净值、仓位、流水，出新成绩单。一条策略一个子进程，可断点续跑。"""
import copy, io, json, os, subprocess, sys, time, traceback, importlib.util
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
W2 = os.path.join(ROOT, "probe/两段时间_1120")
名单 = ["buy_and_hold", "trend_following", "技-3-XING", "技-6-XING", "技-1", "技-4-行业"]
def mod(n, p):
    sp = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m

def 跑一条(名):
    import yaml, numpy as np, pandas as pd
    cj = mod("cj", os.path.join(ROOT, "probe/成绩单_1122/成绩单_1122.py"))
    sys.path.insert(0, W2); sys.path.insert(0, ROOT)
    import 环境2004_1120 as ENV
    env = ENV.install(只留测试期=True); hs = env["留出池"]
    from engine import cache, matrices, data
    from engine_v2 import chain
    has = cache._PANEL["close"].loc[:ENV.END].notna().any(); dev = [x for x in env["dev"] if bool(has.get(x, False))]
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(W2, "流动性池掩膜2004_中.parquet")); perf = mk.index
    liq = mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).astype(bool)
    c = cache._PANEL["close"].reindex(index=m.index, columns=list(m.symbols)).astype(float)
    mom = (c.shift(21) / c.shift(252) - 1).where(liq); rk = mom.rank(axis=1, pct=True, ascending=False)
    sh = lambda a: np.vstack([np.zeros((1, a.shape[1]), bool), a[:-1]])
    base = m.universe & liq.to_numpy()
    臂 = {"A_原样": base}
    for p in (10, 20, 30): 臂[f"B_动量前{p}"] = base & sh((rk <= p / 100).to_numpy())
    res = {"每天动量前20几只_中位": int((rk <= 0.2).loc[perf[0]:perf[-1]].sum(axis=1).median())}
    for nm, u in 臂.items():
        m.universe = u
        r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, ENV.START, ENV.END, m=m, total_return=True, pyramid=None)
        L = r.ledger
        if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
        eq = r.equity.reindex(perf).ffill(); ex = r.exposure.reindex(perf).fillna(0)
        pd.DataFrame({"eq": eq, "expo": ex}).to_parquet(os.path.join(OUT, f"日线_{名}_{nm}.parquet")); L.to_csv(os.path.join(OUT, f"流水_{名}_{nm}.csv"), index=False)
        one = {"策略": cj.成绩单(eq, L, ex), "同样仓位的标普": cj.成绩单(cj.等仓位标普(perf, ex))}
        if len(L):
            p_ = L.groupby("symbol")["net_pnl"].sum().sort_values(ascending=False); tot = float(L["net_pnl"].sum())
            one["最赚的5只票占总利润pct"] = round(float(p_.head(5).sum() / tot * 100), 1) if tot > 0 else None
            yr = eq.groupby(eq.index.year).last(); one["分年pct"] = {int(y): round(float(v) * 100, 1) for y, v in (yr / yr.shift(1).fillna(eq.iloc[0]) - 1).items()}
        res[nm] = one
        print(名, nm, {k: one["策略"][k] for k in ("每年赚pct", "最深亏损pct", "每年赚除以最深亏损")}, flush=True)
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "臂": res}

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        名 = sys.argv[2]; t = time.time()
        try: rec = 跑一条(名)
        except Exception as e: rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
        rec["秒"] = round(time.time() - t, 1)
        json.dump(rec, io.open(os.path.join(OUT, f"结果_{名}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, rec["秒"], flush=True); sys.exit(0)
    for n in 名单:
        if os.path.exists(os.path.join(OUT, f"结果_{n}.json")): continue
        subprocess.run([sys.executable, __file__, "--one", n])
    print("DONE")
