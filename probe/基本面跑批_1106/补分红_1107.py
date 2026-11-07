# -*- coding: utf-8 -*-
"""
★★★★★ 补「全收益」在并池上**其实没开**的洞 —— ★ engine 零改动(进程内替换 data.dividends)。

★ 三秒版:打开 `data.TOTAL_RETURN_DEFAULT = True` 之后,★★★ 策略那一侧**一分钱分红都没收到**。

★★ 查出来的链条(★ 实测打出来的):
  chain.run_chain(total_return=True) → 逐只调 `data.dividends(sym)`(chain.py:497)
  → `dividends()` 第一行 `meta = load_manifest().get(symbol)`(data.py:254)
  → ★★★ 引擎的 manifest 只有老的 **300 只** → 并池 3,858 只里**几乎全部**拿到 None → 返回空序列
  → ★ 开关是开着的,但策略侧收到的分红 = 0。
  ★ 实测:AAPL / MSFT / XOM / KO / T / NVDA 六只,`data.dividends()` 全部返回 **0 条**。
★★★ 而基准侧(SPY)走的是另一条路(基准覆盖层),**是有分红的** →
  ★ 这正是规矩㊽说的「只改一边」,而且方向是**单方面给基准加分**(《24》#77 的反方向)。

★★ 修法:只替换 `data.dividends` —— manifest 里有的票**原样转回原函数**;
  没有的票,按并池烤盘那份(`probe/并池_1107/烤并池_1107.py`)**同一张目录表、同一种多段拼接**
  (四个目录、按日期排、重复日期保留后读到的那段)读出原始行,
  ★ 分红字段、拆股折算**逐行照抄原函数**(复用 `split_gate.ratio_events_from_rows`)。
"""
from __future__ import annotations
import functools, gzip, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_装过 = False
_目录 = None


def _目录表() -> dict:
    global _目录
    if _目录 is None:
        sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
        import 烤并池_1107 as P                   # ★ 同一张目录表(四个目录)
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            P.目录表两处()
        _目录 = dict(P._DIRS)
    return _目录


def _行(symbol: str) -> list:
    rows_by_date = {}
    for p in _目录表().get(symbol) or []:
        op = gzip.open if p.endswith(".gz") else open
        try:
            with op(p, "rt", encoding="utf-8") as fh:
                rows = json.load(fh).get("data") or []
        except (OSError, ValueError):
            continue
        for r in rows:                              # ★ 重复日期保留后读到的那段(同拼接口径)
            rows_by_date[str(r.get("date"))[:10]] = r
    return [rows_by_date[k] for k in sorted(rows_by_date)]


def install() -> dict:
    global _装过
    if _装过:
        return {"★已装过": True}
    import pandas as pd
    from engine import data, split_gate
    旧 = data.dividends

    @functools.lru_cache(maxsize=None)
    def 新(symbol: str) -> pd.Series:
        if data.load_manifest().get(symbol) is not None:
            return 旧(symbol)                         # ★★★ 老 manifest 里有的原样转回
        rows = _行(symbol)
        recs = []
        for r in rows:                                 # ★ 以下逐行照抄 data.dividends
            v = r.get("dividend_amount")
            if v in (None, ""):
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if x == 0.0 or x != x:
                continue
            recs.append((pd.Timestamp(str(r["date"])[:10]), x))
        if not recs:
            return pd.Series(dtype=float)
        s = pd.Series({d: v for d, v in recs}).sort_index()
        for ev in split_gate.ratio_events_from_rows(symbol, rows):
            ts = pd.Timestamp(ev.date)
            m = s.index < ts
            if m.any():
                s.loc[m] = s.loc[m] * ev.ratio
        return s

    data.dividends = 新
    _装过 = True
    样 = {s: int(len(新(s))) for s in ("AAPL", "MSFT", "XOM", "KO", "T", "NVDA")}
    return {"★分红补上了": True, "★★自证·六只的分红条数": 样,
            "★★原函数(老manifest)对这六只": "全部 0 条(1107 晚实测)"}
