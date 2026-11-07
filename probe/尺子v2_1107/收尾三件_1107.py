# -*- coding: utf-8 -*-
"""
★★★ 把上一份对照里**三处没说完的**补齐（★ 不补就会误导）：

★★★★★ ① **#76 要算净效果，不是半截。** ★ 上一份只给基准侧补了分红 →
   ★★ 那是**对我们不利的那一半**。★★★ 策略那一侧的持仓也会收到分红，
   ★ 而这些是**价值/小盘股筛子**，股息率**通常高于 SPY** → ★★★ 补上之后可能往回推更多。
   → ★★ 所以上一份那句「基-20 的正显著没了」**不许单独报** —— 必须等这一份。
   ★ 做法照 `engine/evidence_total_return.py` 的口径（★ 不另造一套）：
     每笔分红现金 = shares × Σ(持有期内除息日的每股分红)，
     持有判定 = **进场日 < 除息日 ≤ 离场日**。

★★★★★ ② **夏普 Lo 修正的截断阶数要跑相邻三点**（★ 红线②：原著没给的参数
   跑相邻三点并报三点是否同向）。★★ 上一份只跑了 q=252 一个点，
   ★★★ 而那是用 ~2,500 天估 251 个自相关 —— ★ 修正比在 0.80~1.89 之间乱跳，
   ★★ 本身就是**不稳**的信号。→ ★★★ 三点不同向就**不许拿它进说明书**。

★★★★★ ③ **「按进场日聚类」在好几条臂上把标准误弄**小**了** ——
   ★ 上一份的「有效笔数」里，基-2·负债0.5 是 **1,496**，而它只有 **1,386 笔**。
   ★★★ 也就是说这个「聚类修正」**不是保守方向**，它在那些臂上**抬高了 t 值**。
   → ★★ 这一份把「有效笔数 > 实际笔数」的臂逐条点出来。
"""
from __future__ import annotations

import glob
import gzip
import importlib.util
import io
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as 台                                        # noqa: E402
from engine import split_gate                                   # noqa: E402

