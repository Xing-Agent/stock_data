# -*- coding: utf-8 -*-
"""
修搜索后重考 · 跑批（2026-11-05）
预先登记：手册/47-修搜索-预先登记-1105.md

★★★ 跑的是 1104 那 16 条臂的**主格**，一条不多一条不少 ——
  ★ 10 条是「要修好的」，★★ 6 条是「自查项 2：结论不能变」。

★★★ engine/ 一个字节不改：
  · 用 `analyze.random_entry_benchmark = 改写版` 做运行时替换；
  · 1104 的 runner 原样 import，★ 只把输出目录指到本轮，不碰它的 parts/。
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "expand_run_1104"))

from engine import analyze                                    # noqa: E402
from probe.searchfix_1105 import fix_search_1105 as FIX       # noqa: E402

# ★★★ 运行时替换 —— ★ 三处一起换（少换一处就白跑，1105 10:52 踩过）
_INSTALLED = FIX.install()
print("★★★ 运行时替换:", json.dumps(_INSTALLED, ensure_ascii=False), flush=True)

import run_expand_1104 as R                                   # noqa: E402

OUT_DIR = HERE
R.PART_DIR = os.path.join(OUT_DIR, "parts")
R.LEDGER_DIR = os.path.join(OUT_DIR, "ledgers_1105")
R.OUT_JSON = os.path.join(OUT_DIR, "run_refix_results_1105.json")

# ★ 1104 那 16 条臂里,哪些是「考不出来」(要修好的),哪些是「已有成绩」(要不变的)
考不出来_1104 = ["扩1-ours", "扩3-orig-cp", "扩3-ours", "扩4-orig", "扩4-ours",
                 "扩5-orig", "扩5-ours", "扩6-ours", "扩7-orig", "扩7-ours"]
已有成绩_1104 = ["扩2-orig", "扩2-ours", "扩3-orig-bm", "扩3-orig-ep",
                 "扩6-orig", "扩8-ours"]
# ★★ 1104 的「没赢」数值 —— 自查项 2 要逐条对
已有成绩_1104_基准一 = {
    "扩2-orig": -0.0411, "扩2-ours": -0.0345, "扩3-orig-bm": -0.0217,
    "扩3-orig-ep": -0.0139, "扩6-orig": -0.2130, "扩8-ours": -0.0006,
}


def main() -> int:
    import pandas as pd
    from engine import cache, data
    from probe.expand_run_1104 import ops_expand_1104 as _unused  # noqa: F401

    R.OX.install()
    os.makedirs(R.PART_DIR, exist_ok=True)
    man = data.load_manifest()
    have_px = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]
    cal = data.trading_calendar()
    _sm, _ = R.RC.scope_mask(syms, cal, R.SCOPE)
    scope_mask = pd.DataFrame(_sm, index=cal, columns=syms)

    todo = [c for c in R.cells() if c[4]]          # ★★ 只跑主格
    print(f"★ 本轮跑 {len(todo)} 个主格(1104 的 16 条臂)", flush=True)

    results, errs = {}, {}
    for i, (cell, cid, slots, rank, is_main) in enumerate(todo):
        part = os.path.join(R.PART_DIR, cell.replace("|", "__") + ".json")
        if os.path.exists(part):
            results[cell] = json.load(open(part, encoding="utf-8"))
            print(f"[{i+1}/{len(todo)}] {cell} (缓存)", flush=True)
            continue
        FIX.reset_trace()
        t0 = time.time()
        raw = R._load(cid)
        try:
            rec = R.run_cell(cid, raw, slots, rank, True, syms, scope_mask)
        except Exception as e:
            rec = {"臂": cid, "slots": slots, "★自由参数档位": rank,
                   "★跑挂了": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-2500:]}
            errs[cell] = rec["★跑挂了"]
        rec["★★★本轮搜索轨迹"] = FIX.get_trace()
        rec["★1104是什么状态"] = ("考不出来" if cid in 考不出来_1104
                                  else "已有成绩(自查项2)")
        rec["★1104基准一值"] = 已有成绩_1104_基准一.get(cid)
        rec["★本轮耗时秒"] = round(time.time() - t0, 1)
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(R._num(rec), fh, ensure_ascii=False, indent=2, default=str)
        results[cell] = rec
        b1 = (rec.get("★基准一_同环境随机进场") or {})
        print(f"[{i+1}/{len(todo)}] {cell} 笔数={rec.get('笔数')} "
              f"偏差={b1.get('★对照笔数偏差')} "
              f"差额={b1.get('★真信号每笔R − 随机进场每笔R')} "
              f"{str(rec.get('★基准/判据跑挂了') or rec.get('★跑挂了') or '')[:90]} "
              f"用时={rec['★本轮耗时秒']}s", flush=True)

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★这一轮是什么": "修搜索后重考 1104 那 16 条臂的主格",
        "★预先登记": "手册/47-修搜索-预先登记-1105.md",
        "窗口": f"{R.DEV[0]} .. {R.DEV[1]}(研发池)",
        "★只用研发池": "★★★ 考卷 exam_1042/ 一个文件都没读。",
        "池子口径": f"{R.SCOPE}(大+中,成交额排名 1–2000)",
        "回测票池只数": len(syms),
        "★★★engine零改动自证": FIX.源码自证(),
        "★容差": analyze.CONTROL_TOL,
        "★容差有没有放宽": "★★★ 没有 —— ±5%,Lin 11-05 原文「容差不放宽」",
        "格子数": len(todo),
        "跑挂的格子": errs,
        "格子": {k: R._num(v) for k, v in results.items()},
    }
    with open(R.OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print("★ 写到", R.OUT_JSON, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
