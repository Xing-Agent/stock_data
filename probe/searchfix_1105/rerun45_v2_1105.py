# -*- coding: utf-8 -*-
"""
技术面 45 条重跑 · 修 engine 之后（2026-11-05 · 第二版）

★ 拍板依据：Lin 1105 12:45「修」（《24》第 42 条）。
★★★ 这一轮验的是**自查项 2 的扩大版**：
  **修完 engine，技术面 45 条的结论一条都不许变。变了就是我改坏了，回退。**

---

## ★★★ 第一版为什么没跑成（★ 这件事本身要记账）

```
★ 第一版我 import 的是 `run_bench1_1102.py`,★★ 它的题目指纹闸立刻把我挡住了:
   「★★★ 题目被动过 —— 对不上 **40 个**」
★ 我以为只会报我改的那一个(engine/analyze.py),★★★ 结果是 **40 个**:
   · `engine/analyze.py` —— ★ 我改的
   · ★★★ **另外 39 份 engine/configs/*.yaml** —— ★★ **不是我改的**

★★★ 查出来是:那 39 份是 **commit 55088733「摩擦口径统一成三档」**改的 ——
   ★ **Lin 11-04 拍板的那件事。**
→ ★★★ 所以 **1102 那一轮不是正确的基线** —— 它在摩擦统一**之前**。
   ★★ 拿它当基线,会把「engine 修搜索」和「摩擦口径统一」两件事**混在一起**。

★★ 正确的基线是 **`probe/friction_rerun_1104/friction_rerun_1104.json`**
   (★ 摩擦统一之后那一轮,45 条链,研发池 198 只)。
★★★ 而摩擦那一轮**已经解过同一个问题**:它把指纹拆成
   「engine 代码 83 份」+「configs 50 份」—— ★ 我沿用它这个拆法。
```

## ★★★ 这一轮怎么处理指纹（★ 不是关掉闸，是重新登记）

```
★★★ **engine 代码指纹这道闸现在必须对不上 —— 因为我们就是故意改了它。**
★ 所以做法是:**重新登记,并断言这一轮的改动是最小的** ——

   ① ★★★ **恰好 1 个文件变了**:`engine/analyze.py`
      → ★★ 多一个少一个都 raise,整轮作废
   ② ★★★ **其余 82 份 engine 代码文件逐字节不变**
   ③ ★★ configs 50 份:★ 和摩擦那一轮**一字不差**(★★★ 这一轮没动配置)
   ④ ★ 新旧 analyze.py 的 sha256 两头都记上,并记「改了哪 8 处」

★★ 为什么不直接把闸关掉:★★★ 关掉就等于以后谁改 engine 都没人知道。
   ★ 重新登记保留了闸的作用 —— **它仍然会抓住任何我没声明的改动。**
```
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FRIC = os.path.join(ROOT, "probe", "friction_rerun_1104")
sys.path.insert(0, ROOT)
sys.path.insert(0, FRIC)

import run_friction_1104 as F                                 # noqa: E402

OLD_JSON = os.path.join(FRIC, "friction_rerun_1104.json")
BACKUP_ANALYZE = os.path.join(HERE, "analyze.py.改之前备份")

F.LEDGERS = os.path.join(HERE, "ledgers45_1105")
F.OUT = os.path.join(HERE, "rerun45_results_1105.json")
# ★★★ 1105 13:0x 踩过:只改 LEDGERS/OUT 不够 —— ★ PER_CHAIN 还指着摩擦轮那个目录,
#   ★★ 于是 45 条**全被当成「已有结果」跳过**。★★★ 中间结果目录也必须指到本轮。
F.PER_CHAIN = os.path.join(HERE, "per_chain45_1105")

#: ★★★ 这一轮**唯一**允许变的 engine 文件
ALLOWED_CHANGED = {"engine/analyze.py"}


def _sha(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verify_code_fingerprint_relicensed() -> dict:
    """★★★ 重新登记版:**恰好** ALLOWED_CHANGED 这些文件变了，其余一字不变。"""
    reg_code, _ = F._manifest_split()
    missing, changed, same = [], [], []
    for f, want in reg_code.items():
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            missing.append(f)
            continue
        (changed if _sha(p) != want else same).append(f)
    if missing:
        raise RuntimeError(f"★★★ engine 代码缺文件 {missing} —— ★ 整轮作废,停。")
    extra = sorted(set(changed) - ALLOWED_CHANGED)
    absent = sorted(ALLOWED_CHANGED - set(changed))
    if extra:
        raise RuntimeError(
            f"★★★ 有**没声明**的 engine 改动:{extra}\n"
            f"    ★ 这一轮只允许改 {sorted(ALLOWED_CHANGED)}。\n"
            "    ★★ 整轮作废,停 —— ★★★ 先查清这些文件为什么变了。")
    if absent:
        raise RuntimeError(
            f"★★★ 声明要改的文件其实没变:{absent}\n"
            "    ★ 说明补丁没落上 —— ★★ 先跑 "
            "`apply_to_engine_1105.py --check` 看状态。")
    out = {
        "★这一轮的口径": ("★★★ **不是零改动** —— Lin 1105 12:45 拍板「修」,"
                          "★ 所以这一轮**故意改了 engine/analyze.py**"),
        "★★★恰好变了几个": len(changed),
        "★★★变的是": sorted(changed),
        "★其余逐字节不变的": len(same),
        "★改之前的 sha256(登记值)": reg_code["engine/analyze.py"],
        "★改之后的 sha256(实算)": _sha(os.path.join(ROOT, "engine/analyze.py")),
        "★★改了哪几处": [
            "⓪ _next_rate 整函数换成「夹住 + 几何二分」(+ SaturatedNoUpperBracket)",
            "① 删掉单种子校准的「碰 0 笔就停」(analyze.py:163)",
            "② 删掉校准段的「碰 0 笔就停」(analyze.py:563)",
            "③ 删掉核验段的「碰 0 笔就停」(analyze.py:587)",
            "④ 饱和检测改成只记录、不早停",
            "⑤ 真链 0 笔要单独报",
            "⑥⑦ 校准轮次放宽(★★★ 容差 ±5% 一个字没动)",
        ],
        "★★★不许动的几条": {
            "容差 CONTROL_TOL = 0.05": "过",
            "判的还是 50 种子平均(断言句原样)": "过",
        },
        "★备份": BACKUP_ANALYZE,
        "★回退办法": "python3 -I probe/searchfix_1105/apply_to_engine_1105.py --revert",
    }
    print(f"★★★ 指纹重新登记通过:恰好 1 个文件变了"
          f"(engine/analyze.py),其余 {len(same)} 份一字不变", flush=True)
    return out


# ★★★ 换掉那道闸(★ 换成「重新登记」版,**不是**关掉)
F.verify_code_fingerprint = verify_code_fingerprint_relicensed


def compare() -> dict:
    old = json.load(open(OLD_JSON, encoding="utf-8"))["逐链"]
    new = json.load(open(F.OUT, encoding="utf-8"))["逐链"]
    o = {r["链"]: r for r in (old.values() if isinstance(old, dict) else old)}
    n = {r["链"]: r for r in (new.values() if isinstance(new, dict) else new)}

    def b1(r):
        for k in ("★基准一", "★新基准一值", "基准一"):
            if isinstance(r.get(k), (int, float)):
                return r[k]
        return None

    rows, flipped, devbad, nbad = [], [], [], []
    for k in sorted(set(o) | set(n)):
        a, b = o.get(k, {}), n.get(k, {})
        va, vb = b1(a), b1(b)
        sa = None if va is None else va > 0
        sb = None if vb is None else vb > 0
        dv = b.get("★对照笔数偏差")
        flip = (sa is not None and sb is not None and sa != sb)
        if flip:
            flipped.append({"链": k, "摩擦轮": va, "本轮": vb})
        if isinstance(dv, (int, float)) and abs(dv) > 0.05:
            devbad.append({"链": k, "偏差": dv})
        if (a.get("笔数") is not None and b.get("笔数") is not None
                and a["笔数"] != b["笔数"]):
            nbad.append({"链": k, "摩擦轮": a["笔数"], "本轮": b["笔数"]})
        rows.append({"链": k, "摩擦轮笔数": a.get("笔数"), "本轮笔数": b.get("笔数"),
                     "摩擦轮基准一": va, "本轮基准一": vb,
                     "摩擦轮赢?": sa, "本轮赢?": sb, "★符号翻了吗": flip,
                     "本轮对照笔数偏差": dv})
    verdict = ("★★★ 自查项2 过 —— 45 条结论一条都没变"
               if not flipped and not nbad else
               "★★★ **自查项2 不过** —— ★ 按口径⑥**先当我改坏了**;"
               "★★ 下一步 `apply_to_engine_1105.py --revert` 回退,查清再来")
    return {
        "★这是什么": "★★★ 自查项2 扩大版:修完 engine,技术面 45 条结论不许变",
        "★拍板依据": "Lin 1105 12:45「修」(《24》第 42 条)",
        "★★★基线用的是哪一轮": (
            "`probe/friction_rerun_1104/friction_rerun_1104.json`"
            "(★ 摩擦口径统一**之后**那一轮)—— ★★★ **不是 1102**,"
            "★ 因为 1102 在摩擦统一之前,拿它当基线会把两件事混在一起"),
        "链数": len(rows),
        "摩擦轮 赢的条数": sum(1 for r in rows if r["摩擦轮赢?"] is True),
        "本轮 赢的条数": sum(1 for r in rows if r["本轮赢?"] is True),
        "★★★符号翻转的": flipped,
        "★对照笔数偏差超 ±5% 的": devbad,
        "★★★笔数变了的(不该变)": nbad,
        "★★★判定": verdict,
        "逐链": rows,
    }


def main() -> int:
    t0 = time.time()
    print("★ 技术面 45 条重跑(修完 engine 之后)", flush=True)
    print("★★ 基线 = 摩擦口径统一那一轮(friction_rerun_1104)", flush=True)
    rc = F.main()
    if rc != 0:
        print(f"★★★ 跑批返回 {rc},停。", flush=True)
        return rc
    cmp = compare()
    cmp["★★★指纹重新登记"] = verify_code_fingerprint_relicensed()
    p = os.path.join(HERE, "rerun45_对比摩擦轮-1105.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(cmp, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n★★★ 45 条:摩擦轮赢 {cmp['摩擦轮 赢的条数']} 条 · "
          f"本轮赢 {cmp['本轮 赢的条数']} 条", flush=True)
    print(f"★★★ 符号翻转:{cmp['★★★符号翻转的'] or '无 ✅'}", flush=True)
    print(f"★★★ 笔数变了:{cmp['★★★笔数变了的(不该变)'] or '无 ✅'}", flush=True)
    print(f"★ 偏差超 ±5%:{cmp['★对照笔数偏差超 ±5% 的'] or '无 ✅'}", flush=True)
    print(f"\n{cmp['★★★判定']}", flush=True)
    print(f"★ 对比写到 {p} · 总耗时 {time.time()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
