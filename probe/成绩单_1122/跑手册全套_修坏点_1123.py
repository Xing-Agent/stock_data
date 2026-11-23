#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2005–2014 那一段，套上数据组 11-23 给的修正后重跑手册全部版本（引擎不动：只在本进程里改内存中的行情面板）。
修正来源：market_ext_1105/日线修正_1123/ —— 优先核的47处（漏记拆股 19、分拆 9：之前的价格 × 系数、量 ÷ 系数；价格坏了 6）、
待核清单里 Yahoo 有记录的漏记拆股 25 处、三只票的修正（TYC、DUK）、MS 2004-01~2006-01-13 整段换成摩根士丹利、2007-06-13 那 13 只当天用前一天的收盘顶上。
其余约 180 处「待核」没动（数据组还在核）。输出到 out_手册_修/，文件名和原来一样，可断点续跑。"""
import io, os, sys, subprocess, json
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); FIXD = os.path.join(ROOT, "market_ext_1105/日线修正_1123")
def 修面板():
    import pandas as pd, numpy as np
    from engine import cache
    P = cache._PANEL; cols = set(P["close"].columns); idx = P["close"].index; log = []
    adj = {}
    a = pd.read_csv(os.path.join(FIXD, "优先核的47处_1123.csv"), encoding="utf-8-sig")
    for _, r in a[a["系数"].notna()].iterrows(): adj[(r["代码"], str(r["日期"])[:10])] = float(r["系数"])
    b = pd.read_csv(os.path.join(FIXD, "2005-2014面板_单日跳超30pct且没记拆股_待核.csv"))
    for _, r in b[b["应补系数"].notna()].iterrows(): adj.setdefault((r["代码"], str(r["日期"])[:10]), float(r["应补系数"]))
    c = pd.read_csv(os.path.join(FIXD, "三只票的修正.csv"))
    for _, r in c[c["系数"].notna()].iterrows(): adj.setdefault((r["代码"], str(r["从哪天"])[:10]), float(r["系数"]))
    for (s, d), k in sorted(adj.items()):
        if s not in cols: log.append(f"不在面板 {s}"); continue
        m = idx < pd.Timestamp(d)
        for f in ("open", "high", "low", "close"): P[f].loc[m, s] = P[f].loc[m, s].astype(float) * k
        P["volume"].loc[m, s] = P["volume"].loc[m, s].astype(float) / k
        log.append(f"{s} {d} ×{k}")
    if "MS" in cols:
        y = pd.read_csv(glob_ms(), parse_dates=["date"]).set_index("date"); y = y[y.index.isin(idx)]
        for f in ("open", "high", "low", "close", "volume"): P[f].loc[y.index, "MS"] = y[f].astype(float).values
        if "dollar_volume" in P: P["dollar_volume"].loc[y.index, "MS"] = (y.close * y.volume).values
        log.append(f"MS 换 {len(y)} 天")
    d0 = pd.Timestamp("2007-06-13")
    if d0 in idx:
        i = idx.get_loc(d0)
        for s in "PNFP IDXX BBBY IDTI SGEN SIRI PTC SLAB AMZN ACGL NTCT CAB SLGN".split():
            if s in cols:
                pv = float(P["close"][s].iloc[i - 1])
                for f in ("open", "high", "low", "close"): P[f].loc[d0, s] = pv
        log.append("2007-06-13 十三只用前收顶上")
    d1 = pd.Timestamp("2014-01-16")
    if "NUS" in cols and d1 in idx: P["close"].loc[d1, "NUS"] = 84.8; P["low"].loc[d1, "NUS"] = min(float(P["low"].loc[d1, "NUS"]), 84.8); log.append("NUS 2014-01-16 收盘改 84.8")
    return log
def glob_ms():
    import glob; return glob.glob(os.path.join(FIXD, "MS_*.csv"))[0]

if __name__ == "__main__":
    src = io.open(os.path.join(HERE, "跑手册全套_1122.py"), encoding="utf-8").read().split('if __name__ == "__main__":')[0]
    src = src.replace('OUT = os.path.join(HERE, "out_手册")', 'OUT = os.path.join(HERE, "out_手册_修")')
    hook = 'env = ENV.install(只留测试期=True); hs = env["留出池"]'
    assert hook in src
    src = src.replace(hook, hook + '\n        import 跑手册全套_修坏点_1123 as _X; _log = _X.修面板(); print("修正", len(_log), flush=True)')
    g = {"__file__": os.path.join(HERE, "跑手册全套_1122.py"), "__name__": "orig"}; sys.path.insert(0, HERE); exec(compile(src, "orig", "exec"), g)
    OUT = g["OUT"]
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        import time, traceback
        名 = sys.argv[2]; t = time.time()
        try: rec = g["跑一条"](名, "二")
        except Exception as ex_: rec = {"名": 名, "段": "二", "跑失败": f"{type(ex_).__name__}: {ex_}", "traceback": traceback.format_exc()[-2000:]}
        rec["秒"] = round(time.time() - t, 1)
        json.dump(rec, io.open(os.path.join(OUT, f"成绩单_二_{名}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        print(("FAIL " if "跑失败" in rec else "ok   "), 名, rec["秒"], flush=True); sys.exit(0)
    names = ["buy_and_hold"] + g["mod"]("w2", os.path.join(g["W2"], "跑第二段_1120.py")).名单()
    for n in names:
        if os.path.exists(os.path.join(OUT, f"成绩单_二_{n}.json")): continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", n])
    print("DONE")
