#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
下单流动性门槛 X 的后果测量(只读;不改 engine/,不改 survivorship_1029/)

大白话:现在的回测里,有些票一天总共才成交几十万美元,我们却「买进」了
十万美元。那种成交在现实里做不到。这个脚本不去定门槛,只回答一句话:
「门槛定在某个数,会挡掉多少笔、挡掉的那些笔原来赚了多少。」

★ 纪律 4(一样东西两种写法)本脚本显式处理的:
  1. 流水表头有 3 种:带 BOM 的 `﻿symbol` / 缺 `size_mult` / 全列。
     → 统一用 encoding='utf-8-sig' 打开,并按列名存在性取值。
  2. 流水目录有两处:engine/ledgers_* 是正本(183 文件);
     probe/breakeven_1029/ledgers/* 是其中 54 个的副本 → 必须排除,否则重复计数。
  3. `adv20_at_entry` 有 8 笔是空/非有限值 → 单独计数,按「挡掉」处理(保守)。
  4. 池子 tier 用中文「大/中/小」,流水里的 `liquidity_tier` 是中文「高/中/低流动性」
     且口径不同(池子按年度成交额排名,流水按当日横截面三分位)→ 两者不可混用。
"""
from __future__ import annotations

import csv
import glob
import json
import math
import os
import sys
from collections import defaultdict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
OUT = os.path.dirname(os.path.abspath(__file__))

# 已知真实数(纪律 4:读到的数必须和已知数核对)
KNOWN_FILES = 183
KNOWN_TRADES = 146_991

TRADING_DAYS_PER_YEAR = 252   # ★ 「天」一律交易日;本脚本中 60d/20d/252 全是交易日

# 引擎自身的仓位口径(engine/chain.py: initial_equity=1_000_000,
# engine/configs/*.yaml: risk_per_trade=1%, max_weight=10%, max_positions=10)
ENGINE_EQUITY = 1_000_000.0
ENGINE_POS_PCT = 0.10
ENGINE_POS_DOLLARS = ENGINE_EQUITY * ENGINE_POS_PCT   # = 100,000

X_GRID = [10, 20, 50, 100, 200, 500, 1000]
ACCOUNTS = [100_000.0, 1_000_000.0, 10_000_000.0]
POS_PCTS = [0.05, 0.10]
MIN_TRADES = 30        # 样本门槛:每条链至少 30 笔


def fnum(s):
    try:
        v = float(s)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- 一 · 读流水
def load_ledgers():
    """正本 = engine/ledgers_*/*.csv。显式排除 probe/breakeven_1029 的副本。"""
    pats = sorted(glob.glob(os.path.join(ROOT, "engine", "ledgers_*", "*.csv")))
    files = [f for f in pats if "breakeven_1029" not in f]
    trades = []
    headers = defaultdict(int)
    for f in files:
        chain_dir = os.path.basename(os.path.dirname(f))
        chain_name = os.path.splitext(os.path.basename(f))[0]
        chain_id = f"{chain_dir}/{chain_name}"
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


# ---------------------------------------------------------------- 二 · 池子分档
def load_pool_tiers():
    """(symbol, year) -> 大/中/小;另外带回全池 ADV 分布,用于「前瞻」一节。

    ★ 纪律 4 第 5 处(本轮新发现的「一样东西两种写法」):
      池子里的代码是**当年年初那一刻的代码**(2018 年的安泰保险写 ANTM),
      流水里的代码是**最后那个代码**(写 ELV)。直接按代码对,8,554 笔(5.8%)
      对不上,而且对不上的几乎全是小票 —— 如果当成「没有」丢掉,小盘档的
      挡掉比例会被系统性低估。
      → 先按 (代码, 年) 对;对不上再按 company_id 对(代码别名从池子的
        symbol 列 + renamed_to 列两边一起收)。456 个代码被不同公司重复用过,
        所以必须再加「那一年确实有这家公司」这个条件,才不会张冠李戴。
    """
    p = os.path.join(ROOT, "probe", "survivorship_1029", "pool_FULL_ALL.csv")
    tier = {}
    by_company = {}
    alias = defaultdict(set)
    adv_by_tier = defaultdict(list)
    n = 0
    with open(p, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            n += 1
            sym, yr, t = r["symbol"].strip(), r["year"].strip(), r["tier"].strip()
            cid = r["company_id"]
            tier[(sym, yr)] = t
            by_company[(cid, yr)] = t
            alias[sym].add(cid)
            rt = (r.get("renamed_to") or "").strip().strip('"')
            if rt:
                alias[rt].add(cid)
            v = fnum(r.get("avg_dollar_volume_60d"))
            if v is not None:
                adv_by_tier[t].append(v)
    return tier, by_company, alias, adv_by_tier, n


def resolve_tier(sym, yr, tier, by_company, alias):
    t = tier.get((sym, yr))
    if t is not None:
        return t, "直接"
    cands = [c for c in alias.get(sym, ()) if (c, yr) in by_company]
    if len(cands) == 1:
        return by_company[(cands[0], yr)], "改名对上"
    return None, ("代码歧义" if len(cands) > 1 else "当年不在池")


# ------------------------------------------------- 二·五 · 信号数(纪律 5)
def load_signal_funnels():
    """从 engine/results_*.json 捞每条链的「合格进场信号数」和笔数。

    大白话:流水里只有「成交了的」。要知道「本来有多少次想买」,得看
    results JSON 里的信号漏斗。两个数差很远:信号 37.9 万,成交 6.2 万 ——
    八成多的信号早就被槽位挡掉了,跟流动性无关。
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