_s = importlib.util.spec_from_file_location("V2", os.path.join(HERE, "尺子v2_1107.py"))
V = importlib.util.module_from_spec(_s); _s.loader.exec_module(V)
_s2 = importlib.util.spec_from_file_location("M91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_s2); _s2.loader.exec_module(M)

EXT = "market_ext_1105"
LEDG = "probe/剔脏日重出_1107/ledgers_clean"
OUT = os.path.join(HERE, "收尾三件_报告_1107.json")
_目录: dict[str, str] | None = None
_缓存: dict[str, pd.Series] = {}


def 目录表() -> dict[str, str]:
    """★★ 目录名可能是 `SYM` 也可能是 `SYM__CIK`（★★★ #72 就是这里栽的）——
    ★ 两种都登记，★★ 裸代码优先。"""
    global _目录
    if _目录 is None:
        _目录 = {}
        for d in sorted(glob.glob(os.path.join(EXT, "*"))):
            if not os.path.isdir(d):
                continue
            b = os.path.basename(d)
            sym = b.split("__")[0]
            if b == sym or sym not in _目录:
                _目录[sym] = d
    return _目录


def 个股分红(sym: str) -> pd.Series:
    """★★★ 一只票的每股现金分红（索引 = 除息日），★ 口径和 `engine/data.dividends` 一字不差：
    ★★ 分红金额要跟着**除息日之前**的拆股折算一起折算，否则「每股分红」和「每股价格」不同口径。
    ★ 拿不到就返回空序列 —— ★★★ 不许用「按市值估个股息率」之类的近似顶上。"""
    if sym in _缓存:
        return _缓存[sym]
    d = 目录表().get(sym)
    out = pd.Series(dtype=float)
    if d:
        for fn in ("daily.json.gz", "daily.json"):
            p = os.path.join(d, fn)
            if not os.path.exists(p):
                continue
            try:
                o = gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")
                with o as fh:
                    rows = json.load(fh).get("data") or []
            except Exception:
                break
            recs = []
            for r in rows:
                v = r.get("dividend_amount")
                if v in (None, ""):
                    continue
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                if x == 0.0 or x != x:
                    continue
                recs.append((pd.Timestamp(r["date"]), x))
            if recs:
                s = pd.Series(dict(recs)).sort_index()
                for ev in split_gate.ratio_events_from_rows(sym, rows):
                    ts = pd.Timestamp(ev.date)
                    m = s.index < ts
                    if m.any():
                        s.loc[m] = s.loc[m] * ev.ratio
                out = s
            break
    _缓存[sym] = out
    return out


def 策略侧分红(d: pd.DataFrame) -> tuple[pd.Series, dict]:
    """★★★ 每笔收到的分红 ÷ 投入金额。★ PIT：进场日 < 除息日 ≤ 离场日。"""
    率 = np.full(len(d), 0.0)
    有数 = np.zeros(len(d), dtype=bool)
    无分红票, 无数据票 = set(), set()
    for k, r in enumerate(d.itertuples(index=False)):
        sym = str(r.symbol)
        s = 个股分红(sym)
        if 目录表().get(sym) is None:
            无数据票.add(sym); continue
        有数[k] = True
        if s.empty:
            无分红票.add(sym); continue
        a, b = r.entry_date, r.exit_date
        if pd.isna(a):
            continue
        b = b if pd.notna(b) else a
        收 = float(s[(s.index > a) & (s.index <= b)].sum())
        if 收 and float(r.notional_in) > 0:
            率[k] = 收 * float(r.shares) / float(r.notional_in)
    return pd.Series(率, index=d.index), {
        "★★★面板外_拿不到分红数据的票数": len(无数据票),
        "该票有数据但区间内无分红的票数": len(无分红票),
        "有分红数据的笔数占比pct": round(float(有数.mean()) * 100, 1),
    }


def main() -> int:
    基 = V.基准两口径("SPY", 打印=True)
    报 = {"★口径头": V.口径头(
        全收益或价格="★★★ 两侧都补上分红（**净效果**）—— ★ 这才是 #76 该报的那个数",
        摩擦档="★ 流水自带", 窗口=f"{M.PERF0.date()} → {M.PERF1.date()}",
        池子="★★★ 老池 2,224 —— ★ 已被并池 3,834 取代，本份是**尺子体检**不是成绩表",
        标签滞后天="★ 沿用原跑批"),
        "①#76净效果": {}, "②夏普Lo相邻三点": {}, "③聚类反而变小的臂": {}, "★★★汇总": {}}

    净 = []
    翻正 = []
    for f in sorted(glob.glob(os.path.join(LEDG, "REAL__*.csv"))):
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("notional_in", "net_pnl", "shares"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "exit_date", "notional_in", "net_pnl"])
        d = d[d["notional_in"] > 0].reset_index(drop=True)
        if len(d) < 20:
            报["①#76净效果"][名] = {"★跑失败": f"只剩 {len(d)} 笔(<20)"}
            print(f"✗ {名[:32]:32s} 笔数不够", flush=True); continue
        真价 = d["net_pnl"] / d["notional_in"]
        替 = V.替身收益_两口径(d, 基)
        策分, 诊 = 策略侧分红(d)
        真全 = 真价 + 策分
        ok = 真价.notna() & 替["_价格"].notna() & 替["_全收益"].notna()
        if int(ok.sum()) < 20:
            报["①#76净效果"][名] = {"★跑失败": f"可配对 {int(ok.sum())} 笔(<20)"}
            continue
        def st(x, y):
            s = 台.聚类t((x - y)[ok], d.loc[ok, "entry_date"])
            return (round(s["均值"] * 100, 4),
                    round(float(s["t"]), 2) if np.isfinite(s["t"]) else None)
        d价价 = st(真价, 替["_价格"])      # ★ 现用（两侧都没分红）
        d全全 = st(真全, 替["_全收益"])    # ★★★ 净效果（两侧都有分红）
        d价全 = st(真价, 替["_全收益"])    # ★ 只修基准侧（上一份那个半截）
        rec = {
            "①现用_两侧都无分红": {"差pct": d价价[0], "t": d价价[1]},
            "②只修基准侧_上一份那个半截": {"差pct": d价全[0], "t": d价全[1]},
            "★★★③净效果_两侧都有分红": {"差pct": d全全[0], "t": d全全[1]},
            "策略侧每笔平均分红率pct": round(float(策分[ok].mean()) * 100, 4),
            "替身侧每笔平均分红率pct": round(float(替["_每笔分红率"][ok].mean()) * 100, 4),
            "★★★策略侧减替身侧pct": round(float((策分[ok] - 替["_每笔分红率"][ok]).mean()) * 100, 4),
            "★数据诊断": 诊,
        }
        报["①#76净效果"][名] = rec
        净.append(rec["★★★策略侧减替身侧pct"])
        if d价价[1] is not None and d全全[1] is not None:
            if abs(d价价[1]) >= 1.96 and abs(d全全[1]) < 1.96:
                翻正.append({"臂": 名, "现用t": d价价[1], "净效果t": d全全[1], "方向": "显著→不显著"})
            elif abs(d价价[1]) < 1.96 and abs(d全全[1]) >= 1.96:
                翻正.append({"臂": 名, "现用t": d价价[1], "净效果t": d全全[1], "方向": "不显著→显著"})
        print(f"✓ {名[:32]:32s} t 现用{d价价[1]} → 半截{d价全[1]} → ★净效果{d全全[1]} "
              f"| 策略分红{rec['策略侧每笔平均分红率pct']}% 替身{rec['替身侧每笔平均分红率pct']}%", flush=True)

    # ══════ ② 夏普 Lo 相邻三点（红线②）
    w = pd.read_parquet("probe/newpool_1106/ohlcv_panel_newpool.parquet")
    cl = w["close"]; del w
    三点 = (21, 63, 252)
    for f in sorted(glob.glob(os.path.join(LEDG, "REAL__*.csv")))[:12]:
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("net_pnl", "shares", "entry_price"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
        if len(d) < 20:
            continue
        有 = [s for s in sorted(set(d["symbol"].astype(str))) if s in cl.columns]
        eq, _, _ = M.逐日净值(d, cl[有])
        wm = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
        eqw = eq.loc[wm].dropna()
        if len(eqw) < 60:
            continue
        r = eqw.pct_change().dropna()
        rb = 基["_全收益日收益"].reindex(eqw.index).dropna()
        ex = (r - rb).dropna()
        三 = {}
        for q in 三点:
            s = V.夏普_Lo(ex, q=q)
            三[f"q={q}"] = {"修正比": s.get("★★★④修正比_eta除根q"),
                          "Lo年化夏普": s.get("★★★③Lo2002修正年化夏普"),
                          "Lo_t": s.get("★★★⑧Lo修正后t值_日夏普"),
                          "朴素t": s.get("⑨朴素t值_日夏普")}
        比 = [三[f"q={q}"]["修正比"] for q in 三点]
        同向 = all(x is not None for x in 比) and (all(x > 1 for x in 比) or all(x < 1 for x in 比))
        三["★★★三点同向吗"] = ("✅ 同向" if 同向 else "★★★ **不同向 —— 作废，不许进说明书**")
        三["★★★三点修正比"] = 比
        报["②夏普Lo相邻三点"][名] = 三
        print(f"  Lo三点 {名[:28]:28s} 比={比} {三['★★★三点同向吗']}", flush=True)

    # ══════ ③ 聚类反而让标准误变小的臂
    上 = json.load(open(os.path.join(HERE, "尺子v2对照_报告_1107.json"), encoding="utf-8"))
    坏 = []
    for k, v in 上["逐条"].items():
        o = (v.get("★★★④第⑧条_重叠交易") or {})
        dd = o.get("③②按进场日聚类_现用") or {}
        n, e = o.get("①笔数"), dd.get("有效笔数")
        if isinstance(n, int) and isinstance(e, int) and e > n:
            坏.append({"臂": k, "笔数": n, "聚类后有效笔数": e,
                       "★倍": round(e / n, 3), "聚类t": dd.get("t"),
                       "朴素t": (o.get("③①朴素iid") or {}).get("t")})
    报["③聚类反而变小的臂"] = {
        "★★★条数": len(坏), "★★★读法": (
            "★ 「有效笔数 > 实际笔数」= 按进场日聚类之后标准误**变小了** → "
            "★★★ 这个修正**不是保守方向**，它在这些臂上**抬高了 t 值**；"
            "★★ 而主判据「大盘替身」报的就是这个 t。"),
        "明细": sorted(坏, key=lambda x: -x["★倍"])}

    三点同向 = [k for k, v in 报["②夏普Lo相邻三点"].items() if "✅" in str(v.get("★★★三点同向吗"))]
    报["★★★汇总"] = {
        "★★★①#76净效果": {
            "★★★策略侧减替身侧_中位pct": (round(float(np.median(净)), 4) if 净 else None),
            "策略侧减替身侧_范围pct": ([round(float(np.min(净)), 4), round(float(np.max(净)), 4)]
                              if 净 else None),
            "★★★净效果让结论翻掉的臂": {"条数": len(翻正), "明细": 翻正},
            "★★★读法": "★ 正数 = 我们的持仓比 SPY 更能收分红 → ★★ 两侧都补之后对我们**有利**",
        },
        "★★★②夏普Lo": {"测了几条": len(报["②夏普Lo相邻三点"]),
                   "★★★三点同向的条数": len(三点同向),
                   "★★★结论": ("★★★ 三点**基本不同向** → 这把尺子按我这个实现**不稳，不许进说明书**"
                            if len(三点同向) < len(报["②夏普Lo相邻三点"]) * 0.8
                            else "★ 三点同向，可用")},
        "★★★③聚类不保守": {"条数": 报["③聚类反而变小的臂"]["★★★条数"]},
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("\n★★★ 汇总:", json.dumps(报["★★★汇总"], ensure_ascii=False, indent=1))
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
