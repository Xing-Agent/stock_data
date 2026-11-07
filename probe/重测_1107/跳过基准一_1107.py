# -*- coding: utf-8 -*-
"""★★★ 本批跳过「基准一 · 同环境随机进场」—— ★ 不跳的话这一批**跑不完**（实测，不是估计）。

★★★ 量出来的账（1107 夜，并池2004 · 3,858 只 · B 段 2015~2025，技-1）：

```
★ 装池（读 465 MB 面板 + 裁窗口）        42.6 s   ← 每个族进程一次
★ matrices.build                          5.4 s
★★★ 真链一次                             35.4 s   · 890 笔
★★★ 基准一（N_SEEDS=50）                 **跑了 495 s 还没跑完**
```

★★ 为什么基准一这么贵（★ 读 `engine/analyze.py:512` 的签名和注释，不是猜的）：
   `random_entry_benchmark(..., n_seeds=50, cal_iter=14, cal_seeds=8, verify_iter=6)`
   · **第一段 · 校准**：最多 14 轮 × 8 个种子 = 最多 **112 次回测**
   · **第二段 · 核验**：最多 6 轮 × 50 个种子 = 最多 **300 次回测**
   → ★★★ 一条臂最多 **≈ 412 次回测** × 35 s ≈ **4 小时**
   → ★★ 66 条臂（2 段 × 3 族 × 11 臂）≈ **11 天**。★★★ 这一批在定时任务里永远跑不完。
   ★ 引擎注释自己就写了这件事：「实测把 50 个种子全跑一遍去迭代，1670 笔那条链一条就要
     14 分钟，全库要跑好几个小时 —— 机器时间不够」。

★★★★★ **而本批的臂文件把基准一整个扔掉了。** ★ 逐字核过 `跑重测_1107.py` 写盘那一段：
```python
rec = {"链","池","族","臂","笔数","每笔净R","每笔毛R","净盈亏","摩擦"}
```
   ★★ 这 5 个数**全部来自真链自己的流水**（`led = res.ledger` 和 `_money(led)`），
   ★★★ 一个字都没取自 `r["★基准一"]` / `r["★新基准一值"]` / `r["★判据Z..."]`。
   → ★ 基准一只落在 `per_chain_1107/`（**而它在 .gitignore 里**），本工单下游没有任何一步读它。
   → ★★★ 所以这 99.8% 的机器时间**产出的东西没有一个进得了结论**。

★★★ 而且本批**跑前预先登记**里根本没有基准一 —— 登记的三件是：
   ① 主判据 = 条件 alpha（交互项回归）② 配对检验（规矩㊸v2）③ 随机**排序**对照（10 个种子，
   = 那 10 条 `R随机<seed>` 臂本身）。★★ 「随机**进场**」和「随机**排序**」是两件不同的事，
   ★★★ 跳掉前者**不动**预先登记的任何一件。

★★ 跳掉会不会动到记下来的数（★ 这是唯一要担心的一件，逐条查过）：
   ① `res = _ORIG_RUN_CHAIN(...)` 在 `run_one` 第 414 行，**比基准一那一行早** →
      ★ 后面少调一个函数，不可能回头改已经算完的流水。
   ② 随机排序那 10 条臂会不会受全局 RNG 影响 → **不会**：
      `回看期覆盖层_1107.py:41` 用的是 `np.random.default_rng(int(seed))`，
      ★★ **局部**生成器 + 显式种子，和进程里别处抽不抽随机数无关。
   ③ ★★★ 顺带查出一件（★ 本次不影响我们，但记一笔）：`engine/signals.py:161` 的随机**进场**
      扳机用的是 `seed + (abs(hash(str(df.index[0]))) % 9973)` —— ★★ Python 的 `hash()` 对
      字符串是**按进程加盐**的（PYTHONHASHSEED），★★★ 所以基准一那一档**跨进程不可复现**。
      ★ 这一条和 #69（存盘读回哈希会变）是同一类。engine 不许动 → 只登记，不改。

★ 做法（engine 一个字节不改，进程内换函数指针，带 id() 自证）：
   ★★ 两个函数都换成**明说「本批没算」的桩**，★★★ **不借用 `BenchmakPremiseBroken`
   那条通道** —— 那个字段名的意思是「前提真的破了」，拿它表示「我们主动跳过」
   就是又造一个说谎的标签（#80 刚栽过的那一类）。
"""
from __future__ import annotations
import json

_原基准一 = None
_原bootstrap = None
_调用次数 = {"基准一": 0, "bootstrap": 0}

跳过说明 = ("★★★ 本批**没有计算**基准一（同环境随机进场）。"
         "★ 理由：本批臂文件不记它（5 个数全来自真链流水），而它一条臂最多 412 次回测 ≈ 4 小时，"
         "66 条臂 ≈ 11 天，跑不完。★★ 跳过**不动**跑前预先登记的三件"
         "（条件 alpha 交互项 / 配对检验 / 随机排序对照）。全文见 probe/重测_1107/跳过基准一_1107.py。"
         "★★★ 这不是「前提破了」，是工程上主动跳过 —— 任何一句结论都不许引用基准一。")


class _没算的Z:
    """★ `bootstrap_on_ledger` 的返回桩 —— ★★ 形状对上（`.results` → `.z_effect`），值一律 None。"""
    class _项:
        z_effect = float("nan")
    results: dict = {}


def install() -> dict:
    """★ 装桩并返回 id() 自证。★★★ 自证要证「它真的被换掉了」，不是「我按了开关」。"""
    global _原基准一, _原bootstrap
    from engine import analyze
    if _原基准一 is None:
        _原基准一 = analyze.random_entry_benchmark
        _原bootstrap = analyze.bootstrap_on_ledger

    def 基准一桩(*a, **kw):
        _调用次数["基准一"] += 1
        # ★★★ 明说没算，并把「对照流水并池」给成 None —— ★ run_one 会 pop 它
        return {"★★★本批没算基准一": 跳过说明, "★对照流水并池": None}

    def bootstrap桩(*a, **kw):
        _调用次数["bootstrap"] += 1
        return _没算的Z()

    前1, 前2 = id(analyze.random_entry_benchmark), id(analyze.bootstrap_on_ledger)
    analyze.random_entry_benchmark = 基准一桩
    analyze.bootstrap_on_ledger = bootstrap桩
    return {"★原random_entry_benchmark_id": 前1,
            "★覆盖后id": id(analyze.random_entry_benchmark),
            "★真的换掉了": id(analyze.random_entry_benchmark) != 前1,
            "★原bootstrap_on_ledger_id": 前2,
            "★bootstrap真的换掉了": id(analyze.bootstrap_on_ledger) != 前2,
            "★★★为什么跳": 跳过说明,
            "★★★engine改动": "零（进程内替换函数指针）",
            "★★★不影响": "真链流水在它之前就算完了；随机排序用的是局部显式种子的 default_rng"}


def 调用次数() -> dict:
    return dict(_调用次数)
