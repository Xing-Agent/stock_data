# -*- coding: utf-8 -*-
"""
★★★ 基-7 烟蒂 · **留出池复验** —— ★ 照《99》预先登记跑,★★★ 判据写死在《99》,这里只产数。

★ 为什么另写一份(不改 `跑基本面_1106.py`):
   ★★ 那一份把池子**写死成研发池**,并且断言「留出池漏进来就报错」——
   ★★★ 本次要跑的正是留出池 → ★ 改它会破坏那 33 条的可重跑性(而且它正被别的会话用)。
   → ★★ 所以这里**只 import 它的装层/工具**,池子换成留出池,engine 零改动。

★ 用法(★★ 可续跑:每条臂一个子进程、跑完立刻落盘):
  python3 probe/基-7留出池复验_1107/跑留出池_1107.py --list
  python3 probe/基-7留出池复验_1107/跑留出池_1107.py --arm 基-7_早期巴菲特烟蒂·八毛
  python3 probe/基-7留出池复验_1107/跑留出池_1107.py --all

★★★ 口径(★ 和研发池那 33 条逐项一致,否则不可比):
   · 池子:**留出池 583 只**(★ `holdout_newpool_1106.json` 的「留出池名单」)
   · 口径收窄:`large_mid`(★ 和 SCOPE 同)· 窗口 PERF_START=2015-01-01
   · 考卷那 1,042 只在烤盘阶段已排除,不在本名单内
★★★ 主判据只有「八毛」一条(《99》写死);五毛/三分之二**只作三点同向的旁证**。
"""
from __future__ import annotations
import copy, io, json, os, subprocess, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "基本面跑批_1106"))
os.chdir(ROOT)

import 跑基本面_1106 as A                                   # noqa: E402

ARMS = os.path.join(HERE, "arms")
LED = os.path.join(HERE, "ledgers")
主臂 = "基-7_早期巴菲特烟蒂·八毛"
本族 = "基-7_早期巴菲特烟蒂"


def 臂表() -> list[dict]:
    """★ 只取 基-7 这一族的三个点(★★ 主判据是八毛,另两点只作旁证)。"""
    return [a for a in A.臂表() if a["配置"].startswith(本族)]


def 跑一条(arm: dict) -> dict:
    import numpy as np, pandas as pd, yaml
    RC, 层 = A.装层()
    from engine import chain, matrices, data

    hold = json.load(io.open(A.HOLD, encoding="utf-8"))
    dev, hs = set(hold["研发池名单"]), hold["留出池名单"]
    assert len(hs) == hold["留出池只数"], "★★★ 留出池名单长度和 json 自报的不一致"

    raw = copy.deepcopy(yaml.safe_load(
        io.open(os.path.join(A.CFG, arm["配置"]), encoding="utf-8")))
    for k, v in arm["覆盖"].items():
        A._设(raw, k, v)

    t0 = time.time()
    cfg = chain.ChainConfig.from_dict(raw)
    m = matrices.build(cfg.raw, hs)                 # ★★★ 池子 = 留出池
    scope = RC.apply_scope(m, A.SCOPE)
    t1 = time.time()
    res = chain.run_chain(cfg, hs, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger

    # ★★★ 反向泄漏检查:研发池的票**不许**出现在留出池的流水里
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & dev)
        if leaked:
            raise RuntimeError(f"★★★ 研发池漏进来了 {len(leaked)} 只:{leaked[:10]}")

    os.makedirs(LED, exist_ok=True)
    lp = os.path.join(LED, f"HOLD__{A.安全名(arm['臂'])}.csv")
    led.to_csv(lp, index=False)

    rec = {"臂": arm["臂"], "配置": arm["配置"], "覆盖": arm["覆盖"], "档": arm["档"],
           "★这是主判据吗": (arm["臂"] == 主臂), "★层": 层,
           "池": f"★★★留出池 {len(hs)} 只 · 口径 {A.SCOPE} · 研发池 {len(dev)} 只已排除",
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
            "离场原因": (led["reason"].value_counts().to_dict()
                      if "reason" in led else "★ 流水里没有 reason 列"),
            "进场年份分布": pd.to_datetime(led["entry_date"]).dt.year
                         .value_counts().sort_index().to_dict(),
        })
    return rec


def 臂文件(name: str) -> str:
    return os.path.join(ARMS, f"{A.安全名(name)}.json")


def main(argv) -> int:
    if "--list" in argv:
        for a in 臂表():
            print(("✓" if os.path.exists(臂文件(a["臂"])) else " "),
                  a["臂"], a["覆盖"], ("← ★★★主判据" if a["臂"] == 主臂 else ""))
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
        # ★★★ 主臂先跑(它是唯一主判据),另两点作旁证
        表 = sorted(臂表(), key=lambda a: (a["臂"] != 主臂, a["臂"]))
        for a in 表:
            if os.path.exists(臂文件(a["臂"])):
                print(f"   跳过(已落盘) {a['臂']}", flush=True)
                continue
            t = time.time()
            r = subprocess.run([sys.executable, __file__, "--arm", a["臂"]], cwd=ROOT)
            if not os.path.exists(臂文件(a["臂"])):
                io.open(臂文件(a["臂"]), "w", encoding="utf-8").write(json.dumps(
                    {"臂": a["臂"],
                     "★★★跑失败": f"子进程退出码 {r.returncode}(多半是 OOM 被杀)"},
                    ensure_ascii=False))
            print(f"   {a['臂']}  {time.time()-t:.0f}s", flush=True)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
