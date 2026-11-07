# -*- coding: utf-8 -*-
"""
★★★★★ 独立检查:**引擎的环境闸是不是用「明天的收盘」决定「明天开盘买不买」**。

★ 为什么做这个:★★ 那一路 1107 查出 #68(ER 用当天收盘决定当天在不在场),
   ★★★ 并立规矩㉙,其中一句:「**我自己写的任何自我担保都不算证据,
   必须有一个独立的检查去验它**」。→ ★ 这一份就是那个独立检查,
   ★★ 而且把范围从「他们那个分析脚本」扩到了「**引擎核心**」。

★★★ 读代码读出来的(engine/chain.py:759，★ 一个字节都没改):
    regime_next = bool(m.regime[i + 1]) if i + 1 < len(idx) else False
  ★ 而 `m.regime[k]` 由 matrices.regime_mask 算,用的是**第 k 天的收盘**
    (`b > b.rolling(n).mean()`,b[k] = 第 k 天收盘;regime 入包时**没有 shift**)。
  ★★ 循环结构:第 i 轮 ②「昨天收盘的信号,今天开盘买入」→ 成交价 `m.open[i]`。
  → ★★★★★ 所以「第 i+1 天开盘买入」这个动作,被 `regime[i+1]`(= 第 i+1 天**收盘**)决定。
     ★★ 关掉闸那一支同理:`regime[i+1]` 为假 → pending_exit → 第 i+1 天**开盘**卖出。

★★★ 这一份怎么验(★ A/B,engine 零改动):
   · A = 原样(`m.regime` 不动)
   · B = **把 m.regime 往后挪一天**(`regime[k] ← regime[k-1]`,第 0 天置 False)
     → ★★ 这样 chain 里的 `m.regime[i+1]` 取到的就是**第 i 天收盘**(今天),
       ★★★ 也就是「**今天收盘决定明天开盘买不买**」—— 正确口径。
★★ 判读:★ 如果 B 明显比 A 差,说明 A 那部分好成绩是**偷看来的**。
   ★★★ 方向预判(★ 事先写下,规矩①):**A 会比 B 好** ——
     因为 A 开闸的日子正好是「当天收盘站上均线」的日子,关闸的日子正好是收跌的日子。
"""
from __future__ import annotations
import copy, io, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "friction_rerun_1104"))
sys.path.insert(0, os.path.join(ROOT, "probe", "v2_rerun_1030"))
os.chdir(ROOT)

import yaml                                                        # noqa: E402
from engine import cache, chain, data, matrices, pool_scope, pat6_ops   # noqa: E402
import rerun_core_1030 as RC                                       # noqa: E402

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
CFG = "probe/新策略_1106/configs"
FCFG = "probe/基本面跑批_1106/configs"
OUT = os.path.join(HERE, "AB_报告_1107.json")

# ★ 四条挂了环境闸的配置(★ 全仓扫出来的,不是记的):逐个 A/B
目标 = [("融-1_震荡", CFG, {}), ("融-2_突破", CFG, {}), ("融-3_大波段", CFG, {})]


def 装层() -> dict:
    pat6_ops.install()
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    idx = pool_scope.PoolIndex(path=NEWPOOL)
    RC._IDX_CACHE["idx"] = idx
    data.PERF_START = "2015-01-01"
    return {"面板只数": int(cache._PANEL["close"].shape[1]),
            "PERF_START": data.PERF_START, "PERF_END": data.PERF_END}


