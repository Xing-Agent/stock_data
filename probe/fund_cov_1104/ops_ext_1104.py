#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 覆盖层(2026-11-04)—— 把 engine 的基本面读取口**指向新库** fundamentals_ext/

三秒版:engine 自己读的是老库 pilot_300(280 只、35 个科目)。
       这个文件在**运行时**把那一个读取函数换掉,改读新库
       fundamentals_ext/<代码>/fundamentals.json.gz(4,015 家、44 个科目),
       ★ 并把新库里 engine 还没登记过的科目补登记成「流量 / 存量」。
       ★★ engine/ 下一个字节都没动;套路照
          probe/gate_decomp_1103/run_gate_decomp_1103.py:_load_ext()。

★★★ 为什么要有这个文件(= 本轮查出来的那个缺口):
   probe/fundamental_buildout_1030/ops_fund_1030.py 的 install() **没有**指向新库。
   它的底座是 engine/data.py:480 load_fundamentals() → 老库 pilot_300,
   上面只「整列替换」了 EBIT / LongTermDebt 两列(从 probe 自己那份
   sec_overlay_1030.json.gz 读)。所以 ops_fund_1030._COLS 里 1104 新加的
   dc / sga / icop 三个键,在原状态下是**取不到**的。

★ 本文件只读新库,不写新库,不碰 exam_1042/。
"""
from __future__ import annotations

import functools
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for _p in (ROOT, os.path.join(ROOT, "probe", "fundamental_buildout_1030")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from engine import data, fundamentals as F          # noqa: E402

EXT_DIR = os.path.join(ROOT, "fundamentals_ext")
MANIFEST_SHA = os.path.join(EXT_DIR, "_MANIFEST.sha256")

#: ★ 新库里 engine 还没登记的科目 —— 不登记的话 F.quarterly() 会 raise KeyError,
#   而 ops_fund_1030.frame() 把 KeyError 吞掉变成空列(= 静默失效)。
#   ★★ 口径按科目性质分:利润表 = 流量(要 YTD 差分 + 滚 TTM);
#      资产负债表 = 存量(某时点余额,不差分不滚)。
NEW_FLOW = (
    "SellingGeneralAndAdministrativeExpense",     # 销售管理费用
    "IncomeLossFromContinuingOperations",         # 持续经营利润
    "OperatingIncomeLoss",                        # ★★★ 营业利润(单列臂才挂)
    "GrossProfit",                                # 毛利
)
NEW_STOCK = (
    "PropertyPlantAndEquipmentNet",               # 固定资产(厂房设备净值)
    "MarketableSecuritiesCurrent",                # 有价证券(流动)
    "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
    "ShortTermInvestments",
    "CashCashEquivalentsAndShortTermInvestments",
)

_orig_loader = None
_stats = {"命中": 0, "文件不存在": 0}
_notes: list[str] = []


def notes() -> list[str]:
    return list(_notes)


def manifest_fingerprint() -> str:
    """★ 库指纹 = 对 _MANIFEST.sha256 整个文件取 sha256(照 CHANGELOG 的口径)。"""
    import hashlib
    h = hashlib.sha256()
    with open(MANIFEST_SHA, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ext_symbols() -> list[str]:
    """新库里的实体轴(文件夹名),★ 排掉 _ 开头的元数据文件。"""
    out = []
    for name in sorted(os.listdir(EXT_DIR)):
        if name.startswith("_") or name.startswith("."):
            continue
        if os.path.exists(os.path.join(EXT_DIR, name, "fundamentals.json.gz")):
            out.append(name)
    return out


@functools.lru_cache(maxsize=256)
def load_ext(symbol: str) -> dict:
    """★ 读新库一只票的全部 financial_versions。算不出就是空,不猜不补。"""
    p = os.path.join(EXT_DIR, symbol, "fundamentals.json.gz")
    if not os.path.exists(p):
        _stats["文件不存在"] += 1
        return {}
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    _stats["命中"] += 1
    return raw.get("financial_versions") or {}


def _clear_caches() -> None:
    import ops_fund_1030 as OF
    for fn in (F.quarterly, F.ttm, F.quarter_frame, F.panel, F.shares_quarterly,
               OF.frame, OF.panel):
        fn.cache_clear()


def install(with_operating_income: bool = False) -> None:
    """★ 把 engine 的基本面读取口指向新库。

    ★★★ with_operating_income —— 照 ops_fund_1030 的铁律②:营业利润
      (OperatingIncomeLoss)和 EBIT **不是同一个指标**,默认**不挂**,
      要挂必须显式传 True,而且必须**单列成一条臂**。
    """
    global _orig_loader
    if _orig_loader is None:
        _orig_loader = data.load_fundamentals
    data.load_fundamentals = load_ext
    for m in NEW_STOCK:
        F.STOCK_METRICS.add(m)
    for m in NEW_FLOW:
        if m == "OperatingIncomeLoss" and not with_operating_income:
            continue
        F.FLOW_METRICS.add(m)
    _clear_caches()
    _notes.append(
        f"★★ engine 的 data.load_fundamentals 已指向新库 {EXT_DIR}"
        f"(实体 {len(ext_symbols())} 家)。★ 新科目已登记:"
        f"流量 {len([m for m in NEW_FLOW if m in F.FLOW_METRICS])} 个 / "
        f"存量 {len(NEW_STOCK)} 个。"
        f"★★★ 营业利润档 {'已挂(单列臂)' if with_operating_income else '未挂'}。")


def uninstall() -> None:
    global _orig_loader
    if _orig_loader is not None:
        data.load_fundamentals = _orig_loader
        _orig_loader = None
    _clear_caches()


def stats() -> dict:
    return dict(_stats)
