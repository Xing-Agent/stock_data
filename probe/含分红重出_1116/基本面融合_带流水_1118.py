#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基本面 + 融合 的配置 · 含分红 · 存逐笔流水和日净值（2026-11-18，给手册每条一页用）

大白话：和技术面那轮（技术面中档_带流水_1116）出同样的几个数：每年赚、最惨跌掉、胜率、盈亏比、
       赚钱的年数、一笔拿多久。区别只有选股范围：基本面和融合沿用原来的范围（研发池内成交额靠前的大中盘，
       口径 large_mid），不套技术面的流动性池。
engine/ 一个字节不改。只用研发池。一条一个子进程，可续跑。
"""
import copy, glob, io, json, os, subprocess, sys, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
# 1118 加：XING_EXCL_JUMP=1 时，把「一天跳三倍」清单里的票整只从选股范围里拿掉（数据可疑，疑似反向拆股没折算），结果另存
SUF = "_剔可疑票" if os.environ.get("XING_EXCL_JUMP") == "1" else ""
# 1118 晚加：XING_SPLIT_FIX=1 时，按数据组的并股事件表在内存里折算面板，并拿掉查不到 / 破产重组 / 断档的票，结果另存
按表 = os.environ.get("XING_SPLIT_FIX") == "1"
if 按表:
    SUF = "_按表折算"
OUT = os.path.join(HERE, "基本面融合_out" + SUF)
LED = os.path.join(HERE, "基本面融合_ledgers" + SUF)
EQ = os.path.join(HERE, "基本面融合_日净值" + SUF)
DIRS = ["probe/基本面跑批_1106/configs", "probe/fundamental_buildout_1030/configs_1030", "probe/新策略_1106/configs"]
sys.path.insert(0, os.path.join(ROOT, "probe/流动性池_1114"))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))


def 清单():
    out = []
    for d in DIRS:
        for f in sorted(glob.glob(os.path.join(ROOT, d, "*.yaml"))):
            b = os.path.basename(f)[:-5]
            if b.startswith(("_TEMPLATE", "buy_and_hold")):
                continue
            out.append((b, os.path.relpath(f, ROOT)))
    return out


def 跑一条(名, 路):
    import yaml, numpy as np, pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data
    from 跑技术面换池_1114 import 指标
    折算报告 = None
    if 按表:
        sys.path.insert(0, HERE)
        import 按表折算_1118 as FIX
        折算报告 = FIX.install()
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, 路), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    RC.apply_scope(m, B.SCOPE)
    剔 = 0
    if 按表:
        剔 = FIX.拿掉(m)
    elif SUF:
        bad = set(pd.read_csv(os.path.join(HERE, "一天跳三倍_清单_1118.csv"))["代码"].astype(str))
        cols = [m.col[x] for x in bad if x in m.col]
        m.universe[:, cols] = False
        剔 = len(cols)
    idx = m.index
    perf = idx[(idx >= pd.Timestamp(data.PERF_START)) & (idx <= pd.Timestamp(data.PERF_END))]
    yrs = (perf[-1] - perf[0]).days / 365.25
    res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END,
                          m=m, total_return=True)
    led = res.ledger
    if len(led) and (set(led["symbol"].astype(str)) & hs):
        raise RuntimeError("留出池漏进来")
    eq = res.equity.reindex(perf).ffill()
    os.makedirs(EQ, exist_ok=True)
    (eq / float(eq.dropna().iloc[0])).to_csv(os.path.join(EQ, 名 + ".csv"), header=["净值"])
    rec = {"名": 名, "配置": 路, "窗口": f"{perf[0].date()} → {perf[-1].date()}",
           "池": f"研发池内 {B.SCOPE} 口径", "分红": "含分红", "剔掉的可疑票只数": 剔, "按表折算了几处": (len(折算报告["折算了"]) if 折算报告 else 0), "笔数": int(len(led)),
           "平均仓位pct": round(float(res.exposure.reindex(perf).fillna(0).mean() * 100), 1), **指标(eq, yrs)}
    if len(led):
        os.makedirs(LED, exist_ok=True)
        led.to_csv(os.path.join(LED, 名 + ".csv"), index=False)
        r = (led["net_pnl"] / led["notional_in"]).astype(float)
        pnl = led["net_pnl"].astype(float)
        赢, 亏 = r[r > 0], r[r < 0]
        days = (pd.to_datetime(led["exit_date"]) - pd.to_datetime(led["entry_date"])).dt.days
        y0 = eq.resample("YE").last()
        ys = [float(y0.iloc[0] / eq.dropna().iloc[0] - 1)] + list(y0.pct_change().dropna().values)
        rec.update({
            "胜率pct": round(float((r > 0).mean() * 100), 1),
            "利润因子_按金额": round(float(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum()), 3) if (pnl < 0).any() else None,
            "盈亏比_平均赚除以平均亏": round(float(赢.mean() / -亏.mean()), 2) if len(赢) and len(亏) else None,
            "持有天数中位": float(days.median()),
            "按年_赚钱的年数": f"{sum(1 for v in ys if v > 0)} / {len(ys)}"})
    return rec


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    L = 清单()
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        路 = dict(L)[名]
        try:
            rec = 跑一条(名, 路)
        except Exception as e:
            rec = {"名": 名, "配置": 路, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-1500:]}
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    for 名, 路 in L:
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        r = subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
        if not os.path.exists(os.path.join(OUT, 名 + ".json")):
            io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(json.dumps(
                {"名": 名, "配置": 路, "跑失败": f"子进程退出码 {r.returncode}"}, ensure_ascii=False))
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