def 一条(名: str, cfgdir: str, 覆盖: dict, dev: list[str]) -> dict:
    raw = yaml.safe_load(io.open(os.path.join(cfgdir, 名 + ".yaml"), encoding="utf-8"))
    raw = copy.deepcopy(raw)
    cfg = chain.ChainConfig.from_dict(raw)
    m = matrices.build(cfg.raw, dev)
    n开 = int(m.regime.sum()); n天 = int(len(m.regime))

    out = {"闸规则": [r.get("type") for r in (raw.get("regime") or {}).get("rules") or []],
           "flatten_when_off": (raw.get("regime") or {}).get("flatten_when_off", True),
           "闸开的天数": n开, "总天数": n天,
           "闸开比例pct": round(n开 / max(1, n天) * 100, 1)}

    def 跑(m2, tag):
        res = chain.run_chain(cfg, dev, data.PERF_START, data.PERF_END, m=m2)
        led = res.ledger
        if not len(led):
            return {"★跑失败": "0 笔"}
        pct = led["net_pnl"] / led["notional_in"] * 100.0
        return {"笔数": int(len(led)),
                "每笔净收益pct均值": round(float(pct.mean()), 4),
                "每笔净收益pct中位": round(float(pct.median()), 4),
                "胜率pct": round(float((led["net_pnl"] > 0).mean() * 100), 1),
                "总净盈亏": round(float(led["net_pnl"].sum()), 2),
                "持有交易日均值": round(float(led["holding_days"].astype(float).mean()), 1),
                "离场原因": led["reason"].value_counts().to_dict()}

    out["A_原样(可能偷看)"] = 跑(m, "A")

    # ★★★ B:把 regime 往后挪一天 —— engine 不动,只动我们手里这份 m
    m2 = copy.copy(m)
    r = np.asarray(m.regime, dtype=bool)
    m2.regime = np.concatenate([[False], r[:-1]])
    assert int(m2.regime.sum()) in (n开, n开 - 1, n开 + 1), "★ 挪一天不该改变开闸总天数"
    out["B_滞后一天(正确口径)"] = 跑(m2, "B")

    a, b = out["A_原样(可能偷看)"], out["B_滞后一天(正确口径)"]
    if "★跑失败" not in a and "★跑失败" not in b:
        out["★★★差多少"] = {
            "每笔均值 A−B(个百分点)": round(a["每笔净收益pct均值"] - b["每笔净收益pct均值"], 4),
            "总净盈亏 A−B": round(a["总净盈亏"] - b["总净盈亏"], 2),
            "总净盈亏 A/B 倍": (round(a["总净盈亏"] / b["总净盈亏"], 3)
                            if b["总净盈亏"] not in (0,) else None),
            "胜率 A−B(个百分点)": round(a["胜率pct"] - b["胜率pct"], 1),
            "笔数 A−B": a["笔数"] - b["笔数"]}
    return out


def main() -> int:
    层 = 装层()
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev = hold["研发池名单"]
    rep = {"★★★这一份在验什么":
           "引擎的环境闸是不是用「明天收盘」决定「明天开盘买不买」(engine/chain.py:759)",
           "★口径": {**层, "池": f"研发池 {len(dev)} 只(留出池一次没碰)",
                    "★★A/B 唯一差别": "B 把 m.regime 往后挪一天;其余一字不差",
                    "★★★engine改动": "零(只动我们手里那份 m 的一个数组)",
                    "⚠ 边界": "本份不做口径收窄(apply_scope),所以绝对数不与"
                             "《新策略结果_1106》对账;★★ 要看的是 A 和 B 的**差**"},
           "逐条": {}}
    for 名, d, ov in 目标:
        t = time.time()
        try:
            rep["逐条"][名] = 一条(名, d, ov, dev)
        except Exception as e:
            import traceback
            rep["逐条"][名] = {"★★★跑失败": f"{type(e).__name__}: {e}",
                              "traceback": traceback.format_exc()[-1500:]}
            print(f"  ✗✗✗ {名} {e}", flush=True)
            continue
        r = rep["逐条"][名]
        d2 = r.get("★★★差多少") or {}
        print(f"\n=== {名} (闸 {r['闸规则']} · 开闸 {r['闸开比例pct']}% 的天) ===", flush=True)
        for k in ("A_原样(可能偷看)", "B_滞后一天(正确口径)"):
            v = r[k]
            if "★跑失败" in v:
                print(f"   {k:22s} {v['★跑失败']}", flush=True)
            else:
                print(f"   {k:22s} 笔{v['笔数']:5d} 每笔均值 {v['每笔净收益pct均值']:+8.4f}% "
                      f"胜率 {v['胜率pct']:5.1f}% 总盈亏 {v['总净盈亏']:>14,.0f}", flush=True)
        if d2:
            print(f"   ★★★ 差:每笔 {d2['每笔均值 A−B(个百分点)']:+.4f}pp · "
                  f"总盈亏 A/B = {d2['总净盈亏 A/B 倍']} 倍 · 笔数差 {d2['笔数 A−B']}  "
                  f"({time.time()-t:.0f}s)", flush=True)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
