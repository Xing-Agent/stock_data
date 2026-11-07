# -*- coding: utf-8 -*-
"""
★★★ 补「股数闸」读不到新池行情的洞 —— ★ engine 零改动(进程内替换一个函数指针)。

★ 三秒版:新池里大约六成的票,**所有基本面指标都是空的** —— 不是没有财报,
  是算股数的那一步**抛了错**,而上层把错吞了、当成「算不出」。

★★ 查出来的链条(★ 实测打出来的,不是猜的):
  fundamentals.quarter_frame → shares_quarterly → share_gate.adjusted_points → scan
  → 股数跳变需要「印证」→ _corroborate → _source_coefficients
  → ★★★ `data.load_manifest()[symbol]` —— 引擎的 manifest 是老池(pilot_300)的,
    **新池的票不在里面 → KeyError**(share_gate.py:232)。
  → ★ quarter_frame 整个抛错 → fundamentals.panel 的 `except Exception` 把它当成「这只票没数据」
    (fundamentals.py:416)→ ★★★ 这只票的市净率、市盈率、F 分数、ROC… **全部是 NaN**。
  ★ 研发池抽 400 只、4 个年末断面:每股净资产只有 36~39% 算得出(★ 财报库本身覆盖 100%)。

★★ 修法:只替换 `share_gate._source_coefficients` —— 老池里有的票**原样转回原函数**;
  不在老池的票,改读新池行情(market_ext_1105)的同一个字段 split_coefficient,
  ★ 读法和原函数**逐行一致**(只多支持 .gz,和烤新池那份一样)。
★★★ 这件事影响**所有在新池上跑基本面的地方**(不只是 A 路)—— 已写进《88》要通知主路。
"""
from __future__ import annotations
import gzip, json, os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXT = os.path.join(ROOT, "market_ext_1105")
# ★★ 1107 并池补:考卷那批的行情在 exam_1042/(★ 和 烤并池_1107 扫同样两个目录)
根们 = (os.path.join(ROOT, "market_ext_1105"), os.path.join(ROOT, "exam_1042"))
_装过 = False
_目录 = None


def _目录表() -> dict:
    """★ 和 烤新池_1106.目录表 同一个口径:SYM 或 SYM__CIK;多个主体取 bar 最多的那个。"""
    global _目录
    if _目录 is None:
        m = {}
        for 根, d in ((r, d) for r in 根们 if os.path.isdir(r) for d in sorted(os.listdir(r))):
            full = os.path.join(根, d)
            if not os.path.isdir(full):
                continue
            for fn in ("daily.json.gz", "daily.json"):
                p = os.path.join(full, fn)
                if os.path.exists(p):
                    m.setdefault(d.split("__")[0], []).append(p)
                    break
        _目录 = m
    return _目录


def _读行(p: str) -> list:
    op = gzip.open if p.endswith(".gz") else open
    with op(p, "rt", encoding="utf-8") as fh:
        return json.load(fh).get("data") or []


def install() -> dict:
    global _装过
    if _装过:
        return {"★已装过": True}
    import pandas as pd
    from engine import data, share_gate, fundamentals as F
    旧 = share_gate._source_coefficients

    def 新(symbol: str):
        if symbol in data.load_manifest():
            return 旧(symbol)                     # ★★★ 老池的票原样转回
        cand = _目录表().get(symbol) or []
        if not cand:
            return []                              # ★ 和原函数「读不到文件 → []」同口径
        rows_all = []
        for p in cand:
            try:
                rows_all.append(_读行(p))
            except (OSError, ValueError):
                rows_all.append([])
        rows = max(rows_all, key=len)             # ★ 多主体取 bar 最多的那个(同烤新池)
        out = []
        for r in rows:
            v = r.get("split_coefficient")
            if v is None:
                continue
            try:
                c = float(v)
            except (TypeError, ValueError):
                continue
            if c != c or c <= 0 or abs(c - 1.0) < 1e-9:
                continue
            out.append((pd.Timestamp(str(r["date"])[:10]), c))
        return out

    share_gate._source_coefficients = 新
    for fn in (getattr(F, "quarter_frame", None), getattr(F, "shares_quarterly", None),
               getattr(F, "panel", None), getattr(F, "metric_quarterly", None)):
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()
    for fn in (getattr(share_gate, n, None) for n in dir(share_gate)):
        if callable(fn) and hasattr(fn, "cache_clear"):
            fn.cache_clear()
    _装过 = True
    return {"★股数闸补上了": True, "新池行情目录数": len(_目录表())}
