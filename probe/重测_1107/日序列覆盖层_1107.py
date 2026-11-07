# -*- coding: utf-8 -*-
"""★★★ 把每条臂的**每日净值 / 每日敞口**存下来 —— ★ 没有它，配对检验和条件 alpha 都做不了。

★★★ 为什么要加这一层（★ 1107 夜自查出来的，★★ 查出来时第一条臂刚开跑，0 个臂文件）：
  `跑重测_1107.py` 自己的**跑前预先登记**第一行写的是：
     「**主判据 = 条件 alpha（交互项回归）**：策略日收益 ~ 指数日收益 + 环境×指数日收益」
  ★★ 而 `run_friction_1104.run_one()` **只存逐笔流水 + 几个汇总标量**：
     `res.equity`（每日净值）和 `res.exposure`（每日敞口）拿到手就**扔了**
     （全文件里 `equity` 只出现在 line 317/322 的函数签名里，一次都没存过）。
  → ★★★ 所以那个预先登记的主判据，**用这个跑批的产物根本算不出来**：
     · 配对检验（规矩㊸v2 第①道，强制的第一道闸）—— 要逐日相减 → **算不了**
     · 条件 alpha 交互项回归（本批自己写的主判据）—— 要策略日收益 → **算不了**
     · 「最多多少天没新高」—— 要净值曲线 → **算不了**
  ★★ 能从逐笔流水算的只有：最长连亏笔数、持仓画像、每笔 R 的随机对照分位数。
→ ★★★ 这是「**预先登记和实现不一致**」，不是「结论不好看」。
  ★ 发现得早（0 个臂文件）→ 现在修的代价是 0；跑完 66 条再修 = 整批重跑。

★★★ 做法（照规矩：engine 一个字节不改）：
  ★ 在**本进程内**把 `run_friction_1104._ORIG_RUN_CHAIN` 换成一个**透传**包装：
    照原样调用原函数、原样返回它的返回值，★★ 只是顺手把 `res.equity / res.exposure`
    写到 `日序列_1107/` 下。★★★ 带 `id()` 自证；★ 出任何岔子**原样退回**，不许影响跑批。

★★ 一个坑（★ 必须说清，否则存出来的是错的）：
  `run_one()` 里 `_ORIG_RUN_CHAIN` **不止被调一次** ——
  第 414 行先跑**真链**，★★ 紧接着 `analyze.random_entry_benchmark(...)` 里面
  还会按 N 个种子**再跑一堆随机进场对照**。
  → ★★★ 所以只认**每条臂的第 1 次调用**（真链），后面那些一律不存。
  ★ 靠 `开始新臂(label)` 显式重置计数，**不靠猜**。
"""
from __future__ import annotations
import io, json, os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(HERE, "日序列_1107")
_当前臂: str | None = None
_本臂第几次调用 = 0
_原run_chain = None
_已存: dict[str, str] = {}
_自证: dict = {}


def 安全名(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def 开始新臂(label: str) -> None:
    """★★★ 每条臂开跑前必须调一次 —— ★ 计数靠显式重置，不靠猜第几次。"""
    global _当前臂, _本臂第几次调用
    _当前臂 = label
    _本臂第几次调用 = 0


def 路径(label: str) -> str:
    return os.path.join(OUTDIR, f"d_{安全名(label)}.csv")


def 已有(label: str) -> bool:
    return os.path.exists(路径(label))


def install() -> dict:
    """★ 装上透传包装，返回 id() 自证。★★ 重复装不会叠加（原函数只记第一次）。"""
    global _原run_chain, _自证
    import run_friction_1104 as F
    if _原run_chain is None:
        _原run_chain = F._ORIG_RUN_CHAIN
    os.makedirs(OUTDIR, exist_ok=True)

    def 包装(*a, **kw):
        global _本臂第几次调用
        res = _原run_chain(*a, **kw)              # ★★★ 先原样调用，返回值一个字不改
        try:
            _本臂第几次调用 += 1
            if _当前臂 is not None and _本臂第几次调用 == 1:
                eq = getattr(res, "equity", None)
                ex = getattr(res, "exposure", None)
                if eq is not None and len(eq):
                    df = pd.DataFrame({"净值": pd.Series(eq).astype(float)})
                    if ex is not None and len(ex):
                        df["敞口"] = pd.Series(ex).reindex(df.index).astype(float)
                    df.index.name = "日期"
                    df.to_csv(路径(_当前臂))
                    _已存[_当前臂] = f"{len(df)} 天 · {df.index.min()} → {df.index.max()}"
        except Exception as e:
            # ★★★ 存盘失败绝不许影响跑批 —— ★ 大声记一行，继续
            _已存[str(_当前臂)] = f"★ 存失败 {type(e).__name__}: {e}"
        return res

    前 = id(F._ORIG_RUN_CHAIN)
    F._ORIG_RUN_CHAIN = 包装
    _自证 = {"★原run_chain_id": 前, "★覆盖后id": id(F._ORIG_RUN_CHAIN),
            "★真的换掉了": id(F._ORIG_RUN_CHAIN) != 前,
            "★★★只存每条臂的第1次调用": "后面 random_entry_benchmark 那些种子不存",
            "★★★engine改动": "零（进程内替换函数指针）",
            "★出岔子怎么办": "原样返回原函数的结果，只是不存这一条",
            "★输出目录": OUTDIR}
    return _自证


def 已存清单() -> dict:
    return dict(_已存)
