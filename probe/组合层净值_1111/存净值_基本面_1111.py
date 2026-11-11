#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把基本面那批的「组合层每日净值」存下来（2026-11-11）

★★★★★ 为什么重写：我第一版想**从流水反推**净值，★★ 方向整个是错的 ——
   ★ 引擎第 605~615 行是**每天用当时净值重算仓位**的（复利）：
       `equity_now = cash + Σ shares×price`
       `by_risk = (equity_now * rf) / (entry_px - stop0) * entry_px`
   ★★★★★ 也就是说**仓位本身是净值的函数** → ★★ 事后按流水记现金**永远对不上**，顺序反了。
   ★★★ 实测症状：净值跑成负数（`invalid value encountered in scalar power`）。

★ 而引擎本来就产出净值 —— `engine/chain.py:135  equity: pd.Series  # 净值(已扣摩擦)`。
★★★★★ 所以正确做法是**重跑 chain 把 equity 存盘**，不是反推。

★★ 本脚本**只加一件事**：复用 `跑基本面_1106.py` 自己的 `装层()` / `臂表()` / 配置，
   跑完把 `res.equity` 和 `res.equity_gross` 写成 csv。
   ★★★ 口径、池子、窗口、摩擦**一个字都不改** —— ★★★★★ 改了就不能和已有成绩对照。

