#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""技术面配置换到流动性池里重跑（2026-11-14 · Lin 1112 拍板《172》第 2 条 + 两列内部对照的第一列）

大白话：同一条策略跑四遍 —— 老池子（当年成交额前 2000 名）一遍，
       流动性池的低 / 中 / 高三个门槛各一遍，老的新的并排放。
       每一遍都带上：主对标（机会集宽基）、副对标（满仓 SPY）、国库券及格线、
       同等仓位基准（每天实际仓位 x 主对标 + 其余 x 国库券）。

engine/ 一个字节不改：换池是在内存里把 ① 的掩膜换掉。只用研发池。
策略侧和对标侧都含分红（补分红_1107 进程内安装 + total_return=True）。
国库券：仓库里只有 DTB3（贴现口径），第 41 轮定的是 DGS3MO —— 这里临时用 DTB3 并写明。
每条配置一个子进程，跑完落盘，可续跑。
"""
import copy
import glob
import gzip
import io
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
EQ = os.path.join(HERE, "日净值")


def 清单():
    return [os.path.basename(f)[:-5] for f in sorted(glob.glob(os.path.join(ROOT, "engine/configs/技-*.yaml")))]


def 出文件(名):
    return os.path.join(OUT, 名 + ".json")


def 指标(eq, yrs):
    import numpy as np
    eq = eq.dropna()
    v = float(eq.iloc[-1] / eq.iloc[0])
    ann = v ** (1 / yrs) - 1 if v > 0 else None
    dd = float((eq / eq.cummax() - 1).min())
    return {"复合年化pct": None if ann is None else round(ann * 100, 2),
            "最大回撤pct": round(dd * 100, 2),
            "卡玛": (round(ann / abs(dd), 3) if (ann is not None and dd < 0) else None)}


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    import yaml
    import numpy as np
    import pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    t0 = time.time()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    m = matrices.build(cfg.raw, dev)
    u0 = m.universe.copy()
    start, end = data.PERF_START, data.PERF_END
    宽基 = pd.read_csv(os.path.join(HERE, "机会集宽基_日净值.csv"), index_col=0, parse_dates=True)
    perf = 宽基.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    spy_r, spy_div = data.benchmark_total_return_daily("SPY", perf)
    spy_eq = (1 + spy_r.reindex(perf).fillna(0.0)).cumprod()
    d = json.load(gzip.open(os.path.join(ROOT, "market_macro_1105/DTB3/daily.json.gz")))["data"]
    rf = pd.Series({pd.Timestamp(x["date"]): x["close"] for x in d if x["close"] is not None}).sort_index()
    rf_d = (rf / 100.0 / 252.0).reindex(perf, method="ffill").fillna(0.0)
    rf_eq = (1 + rf_d).cumprod()

    def 跑(掩膜名, 含分红=True):
        if 掩膜名 == "老池子":
            m.universe = u0.copy()
            RC.apply_scope(m, B.SCOPE)
        else:
            mk = pd.read_parquet(os.path.join(HERE, f"流动性池掩膜_{掩膜名}.parquet"))
            mk = mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
            m.universe = u0 & mk
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, start, end, m=m,
                              total_return=含分红)
        led = res.ledger
        if len(led) and (set(led["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        eq = res.equity.reindex(perf).ffill()
        ex = res.exposure.reindex(perf).fillna(0.0)
        r = {"笔数": int(len(led)), "平均仓位pct": round(float(ex.mean() * 100), 1), **指标(eq, yrs)}
        if 掩膜名 != "老池子":
            b = 宽基[f"机会集宽基_{掩膜名}"]
            br = b.pct_change().fillna(0.0)
            同 = (1 + ex.shift(1).fillna(0.0) * br + (1 - ex.shift(1).fillna(0.0)) * rf_d).cumprod()
            r["主对标_机会集宽基"] = 指标(b, yrs)
            r["同等仓位基准"] = 指标(同, yrs)
        return r, eq

    rec = {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": f"研发池 {len(dev)} 只",
           "分红": "策略侧、对标侧都含分红", "SPY含分红": bool(spy_div),
           "国库券口径": "DTB3（临时；第 41 轮定的是 DGS3MO，仓库里还没有）",
           "副对标_满仓SPY": 指标(spy_eq, yrs), "国库券及格线": 指标(rf_eq, yrs), "各版": {}}
    os.makedirs(EQ, exist_ok=True)
    eqs = {}
    for k in ("老池子", "低", "中", "高"):
        rec["各版"][k], eqs[k] = 跑(k)
    # 对账用：老池子、策略侧不含分红 —— 和微仓诊断、此前跑批同一口径（引擎默认不开分红）
    rec["各版"]["老池子_不含分红_对账用"], eqs["老池子_不含分红"] = 跑("老池子", 含分红=False)
    pd.DataFrame(eqs).to_csv(os.path.join(EQ, 名 + ".csv"))
    rec["总秒"] = round(time.time() - t0, 1)
    return rec


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        try:
            rec = 跑一条(名)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
        io.open(出文件(名), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    for 名 in 清单():
        if os.path.exists(出文件(名)):
            continue
        t = time.time()
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
        if not os.path.exists(出文件(名)):
            io.open(出文件(名), "w", encoding="utf-8").write(json.dumps(
                {"名": 名, "跑失败": f"子进程退出码 {r.returncode}"}, ensure_ascii=False))
        print(f"   {名}  {time.time() - t:.0f}s", flush=True)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
