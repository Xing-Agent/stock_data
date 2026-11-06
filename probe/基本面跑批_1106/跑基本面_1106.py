# -*- coding: utf-8 -*-
"""
★★★ A 路 · 23 条基本面 · 跑批器(★ 可续跑:每条臂一个子进程、跑完立刻落盘)。

★ 用法:
  python3 probe/基本面跑批_1106/跑基本面_1106.py --list            # 列出全部臂
  python3 probe/基本面跑批_1106/跑基本面_1106.py --arm <臂名>       # 只跑一条(子进程里用)
  python3 probe/基本面跑批_1106/跑基本面_1106.py --all              # 逐条起子进程跑,已落盘的跳过

★★ 每条臂 = 一份配置 × 「扫参」里的一个点。
★★★ 落盘两样:流水 `ledgers/REAL__<臂名>.csv` + 结果 `arms/<臂名>.json`
   (含三把尺子:大盘替身 · 尺子C · 账户百分比 —— ★ 直接 import 仓库里那三份的「一条()」,不改它们)。
★★★ 跑失败也落盘(写明原因),报表打印器必须大声报 —— 规矩⑯。
★ engine 零改动:四层进程内覆盖层(新财报库 → 瘦身读法 → 基本面零件 → 本路策略零件)。
"""
from __future__ import annotations
import copy, gc, glob, io, json, os, subprocess, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CFG = os.path.join(HERE, "configs")
ARMS = os.path.join(HERE, "arms")
LED = os.path.join(HERE, "ledgers")
NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
SCOPE = "large_mid"                       # ★ 和挂闸/新策略同口径
PERF_START = "2015-01-01"                 # ★ 和挂闸同口径(新池日历 2014 起,留一年热机)


def 装层():
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    for d in ("probe/补齐能力_1106", "probe/基本面跑批_1106",
              "probe/v2_rerun_1030", "probe/friction_rerun_1104"):
        sys.path.insert(0, os.path.join(ROOT, d))
    import pandas as pd
    from engine import cache, data, pool_scope, pat6_ops
    pat6_ops.install()
    import 接新财报库_1106 as EXT, 瘦身财报库_1106 as SLIM
    import 基本面零件_1106 as PARTS, 策略零件_1106 as MINE
    import rerun_core_1030 as RC
    a = EXT.install(); b = SLIM.install(); c = PARTS.install(); d = MINE.install()
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path=NEWPOOL)
    data.PERF_START = PERF_START
    return RC, {"财报库": a.get("★家数"), "瘦身": b.get("只数"),
                "零件": len(c.get("★★新规则") or []), "本路": d.get("新规则")}


def 臂表() -> list[dict]:
    import yaml
    arms = []
    for f in sorted(glob.glob(os.path.join(CFG, "*.yaml"))):
        raw = yaml.safe_load(io.open(f, encoding="utf-8"))
        pts = raw.get("扫参") or [{"名": "唯一点", "覆盖": {}}]
        for p in pts:
            arms.append({"臂": f"{os.path.basename(f)[:-5]}·{p['名']}",
                         "配置": os.path.basename(f), "覆盖": p.get("覆盖") or {},
                         "档": p.get("档", "")})
    return arms