★ 不碰 engine/ 一个字节。
"""
import io
import json
import os
import sys
import time

import numpy as np
import pandas as pd

ROOT = "/home/claude/xing-agent-stock_data"
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
OUT = os.path.join(ROOT, "probe/组合层净值_1111/出_基本面")
os.makedirs(OUT, exist_ok=True)


def 指标(nv, 在场率):
    nv = nv.dropna()
    if len(nv) < 60 or nv.iloc[0] <= 0 or nv.iloc[-1] <= 0:
        return {"★": "净值不可用（点数不足或出现非正值）", "点数": len(nv)}
    年数 = (nv.index[-1] - nv.index[0]).days / 365.25
    # ★★★★★ 复合年化（Lin 2026-11-11 15:10 定）：空仓的日子也算在内
    cagr = (nv.iloc[-1] / nv.iloc[0]) ** (1 / 年数) - 1
    回撤 = nv / nv.cummax() - 1
    mdd = 回撤.min()
    水下, 最长, 当前 = 回撤 < 0, 0, 0
    for v in 水下:
        当前 = 当前 + 1 if v else 0
        最长 = max(最长, 当前)
    日 = nv.pct_change().dropna()
    下 = 日[日 < 0]
    return {
        "起": str(nv.index[0].date()), "止": str(nv.index[-1].date()), "年数": round(年数, 2),
        "复合年化%": round(cagr * 100, 2),
        "最大回撤%": round(mdd * 100, 2),
        "最长水下天数": int(最长),
        "卡玛": round(cagr / abs(mdd), 3) if mdd < 0 else None,
        "索提诺": round(cagr / (下.std() * np.sqrt(252)), 3) if len(下) > 5 and 下.std() > 0 else None,
        "在场率%": round(在场率 * 100, 1) if 在场率 is not None else None,
    }


def main(只跑=None):
    """★★★★★ 结构改过一次（★ 记在这里）：
    【第一版】33 条臂在**同一个进程**里连着跑 → 🔴 **被 OOM 杀掉**
      ★ 症状：日志只有 6 行、`echo EXIT=` 一次都没执行（★★ 进程是被杀的，不是正常退出）
      ★★★ 原因：每条臂都要 `matrices.build(2224 只)`，★ 同进程里内存不释放。
      ★★★★★ 这正是之前「33 条基本面跑批 OOM」的同一个坑 —— ★★ 不是逻辑错，是**结构错**。
    【第二版 · 现行】**一条臂一个进程**：加 `--arm N`，外层 shell 循环，
      ★★★ 每条跑完进程退出、内存归还。
    """
    import copy
    import yaml
    import 跑基本面_1106 as B
    from engine import chain, matrices, data

    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    print(f"【前置】研发池 {len(dev)} 只 · 留出池 {len(hs)} 只（★ 已排除）")

    print("【前置】装新池层（★ 复用跑批自己的 装层()，不自己拼）…")
    RC, 信息 = B.装层()
    print(f"【前置】装层完成：{信息}")
    print(f"【前置】data.PERF_START = {data.PERF_START} · PERF_END = {data.PERF_END}")
    assert str(data.PERF_START).startswith("2015"), \
        f"🔴 窗口起点是 {data.PERF_START}，不是 2015 —— ★★ 和已有成绩不可比，停"

    臂 = B.臂表()
    if 只跑 is not None:
        if not (0 <= 只跑 < len(臂)):
            print(f"🔴 --arm {只跑} 超范围（共 {len(臂)} 条）"); return 2
        臂 = [臂[只跑]]
        print(f"【前置】臂表共 {len(B.臂表())} 条 —— ★ 本进程只跑第 {只跑} 条\n")
    else:
        print(f"【前置】臂表 {len(臂)} 条\n")

    行, 失败 = [], []
    for i, arm in enumerate(臂, 1):
        名 = arm.get("臂") or arm.get("name") or f"arm{i}"
        t0 = time.time()
        # ★★★★★ 做法改过一次（★ 记在这里）：
        #   【第一版】直接调 `B.跑一条(arm)` 想从它的返回里拿 res.equity
        #     🔴 **拿不到** —— ★★ 跑一条() 返回的是 `rec` 记录字典，
        #        `res` 是它的局部变量，用完就丢（见 跑基本面_1106.py:96~112）。
        #   【第二版 · 现行】照 跑一条() 第 83~96 行**逐行复制**那段调用，
        #     ★★★★★ **一个参数都不改** —— ★ 改了就不能和已有成绩对照。
        try:
            raw = yaml.safe_load(io.open(os.path.join(B.CFG, arm["配置"]), encoding="utf-8"))
            raw = copy.deepcopy(raw)
            for k, v in arm["覆盖"].items():
                B._设(raw, k, v)
            cfg = chain.ChainConfig.from_dict(raw)
            m = matrices.build(cfg.raw, dev)
            RC.apply_scope(m, B.SCOPE)
            res = chain.run_chain(cfg, dev, data.PERF_START, data.PERF_END, m=m)
            # ★★★ 留出池闸：照原文第 98~101 行，★ 漏了就必须炸，不许静默
            led = res.ledger
            if len(led):
                leaked = sorted(set(led["symbol"].astype(str)) & hs)
                if leaked:
                    raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")
        except Exception as e:
            失败.append({"臂": 名, "原因": f"{type(e).__name__}: {str(e)[:300]}"})
            print(f"  🔴 {名[:48]:50s} 失败 {type(e).__name__}: {str(e)[:80]}")
            continue
        nv = res.equity
        在场 = None
        try:
            led = res.ledger
            if len(led):
                cal = nv.index
                held = pd.Series(0, index=cal)
                for t in led.itertuples(index=False):
                    a = cal.searchsorted(pd.to_datetime(t.entry_date))
                    b = cal.searchsorted(pd.to_datetime(t.exit_date))
                    held.iloc[a:min(b + 1, len(cal))] += 1
                在场 = float((held > 0).mean())
        except Exception:
            pass
        nv.to_frame("净值").to_csv(os.path.join(OUT, f"净值__{B.安全名(名)[:80]}.csv"))
        m = 指标(nv, 在场)
        m["臂"] = 名
        m["耗时秒"] = round(time.time() - t0, 1)
        行.append(m)
        print(f"  ✅ {名[:48]:50s} 年化 {m.get('复合年化%')}% · 回撤 {m.get('最大回撤%')}% "
              f"· 卡玛 {m.get('卡玛')} · {m['耗时秒']}s")

    # ★★★ 一条臂一个进程 → ★ 每条各写自己的小文件，★★ 最后另外合并（不覆盖别人的）
    后缀 = f"_arm{只跑:02d}" if 只跑 is not None else "_all"
    pd.DataFrame(行).to_csv(os.path.join(OUT, f"指标{后缀}.csv"), index=False)
    json.dump(失败, io.open(os.path.join(OUT, f"失败{后缀}.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n【结果】成功 {len(行)} · 失败 {len(失败)} → {OUT}")
    print("\n★★★★★ **自证还没做** —— ★★ 必须拿这里算出的组合层数，")
    print("   和《93》里已有的 21 条「组合层 alpha / 回撤」对一遍。")
    print("   ★★★ 对不上就是这次跑的口径和当初不一样，★ 不许直接用。")


if __name__ == "__main__":
    n = None
    if "--arm" in sys.argv:
        n = int(sys.argv[sys.argv.index("--arm") + 1])
    sys.exit(main(n) or 0)
