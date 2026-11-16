#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术面 36 份配置 · 流动性池中档 · 含分红 · 这次把逐笔流水存下来（2026-11-16）

大白话：1114 那轮换池只存了年化和回撤，没存每一笔交易，所以胜率、盈亏比出不来。
       这轮同口径再跑一遍中档，把流水存下，手册每页成绩单要用的几个数一次出齐。
engine/ 一个字节不改。只用研发池。一条一个子进程，可续跑。
"""
import copy, io, json, os, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
POOL = os.path.join(ROOT, "probe/流动性池_1114")
OUT = os.path.join(HERE, "技术面中档_out")
LED = os.path.join(HERE, "技术面中档_ledgers")
sys.path.insert(0, POOL)
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))


def 跑一条(名):
    import yaml, numpy as np, pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data
    from 跑技术面换池_1114 import 指标
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    perf = mk.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END,
                          m=m, total_return=True)
    led = res.ledger
    if len(led) and (set(led["symbol"].astype(str)) & hs):
        raise RuntimeError("留出池漏进来")
    eq = res.equity.reindex(perf).ffill()
    rec = {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内流动性池中档", "分红": "含分红",
           "笔数": int(len(led)), "平均仓位pct": round(float(res.exposure.reindex(perf).fillna(0).mean() * 100), 1),
           **指标(eq, yrs)}
    if len(led):
        os.makedirs(LED, exist_ok=True)
        led.to_csv(os.path.join(LED, 名 + ".csv"), index=False)
        r = (led["net_pnl"] / led["notional_in"]).astype(float)
        pnl = led["net_pnl"].astype(float)
        赢, 亏 = r[r > 0], r[r < 0]
        days = (pd.to_datetime(led["exit_date"]) - pd.to_datetime(led["entry_date"])).dt.days
        rec.update({
            "胜率pct": round(float((r > 0).mean() * 100), 1),
            "利润因子_按金额": round(float(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum()), 3) if (pnl < 0).any() else None,
            "盈亏比_平均赚除以平均亏": round(float(赢.mean() / -亏.mean()), 2) if len(赢) and len(亏) else None,
            "平均每笔赚pct_赢的": round(float(赢.mean() * 100), 2) if len(赢) else None,
            "平均每笔亏pct_输的": round(float(亏.mean() * 100), 2) if len(亏) else None,
            "持有天数中位": float(days.median()),
            "按年_赚钱的年数": None})
        y = eq.resample("YE").last().pct_change().dropna()
        y0 = eq.resample("YE").last()
        first = float(y0.iloc[0] / eq.iloc[0] - 1)
        ys = [first] + list(y.values)
        rec["按年_赚钱的年数"] = f"{sum(1 for v in ys if v > 0)} / {len(ys)}"
    return rec


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    import glob
    names = [os.path.basename(f)[:-5] for f in sorted(glob.glob(os.path.join(ROOT, "engine/configs/技-*.yaml")))]
    names += ["trend_following", "trend_following-原著-唐奇安反向通道离场"]
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        try:
            rec = 跑一条(名)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1500:]}
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    for 名 in names:
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
        if not os.path.exists(os.path.join(OUT, 名 + ".json")):
            io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(json.dumps(
                {"名": 名, "跑失败": f"子进程退出码 {r.returncode}"}, ensure_ascii=False))
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