# ---------------------------------------------------------------- 三 · 指标
def metrics(rows):
    """只用「对子集有定义」的指标。路径相关的净值曲线不能从子集重建 → 不报。"""
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


def quantiles(vals, qs=(0.1, 0.25, 0.5, 0.75, 0.9)):
    if not vals:
        return {}
    v = sorted(vals)
    out = {}
    for q in qs:
        i = min(len(v) - 1, max(0, int(round(q * (len(v) - 1)))))
        out[f"p{int(q*100)}"] = v[i]
    return out


# ---------------------------------------------------------------- 四 · 主流程
def main():
    files, trades, headers = load_ledgers()
    print(f"[核对] 流水文件 {len(files)} 个(已知 {KNOWN_FILES})  "
          f"{'✓' if len(files) == KNOWN_FILES else '✗ 不一致!'}")
    print(f"[核对] 成交笔数 {len(trades)} 笔(已知 {KNOWN_TRADES})  "
          f"{'✓' if len(trades) == KNOWN_TRADES else '✗ 不一致!'}")
    print(f"[核对] 表头写法 {len(headers)} 种:"
          + "; ".join(f"{c}个文件/{len(h)}列" for h, c in headers.items()))
    if len(files) != KNOWN_FILES or len(trades) != KNOWN_TRADES:
        print("★ 和已知数不一致,停。")
        return 1

    tier_map, by_company, alias, pool_adv, pool_n = load_pool_tiers()
    print(f"[核对] 全量池 {pool_n} 行(已知 74268)  "
          f"{'✓' if pool_n == 74268 else '✗'}")

    # --- 把每笔映射到池子分档(两种代码写法都要认,见 load_pool_tiers 注释)
    how = defaultdict(int)
    miss = 0
    for t in trades:
        tt, src = resolve_tier(t["symbol"], t["year"], tier_map, by_company, alias)
        how[src] += 1
        if tt is None:
            miss += 1
            tt = "未映射"
        t["tier"] = tt
    print(f"[核对] 分档映射:" + ", ".join(f"{k}={v}" for k, v in sorted(how.items()))
          + f" —— 仍未映射 {miss} 笔 ({miss/len(trades):.2%})")

    no_adv = sum(1 for t in trades if t["adv20"] is None)
    no_not = sum(1 for t in trades if not t["notional"])
    print(f"[核对] adv20 缺失/非有限 {no_adv} 笔;notional_in 缺失或 0 {no_not} 笔"
          f" —— 两类都按『挡掉』处理(保守)")

    chains = sorted({t["chain"] for t in trades})
    print(f"[核对] 策略链 {len(chains)} 条(文件 {len(files)} 个;差 "
          f"{len(files)-len(chains)} 个是空流水 —— "
          f"engine/ledgers_1028/流派二_VCP_紧端(原著另一端).csv 0 笔)")

    funnels = load_signal_funnels()
    sig_tot = sum(v["信号数"] or 0 for v in funnels.values())
    fill_tot = sum(v["笔数"] or 0 for v in funnels.values())
    print(f"[核对·纪律5] 能找到信号数的链 {len(funnels)} 条:合格进场信号 "
          f"{sig_tot:,} 个 → 成交 {fill_tot:,} 笔(成交率 {fill_tot/sig_tot:.1%})"
          f" —— 全库成交 {len(trades):,} 笔,信号数只覆盖其中 {fill_tot/len(trades):.0%}")
    results_signals = {"有信号数的链数": len(funnels), "信号数合计": sig_tot,
                       "这些链的成交笔数": fill_tot,
                       "成交率": fill_tot / sig_tot if sig_tot else None,
                       "全库成交笔数": len(trades), "每链": funnels}

    by_tier = defaultdict(int)
    for t in trades:
        by_tier[t["tier"]] += 1
    print("[分布] 成交笔数按池子分档:",
          {k: f"{v}({v/len(trades):.1%})" for k, v in sorted(by_tier.items())})

    base_all = metrics(trades)
    print(f"[基线] 全库 {base_all['笔数']} 笔,每笔净R均值 "
          f"{base_all['每笔净R均值']:.4f},名义加权总收益率 "
          f"{base_all['名义加权总收益率']:.4%},占用资金年化 "
          f"{base_all['占用资金年化收益率']:.4%},胜率 {base_all['胜率']:.2%}")

    # ---- 每笔「实际达到的 ADV 倍数」k = adv20 / 计划仓位
    #      定义 B 用它:门槛 X 作用在引擎自己的计划仓位上,再按账户规模缩放。
    for t in trades:
        if t["adv20"] is None or not t["notional"]:
            t["k_engine"] = None      # 判为挡掉
        else:
            t["k_engine"] = t["adv20"] / t["notional"]
    ks = [t["k_engine"] for t in trades if t["k_engine"] is not None]
    print("[分布] k = ADV20 / 引擎计划仓位 的分位:",
          {k: f"{v:,.0f}x" for k, v in quantiles(ks).items()})

    advs = [t["adv20"] for t in trades if t["adv20"] is not None]
    print("[分布] 成交笔的 ADV20(美元)分位:",
          {k: f"{v:,.0f}" for k, v in quantiles(advs).items()})

    results = {
        "核对": {"文件数": len(files), "笔数": len(trades), "链数": len(chains),
                 "池子行数": pool_n, "分档未映射笔数": miss,
                 "adv20缺失笔数": no_adv, "notional缺失笔数": no_not},
        "基线_全库": base_all,
        "引擎仓位口径": {"initial_equity": ENGINE_EQUITY,
                         "单笔仓位上限比例": ENGINE_POS_PCT,
                         "单笔计划仓位美元": ENGINE_POS_DOLLARS},
        "k分位": quantiles(ks),
        "adv20分位": quantiles(advs),
        "笔数按分档": dict(by_tier),
        "分档映射方式": dict(how),
        "信号数": results_signals,
        "空流水文件": "engine/ledgers_1028/流派二_VCP_紧端(原著另一端).csv",
        "网格": [],
        "按链": {},
        "全池前瞻": {},
    }

    # ---------------- 网格:账户规模 × 单笔比例 × X
    for A in ACCOUNTS:
        for p in POS_PCTS:
            plan = A * p                     # 定义 A 的「计划仓位」
            scale = plan / ENGINE_POS_DOLLARS  # 定义 B 的缩放系数
            for X in X_GRID:
                thr_flat = X * plan          # 定义 A:一个固定的美元门槛

                # 定义 A:固定仓位口径
                keepA = [t for t in trades
                         if t["adv20"] is not None and t["adv20"] >= thr_flat]
                blkA = [t for t in trades
                        if not (t["adv20"] is not None and t["adv20"] >= thr_flat)]
                # 定义 B:引擎自己的计划仓位,按账户缩放
                keepB = [t for t in trades
                         if t["k_engine"] is not None and t["k_engine"] >= X * scale]
                blkB = [t for t in trades
                        if not (t["k_engine"] is not None and t["k_engine"] >= X * scale)]

                mA, mB = metrics(keepA), metrics(keepB)
                bA = metrics(blkA)
                tier_blk = {}
                for tname in ("大", "中", "小", "未映射"):
                    tot = by_tier.get(tname, 0)
                    if tot:
                        b = sum(1 for t in blkA if t["tier"] == tname)
                        tier_blk[tname] = {"总笔数": tot, "挡掉": b, "挡掉比例": b / tot}

                row = {
                    "账户规模": A, "单笔仓位比例": p, "计划仓位美元": plan, "X": X,
                    "门槛_日均成交额美元": thr_flat,
                    "定义A_挡掉笔数": len(blkA),
                    "定义A_挡掉比例": len(blkA) / len(trades),
                    "定义A_剩余笔数": len(keepA),
                    "定义A_剩余_每笔净R": mA["每笔净R均值"],
                    "定义A_剩余_名义加权总收益率": mA["名义加权总收益率"],
                    "定义A_剩余_占用资金年化": mA["占用资金年化收益率"],
                    "定义A_剩余_胜率": mA["胜率"],
                    "定义A_挡掉部分_每笔净R": bA["每笔净R均值"],
                    "定义A_挡掉部分占总净盈亏比例": (
                        bA["净盈亏"] / base_all["净盈亏"]
                        if base_all["净盈亏"] else None),
                    "定义A_按分档挡掉": tier_blk,
                    "定义B_挡掉比例": len(blkB) / len(trades),
                    "定义B_剩余笔数": len(keepB),
                    "定义B_剩余_每笔净R": mB["每笔净R均值"],
                    "定义B_剩余_占用资金年化": mB["占用资金年化收益率"],
                }
                results["网格"].append(row)

    # ---------------- 打印主网格
    print("\n===== 主表:账户规模 × 单笔比例 × X(定义A:计划仓位=账户×比例)=====")
    print(f"{'账户':>9} {'比例':>5} {'X':>5} {'门槛ADV($)':>14} {'挡掉%':>7} "
          f"{'剩余笔数':>8} {'大挡%':>6} {'中挡%':>6} {'小挡%':>6} "
          f"{'剩余每笔R':>9} {'剩余年化%':>9} {'挡掉占总盈亏%':>12}")
    for r in results["网格"]:
        tb = r["定义A_按分档挡掉"]
        g = lambda k: f"{tb[k]['挡掉比例']*100:5.1f}" if k in tb else "   na"
        rr = r["定义A_剩余_每笔净R"]
        an = r["定义A_剩余_占用资金年化"]
        cp = r["定义A_挡掉部分占总净盈亏比例"]
        print(f"{r['账户规模']/1e6:8.2f}M {r['单笔仓位比例']*100:4.0f}% "
              f"{r['X']:5d} {r['门槛_日均成交额美元']:14,.0f} "
              f"{r['定义A_挡掉比例']*100:6.2f}% {r['定义A_剩余笔数']:8,d} "
              f"{g('大')} {g('中')} {g('小')} "
              f"{(f'{rr:9.4f}' if rr is not None else '       na')} "
              f"{(f'{an*100:8.2f}%' if an is not None else '       na')} "
              f"{(f'{cp*100:11.1f}%' if cp is not None else '         na')}")

    # ---------------- 按链(用引擎自己的口径:A=1M, p=10% → plan=100,000)
    #   这是生成这批流水的那个账户,所以链级结论在这一档最可信。
    per_chain = {}
    chain_rows = defaultdict(list)
    for t in trades:
        chain_rows[t["chain"]].append(t)
    for c, rows in chain_rows.items():
        base = metrics(rows)
        ent = {"基线": base, "按X": {}}
        for X in X_GRID:
            thr = X * ENGINE_POS_DOLLARS
            keep = [t for t in rows
                    if t["adv20"] is not None and t["adv20"] >= thr]
            m = metrics(keep)
            ent["按X"][str(X)] = {
                "剩余笔数": m["笔数"],
                "挡掉比例": 1 - m["笔数"] / base["笔数"],
                "剩余_每笔净R": m["每笔净R均值"],
                "剩余_名义加权总收益率": m["名义加权总收益率"],
                "剩余_占用资金年化": m["占用资金年化收益率"],
                "样本不足": m["笔数"] < MIN_TRADES,
            }
        per_chain[c] = ent
    results["按链"] = per_chain

    # ---------------- 全池前瞻:新池子每档的 ADV 分布 vs 门槛
    for tname, vals in pool_adv.items():
        q = quantiles(vals)
        results["全池前瞻"][tname] = {"只数年次": len(vals), "分位": q}
    print("[前瞻] 全量池 avg_dollar_volume_60d 分位(美元):")
    for tname in ("大", "中", "小"):
        q = results["全池前瞻"].get(tname, {}).get("分位", {})
        print(f"   {tname}: " + ", ".join(f"{k}={v:,.0f}" for k, v in q.items()))

    # 各门槛下,新池子有多少「只×年」买不进去
    pool_block = {}
    for A in ACCOUNTS:
        for p in POS_PCTS:
            for X in X_GRID:
                thr = X * A * p
                d = {}
                for tname in ("大", "中", "小"):
                    vals = pool_adv.get(tname, [])
                    if vals:
                        d[tname] = sum(1 for v in vals if v < thr) / len(vals)
                allv = [v for tn in ("大", "中", "小") for v in pool_adv.get(tn, [])]
                d["全池"] = sum(1 for v in allv if v < thr) / len(allv)
                pool_block[f"A={A:.0f}|p={p}|X={X}"] = d
    results["全池前瞻_不可交易比例"] = pool_block

    with open(os.path.join(OUT, "gate_results_1030.json"), "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n[写出] {os.path.join(OUT, 'gate_results_1030.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