def _设(d: dict, path: str, v):
    """★ 覆盖写法:'universe.rules.0.params.rank_top_pct' → 逐级下钻。"""
    ks = path.split(".")
    cur = d
    for k in ks[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    last = ks[-1]
    if isinstance(cur, list):
        cur[int(last)] = v
    else:
        cur[last] = v


def 安全名(s: str) -> str:
    return s.replace("/", "／").replace(" ", "_")


def 跑一条(arm: dict) -> dict:
    import numpy as np, pandas as pd, yaml
    RC, 层 = 装层()
    from engine import chain, matrices, data, fundamentals as F
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(CFG, arm["配置"]), encoding="utf-8"))
    raw = copy.deepcopy(raw)
    for k, v in arm["覆盖"].items():
        _设(raw, k, v)
    t0 = time.time()
    cfg = chain.ChainConfig.from_dict(raw)
    m = matrices.build(cfg.raw, dev)
    scope = RC.apply_scope(m, SCOPE)
    t1 = time.time()
    res = chain.run_chain(cfg, dev, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & hs)
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")
    os.makedirs(LED, exist_ok=True)
    lp = os.path.join(LED, f"REAL__{安全名(arm['臂'])}.csv")
    led.to_csv(lp, index=False)

    rec = {"臂": arm["臂"], "配置": arm["配置"], "覆盖": arm["覆盖"], "档": arm["档"],
           "★层": 层, "池": f"研发池 {len(dev)} 只 · 口径 {SCOPE} · 留出池 {len(hs)} 只已排除",
           "窗口": f"{data.PERF_START} → {data.PERF_END}",
           "universe收窄": scope,
           "合格票日(universe)": int(m.universe.sum()),
           "合格进场(entry&universe)": int((m.entry & m.universe).sum()),
           "笔数": int(len(led)),
           "引擎留言": list(dict.fromkeys(matrices._DISABLED_LOG))[-12:],
           "建矩阵秒": round(t1 - t0, 1), "跑链秒": round(time.time() - t1, 1)}
    if len(led):
        hd = led["holding_days"].astype(float)
        rec.update({
            "每笔净收益率均值pct": round(float((led["net_pnl"] / led["notional_in"]).mean() * 100), 4),
            "胜率pct": round(float((led["net_pnl"] > 0).mean() * 100), 1),
            "持有交易日_中位": float(hd.median()), "持有交易日_均值": round(float(hd.mean()), 1),
            "不同股票数": int(led["symbol"].nunique()),
            "离场原因": led["reason"].value_counts().to_dict() if "reason" in led else "★ 流水里没有 reason 列",
            "进场年份分布": pd.to_datetime(led["entry_date"]).dt.year.value_counts().sort_index()
                         .to_dict(),
        })
    # ★★★ 三把尺子(★ 直接调仓库里的,不改它们)
    for 名, 路 in (("★★★大盘替身(主判据)", "probe/大盘替身_1106"),
                   ("尺子C(只量进场)", "probe/尺子C_1106"),
                   ("账户百分比(给用户看)", "probe/账户百分比_1106")):
        try:
            sys.path.insert(0, os.path.join(ROOT, 路))
            mod = {"probe/大盘替身_1106": "大盘替身_1106", "probe/尺子C_1106": "尺子C_1106",
                   "probe/账户百分比_1106": "按净值百分比_1106"}[路]
            M = __import__(mod)
            rec[名] = M.一条(lp) if len(led) else {"★算不出": "0 笔"}
        except Exception as e:
            rec[名] = {"★跑失败": f"{type(e).__name__}: {str(e)[:300]}"}
    return rec


def 臂文件(name: str) -> str:
    return os.path.join(ARMS, f"{安全名(name)}.json")


def main(argv) -> int:
    if "--list" in argv:
        for a in 臂表():
            done = "✓" if os.path.exists(臂文件(a["臂"])) else " "
            print(done, a["臂"], a["覆盖"])
        return 0
    if "--arm" in argv:
        name = argv[argv.index("--arm") + 1]
        arm = next(a for a in 臂表() if a["臂"] == name)
        os.makedirs(ARMS, exist_ok=True)
        try:
            rec = 跑一条(arm)
        except Exception as e:
            rec = {"臂": name, "★★★跑失败": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-3000:]}
        io.open(臂文件(name), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("✗ " if "★★★跑失败" in rec else "✓ ") + name, flush=True)
        return 0
    if "--all" in argv:
        only = argv[argv.index("--only") + 1] if "--only" in argv else None
        for a in 臂表():
            if only and not a["臂"].startswith(only):
                continue
            if os.path.exists(臂文件(a["臂"])):
                continue
            t = time.time()
            r = subprocess.run([sys.executable, __file__, "--arm", a["臂"]], cwd=ROOT)
            if not os.path.exists(臂文件(a["臂"])):
                # ★★★ 子进程被杀(多半是 OOM)—— 落一份失败记录,不悄悄跳过
                io.open(臂文件(a["臂"]), "w", encoding="utf-8").write(json.dumps(
                    {"臂": a["臂"], "★★★跑失败": f"子进程退出码 {r.returncode}(多半是 OOM 被杀)"},
                    ensure_ascii=False))
            print(f"   {a['臂']}  {time.time()-t:.0f}s", flush=True)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
