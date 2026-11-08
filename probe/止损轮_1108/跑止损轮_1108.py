# -*- coding: utf-8 -*-
"""★★★ 《128》口径② —— 硬止损三点（2.0 / 2.5 / 3.0 倍 ATR）。

★★ 三秒版：同一条大波段，只把**硬止损的宽度**换成三档，各跑一遍，逐日配对比。
★ 跑前登记见《128》—— ★★★ 门槛已写死：配对 |t|>2.5 · 三点必须同向 ·
  大单保留率 ≥85%。★★ 出数时不许动。

★★★ 复用《跑重测_1107》的台子（装池 / 分红覆盖层 / 日净值落盘），★ 只换配置。
  → ★★ 这样和《113》那批 A原样 **同一个口径**，才配得上对。
"""
from __future__ import annotations
import glob
import io
import json
import os
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe/重测_1107"))
sys.path.insert(0, os.path.join(ROOT, "probe/friction_rerun_1104"))
sys.path.insert(0, os.path.join(ROOT, "probe/并池_1107"))

import pandas as pd                                            # noqa: E402
import 跑重测_1107 as RT                                        # noqa: E402
import run_friction_1104 as F                                  # noqa: E402
import 日序列覆盖层_1107 as DS                                   # noqa: E402
import 跳过基准一_1107 as SK                                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "configs")
ARMS = os.path.join(HERE, "arms_1108")
# ★ 日净值由 日序列覆盖层_1107 写（目录用 XING_DS_DIR 指过来）
OUT = os.path.join(HERE, "止损轮结果_1108.json")
窗口起, 窗口止, 窗口名 = "2015-01-01", "2025-12-31", "B_2015到2025"


def main() -> int:
    t0 = time.time()
    for d in (ARMS,):
        os.makedirs(d, exist_ok=True)
    F.CONFIG_DIR = CFG
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1108")
    F.LEDGERS = os.path.join(HERE, "ledgers_1108")
    for d in (F.PER_CHAIN, F.LEDGERS):
        os.makedirs(d, exist_ok=True)

    # ★★★ 日净值落盘 + 跳过基准一 —— ★ 用 1107 夜里做好的**正式覆盖层**，
    #   ★★ 不再手写一遍（账本 #83 那次我是内联补的，★★★ 正式层有 id() 自证和调用计数）。
    自证日序列 = DS.install()
    自证跳过 = SK.install()
    print(f"★ 日序列覆盖层: {json.dumps(自证日序列, ensure_ascii=False)}", flush=True)
    print(f"★ 跳过基准一: {json.dumps(自证跳过, ensure_ascii=False)}", flush=True)

    RT.窗口起, RT.窗口止, RT.窗口名 = 窗口起, 窗口止, 窗口名
    os.environ["XING_WIN_START"], os.environ["XING_WIN_END"] = 窗口起, 窗口止
    自证 = RT.装池("并池2004")
    dev = RT.可买名单("并池2004")
    自证分红 = RT.DV.install(需覆盖=dev)        # ★★★ #80：覆盖率不足会直接抛
    print(f"★★★ 分红自证: {自证分红['★★★查得到文件的比例']} · "
          f"SPY {自证分红['★★★基准侧分红']['SPY']}", flush=True)
    print(f"★ 池自证: {json.dumps(自证, ensure_ascii=False)}", flush=True)
    # ★ `hold` 在《跑重测_1107》里是 main() 的局部变量 → ★★ 这里自己读一遍
    hold = json.load(io.open(os.path.join(ROOT, RT.HOLD), encoding="utf-8"))
    # ★★★ 本轮和 A原样 同口径：**全量 3,858 只一档，无静态留出池**（Lin 1107 16:58 拍板）
    F.load_pools = lambda d=dev, h=hold: (d, set(), h)

    报 = {"★预先登记": "《128》跑前预先登记-止损反事实与硬止损三点-1108.md",
         "【本次口径】": (f"全收益（分红再投，两侧同口径）· 摩擦档 配置自带三档 · "
                   f"窗口 {窗口起}~{窗口止} · 池 并池2004(3858,一档) · 标签滞后 1 天"
                   f" · ★★★ 本轮**不挂环境闸**（和 A原样 同口径）"),
         "分红自证": 自证分红, "池自证": 自证, "结果": [], "失败明细": []}

    for p in sorted(glob.glob(os.path.join(CFG, "_stop_*.yaml"))):
        名 = os.path.basename(p)[:-5]
        label = f"{窗口名}·并池2004·大波段·技-1·{名}"
        ap = os.path.join(ARMS, f"{F.safe_name(label)}.json")
        if os.path.exists(ap) and DS.已有(label):   # ★ 可续跑；★★ 没曲线也要重跑
            报["结果"].append(json.load(io.open(ap, encoding="utf-8")))
            print(f"↷ 已有结果，跳过 {名}", flush=True)
            continue
        print(f"▶ {label}", flush=True)
        DS.开始新臂(label)          # ★ 显式重置「本臂第几次调用」，不靠猜
        try:
            r = F.run_one(label, os.path.basename(p), None, "止损轮_1108", dev, set(), {})
        except Exception as e:
            报["失败明细"].append({"臂": label, "错": f"{type(e).__name__}: {e}"})
            print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True)
            continue
        rec = {"链": label, "档": 名, "笔数": r["笔数"], "每笔净R": r["每笔净R"],
               "每笔毛R": r["每笔毛R"], "净盈亏": r["★真链美元"]["净盈亏"],
               "摩擦": r["★真链美元"]["摩擦总额"]}
        io.open(ap, "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        报["结果"].append(rec)
        print(f"   ✓ {名} 笔数 {r['笔数']} 每笔净R {r['每笔净R']:+.4f}", flush=True)
        io.open(OUT, "w", encoding="utf-8").write(
            json.dumps({**报, "★进行中": True}, ensure_ascii=False, indent=1, default=str))

    报["★日序列自证"] = {**自证日序列, "★已存清单": DS.已存清单()}
    报["★★★本轮没算基准一"] = {**自证跳过, "★实际调用次数": SK.调用次数()}
    报["★★★失败条数"] = len(报["失败明细"])
    报["★用时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写到 {OUT} · 失败 {len(报['失败明细'])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
