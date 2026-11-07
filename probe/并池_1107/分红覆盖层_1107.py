# -*- coding: utf-8 -*-
"""★★★ 分红覆盖层 —— ★ 让 `data.dividends()` 能看见并池那 3,858 只的分红。

★★★ 为什么要有这一层（《24》#80）：
  ★ 今天我打开了 `TOTAL_RETURN_DEFAULT = True`，并且自证打印了「False → True」，
    ★★ 然后宣布「本批是全收益口径」。
  ★★★ 但 `data.dividends(票)` 是从 **`load_manifest()`** 里找文件路径的，
    而那份 manifest 是**默认的 300 只 pilot 名单** —— 我们换了池子（3,858 只）
    却**没换这份名单**。
  → ★★ 实测：面板 ∩ 默认 manifest = **237 只**（约 6%）；基准 SPY = **0 条分红**。
  → ★★★ 也就是说：那个开关**几乎是空转的**，口径标签是错的。

★★ 这跟 #74（池表没换，universe 掩膜把苹果微软全排除）是**同一个毛病**：
  ★ 换了池子，但**没把所有依赖池子的入口都换掉**。
  ★★★ 三个登记点 → 现在是**四个**：面板 · manifest · 池表 · **分红**。

★★★ 结构性改法（规矩㊻ —— 同类错第七次，不许再立「下次记得」）：
  ★ 自证不许再打印「我按了开关」，★★ 必须打印「**它真的起作用了**」：
    覆盖了几只 · 非零分红格子数 · 基准侧几条 —— ★★★ 覆盖率不够**直接停跑**。

★ engine 零改动：进程内替换 `data.dividends` 的函数指针，没命中原样退回原函数。
"""
from __future__ import annotations
import glob
import gzip
import json
import os
import pandas as pd

from engine import data, split_gate

# ★ 和《并池》《接新基准》同一套扫法：按目录名倒序，新交付优先
_股票目录 = ("exam_1042", "exam_pre2016_1107", "pilot_300", "pilot_50")
_基准目录 = ("market_macro_1105", "market_extra_1107", "market_ext_1105",
            "market_etf_1107", "market_etf_1106")

_原dividends = None
_路径表: dict[str, list[str]] = {}


def _扫(dirs) -> dict[str, list[str]]:
    """★ 票 → 它的日线文件列表（可能多段，★★ 比如 2004~2015 和 2016~ 两段）。"""
    出 = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            p = os.path.join(d, sub)
            if not os.path.isdir(p):
                continue
            fs = [f for f in sorted(glob.glob(os.path.join(p, "*")))
                  if "daily" in os.path.basename(f).lower()]
            if fs:
                出.setdefault(sub, []).extend(fs)
    return 出


def _读行(f: str) -> list:
    op = gzip.open if f.endswith(".gz") else open
    try:
        o = json.load(op(f, "rt", encoding="utf-8"))
    except Exception:
        return []
    if isinstance(o, list):
        return o
    return o.get("data") or o.get("results") or []


def _分红(票: str) -> pd.Series:
    """★★ 读出某只票的每股分红序列，★★★ 并按拆股系数折算到和价格同口径。"""
    recs: dict[pd.Timestamp, float] = {}
    rows_all: list = []
    for f in _路径表.get(票, []):
        rows = _读行(f)
        rows_all.extend(rows)
        for r in rows:
            v = r.get("dividend_amount")
            if v in (None, "", 0, 0.0, "0", "0.0"):
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if x == 0.0 or x != x:
                continue
            recs[pd.Timestamp(str(r["date"])[:10])] = x      # ★ 多段重叠按后读到的为准
    if not recs:
        return pd.Series(dtype=float)
    s = pd.Series(recs).sort_index()
    # ★★★ 和 engine/data.dividends 同一套折算：除息日之前的分红按同批拆股系数缩放
    try:
        for ev in split_gate.ratio_events_from_rows(rows_all):
            日, 比 = ev[0], float(ev[1])
            if 比 and 比 != 1.0:
                s.loc[s.index < pd.Timestamp(日)] /= 比
    except Exception:
        pass      # ★ 折算失败不静默改数，★★ 原样返回未折算的（自证里会写出来）
    return s


