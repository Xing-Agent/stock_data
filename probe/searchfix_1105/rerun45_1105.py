# -*- coding: utf-8 -*-
"""
技术面 45 条重跑 · 修 engine 之后（2026-11-05）

★ 拍板依据：Lin 1105 12:45「修」（《24》第 42 条）。
★★★ 这一轮验的是**自查项 2 的扩大版**：

  **修完 engine，技术面 45 条的结论一条都不许变。变了就是我改坏了，回退。**

★★ 做法：1102 那个跑批原样 import，★ 只把输出目录指到本轮，不碰它的结果。
★★★ 题目指纹那道闸**照旧**（★ 对不上就停，整轮作废）。

★ 比的是什么（★★ 逐条对 1102 那一轮）：
  · **★基准一** 的值（★★★ 主要看**符号有没有变** —— 赢变输 / 输变赢）
  · **★对照笔数偏差** 有没有都落在 ±5% 内
  · ★ 笔数有没有变（★★ 不该变 —— 真链和 engine 的搜索无关）
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "bench1_rerun_1102"))

OLD = os.path.join(ROOT, "probe", "bench1_rerun_1102", "bench1_rerun_1102.json")

import run_bench1_1102 as B                                   # noqa: E402

B.LEDGERS = os.path.join(HERE, "ledgers45_1105")
B.OUT = os.path.join(HERE, "rerun45_results_1105.json")


def compare() -> dict:
    """★ 逐条对 1102 那一轮 —— ★★★ 这是自查项 2 的判决书。"""
    old = json.load(open(OLD, encoding="utf-8"))["逐链"]
    new = json.load(open(B.OUT, encoding="utf-8"))["逐链"]
    o = {r["链"]: r for r in (old.values() if isinstance(old, dict) else old)}
    n = {r["链"]: r for r in (new.values() if isinstance(new, dict) else new)}
    rows, flipped, devbad, nbad = [], [], [], []
    for k in sorted(set(o) | set(n)):
        a, b = o.get(k, {}), n.get(k, {})
        b1o, b1n = a.get("★基准一"), b.get("★基准一")
        so = (None if not isinstance(b1o, (int, float)) else (b1o > 0))
        sn = (None if not isinstance(b1n, (int, float)) else (b1n > 0))
        dv = b.get("★对照笔数偏差")
        row = {
            "链": k, "1102笔数": a.get("笔数"), "本轮笔数": b.get("笔数"),
            "1102基准一": b1o, "本轮基准一": b1n,
            "1102赢?": so, "本轮赢?": sn,
            "★符号翻了吗": (so is not None and sn is not None and so != sn),
            "本轮对照笔数偏差": dv,
        }
        if row["★符号翻了吗"]:
            flipped.append(k)
        if isinstance(dv, (int, float)) and abs(dv) > 0.05:
            devbad.append((k, dv))
        if (a.get("笔数") is not None and b.get("笔数") is not None
                and a["笔数"] != b["笔数"]):
            nbad.append((k, a["笔数"], b["笔数"]))
        rows.append(row)
    ok_o = sum(1 for r in rows if r["1102赢?"] is True)
    ok_n = sum(1 for r in rows if r["本轮赢?"] is True)
    verdict = ("★★★ 自查项2 过 —— 45 条结论一条都没变"
               if not flipped and not nbad else
               "★★★ **自查项2 不过** —— ★ 按口径⑥**先当我改坏了**,"
               "★★ 下一步:`apply_to_engine_1105.py --revert` 回退,查清再来")
    return {
        "★这是什么": "★★★ 自查项2 扩大版:修完 engine,技术面 45 条结论不许变",
        "★拍板依据": "Lin 1105 12:45「修」(《24》第 42 条)",
        "链数": len(rows),
        "1102 赢的条数": ok_o, "本轮 赢的条数": ok_n,
        "★★★符号翻转的链": flipped,
        "★对照笔数偏差超 ±5% 的链": devbad,
        "★★★笔数变了的链(不该变)": nbad,
        "★★★判定": verdict,
        "逐链": rows,
    }


def main() -> int:
    t0 = time.time()
    print("★ 技术面 45 条重跑开始(修完 engine 之后)", flush=True)
    rc = B.main()
    if rc != 0:
        print(f"★★★ 跑批返回 {rc},停。", flush=True)
        return rc
    cmp = compare()
    p = os.path.join(HERE, "rerun45_对比1102-1105.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cmp, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n★★★ 45 条:1102 赢 {cmp['1102 赢的条数']} 条 · "
          f"本轮赢 {cmp['本轮 赢的条数']} 条", flush=True)
    print(f"★★★ 符号翻转的:{cmp['★★★符号翻转的链'] or '无 ✅'}", flush=True)
    print(f"★★★ 笔数变了的:{cmp['★★★笔数变了的链(不该变)'] or '无 ✅'}", flush=True)
    print(f"★ 偏差超 ±5% 的:{cmp['★对照笔数偏差超 ±5% 的链'] or '无 ✅'}", flush=True)
    print(f"\n{cmp['★★★判定']}", flush=True)
    print(f"★ 对比写到 {p} · 总耗时 {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
