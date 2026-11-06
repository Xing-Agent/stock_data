# -*- coding: utf-8 -*-
"""
★★★ 技-7 / 技-9 需要的两个零件 —— 进程内覆盖层（engine/ 零改动）

  ① 进场类型 b_ep_gap          —— 技-7 库拉麦吉 EP(大跳空 + 放量 + 之前长期没涨)
  ② 选股池类型 b_listed_within —— 技-9 次新股(上市 N 个日历日以内)

★ 挂法照抄 engine/pat6_ops.install():替换 matrices._entry_rule_raw / _universe_rule_mask 的函数指针,
  ★★★ 认不出的类型**原样转回原函数**(不吞掉),并把新类型登记进 config_adapter.IMPLEMENTED。

★★ 「上市日期」我们的库里**没有这个字段**(规矩⑬:已把字段列表打出来查过 ——
   panel_meta 列:status/n_bars/first_bar/last_bar/delisted/zero_bar/settlement_*/size_group/sector;
   manifest 列:…/delisting_date/size_group_at_start/market_cap_at_start_*;
   manifest_detail 列:…/start_date/end_date/bars/…;daily.json 顶层:…/start_date/end_date/…)。
   → ★ 代理:**这只票在我们行情里的第一根 K 线**(first_bar)。
   ★★★ 代理的毛病必须写明:① 2014-01 之前就上市的票 first_bar 都是窗口起点,不算次新(已排除);
       ② 拆分出来的新公司、SPAC 合并后的新代码、换 CIK 的,first_bar 也晚 —— **会混进来,当成次新**;
       ③ 数据中途缺口也会让 first_bar 变晚(老 300 池里查到过 3 只这样的)。
"""
from __future__ import annotations
import gzip, json, os
import numpy as np, pandas as pd

from engine import cache, matrices, config_adapter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
META = os.path.join(ROOT, "probe", "newpool_1106", "panel_meta_newpool.parquet")
FUND = os.path.join(ROOT, "fundamentals_ext")
窗口起点 = pd.Timestamp("2014-03-01")      # ★ first_bar 早于它 = 窗口起点前就在交易,不算次新

_orig_entry = None
_orig_uni = None
_ENTRY = {"b_ep_gap"}
_UNI = {"b_listed_within"}


def _need(p, k, t):
    if k not in p:
        raise ValueError(f"{t} 缺参数 {k} —— ★ 不给默认值")
    return p[k]


_FILE_CACHE = {}


def 财报公布日(sym: str) -> list:
    """★ 10-Q/10-K 的 SEC **接收时间**(available_at)。★★ 注意:这是**交报表**的时间,
    不一定是**发业绩新闻稿**的时间(很多公司先发 8-K 新闻稿,几天到几周后才交 10-Q)。"""
    if sym in _FILE_CACHE:
        return _FILE_CACHE[sym]
    p = os.path.join(FUND, sym, "fundamentals.json.gz")
    out = set()
    if os.path.exists(p):
        d = json.load(gzip.open(p, "rt"))
        for k in ("Revenue", "DilutedEPS", "NetIncomeLoss", "TotalAssets"):
            for r in (d.get("financial_versions") or {}).get(k, []) or []:
                if str(r.get("form", "")).startswith(("10-Q", "10-K")) and r.get("available_at"):
                    out.add(pd.Timestamp(r["available_at"]).tz_convert("America/New_York"))
    _FILE_CACHE[sym] = sorted(out)
    return _FILE_CACHE[sym]


def ep_gap(symbols, gap_min, vol_mult, vol_period, prior_lookback, prior_max_ret,
           hold_gap=True, near_filing_days=None):
    o = cache.field("open", symbols); c = cache.field("close", symbols)
    v = cache.field("volume", symbols)
    pc = c.shift(1)
    gap = o / pc - 1.0 >= gap_min
    vavg = v.rolling(vol_period, min_periods=vol_period).mean().shift(1)
    big = v >= vol_mult * vavg
    # ★ 「之前长期趴着没涨过」:跳空前一天往回 prior_lookback 日的涨幅 ≤ prior_max_ret
    flat = (pc / c.shift(1 + prior_lookback) - 1.0) <= prior_max_ret
    sig = gap & big & flat
    if hold_gap:
        sig &= c >= o                       # ★ 当天收盘守住开盘价(「不追最高点」的日线近似)
    if near_filing_days is not None:
        idx = c.index
        near = pd.DataFrame(False, index=idx, columns=c.columns)
        for s in c.columns:
            ts = 财报公布日(s)
            if not ts:
                continue
            # ★ 盘后接收 → 下一个交易日才是反应日;盘中/盘前 → 当天
            days = []
            for t in ts:
                d0 = pd.Timestamp(t.date())
                if t.hour >= 16:
                    d0 = d0 + pd.Timedelta(days=1)
                days.append(d0)
            pos = idx.searchsorted(pd.DatetimeIndex(days))
            col = np.zeros(len(idx), bool)
            for k in pos:
                col[k:min(len(idx), k + int(near_filing_days) + 1)] = True
            near[s] = col
        sig &= near
    return sig.fillna(False)


def listed_within(symbols, index, max_days):
    meta = pd.read_parquet(META)
    fb = meta["first_bar"].reindex(symbols)
    m = pd.DataFrame(False, index=index, columns=symbols)
    for s in symbols:
        f = fb.get(s)
        if f is None or pd.isna(f) or pd.Timestamp(f) < 窗口起点:
            continue
        age = (index - pd.Timestamp(f)).days
        m[s] = (age >= 0) & (age <= int(max_days))
    return m


def _entry(rule, symbols):
    t = rule.get("type")
    if t not in _ENTRY:
        return _orig_entry(rule, symbols)
    p = rule.get("params", {}) or {}
    return ep_gap(symbols, float(_need(p, "gap_min", t)), float(_need(p, "vol_mult", t)),
                  int(_need(p, "vol_period", t)), int(_need(p, "prior_lookback", t)),
                  float(_need(p, "prior_max_ret", t)), bool(p.get("hold_gap", True)),
                  p.get("near_filing_days"))


def _uni(rule, syms, index):
    t = rule.get("type")
    if t not in _UNI:
        return _orig_uni(rule, syms, index)
    p = rule.get("params", {}) or {}
    return listed_within(syms, index, int(_need(p, "max_days", t)))


def install():
    global _orig_entry, _orig_uni
    if _orig_entry is None:
        _orig_entry = matrices._entry_rule_raw
        matrices._entry_rule_raw = _entry
    if _orig_uni is None:
        _orig_uni = matrices._universe_rule_mask
        matrices._universe_rule_mask = _uni
    config_adapter.IMPLEMENTED["entry"] |= _ENTRY
    config_adapter.IMPLEMENTED["universe"] |= _UNI
