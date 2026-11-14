#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大波段闸四道检验的前三道 + 两个对照版（2026-11-14 · Lin 1112 拍板《172》第 1 条）

大白话：大盘闸 =「SPY 在 200 日线上方，且 200 日线近 20 天在往上走」才允许开新仓（不强平）。
       这里只在 2015–2025、研发池里看它稳不稳：
       第一道  判定日往后挪 0 / 1 / 2 天，三版方向一不一样
       第二道  均线换 160 / 180 / 200 / 220 / 240 五个点，几个同向
       第三道  同一类的几条策略用同一套参数（这里每条都是同一套，逐条列）
       第四道  2004–2014 和留出池 —— 本脚本不做：留出池只能最后用一次，等 Lin 说跑再跑
       对照甲  去掉「20 日斜率」
       对照乙  用「研发池里站上自己 200 日线的比例」代替 SPY（比例门槛原著没给 → 40 / 50 / 60 三点）

「同向」的定义（跑前写死）：挂闸版的卡玛 − 不挂闸版的卡玛 的正负号。同时列年化和回撤，不只看一个数。
选股范围：流动性池「中」档（新规则）。策略侧含分红。engine/ 一个字节不改：闸是在内存里换 m.regime。
"""
import copy
import io
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
POOL = os.path.join(ROOT, "probe/流动性池_1114")
大波段类 = ["技-1", "技-1-原著-唐奇安反向通道离场", "trend_following", "trend_following-原著-唐奇安反向通道离场"]


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    sys.path.insert(0, POOL)
    import yaml
    import numpy as np
    import pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data, cache
    from 跑技术面换池_1114 import 指标
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    原闸 = (raw.get("regime") or {}).get("rules") or []
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    reg0 = m.regime.copy()
    idx = m.index
    start, end = data.PERF_START, data.PERF_END
    perf = mk.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    # 对照乙用的广度：研发池每只票收盘在自己 200 日线上方的比例（只算有 200 日线的票）
    cl = cache._PANEL["close"][[s for s in dev if s in cache._PANEL["close"].columns]].astype(float).reindex(idx)
    ma = cl.rolling(200, min_periods=200).mean()
    广度 = ((cl > ma) & ma.notna()).sum(axis=1) / ma.notna().sum(axis=1).replace(0, np.nan)

    def spy闸(n, 斜率=True):
        rules = [{"type": "index_above_ma", "params": {"symbol": "SPY", "ma": n}}]
        if 斜率:
            rules.append({"type": "index_ma_slope", "params": {"symbol": "SPY", "ma": n, "lookback": 20}})
        return matrices.regime_mask({"rules": rules}, idx, None, None).to_numpy(dtype=bool)

    def 跑(reg, 挪=0):
        r = reg.copy()
        if 挪:
            r = np.concatenate([np.zeros(挪, dtype=bool), r[:-挪]])
        m.regime = reg0 & r
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, start, end, m=m,
                              total_return=True)
        if len(res.ledger) and (set(res.ledger["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        eq = res.equity.reindex(perf).ffill()
        ex = res.exposure.reindex(perf).fillna(0.0)
        开 = pd.Series(m.regime, index=idx).reindex(perf)
        return {"笔数": int(len(res.ledger)), "平均仓位pct": round(float(ex.mean() * 100), 1),
                "闸开着的天数占比pct": round(float(开.mean() * 100), 1), **指标(eq, yrs)}

    全开 = np.ones(len(idx), dtype=bool)
    版 = {"不挂闸": 跑(全开)}
    for n in (160, 180, 200, 220, 240):
        版[f"均线{n}_带斜率_挪0天"] = 跑(spy闸(n))
    for k in (1, 2):
        版[f"均线200_带斜率_挪{k}天"] = 跑(spy闸(200), 挪=k)
    版["对照甲_均线200_不带斜率"] = 跑(spy闸(200, 斜率=False))
    for thr in (40, 50, 60):
        版[f"对照乙_研发池站上200日线比例大于{thr}pct"] = 跑((广度 > thr / 100.0).fillna(False).to_numpy(dtype=bool))
    基 = 版["不挂闸"]
    for k, v in 版.items():
        if k != "不挂闸" and v["卡玛"] is not None and 基["卡玛"] is not None:
            v["卡玛差_挂减不挂"] = round(v["卡玛"] - 基["卡玛"], 3)
            v["年化差pct"] = round(v["复合年化pct"] - 基["复合年化pct"], 2)
            v["回撤差pct"] = round(v["最大回撤pct"] - 基["最大回撤pct"], 2)
    号 = lambda ks: [(版[k].get("卡玛差_挂减不挂") or 0) > 0 for k in ks]
    一 = 号(["均线200_带斜率_挪0天", "均线200_带斜率_挪1天", "均线200_带斜率_挪2天"])
    二 = 号([f"均线{n}_带斜率_挪0天" for n in (160, 180, 200, 220, 240)])
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内的流动性池「中」档",
            "配置里原有的闸条数": len(原闸), "分红": "策略侧含分红",
            "第一道_挪0_1_2天_卡玛变好的版数": f"{sum(一)} / 3", "第一道_三版同向": len(set(一)) == 1,
            "第二道_五个均线点_卡玛变好的点数": f"{sum(二)} / 5", "第二道_至少四个同向": max(sum(二), 5 - sum(二)) >= 4,
            "各版": 版}


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        t = time.time()
        try:
            rec = 跑一条(名)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
        rec["总秒"] = round(time.time() - t, 1)
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    import subprocess
    for 名 in 大波段类:
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
