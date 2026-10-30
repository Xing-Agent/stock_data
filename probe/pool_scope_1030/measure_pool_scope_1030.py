#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
收窄到「大盘+中盘」之后重跑(只读;不改 engine/ 里的任何既有文件,
不碰 probe/phaseshift_1030/、probe/liquidity_gate_1030/、
probe/schema_addon_1030/、probe/survivorship_1029/)。

三秒版:策略组拍板「只做大+中(排名 1–2000)」。这个脚本回答三件事:
  ① 收窄之后还需不需要流动性门槛(用实测的挡掉比例说话,不假设);
  ② 原来那 16 条「由赚转亏」的链,在大+中池上还活着吗;
  ③ 和全池比,整体每笔 R 和笔数变成多少。

★ 口径开关在 engine/pool_scope.py 的 DEFAULT_SCOPE —— 本脚本**不自带**口径,
  也不硬编码 2000 这个数,全部从那个模块拿。

★ 纪律 4(一样东西两种写法)本脚本显式处理的:
  1. 流水目录两处:engine/ledgers_* 是正本(183 文件 / 146,991 笔);
     probe/breakeven_1029/ledgers/* 是其中 54 个的副本 → 必须排除。
     `*ledger*` 一把捞会得 237 个文件。
  2. 表头 3 种写法(带 BOM 的 `﻿symbol` / 缺 size_mult / 全列)→ utf-8-sig + 按列名取值。
  3. 池子代码 = 当年年初代码(ANTM),流水代码 = 最终代码(ELV)
     → 用 company_id + 年份双条件(engine/pool_scope.PoolIndex)。
  4. 池子 tier(大/中/小)≠ 流水 liquidity_tier(高/中/低流动性),不可混用。
  5. ★ 链名也有两种写法:results JSON 里是「技-1 · 海龟 System 2(55 日入 / 20 日出)」,
     流水文件名是「技-1·海龟 System2(55日入_20日出)」—— 空格、全角点、/ vs _
     全不一样。→ 归一化后再对(_norm())。只认一种就是这一类 bug 的第 8 次。

★ 「天」一律**交易日**:252 是一年的交易日数,ADV20 / 60d 都是交易日。
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import re
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)

from engine import pool_scope as PS                                # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))

KNOWN_FILES = 183
KNOWN_TRADES = 146_991
KNOWN_CHAINS = 182            # 183 个文件里有 1 个是空流水
KNOWN_FUNNEL_CHAINS = 93
KNOWN_SIGNALS = 378_841
KNOWN_FUNNEL_TRADES = 62_336

TRADING_DAYS_PER_YEAR = 252
ENGINE_EQUITY = 1_000_000.0
ENGINE_POS_PCT = 0.10
ENGINE_POS_DOLLARS = ENGINE_EQUITY * ENGINE_POS_PCT     # = 100,000
MIN_TRADES = 30

#: ★★ 流动性门槛网格,直接用**绝对门槛(日均成交额美元)**。
#  上一轮已经证明门槛是**一维**的:门槛 = X × 账户规模 × 单笔仓位比例,
#  同一个门槛值下所有数字完全一样。所以这一轮不再排 X × 账户 的网格,
#  直接排门槛本身 —— 并且**必须包含 $50,000**,因为上一轮的头条数字
#  (「松到 $5 万/日 就挡掉 2.05% 成交、而那 2.05% 占全库净利 25.7%」)
#  就在这一档,不放进来就没法说「收窄之后这个数变成多少」。
THR_GRID = [50_000, 100_000, 250_000, 500_000, 1_000_000, 2_000_000,
            5_000_000, 10_000_000, 50_000_000, 100_000_000]

#: 门槛 ↔ X 的换算(X = 门槛 ÷ 计划仓位)。引擎自己的计划仓位 = $100,000。
X_GRID = [10, 20, 50, 100, 200, 500, 1000]

#: ★ 上一轮(全池)点名的 16 条「由赚转亏」链 —— 判据是 X=10 下仍 ≥30 笔但每笔 R 转负。
#  这里只存链名(目录/文件名),用来逐条回答「在大+中池上还活着吗」。
FLIPPED_16 = [
    "批五修正/技-11_★两日结构(Spring日量≥1.2×_窗口2日)",
    "批五修正/技-11_★两日结构(Spring日量≥1.0×_窗口2日)",
    "批五修正/技-11_★两日结构(Spring日量≥1.0×_窗口3日)",
    "批五修正/技-11_★两日结构(Spring日量≥1.2×_窗口3日)",
    "A0十二条/技-1·海龟 System2(55日入_20日出)",
    "批五修正/技-11_★两日结构(Spring日量≥0.8×_窗口3日)",
    "技术派六条三版/技-5_行业版(次数≥3_衰减0.65_缩量0.60)",
    "原著离场/技-6_原著版3日规则(箱底0容差)",
    "剔污染/技-6_原著版3日规则(箱底0容差)__污染版",
    "批五修正/技-11_★两日结构(Spring日量≥0.8×_窗口2日)",
    "技术派六条三版/技-6_原著版(3日规则,★无振幅条件)",
    "技术派六条三版/技-3_行业版(放量1.55×_中值)",
    "批五修正/技-11_★两日结构(Spring日量≥1.2×_窗口5日)",
    "A0十二条_新拆股口径/技-12·康纳斯(RSI2<5)",
    "新基准线/技-12_康纳斯均值回归",
    "剔污染/技-12_康纳斯(RSI2<5)__污染版",
]

#: 上一轮报的「原每笔 R → 加门槛后每笔 R」,报告里要对照
FLIPPED_16_OLD = {
    "批五修正/技-11_★两日结构(Spring日量≥1.2×_窗口2日)": (0.6929, -0.1950),
    "批五修正/技-11_★两日结构(Spring日量≥1.0×_窗口2日)": (0.4014, -0.1950),
    "批五修正/技-11_★两日结构(Spring日量≥1.0×_窗口3日)": (0.2159, -0.1251),
    "批五修正/技-11_★两日结构(Spring日量≥1.2×_窗口3日)": (0.3715, -0.1206),
    "A0十二条/技-1·海龟 System2(55日入_20日出)": (0.3531, -0.0677),
    "批五修正/技-11_★两日结构(Spring日量≥0.8×_窗口3日)": (0.0526, -0.0634),
    "技术派六条三版/技-5_行业版(次数≥3_衰减0.65_缩量0.60)": (0.0086, -0.0211),
    "原著离场/技-6_原著版3日规则(箱底0容差)": (0.0039, -0.0173),
    "剔污染/技-6_原著版3日规则(箱底0容差)__污染版": (0.0039, -0.0173),
    "批五修正/技-11_★两日结构(Spring日量≥0.8×_窗口2日)": (0.1780, -0.0130),
    "技术派六条三版/技-6_原著版(3日规则,★无振幅条件)": (0.0156, -0.0029),
    "技术派六条三版/技-3_行业版(放量1.55×_中值)": (0.0199, -0.0009),
    "批五修正/技-11_★两日结构(Spring日量≥1.2×_窗口5日)": (0.2526, -0.0008),
    "A0十二条_新拆股口径/技-12·康纳斯(RSI2<5)": (0.0005, -0.0001),
    "新基准线/技-12_康纳斯均值回归": (0.0000, -0.0001),
    "剔污染/技-12_康纳斯(RSI2<5)__污染版": (0.0000, -0.0001),
}


def fnum(s):
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def _norm(s: str) -> str:
    """★★ 链名归一化(纪律 4 第 8 处「同一样东西两种写法」)。

    同一条链在仓库里有**三种写法**:
      流水文件名   技-11_★两日结构(Spring日量≥1.2×_Test窗口2日)
      results JSON 技-11 · ★两日结构(Spring 日量 ≥1.2× · Test 窗口 2 日)
      上一轮报告里 技-11_★两日结构(Spring日量≥1.2×_窗口2日)      ← 连 Test 都掉了
    差的全是**分隔符和空格**:空格 / 全角点「·」/ 下划线 / 斜杠 / 全角括号,
    外加报告手写时漏掉的 "Test"。
    ★ 所以归一化就是:删掉全部空白和分隔符、全角括号折半、删掉 "Test"。
    ★ 代价:160 个 key 对应 183 个文件 —— 同名链出现在多个流水目录里
      (同一策略在不同批次各跑过一遍)。所以归一化只用来**对名字**,
      不用来当唯一键;归不唯一的地方必须标出来,见 `信号数_归属`。
    """
    s = re.sub(r"\s+", "", str(s))
    s = s.replace("(", "(").replace(")", ")").replace("Test", "")
    return re.sub(r"[·・_/,、]", "", s)


# ---------------------------------------------------------------- 一 · 读流水
def load_ledgers():
    pats = sorted(glob.glob(os.path.join(ROOT, "engine", "ledgers_*", "*.csv")))
    files = [f for f in pats if "breakeven_1029" not in f]
    trades = []
    headers = defaultdict(int)
    for f in files:
        chain_dir = os.path.basename(os.path.dirname(f))
        # 目录名统一去掉 "ledgers_1029_" / "ledgers_1028_" / "ledgers_1030_" 前缀
        short = re.sub(r"^ledgers_10\d\d_?", "", chain_dir) or chain_dir
        chain_name = os.path.splitext(os.path.basename(f))[0]
        chain_id = f"{short}/{chain_name}"
        with open(f, newline="", encoding="utf-8-sig") as fh:
            rd = csv.DictReader(fh)
            headers[tuple(rd.fieldnames or ())] += 1
            for r in rd:
                trades.append({
                    "chain": chain_id,
                    "symbol": (r.get("symbol") or "").strip(),
                    "year": (r.get("entry_date") or "")[:4],
                    "adv20": fnum(r.get("adv20_at_entry")),
                    "notional": fnum(r.get("notional_in")),
                    "net_pnl": fnum(r.get("net_pnl")) or 0.0,
                    "cap_days": fnum(r.get("capital_days")) or 0.0,
                    "r_net": fnum(r.get("r_multiple_net")),
                })
    return files, trades, headers


def load_signal_funnels():
    """信号数只存在于 results_*.json 的信号漏斗里。

    ★★ 重要口径说明:信号数是**全池口径**的 —— 没成交的信号在流水里没有
       任何记录(没有 symbol、没有年份),所以**事后无法按池子重切**。
       收窄池子之后真实的信号数只能靠重跑回测拿到。本轮不重跑回测,
       所以报告里信号数一律标注「全池口径,不可按池子重切」。
    """
    rows = {}

    def walk(o):
        if isinstance(o, dict):
            if "信号漏斗" in o and "笔数" in o:
                nm = str(o.get("报表名") or o.get("链名"))
                f = o["信号漏斗"] or {}
                sig = (f.get("逐关") or [{}])[-1].get("累计")
                rows[nm] = {"笔数": o.get("笔数"), "信号数": sig}
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for f in glob.glob(os.path.join(ROOT, "engine", "results_*.json")):
        try:
            with open(f, encoding="utf-8") as fh:
                walk(json.load(fh))
        except Exception:
            continue
    return rows


# ---------------------------------------------------------------- 二 · 指标
def metrics(rows):
    n = len(rows)
    if n == 0:
        return {"笔数": 0, "每笔净R均值": None, "名义加权总收益率": None,
                "占用资金年化收益率": None, "胜率": None, "净盈亏": 0.0}
    pnl = sum(r["net_pnl"] for r in rows)
    notional = sum(r["notional"] or 0.0 for r in rows)
    capd = sum(r["cap_days"] for r in rows)
    rs = [r["r_net"] for r in rows if r["r_net"] is not None]
    wins = sum(1 for r in rows if r["net_pnl"] > 0)
    return {
        "笔数": n,
        "每笔净R均值": (sum(rs) / len(rs)) if rs else None,
        "名义加权总收益率": (pnl / notional) if notional > 0 else None,
        "占用资金年化收益率": (pnl / (capd / TRADING_DAYS_PER_YEAR)) if capd > 0 else None,
        "胜率": wins / n,
        "净盈亏": pnl,
    }


def fmt(v, spec="{:.4f}"):
    return spec.format(v) if v is not None else "na"


# ---------------------------------------------------------------- 三 · 主流程
def main():
    print("=" * 74)
    print("★ 池子口径戳")
    print(PS.stamp_text(prefix="   "))
    print("=" * 74)

    # ---- 核对 1:流水
    files, trades, headers = load_ledgers()
    ok = True
    print(f"[核对] 流水文件 {len(files)} 个(已知 {KNOWN_FILES}) "
          f"{'✓' if len(files) == KNOWN_FILES else '✗'}")
    print(f"[核对] 成交笔数 {len(trades):,} 笔(已知 {KNOWN_TRADES:,}) "
          f"{'✓' if len(trades) == KNOWN_TRADES else '✗'}")
    all_pat = glob.glob(os.path.join(ROOT, "**", "*ledger*", "*.csv"), recursive=True)
    print(f"[核对] 一把捞 `*ledger*` 会得 {len(all_pat)} 个文件(已知 237,"
          f"多出的 54 个是 breakeven_1029 副本)—— 已显式排除")
    print("[核对] 表头写法 " + str(len(headers)) + " 种(按列集合):"
          + "; ".join(f"{c}个文件/{len(h)}列" for h, c in headers.items()))
    # ★ BOM 要在**字节层**查:用 utf-8-sig 打开的话 BOM 已经被吃掉了,
    #   在 fieldnames 里永远查不到 —— 这本身就是「两种写法只认一种」的变体。
    bom = 0
    for f in files:
        with open(f, "rb") as fb:
            if fb.read(3) == b"\xef\xbb\xbf":
                bom += 1
    print(f"[核对] 带 BOM 的文件 {bom} 个(已知 3)"
          f"{' ✓' if bom == 3 else ' ✗'} —— 全部用 utf-8-sig 打开,已吸收")
    if bom != 3:
        ok = False
    if len(files) != KNOWN_FILES or len(trades) != KNOWN_TRADES:
        print("★ 和已知数不一致,停。")
        return 1

    chains = sorted({t["chain"] for t in trades})
    print(f"[核对] 策略链 {len(chains)} 条(已知 {KNOWN_CHAINS}) "
          f"{'✓' if len(chains) == KNOWN_CHAINS else '✗'}")
    if len(chains) != KNOWN_CHAINS:
        ok = False

    # ---- 核对 2:池子
    idx = PS.PoolIndex()
    print(f"[核对] 池子 {idx.rows:,} 行(已知 {PS.POOL_KNOWN_ROWS:,}) "
          f"{'✓' if idx.rows == PS.POOL_KNOWN_ROWS else '✗'}")
    print(f"[核对] rank 带 vs tier 列 不一致 {len(idx.tier_mismatch)} 行 "
          f"{'✓ 两列恒等,筛 rank 和筛 tier 等价' if not idx.tier_mismatch else '✗'}")
    if idx.rows != PS.POOL_KNOWN_ROWS or idx.tier_mismatch:
        print("★ 池子和已知数不一致,停。")
        return 1

    # ---- 核对 3:信号数(纪律 3)
    funnels = load_signal_funnels()
    sig_tot = sum(v["信号数"] or 0 for v in funnels.values())
    fill_tot = sum(v["笔数"] or 0 for v in funnels.values())
    print(f"[核对·纪律3] 有信号数的链 {len(funnels)} 条(已知 {KNOWN_FUNNEL_CHAINS})"
          f" {'✓' if len(funnels) == KNOWN_FUNNEL_CHAINS else '✗'};"
          f"合格进场信号 {sig_tot:,}(已知 {KNOWN_SIGNALS:,})"
          f" {'✓' if sig_tot == KNOWN_SIGNALS else '✗'} → 成交 {fill_tot:,} 笔"
          f"(已知 {KNOWN_FUNNEL_TRADES:,})"
          f" {'✓' if fill_tot == KNOWN_FUNNEL_TRADES else '✗'},"
          f"成交率 {fill_tot/sig_tot:.1%}")
    print("   ★★ 信号数是**全池口径**:没成交的信号在流水里没有 symbol/年份,"
          "事后无法按池子重切 → 收窄后的真实信号数要重跑回测才有。")
    if (len(funnels) != KNOWN_FUNNEL_CHAINS or sig_tot != KNOWN_SIGNALS
            or fill_tot != KNOWN_FUNNEL_TRADES):
        ok = False
    if not ok:
        print("★ 有核对项不一致,停。")
        return 1

    # ---- 把每笔映射到池子排名
    how = defaultdict(int)
    for t in trades:
        rk, tier, src = idx.resolve(t["symbol"], t["year"])
        t["rank"], t["tier"], t["src"] = rk, tier, src
        how[src] += 1
    unmapped = how["当年不在池"] + how["代码歧义"]
    print(f"[核对] 排名映射:" + ", ".join(f"{k}={v:,}" for k, v in sorted(how.items()))
          + f" —— 未映射 {unmapped:,} 笔 ({unmapped/len(trades):.2%})")
    print("   ★ 未映射的按「不在口径内」处理(保守)。第 5 节有敏感度:"
          "把它们全算进大+中,结论是否翻转。")

    by_tier = defaultdict(int)
    for t in trades:
        by_tier[t["tier"] or "未映射"] += 1
    print("[分布] 成交笔数按池子分档:",
          {k: f"{v:,}({v/len(trades):.1%})" for k, v in sorted(by_tier.items())})

    # ---- 三个口径的全库对比
    scope_sets = {}
    for s in ("full", "large_mid", "large"):
        scope_sets[s] = [t for t in trades if PS.in_scope(t["rank"], s)]
    # full 口径下「未映射」的笔要不要算?full = 全池,未映射的本来就不在池里,
    # 所以 full 也按 in_scope 判(未映射 rank=None → False)。
    # ★ 另单独给一个「全库 146,991 笔」作为上一轮报告的基线,便于对数。
    base_lib = metrics(trades)
    print(f"\n[基线·上一轮口径] 全库 {base_lib['笔数']:,} 笔(含未映射),"
          f"每笔净R {base_lib['每笔净R均值']:.4f},胜率 {base_lib['胜率']:.2%},"
          f"占用资金年化 {base_lib['占用资金年化收益率']:.4%}")

    scope_metrics = {}
    print("\n===== 表一:三个口径的全库对比 =====")
    print(f"{'口径':>10} {'笔数':>9} {'占全库':>7} {'每笔净R':>9} {'胜率':>7} "
          f"{'名义加权总收益':>12} {'占用资金年化':>11} {'净盈亏($)':>14}")
    for s in ("full", "large_mid", "large"):
        m = metrics(scope_sets[s])
        scope_metrics[s] = m
        print(f"{s:>10} {m['笔数']:9,d} {m['笔数']/len(trades):6.1%} "
              f"{fmt(m['每笔净R均值'], '{:9.4f}')} "
              f"{fmt(m['胜率'], '{:6.2%}')} "
              f"{fmt(m['名义加权总收益率'], '{:11.4%}')} "
              f"{fmt(m['占用资金年化收益率'], '{:10.4%}')} "
              f"{m['净盈亏']:14,.0f}")

    # 小盘被排除了多少(口径戳要求)
    small = [t for t in trades if t["tier"] == "小"]
    small_rows = sum(1 for rk in idx.rank.values() if rk > 2000)
    excl = {
        "小盘_池子行数": small_rows,
        "小盘_池子行数占比": small_rows / idx.rows,
        "小盘_只数年次": small_rows,
        "小盘_成交笔数": len(small),
        "小盘_成交笔数占比": len(small) / len(trades),
        "小盘_净盈亏": metrics(small)["净盈亏"],
        "小盘_净盈亏占全库比例": (metrics(small)["净盈亏"] / base_lib["净盈亏"]
                                   if base_lib["净盈亏"] else None),
        "未映射_笔数": unmapped,
        "未映射_笔数占比": unmapped / len(trades),
        "★一行都没删": "pool_FULL_ALL.csv 74,268 行原样保留,只读",
    }
    print(f"\n[排除量] 小盘:池子 {small_rows:,} 只×年"
          f"({small_rows/idx.rows:.1%});成交 {len(small):,} 笔"
          f"({len(small)/len(trades):.2%});净盈亏 {excl['小盘_净盈亏']:,.0f} "
          f"= 全库的 {excl['小盘_净盈亏占全库比例']:.1%}")
    print(f"[排除量] 另有未映射 {unmapped:,} 笔({unmapped/len(trades):.2%})"
          f"也被排除在大+中之外")

    # ---- ★★★ 必答题:收窄之后还需要流动性门槛吗
    print("\n===== 表二:★★★ 大+中池上,流动性门槛还挡得掉多少 =====")
    gate = {}
    for s in ("full", "large_mid", "large"):
        rows = scope_sets[s]
        base = metrics(rows)
        gate[s] = {"基线": base, "按门槛": {}}
        for thr in THR_GRID:
            keep = [t for t in rows if t["adv20"] is not None and t["adv20"] >= thr]
            blk = [t for t in rows
                   if not (t["adv20"] is not None and t["adv20"] >= thr)]
            mk, mb = metrics(keep), metrics(blk)
            gate[s]["按门槛"][str(thr)] = {
                "门槛_日均成交额美元": thr,
                "等价X(计划仓位10万)": thr / ENGINE_POS_DOLLARS,
                "挡掉笔数": len(blk),
                "挡掉比例": len(blk) / base["笔数"] if base["笔数"] else None,
                "剩余笔数": mk["笔数"],
                "剩余_每笔净R": mk["每笔净R均值"],
                "剩余_胜率": mk["胜率"],
                "剩余_占用资金年化": mk["占用资金年化收益率"],
                "挡掉部分占本口径净盈亏比例": (mb["净盈亏"] / base["净盈亏"]
                                               if base["净盈亏"] else None),
            }
    print(f"{'门槛($/日)':>13} {'=X':>6} | " + " | ".join(
        f"{s}:挡掉% / 剩余每笔R / 挡掉占盈亏%" for s in ("full", "large_mid", "large")))
    for thr in THR_GRID:
        cells = []
        for s in ("full", "large_mid", "large"):
            g = gate[s]["按门槛"][str(thr)]
            cells.append(f"{g['挡掉比例']*100:6.2f}% / {fmt(g['剩余_每笔净R'],'{:8.4f}')} "
                         f"/ {fmt(g['挡掉部分占本口径净盈亏比例'],'{:7.1%}')}")
        print(f"{thr:13,.0f} {thr/ENGINE_POS_DOLLARS:6.1f} | " + " | ".join(cells))

    # ---- 按链
    chain_rows = defaultdict(list)
    for t in trades:
        chain_rows[t["chain"]].append(t)

    # 链名 -> 信号数(归一化匹配)。★ 归一化 key 不唯一(同名链在多个流水目录里),
    #   所以一个 key 对上几条流水链就标出来,不许悄悄挂给其中一条。
    fn_norm = {_norm(k): v for k, v in funnels.items()}
    key_chains = defaultdict(list)
    for c in chain_rows:
        key_chains[_norm(c.split("/", 1)[1])].append(c)

    sig_matched = sig_unique = 0
    per_chain = {}
    for c, rows in chain_rows.items():
        base = metrics(rows)
        lm = metrics([t for t in rows if PS.in_scope(t["rank"], "large_mid")])
        lg = metrics([t for t in rows if PS.in_scope(t["rank"], "large")])
        k = _norm(c.split("/", 1)[1])
        sig = fn_norm.get(k)
        n_same = len(key_chains[k])
        if sig:
            sig_matched += 1
            if n_same == 1:
                sig_unique += 1
        per_chain[c] = {
            "全池": base, "大中": lm, "只大": lg,
            "信号数_全池口径": (sig or {}).get("信号数"),
            "信号数_归属": ("唯一" if sig and n_same == 1
                            else (f"同名流水 {n_same} 条,不可唯一归属" if sig
                                  else "results JSON 里没有这条的漏斗")),
            "样本够_全池": base["笔数"] >= MIN_TRADES,
            "样本够_大中": lm["笔数"] >= MIN_TRADES,
            # ★★ 「这条链还能不能用」的判据:大+中池上 ≥30 笔 且 每笔净 R > 0
            "大中可用": (lm["笔数"] >= MIN_TRADES
                         and (lm["每笔净R均值"] or 0) > 0),
        }
    unmatched_fn = [n for n in funnels if _norm(n) not in key_chains]
    print(f"\n[核对·纪律3] 信号漏斗 {len(funnels)} 条链;归一化后 "
          f"{len(funnels)-len(unmatched_fn)} 条能对上流水,其中 {sig_unique} 条"
          f"能**唯一**归属到一条流水链(其余是同一策略在多个批次各跑过一遍,"
          f"同名)。对不上的 {len(unmatched_fn)} 条是 results JSON 里的报表名"
          f"在流水目录里换了叫法(如「技-1 · ★原著离场 · System 2」)。")
    print(f"   ★ 全库 {len(trades):,} 笔中,有信号数覆盖的只有 {fill_tot:,} 笔"
          f"({fill_tot/len(trades):.0%});信号数一律是**全池口径**。")

    # ---- ★ 那 16 条
    print("\n===== 表三:★★★ 上一轮 16 条「由赚转亏」的链,在大+中池上 =====")
    print(f"{'全池笔数':>8} {'大中笔数':>8} {'收窄掉%':>7} "
          f"{'全池每笔R':>10} {'大中每笔R':>10} {'上轮加门槛后R':>12} {'判定':>12}  链")
    # ★ 报告里的链名和流水文件名写法不同(漏了 "Test"、少了空格)→ 用归一化 key 对
    loose = {_norm(c): c for c in per_chain}
    flipped = {}
    for c0 in FLIPPED_16:
        old_r, old_gate_r = FLIPPED_16_OLD.get(c0, (None, None))
        real = loose.get(_norm(c0))
        e = per_chain.get(real) if real else None
        c = real or c0
        if e is None:
            print(f"{'?':>8} —— 流水里找不到这条链:{c0}")
            flipped[c0] = {"状态": "流水里找不到"}
            continue
        b, lm = e["全池"], e["大中"]
        shrink = 1 - lm["笔数"] / b["笔数"] if b["笔数"] else None
        if lm["笔数"] < MIN_TRADES:
            verdict = "样本不足"
        elif lm["每笔净R均值"] is not None and lm["每笔净R均值"] > 0:
            verdict = "★ 活了"
        else:
            verdict = "仍为负"
        flipped[c] = {
            "全池笔数": b["笔数"], "大中笔数": lm["笔数"], "收窄掉比例": shrink,
            "全池每笔R": b["每笔净R均值"], "大中每笔R": lm["每笔净R均值"],
            "大中胜率": lm["胜率"],
            "上轮_全池加门槛后每笔R(X=10)": old_gate_r,
            "判定": verdict,
        }
        print(f"{b['笔数']:8,d} {lm['笔数']:8,d} "
              f"{fmt(shrink, '{:6.1%}')} "
              f"{fmt(b['每笔净R均值'], '{:10.4f}')} "
              f"{fmt(lm['每笔净R均值'], '{:10.4f}')} "
              f"{fmt(old_gate_r, '{:12.4f}')} {verdict:>12}  {c}")

    # ---- ★ 样本门槛 30 笔:点名
    print("\n===== 表四:★★ 大+中池上跌破 30 笔的链(点名 + 分因) =====")
    below = []
    for c, e in sorted(per_chain.items()):
        if e["大中"]["笔数"] < MIN_TRADES:
            cause = ("本来就不足" if e["全池"]["笔数"] < MIN_TRADES
                     else "★ 被收窄池子打没的")
            below.append({"链": c, "全池笔数": e["全池"]["笔数"],
                          "大中笔数": e["大中"]["笔数"], "原因": cause})
    n_orig = sum(1 for x in below if x["原因"] == "本来就不足")
    print(f"共 {len(below)} 条跌破 30 笔:本来就不足 {n_orig} 条,"
          f"被收窄打没 {len(below)-n_orig} 条")
    for x in below:
        print(f"   {x['全池笔数']:6,d} → {x['大中笔数']:5,d}  {x['原因']:<14} {x['链']}")

    # ---- ★★★ 优先级最高的一问:还剩哪些链是可用的
    print("\n===== 表六:★★★ 大+中池上「还能用」的链(≥30 笔 且 每笔净R>0) =====")
    usable = sorted(
        [(c, e) for c, e in per_chain.items() if e["大中可用"]],
        key=lambda x: -(x[1]["大中"]["每笔净R均值"] or 0))
    died = sorted(
        [(c, e) for c, e in per_chain.items()
         if not e["大中可用"] and e["样本够_大中"]],
        key=lambda x: (x[1]["大中"]["每笔净R均值"] or 0))
    print(f"   可用 {len(usable)} 条 / 样本够但为负 {len(died)} 条 / "
          f"样本不足 {len(below)} 条 —— 合计 {len(per_chain)} 条")
    print(f"   {'大中笔数':>8} {'大中每笔R':>10} {'大中胜率':>8} {'全池每笔R':>10}  链")
    for c, e in usable[:25]:
        print(f"   {e['大中']['笔数']:8,d} {e['大中']['每笔净R均值']:10.4f} "
              f"{fmt(e['大中']['胜率'],'{:8.2%}')} "
              f"{fmt(e['全池']['每笔净R均值'],'{:10.4f}')}  {c}")
    print(f"   …(前 25 条;完整名单见 按链-大中池-1030.csv)")
    print(f"\n   ★ 由正转负(全池为正、大+中为负、样本够)的链:")
    turned = [(c, e) for c, e in died if (e["全池"]["每笔净R均值"] or 0) > 0]
    print(f"     共 {len(turned)} 条")
    for c, e in turned[:25]:
        print(f"     {e['全池']['每笔净R均值']:+8.4f} → "
              f"{e['大中']['每笔净R均值']:+8.4f}  "
              f"({e['全池']['笔数']:,}→{e['大中']['笔数']:,} 笔)  {c}")
    rescued = [(c, e) for c, e in usable
               if (e["全池"]["每笔净R均值"] or 0) <= 0]
    print(f"\n   ★ 反过来:全池为负、收窄后转正的链 {len(rescued)} 条")
    for c, e in rescued[:15]:
        print(f"     {e['全池']['每笔净R均值']:+8.4f} → "
              f"{e['大中']['每笔净R均值']:+8.4f}  "
              f"({e['全池']['笔数']:,}→{e['大中']['笔数']:,} 笔)  {c}")

    # ---- 敏感度:未映射的笔全算进大+中
    print("\n===== 表五:敏感度 —— 把未映射的笔全算进大+中(上界) =====")
    lm_plus = [t for t in trades
               if PS.in_scope(t["rank"], "large_mid") or t["rank"] is None]
    m_plus = metrics(lm_plus)
    m_lm = scope_metrics["large_mid"]
    print(f"   保守(未映射算排除):{m_lm['笔数']:,} 笔,每笔净R "
          f"{fmt(m_lm['每笔净R均值'])},胜率 {fmt(m_lm['胜率'],'{:.2%}')}")
    print(f"   上界(未映射算纳入):{m_plus['笔数']:,} 笔,每笔净R "
          f"{fmt(m_plus['每笔净R均值'])},胜率 {fmt(m_plus['胜率'],'{:.2%}')}")
    gate_plus = {}
    for thr in THR_GRID:
        blk = [t for t in lm_plus
               if not (t["adv20"] is not None and t["adv20"] >= thr)]
        gate_plus[str(thr)] = len(blk) / len(lm_plus)
    print("   上界口径下门槛挡掉比例:"
          + ", ".join(f"${int(k):,}:{v:.2%}" for k, v in gate_plus.items()))

    # ---- 写出
    results = {
        "口径戳": PS.stamp(extra={
            "小盘被排除了多少": excl,
            "核对": {"流水文件数": len(files), "成交笔数": len(trades),
                     "链数": len(chains), "池子行数": idx.rows,
                     "信号数_全池口径": sig_tot,
                     "有信号数的链数": len(funnels),
                     "这些链的成交笔数": fill_tot,
                     "成交率": fill_tot / sig_tot,
                     "排名映射方式": dict(how)},
        }),
        "三口径对比": scope_metrics,
        "上一轮基线_全库含未映射": base_lib,
        "笔数按分档": dict(by_tier),
        "流动性门槛_按口径": gate,
        "十六条由赚转亏的链_在大中池上": flipped,
        "跌破30笔_点名": below,
        "敏感度_未映射算纳入": {"指标": m_plus, "门槛挡掉比例": gate_plus},
        "可用性汇总": {
            "大中可用(≥30笔且每笔R>0)": len(usable),
            "样本够但为负": len(died),
            "样本不足30笔": len(below),
            "合计链数": len(per_chain),
            "由正转负": [c for c, _ in turned],
            "由负转正": [c for c, _ in rescued],
            "可用名单": [c for c, _ in usable],
        },
        "按链": per_chain,
    }
    jp = os.path.join(OUT, "pool_scope_results_1030.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n[写出] {jp}")

    # 按链 csv(口径戳写在前几行注释里)
    cp = os.path.join(OUT, "按链-大中池-1030.csv")
    with open(cp, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        for k, v in PS.stamp().items():
            w.writerow([f"# {k}", v])
        w.writerow(["# 小盘被排除",
                    f"池子 {small_rows:,} 只×年 / 成交 {len(small):,} 笔"
                    f"({len(small)/len(trades):.2%});另有未映射 {unmapped:,} 笔"])
        w.writerow(["# 信号数口径", "全池口径,事后不可按池子重切"])
        w.writerow([])
        w.writerow(["链", "信号数(全池口径)", "信号数归属", "全池笔数",
                    "全池每笔净R", "全池胜率",
                    "大中笔数", "大中每笔净R", "大中胜率", "大中占用资金年化",
                    "只大笔数", "只大每笔净R", "大中样本够30笔", "大中可用"])
        for c, e in sorted(per_chain.items()):
            w.writerow([c, e["信号数_全池口径"], e["信号数_归属"],
                        e["全池"]["笔数"], e["全池"]["每笔净R均值"], e["全池"]["胜率"],
                        e["大中"]["笔数"], e["大中"]["每笔净R均值"], e["大中"]["胜率"],
                        e["大中"]["占用资金年化收益率"],
                        e["只大"]["笔数"], e["只大"]["每笔净R均值"],
                        e["样本够_大中"], e["大中可用"]])
    print(f"[写出] {cp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