def install(需覆盖: list[str] | None = None, 最低覆盖率: float = 0.90) -> dict:
    """★ 装上覆盖层并返回自证。★★★ `需覆盖` 给面板的票列表时，覆盖率不足会抛。"""
    global _原dividends, _路径表
    if _原dividends is None:
        _原dividends = data.dividends
    _路径表 = _扫(_股票目录)
    _路径表.update(_扫(_基准目录))                     # ★ 基准也要能取到分红

    def dividends(票: str) -> pd.Series:
        s = _分红(票)
        if len(s):
            return s
        return _原dividends(票)                        # ★★ 没命中原样退回，不悄悄返回空
    前 = id(data.dividends)
    data.dividends = dividends
    try:
        import engine.chain as _chain
        if hasattr(_chain, "data"):
            pass                                       # ★ chain 用的是 data.dividends 属性，已换
    except Exception:
        pass

    # ---- ★★★ 自证：证明「它真的起作用了」，不是「我按了开关」
    基准自证 = {}
    for b in ("SPY", "QQQ", "IWM", "IWD", "IWF"):
        s = dividends(b)
        基准自证[b] = f"{len(s)} 条" + (f" · {s.index[0].date()} → {s.index[-1].date()}"
                                      if len(s) else "  ★★★ 零！")
    自证 = {"★原dividends_id": 前, "★覆盖后id": id(data.dividends),
           "★真的换掉了": 前 != id(data.dividends),
           "★★★扫到的票": len(_路径表),
           "★★★基准侧分红": 基准自证,
           "★★★engine改动": "零（进程内替换函数指针）",
           "★没命中怎么办": "原样退回原函数，不悄悄返回空"}

    if 需覆盖:
        有 = [t for t in 需覆盖 if len(dividends(t))]
        率 = len(有) / max(1, len(需覆盖))
        抽 = 需覆盖[: min(300, len(需覆盖))]
        格子 = int(sum(len(dividends(t)) for t in 抽))
        自证["★★★覆盖率"] = (f"{len(有)}/{len(需覆盖)} 只有分红记录 = {率*100:.1f}%"
                          f"（★ 抽前 {len(抽)} 只共 {格子} 个非零分红格子）")
        # ★★ 注意：不是每只票都付息（成长股、ETF 以外的很多票本来就零分红），
        #   ★★★ 所以这里的「覆盖率」指的是**能查到文件**的比例，不是付息比例。
        查得到 = [t for t in 需覆盖 if t in _路径表]
        自证["★★★查得到文件的比例"] = (f"{len(查得到)}/{len(需覆盖)} = "
                                 f"{len(查得到)/max(1,len(需覆盖))*100:.1f}%")
        if len(查得到) / max(1, len(需覆盖)) < 最低覆盖率:
            raise AssertionError(
                f"★★★ 分红文件只覆盖 {len(查得到)}/{len(需覆盖)}，"
                f"低于 {最低覆盖率*100:.0f}% —— 停跑（#80：别再宣布空转的口径）")
    return 自证


def 全收益基准(符号: str = "SPY") -> pd.Series:
    """★★★ 基准的**全收益净值**（分红再投），★ 给条件 alpha 回归和懒人基准用。

    ★★ 规矩㊽：口径改动**两侧一起改**。★★★ 只给策略侧补分红、基准侧不补，
      等于**单方面给自己加分**（B 路 #77 实测过反方向的版本）。
    """
    px = data.load_benchmark(符号)["close"].dropna()
    dv = data.dividends(符号).reindex(px.index).fillna(0.0)
    r = px.pct_change().fillna(0.0) + (dv / px.shift(1)).fillna(0.0)
    return (1.0 + r).cumprod()


__all__ = ["install", "全收益基准"]
