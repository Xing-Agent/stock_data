#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 从**现有流水**直接量的两组事实 —— 一次回测都不跑(2026-10-30)

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版:两件事都不用改引擎就能量出来。
  ① 「重新进场」**引擎里本来就有**(chain.py 第 ⑤ 步只排除 `j in pos`,
     进场条件重新成立 + 槽位空着 → 就会再进一次)。★ 所以本文件量的是
     **现有流水里重进的那些笔到底是赚还是亏** —— 必答四问的第 4 问。
  ② 组合集中度三个数,全部从流水的 (exit_date, reason, net_pnl) 算。
══════════════════════════════════════════════════════════════════════════

★ 口径(一条都没另发明):
   流水    = engine/ledgers_1030_剔污染/*剔除版.csv(18 条链,最新的剔污染版)
             ★ 显式列目录,**不用 `*ledger*` 一把捞** —— 那样会多出 54 个
               breakeven 副本(今天的已知坑)。
   R       = r_multiple_net(扣摩擦后)。★ 无止损的链(buy_and_hold / 技-2 /
             技-12×2)的 R 退化成收益率,★ 单独标出、**不和有止损的放一列排序**。
   「重进」 = 同一只票在同一条链里**按 entry_date 排序后的第 2 笔及以后**。
             ★ 这是机械定义,不含任何阈值。

★★★ 我自己填的数(一律标「XING 填的」,不许标原著):本文件**零个**。
     全是机械统计,没有一个阈值。
"""
from __future__ import annotations

import glob
import json
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

LEDGER_GLOB = os.path.join(ROOT, "engine", "ledgers_1030_剔污染", "*剔除版.csv")

#: ★ 全库只有这 4 条无止损 → 1R = 进场价 → R 退化成收益率(今天的已知坑)
NO_STOP_CHAINS = ("buy_and_hold", "技-2", "技-12")

INITIAL_EQUITY = 1_000_000.0      # ★ 引擎默认值 chain.run_chain(initial_equity)


def _chain_name(path: str) -> str:
    return os.path.basename(path).replace("__剔除版.csv", "")


def _no_stop(name: str) -> bool:
    return any(k in name for k in NO_STOP_CHAINS)


def load_all() -> dict[str, pd.DataFrame]:
    out = {}
    for f in sorted(glob.glob(LEDGER_GLOB)):
        d = pd.read_csv(f, parse_dates=["entry_date", "exit_date"])
        if not len(d):
            continue
        d = d.sort_values(["symbol", "entry_date"], kind="mergesort").reset_index(drop=True)
        # ★ 机械定义:同票内按进场日排序的第几笔(0 = 首次进场)
        d["entry_seq"] = d.groupby("symbol").cumcount()
        d["is_reentry"] = d["entry_seq"] > 0
        out[_chain_name(f)] = d
    return out


# ══════════════════════════════════════════════════════════════════════════
# 一 · 必答四问 第 4 问 —— 重进的笔单独的胜率和 R
# ══════════════════════════════════════════════════════════════════════════

def _blk(d: pd.DataFrame) -> dict:
    r = d["r_multiple_net"].astype(float).to_numpy()
    r = r[np.isfinite(r)]
    pnl = d["net_pnl"].astype(float).to_numpy()
    return {
        "笔数": int(len(d)),
        "胜率": float((r > 0).mean()) if r.size else None,
        "每笔净R": float(r.mean()) if r.size else None,
        "总净R": float(r.sum()) if r.size else None,
        "净盈亏": float(np.nansum(pnl)),
    }


def reentry_split(leds: dict[str, pd.DataFrame]) -> dict:
    rows = []
    for name, d in leds.items():
        first = d[~d["is_reentry"]]
        re_ = d[d["is_reentry"]]
        rows.append({
            "链": name,
            "无止损链(R=收益率,不可与有止损链同列排序)": _no_stop(name),
            "票数": int(d["symbol"].nunique()),
            "重进过的票数": int((d.groupby("symbol").size() > 1).sum()),
            "单票最多进场次数": int(d.groupby("symbol").size().max()),
            "首次进场": _blk(first),
            "重进": _blk(re_),
        })
    return {"逐链": rows}


# ══════════════════════════════════════════════════════════════════════════
# 二 · 组合级集中度 —— ② 同一天同时触发止损的笔数 · ③ 最严重那一天
# ══════════════════════════════════════════════════════════════════════════

def stop_resonance(leds: dict[str, pd.DataFrame]) -> dict:
    """
    ★ 「同向共振」= 同一个 exit_date 上 reason == '止损' 的笔数 ≥ 2。
    ★ 亏损占账户的分母:**初始资金 1,000,000**(引擎默认值)。
      ★★★ 这是「占初始资金」,不是「占当日净值」—— 流水里没有净值序列,
        ★ 真跑的那几条链另给「占当日净值」的版本(见 run_reentry_grid_1030.py)。
    """
    rows, worst = [], []
    for name, d in leds.items():
        s = d[d["reason"] == "止损"]
        if not len(s):
            rows.append({"链": name, "止损笔数": 0, "有共振的日子数": 0})
            continue
        g = s.groupby("exit_date").agg(同时止损笔数=("symbol", "size"),
                                       合计净亏=("net_pnl", "sum"))
        g["占初始资金"] = g["合计净亏"] / INITIAL_EQUITY
        multi = g[g["同时止损笔数"] >= 2]
        w = g.sort_values("合计净亏").head(1)
        rows.append({
            "链": name,
            "止损笔数": int(len(s)),
            "有共振的日子数(同日≥2笔止损)": int(len(multi)),
            "共振日占全部止损日比": (float(len(multi) / len(g)) if len(g) else None),
            "同日止损笔数最大值": int(g["同时止损笔数"].max()),
            "最惨一天": {
                "日期": str(w.index[0].date()),
                "同时止损笔数": int(w["同时止损笔数"].iloc[0]),
                "合计净亏": float(w["合计净亏"].iloc[0]),
                "占初始资金": float(w["占初始资金"].iloc[0]),
            },
        })
        for dt, rr in g.iterrows():
            worst.append({"链": name, "日期": str(dt.date()),
                          "同时止损笔数": int(rr["同时止损笔数"]),
                          "合计净亏": float(rr["合计净亏"]),
                          "占初始资金": float(rr["占初始资金"])})
    worst.sort(key=lambda x: x["合计净亏"])
    return {"逐链": rows, "全库最惨的20天": worst[:20]}


# ══════════════════════════════════════════════════════════════════════════
# 三 · 同时持仓里的行业集中度 —— ① 同一 SIC 两位占几成
# ══════════════════════════════════════════════════════════════════════════

def sic_two_digit_map(symbols: list[str]) -> dict[str, int]:
    """
    ★ 行业分类**不重写**:直接用 engine/ops_1029.py 里已有的严格 PIT SIC 面板
      (`sic_daily`),★ 取每只票**最后一个有值**的 SIC 码的两位。
    ★★ 为什么取最后一个而不是逐日:集中度这一层只要「这两只票是不是同一行业」,
      ★ 而实测 250 只里只有 15 只 SIC 变过 —— 逐日 PIT 在这一层是过度工程。
      ★★★ 这个取舍是减配,报告里写明。
    """
    import sys
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from engine import ops_1029
    out: dict[str, int] = {}
    try:
        panel = ops_1029.sic_daily(tuple(sorted(set(symbols))))
    except Exception as exc:                       # pragma: no cover
        raise RuntimeError(f"SIC 面板取不到:{exc!r} —— ★ 不拿行业名近似顶上") from exc
    for sym in panel.columns:
        ser = panel[sym].dropna()
        if len(ser):
            try:
                out[sym] = int(float(ser.iloc[-1])) // 100
            except Exception:
                continue
    return out


def concurrent_industry(leds: dict[str, pd.DataFrame], sic2: dict[str, int]) -> dict:
    """
    ★ 逐时点(逐交易日)重建「当天同时持仓」= entry_date ≤ t < exit_date,
      再看同一个 SIC 两位占了几成。只报每条链的**最大值与均值**。
    """
    rows = []
    for name, d in leds.items():
        ev = []
        for _, r in d.iterrows():
            ev.append((r["entry_date"], +1, r["symbol"]))
            ev.append((r["exit_date"], -1, r["symbol"]))
        ev.sort(key=lambda x: (x[0], -x[1]))
        live: dict[str, int] = {}
        pts = []
        miss = 0
        for _, delta, sym in ev:
            live[sym] = live.get(sym, 0) + delta
            if live[sym] <= 0:
                live.pop(sym, None)
            if len(live) >= 2:
                codes = []
                for s in live:
                    c = sic2.get(s)
                    if c is None:
                        miss += 1
                    else:
                        codes.append(c)
                if codes:
                    vc = pd.Series(codes).value_counts()
                    pts.append((int(vc.iloc[0]), len(live),
                                float(vc.iloc[0] / len(live))))
        if not pts:
            rows.append({"链": name, "说明": "同时持仓从未达到 2 → 无集中度可言"})
            continue
        share = np.array([p[2] for p in pts])
        top = max(pts, key=lambda p: (p[2], p[0]))
        rows.append({
            "链": name,
            "有效时点数(同时持仓≥2)": len(pts),
            "同一SIC两位占比_均值": float(share.mean()),
            "同一SIC两位占比_最大": float(share.max()),
            "最集中那一刻": {"同行业仓位数": top[0], "总持仓数": top[1],
                             "占比": top[2]},
            "SIC查不到的次数": int(miss),
        })
    return {"逐链": rows}


def main() -> int:
    leds = load_all()
    out: dict = {"口径": {
        "流水目录": "engine/ledgers_1030_剔污染/*剔除版.csv",
        "链数": len(leds),
        "R": "r_multiple_net(扣摩擦)",
        "重进定义": "同票同链内按 entry_date 排序的第 2 笔及以后(机械,无阈值)",
        "★我们自己填的数": "零个 —— 本文件全是机械统计",
    }}
    out["一_重进与首次进场分开统计"] = reentry_split(leds)
    out["二_同日止损共振"] = stop_resonance(leds)
    syms = sorted({s for d in leds.values() for s in d["symbol"].unique()})
    sic2 = sic_two_digit_map(syms)
    out["口径"]["SIC两位_覆盖票数"] = f"{len(sic2)}/{len(syms)}"
    out["三_同时持仓行业集中度"] = concurrent_industry(leds, sic2)

    # ★★★ 先写结果,再打印(今天丢过一次 437 秒的跑批,原因是写出前的 print 报错)
    dst = os.path.join(HERE, "ledger_facts_1030.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print(f"已写 {dst}")
        print(f"链数 {len(leds)} · SIC 两位覆盖 {out['口径']['SIC两位_覆盖票数']}")
        w = out["二_同日止损共振"]["全库最惨的20天"]
        if w:
            print("全库最惨一天:", w[0])
    except Exception as exc:                       # pragma: no cover
        print("打印出错(结果已写出):", repr(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
