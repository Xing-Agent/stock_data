#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 任务一 · 核清管线指向(2026-11-04)

三秒版:问一句话 —— 「engine 的 PIT 流水线现在到底从哪儿读数?那 7 个新字段
       能不能取到?」答法:两条臂实测同一批票。
         臂 A = 现状(ops_fund_1030.install(),不碰任何东西)
         臂 B = 把读取口指向新库(probe/fund_cov_1104/ops_ext_1104.py)
       ★ 只读,只写 probe/fund_cov_1104/ 下的新文件。考卷 exam_1042/ 一只没碰。

跑法:python3 probe/fund_cov_1104/pipeline_check_1104.py
"""
from __future__ import annotations

import json
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "fundamental_buildout_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

OUT = os.path.join(HERE, "pipeline_check_1104.json")

PROBE_SYMS = ("AAPL", "UNP", "JPM")
#: ★ ops_fund_1030._COLS 里 1104 新加的四个键
FOUR_KEYS = ("dc", "sga", "icop", "liab")
#: ★★ 数据组 11-04 说新增的 7 个字段 → 真实 us-gaap 标签名
SEVEN_FIELDS = {
    "固定资产": "PropertyPlantAndEquipmentNet",
    "毛利": "GrossProfit",
    "营业利润": "OperatingIncomeLoss",
    "总负债": "Liabilities",
    "SG&A": "SellingGeneralAndAdministrativeExpense",
    "持续经营利润": "IncomeLossFromContinuingOperations",
    "有价证券": "MarketableSecuritiesCurrent",
}


def _col_report(sym: str) -> dict:
    """★ 实测 ops_fund_1030.frame(sym) 里那四个键能不能取到非空序列。"""
    import ops_fund_1030 as OF
    try:
        v, _e = OF.frame(sym)
    except Exception as exc:                       # noqa: BLE001
        return {"错误": f"{type(exc).__name__}: {exc}"}
    if v.empty:
        return {k: 0 for k in FOUR_KEYS} | {"期数合计": 0}
    return {k: int(v[k].notna().sum()) if k in v.columns else "列不存在"
            for k in FOUR_KEYS} | {"期数合计": int(len(v))}


def _raw_registry_report() -> dict:
    """★ engine 的流量/存量登记表里有没有这 7 个科目(没登记 → quarterly() raise)。"""
    from engine import fundamentals as F
    out = {}
    for zh, tag in SEVEN_FIELDS.items():
        where = ("FLOW_METRICS" if tag in F.FLOW_METRICS
                 else "STOCK_METRICS" if tag in F.STOCK_METRICS else None)
        out[f"{zh}({tag})"] = where or "★★★ 两张登记表都没有 → quarterly() 会 raise KeyError"
    return out


def main() -> None:
    import ops_ext_1104 as EXT
    from engine import data, fundamentals as F

    rep: dict = {"报告": "任务一 · 管线指向核查(2026-11-04)"}
    rep["库指纹_跑前"] = EXT.manifest_fingerprint()
    rep["老库路径(engine 自己的)"] = {
        "代码位置": "engine/data.py:36 PILOT / :104 fpath / :480 load_fundamentals",
        "实际路径": "pilot_300/<代码>/fundamentals.json",
        "实体只数": len([n for n in os.listdir(os.path.join(ROOT, "pilot_300"))
                        if os.path.isdir(os.path.join(ROOT, "pilot_300", n))]),
    }
    rep["新库路径(数据组 1104)"] = {
        "实际路径": "fundamentals_ext/<代码>/fundamentals.json.gz",
        "实体只数": len(EXT.ext_symbols()),
    }

    # ── 0 · 登记表(没挂任何覆盖层时的原状) ──────────────────────────
    rep["0_engine登记表原状"] = _raw_registry_report()

    # ── 臂 A · 现状:ops_fund_1030.install() ────────────────────────
    import ops_fund_1030 as OF
    armA: dict = {}
    try:
        OF.install()                      # ★ 默认 source="sec_table"
        armA["install()_读的是什么"] = {
            "底座": "engine/data.py:480 load_fundamentals → pilot_300/<代码>/fundamentals.json",
            "覆盖层文件": os.path.relpath(OF._SEC_OVERLAY, ROOT),
            "覆盖层只替换哪两列": list(OF._SEC_METRICS),
            "证据_行号": [
                "probe/fundamental_buildout_1030/ops_fund_1030.py:97  _SEC_OVERLAY = HERE/sec_overlay_1030.json.gz",
                "probe/fundamental_buildout_1030/ops_fund_1030.py:112 base = dict(_orig_load_fund(symbol))",
                "probe/fundamental_buildout_1030/ops_fund_1030.py:135 _orig_load_fund = data.load_fundamentals",
                "probe/fundamental_buildout_1030/ops_fund_1030.py:509-512 install() → install_sec_overlay / install_overlay",
                "★ 全文搜索 fundamentals_ext:只在 :226 的注释里出现，没有任何路径读取",
            ],
        }
        armA["四个键实测"] = {s: _col_report(s) for s in PROBE_SYMS}
    except Exception:                                  # noqa: BLE001
        armA["错误"] = traceback.format_exc(limit=4)
    rep["A_现状"] = armA

    # ── 臂 B · 指向新库(不挂营业利润) ──────────────────────────────
    EXT.install(with_operating_income=False)
    rep["B_指向新库_不挂营业利润"] = {
        "备注": EXT.notes()[-1],
        "登记表": _raw_registry_report(),
        "四个键实测": {s: _col_report(s) for s in PROBE_SYMS},
    }

    # ── 臂 B' · 指向新库 + 单列挂上营业利润 ────────────────────────
    EXT.install(with_operating_income=True)
    rep["B2_指向新库_挂营业利润"] = {
        "备注": EXT.notes()[-1],
        "四个键实测": {s: _col_report(s) for s in PROBE_SYMS},
    }

    # ── 7 个字段逐个:新库里有没有 + PIT 流水线取不取得到 ───────────
    seven: dict = {}
    for zh, tag in SEVEN_FIELDS.items():
        row: dict = {"us-gaap 标签": tag}
        raw_cnt = {}
        for s in PROBE_SYMS:
            raw_cnt[s] = len(EXT.load_ext(s).get(tag) or [])
        row["新库原始记录条数"] = raw_cnt
        # 过一遍 engine 的 PIT 流水线(ttm 或 quarterly)
        kind = "ttm" if tag in F.FLOW_METRICS else (
            "quarterly" if tag in F.STOCK_METRICS else None)
        pit = {}
        for s in PROBE_SYMS:
            if kind is None:
                pit[s] = "★★★ 科目未登记 → quarterly() raise KeyError"
                continue
            try:
                ser = F.ttm(s, tag) if kind == "ttm" else F.quarterly(s, tag)
                pit[s] = len(ser)
            except Exception as exc:                    # noqa: BLE001
                pit[s] = f"{type(exc).__name__}: {exc}"
        row["过 engine PIT 流水线后的期数"] = pit
        row["口径"] = kind
        seven[zh] = row
    rep["7个新字段_逐个"] = seven
    rep["新库读取统计"] = EXT.stats()
    rep["库指纹_跑后"] = EXT.manifest_fingerprint()
    rep["库指纹_跑前跑后一致"] = rep["库指纹_跑前"] == rep["库指纹_跑后"]
    rep["没碰考卷"] = "★ 全程没有打开 exam_1042/ 下任何文件;实体只从 fundamentals_ext / pilot_300 来"

    with open(OUT, "w", encoding="utf-8") as fh:        # ★ 先写文件再打印
        json.dump(rep, fh, ensure_ascii=False, indent=2)
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"\n★ 已写 {OUT}")


if __name__ == "__main__":
    main()
