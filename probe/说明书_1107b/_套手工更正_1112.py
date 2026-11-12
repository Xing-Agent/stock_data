#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给《93》套上手工更正（2026-11-12）

★★★★★ 为什么要有这个文件：
   ★ 生成器 `生成说明书_1107b.py` **整文件覆盖写**到《93》那个路径 ——
     ★★ 所以跑一次就会把抬头那 6 段必读、融-1 改名、所有口径更正**全冲掉**。
   ★★★ 这正是「正文一直没重出」的真原因（★ Lin 1112：「这一版很多都没更新」）。
   ★★★★★ 所以更正**不能只活在手工编辑里** —— 必须变成**数据**，每次重出都套上。

★★ 套法：**按文本找、带游标、一遍扫过去**（★ 不按行号 —— 行号一变就错位且不报警）。
🔴 ★★★★★ **任何一条的「旧」找不到 → 拒绝写文件**，不许静默漏掉一条更正。
"""
import io, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
补丁表 = os.path.join(os.path.dirname(__file__), "_手工更正_1112.json")


def 套(行们: list) -> list:
    """★★ 按文本找、带游标、一遍扫过去（★ 不按行号 —— 行号一变就错位且不报警）。
    🔴 ★★★★★ 任何一条落不下去 → **拒绝写文件**，不许静默漏掉一条更正。
    ★★ 纯插入（旧=0 行）靠「锚」定位：★★★ 锚是生成器那几行原文，**插在锚之后，锚本身不动**；
       ★ 锚一律裁在上一条更正之后，否则游标已经越过去了。
    """
    ops = json.load(io.open(补丁表, encoding="utf-8"))
    # ★★★★★ 去掉「旧 / 锚 / 新」末尾的空行 —— ★★ 补丁表是从**文件**抽的（末尾多一个空行），
    #   ★★★ 而生成器交给我们的是**内存里的行表**（没有那个空行）→ ★ 不去掉，最后一条永远落不下去。
    def _修(xs):
        while xs and xs[-1] == "":
            xs = xs[:-1]
        return xs
    for _op in ops:
        _op["旧"] = _修(_op["旧"])
        if "锚" in _op:
            _op["锚"] = _修(_op["锚"])
    out, i, 用了 = [], 0, 0
    for 序, op in enumerate(ops, 1):
        旧, 新 = op["旧"], op["新"]
        找 = 旧 if 旧 else op["锚"]
        pos = -1
        for k in range(i, len(行们) - len(找) + 1):
            if 行们[k:k + len(找)] == 找:
                pos = k
                break
        if pos < 0:
            raise SystemExit(
                f"🔴 ★★★★★ 第 {序} 条更正落不下去 —— **拒绝写文件**。\n"
                f"   说明：{op['说明']}\n"
                f"   ★★ 大概是生成器那一段的措辞变了。★★★ 要么改补丁表，要么别重出。")
        if 旧:
            out += 行们[i:pos] + 新
            i = pos + len(旧)
        else:
            out += 行们[i:pos + len(找)] + 新
            i = pos + len(找)
        用了 += 1
    out += 行们[i:]
    print(f"★ 手工更正：{用了}/{len(ops)} 条全部套上")
    if 用了 != len(ops):
        raise SystemExit("🔴 有更正没套上 —— 拒绝写文件")
    return out

if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "手册/_93试跑_1112.md")
    dst = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "手册/_93套完_1112.md")
    行 = io.open(src, encoding="utf-8").read().split("\n")
    io.open(dst, "w", encoding="utf-8").write("\n".join(套(行)))
    print(f"★ 写到 {dst}")
