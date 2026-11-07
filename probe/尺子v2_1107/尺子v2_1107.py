# -*- coding: utf-8 -*-
"""
★★★★★ 尺子 v2 —— 把 Gemini 第 55 轮那张「尺子用错清单」里**我们还没处理的四条**补上，
   ★ 外加 **#76 的下半截**（★★★ 策略侧打开了全收益，基准侧没打开）。

★★ 来历：《24》#76 末尾那张表是另一路自己写的「下一轮必须做」：
   | ⑧ | 交易在时间上重叠却当成互相独立的样本 → 按日期聚类，或换成每天的组合收益序列 |
   | ⑪ | 随机结果的分布是偏的，而我用了「均值 ± 2 个标准差」→ 要改成**分位数**(2.5/97.5) |
   | ③ | 夏普的显著性不能直接按 √T 算（多日持仓最明显）→ Newey-West / Lo 2002 |
   | ⑥ | 多期复合收益不能直接按算术平均检验 → 用对数收益 |

★★★★★ ⚠ **先查代码再喊结论**（规矩⑬ + #75 那条「同一类错第五次」的教训）——
   ★ 我在动手之前把这四条**逐条在代码里核过了**，★★ 结果**有两条已经做了一半**，
   ★★★ 如果不核就动手，我会第六次犯同一类错（把「某处没有」当成「不存在」）：

   | # | 代码里的真实状态（★ 逐处打出来核过） |
   |---|---|
   | ⑧ | 🟡 **已做一半** —— `台_公共_1106.聚类t()` **按进场日聚类**了，`块重抽样()` 还按**进场月**成块。<br>★★★ 但**没有任何地方处理「持有期互相重叠」**：按进场日聚类假定「不同进场日互相独立」，<br>★ 而一笔 1 月进场持 6 个月的单子，和 2~6 月进场的单子**吃的是同一段行情**。 |
   | ⑪ | ❌ **没做** —— `probe/B路重测_1107/台_1107.py:232 噪声判()` 仍然是 `z=(真−mu)/sd` + `|z|` 分档，<br>★★★ 而且 `len(a) < 5` 才拒绝（★ 规矩㊸v2 今天上午刚写「随机对照 ≥100 次」）。<br>★★ 实际调用处用了 1000 次 / 20 个种子 —— ★ **次数够，但尺子形状不对**。 |
   | ③ | ❌ **完全没有** —— 全仓库没有任何地方算夏普的显著性（★ grep 过，连夏普本身都没进报告）。 |
   | ⑥ | 🟡 **年化本来就是几何的**（`总倍**(1/年数)`，对的）；<br>★★★ 但**检验**用的全是算术均值（`ex.mean()/ex.std()`、`diff.mean()`）—— 那一层没做。 |
   | #76下半截 | ❌ **没做** —— ★★★ 这一条最硬，单独见下。 |

★★★★★ #76 的下半截（★ 本轮最该报给 Lin 的一件）：
   ★ 另一路今天上午在 `probe/重测_1107/跑重测_1107.py:133` 打开了 `TOTAL_RETURN_DEFAULT = True`
     —— ★★ 那是**策略那一侧**。
   ★★★ 但**主判据「大盘替身」买的 SPY 还是纯价格**：
     `台_公共_1106.替身收益():178` → `data.load_benchmark("SPY")` 的 open/close，**一个字的分红都没加**。
   ★★★ 而 `engine/evidence_total_return.py` 的开头就写着：
     「★★ ④ 基准也必须换成总收益 —— 否则造出一个方向相反的新偏差。」
   → ★★★★★ 也就是：**我们自己一个月前写下的警告，今天上午刚好踩进去了。**
   ★★ 并且 `data.dividends("SPY")` 返回 **0 条**（★ SPY 不在 `load_manifest()` 的 300 只里），
     ★★★ 所以**光打开引擎开关不会让基准拿到分红** —— 必须显式从文件读（见 `基准两口径()`）。

★★★ 这一份**不跑回测**，只换量法；engine/ 一个字节都不许改。
★★ 口径头按规矩㊼ 逐份打印。
"""
from __future__ import annotations

import glob
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from engine import split_gate  # noqa: E402

TRADING_DAYS = 252.0


# ══════════════════════════════════════════════════ 规矩㊼ · 口径头
def 口径头(**kw) -> dict:
    """★★★ 规矩㊼：每份报告头部必须打印「本次口径」——
    全收益/价格 · 摩擦档 · 窗口 · 池子 · 标签滞后几天。★ 缺一项就写「★未声明」。"""
    必 = ("全收益或价格", "摩擦档", "窗口", "池子", "标签滞后天")
    头 = {k: kw.get(k, "★未声明") for k in 必}
    头["★★★规矩㊼"] = "★ 开关类默认值当成结论字段来报 —— 关着的能力比缺失的能力更危险"
    缺 = [k for k in 必 if 头[k] == "★未声明"]
    if 缺:
        头["★★★口径没声明的项"] = 缺
    return 头


# ══════════════════════════════════════════════════ #76 下半截 · 基准两口径
def _读一份(p: str) -> list:
    o = gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") else open(p, encoding="utf-8")
    with o as fh:
        return json.load(fh).get("data") or []


def 基准源目录(symbol: str) -> list[tuple[str, int, str, str]]:
    """★★★ 规矩㊻：「要去 N 个地方查」一律改成**代码自动枚举**，不许手写目录名。
    ★ 返回 [(路径, 根数, 起, 止)]，★★ 按根数从多到少排（★★★ 显式定优先级，不靠字典序 —— #75）。"""
    pats = [f"{symbol}/daily.json", f"market_*/{symbol}/daily.json",
            f"market_*/{symbol}/daily.json.gz", f"pilot_*/benchmarks/{symbol}/daily.json",
            f"pilot_*/benchmarks/{symbol}/daily.json.gz"]
    found = []
    for pat in pats:
        for p in sorted(glob.glob(pat)):
            try:
                rows = _读一份(p)
            except Exception:
                continue
            if not rows:
                continue
            ds = [r["date"] for r in rows]
            found.append((p, len(rows), min(ds), max(ds)))
    # ★★★ 显式优先级：根数多的优先（★ 覆盖窗口最宽），同根数按路径名定序以保证可复现
    return sorted(found, key=lambda x: (-x[1], x[0]))


def 基准两口径(symbol: str = "SPY", 打印: bool = True) -> dict:
    """★★★ 同一只基准，**同时**算纯价格和全收益两条净值 —— ★ 两条都返回，调用方必须自己选。

    ★★ 做法和 `engine/data.load_benchmark` 走**同一条**拆股修正路径
       （`split_gate.ratio_events_from_rows`），★★★ 不另造一套，免得「个股修了基准没修」。
    ★★★ 全收益日收益 = (收_t − 收_{t−1} + 每股分红_t) / 收_{t−1}
       · 分红所在那天是**除息日**（PIT 口径见 `engine/data.dividends` 的说明）。
    ★ 分红金额和除息日之前的价格要在同一个拆股口径上 → **分红也要跟着折算**（和 data.dividends 一致）。
    """
    srcs = 基准源目录(symbol)
    if not srcs:
        raise FileNotFoundError(f"★ 仓库里没有 {symbol} 的日线 —— 拿不到就是拿不到，不用别的顶上")
    p, n, d0, d1 = srcs[0]
    rows = _读一份(p)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    for c in ("open", "high", "low", "close"):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    div = pd.to_numeric(df.get("dividend_amount"), errors="coerce").fillna(0.0) \
        if "dividend_amount" in df.columns else pd.Series(0.0, index=df.index)
    # ★ 拆股修正（★★ 和个股/基准同一条路径）
    evs = list(split_gate.ratio_events_from_rows(symbol, rows))
    for ev in evs:
        ts = pd.Timestamp(ev.date)
        mask = df.index < ts
        if not mask.any():
            continue
        for c in ("open", "high", "low", "close"):
            if c in df.columns:
                df.loc[mask, c] = df.loc[mask, c] * ev.ratio
        div.loc[mask] = div.loc[mask] * ev.ratio
    cl = df["close"].dropna()
    div = div.reindex(cl.index).fillna(0.0)
    r_px = cl.pct_change()
    r_tr = (cl.diff() + div) / cl.shift(1)
    out = {
        "★★★口径": "★ 两条都给：价格 / 全收益（★★ 调用方必须显式选，不许默认）",
        "源文件": p, "★自动枚举到的源": [{"路径": a, "根数": b, "起": c, "止": d} for a, b, c, d in srcs],
        "★★★为什么不用 data.load_benchmark": (
            "★ 它只找 pilot_300/benchmarks 和板块 ETF 目录 → "
            f"{symbol} 只能拿到 2014 起那份；★★★ 而 market_* 里有更宽的（规矩㊻ 自动枚举）"),
        "根数": int(len(cl)), "窗口": [str(cl.index[0].date()), str(cl.index[-1].date())],
        "★★★非零分红条数": int((div > 0).sum()),
        "分红首尾": ([str(div[div > 0].index[0].date()), str(div[div > 0].index[-1].date())]
                 if (div > 0).any() else None),
        "拆股事件数": len(evs),
        "_价格日收益": r_px, "_全收益日收益": r_tr, "_收盘": cl, "_开盘": df.get("open"),
        "_每股分红": div,
    }
    if 打印:
        print(f"★★★ 基准 {symbol} 两口径自证：{p}", flush=True)
        print(f"     根数 {len(cl)} | {out['窗口'][0]} → {out['窗口'][1]} | "
              f"非零分红 {out['★★★非零分红条数']} 条 | 拆股事件 {len(evs)}", flush=True)
    return out


def 年化(r: pd.Series) -> float:
    r = r.dropna()
    if r.empty:
        return float("nan")
    return float(np.expm1(np.log1p(r).sum() / (len(r) / TRADING_DAYS)))


# ══════════════════════════════════════════════════ #3 · 夏普的显著性（Lo 2002）
def 夏普_Lo(r: pd.Series, q: int = int(TRADING_DAYS)) -> dict:
    """★★★ 清单第 ③ 条：夏普的显著性**不能按 √T 算** —— 多日持仓时日收益有自相关。

    ★★ 两件事分开：
      · **年化**：朴素做法是 SR_日 × √q；★★★ Lo (2002) 的修正是 SR_日 × η(q)，
        η(q) = q / sqrt(q + 2·Σ_{k=1}^{q−1}(q−k)·ρ_k) —— ★ 正自相关 → η < √q → **朴素年化偏高**。
      · **标准误**：iid 下 SE(SR_日) = sqrt((1 + SR_日²/2)/T)（Lo 2002 式 9），
        ★★ 再乘同一个 η(q)/√q 的修正比。
    ★ 出处档：**⑤ 外部模型说的·待核** —— ★★★ Lo (2002) 原文我们没读到，是 Gemini 第 55 轮给的。
    """
    r = r.dropna()
    T = len(r)
    if T < 60:
        return {"★算不出": f"只有 {T} 天(<60)"}
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return {"★算不出": "日收益标准差为 0"}
    sr_d = mu / sd
    q = int(min(q, T - 1))
    # ★ 自相关（样本自相关，★★ 只用到 q−1 阶）
    x = r.to_numpy() - mu
    denom = float((x * x).sum())
    rho = []
    for k in range(1, q):
        if T - k <= 1 or denom <= 0:
            rho.append(0.0)
        else:
            rho.append(float((x[k:] * x[:-k]).sum() / denom))
    s = q + 2.0 * sum((q - (k + 1)) * rho[k] for k in range(len(rho)))
    eta = q / np.sqrt(s) if s > 0 else float("nan")
    朴素年化SR = sr_d * np.sqrt(q)
    Lo年化SR = sr_d * eta if np.isfinite(eta) else float("nan")
    比 = (eta / np.sqrt(q)) if np.isfinite(eta) else float("nan")
    se_iid_d = np.sqrt((1.0 + 0.5 * sr_d ** 2) / T)
    se_Lo_d = se_iid_d * 比 if np.isfinite(比) else float("nan")
    return {
        "①日夏普": round(sr_d, 5),
        "②朴素年化夏普_乘根252": round(float(朴素年化SR), 3),
        "★★★③Lo2002修正年化夏普": (round(float(Lo年化SR), 3) if np.isfinite(Lo年化SR) else None),
        "★★★④修正比_eta除根q": (round(float(比), 4) if np.isfinite(比) else None),
        "⑤一阶自相关rho1": round(rho[0], 4) if rho else None,
        "⑥前5阶自相关": [round(v, 4) for v in rho[:5]],
        "⑦iid标准误_日": round(float(se_iid_d), 5),
        "★★★⑧Lo修正后t值_日夏普": (round(float(sr_d / se_Lo_d), 2)
                           if np.isfinite(se_Lo_d) and se_Lo_d > 0 else None),
        "⑨朴素t值_日夏普": round(float(sr_d / se_iid_d), 2) if se_iid_d > 0 else None,
        "★读法": ("★ 修正比 < 1 → **朴素年化夏普和朴素 t 都偏高**（正自相关）；"
                "★★ > 1 → 偏低（负自相关）"),
        "★出处档": "⑤ 外部模型说的·待核（Lo 2002，★★★ 原文我们没读到）",
    }


# ══════════════════════════════════════════════════ #6 · 对数收益
def 对数检验(r: pd.Series, rb: pd.Series) -> dict:
    """★★★ 清单第 ⑥ 条：多期复合收益**不能按算术平均检验** —— 要用对数收益。

    ★★ 为什么：算术均值刻画的是「每期期望」，★★★ 而我们真正拿到手的是**复利结果**，
       两者差一个波动拖累 ≈ σ²/2。★ 波动越大，算术均值越高估我们实际拿到的东西。
    ★ 所以这里**两个都报**，并把差额（波动拖累）单独列出来。
    """
    共 = r.dropna().index.intersection(rb.dropna().index)
    r, rb = r.loc[共], rb.loc[共]
    if len(共) < 60:
        return {"★算不出": f"共同交易日只有 {len(共)}(<60)"}
    lr, lrb = np.log1p(r), np.log1p(rb)
    ex_算 = (r - rb)
    ex_对 = (lr - lrb)
    def t(x):
        x = x.dropna().to_numpy()
        s = x.std(ddof=1)
        return float(x.mean() / (s / np.sqrt(len(x)))) if s > 0 else float("nan")
    拖 = float(r.mean() - lr.mean())
    return {
        "①交易日数": int(len(共)),
        "②算术年化_策略pct": round(float(r.mean() * TRADING_DAYS) * 100, 3),
        "★★★③对数(复利)年化_策略pct": round(float(np.expm1(lr.mean() * TRADING_DAYS)) * 100, 3),
        "★★★④波动拖累pct_年": round(拖 * TRADING_DAYS * 100, 3),
        "⑤算术超额t_不算自相关": round(t(ex_算), 2),
        "★★★⑥对数超额t_不算自相关": round(t(ex_对), 2),
        "⑦两个t的差": round(t(ex_对) - t(ex_算), 3),
        "★读法": ("★ 算术年化**系统性高于**对数年化，差额就是波动拖累；"
                "★★★ 报成绩要用对数那一行，★★ 算术那一行只能当中间量"),
        "★出处档": "② 行业通行（对数收益可加；★ 波动拖累 σ²/2 是教科书结论）",
    }


# ══════════════════════════════════════════════════ #8 · 重叠交易
def 重叠聚类t(diff: pd.Series, 进: pd.Series, 离: pd.Series) -> dict:
    """★★★ 清单第 ⑧ 条：交易**在时间上重叠**却当成互相独立的样本。

    ★★ 仓库里已经做了一半（★ 我核过代码）：`台_公共_1106.聚类t()` 按**进场日**聚类、
       `块重抽样()` 按**进场月**成块。★★★ 但这两个都假定「不同进场日/不同月互相独立」——
       ★ 而一笔 1 月进场、持 6 个月的单子，和 2~6 月进场的那些单子**吃的是同一段行情**。
    ★★ 这一份把四种标准误**并排报**，并报**平均同时在场笔数**（= 重叠有多重）：
       ① 朴素 iid  ② 按进场日聚类（现用）  ③ 按进场月成块
       ★★★ ④ 按「持有期重叠连通块」聚类 —— ★ 两笔只要持有期有一天重叠就归一组（并查集），
          ★★ 这是最保守的一种：它把「互相有重叠」的整串单子当成**一个**观测。
    ★ 有效样本量 = (朴素标准误 / 该口径标准误)² × n —— ★★ 直观告诉我们「真正独立的有几笔」。
    """
    d = pd.DataFrame({"x": pd.to_numeric(diff, errors="coerce"),
                      "a": pd.to_datetime(进, errors="coerce"),
                      "b": pd.to_datetime(离, errors="coerce")}).dropna(subset=["x", "a"])
    d["b"] = d["b"].fillna(d["a"])
    n = len(d)
    if n < 20:
        return {"★算不出": f"只有 {n} 笔(<20)"}
    m = float(d["x"].mean())

    def se_聚类(key) -> tuple[float, int]:
        g = d.groupby(key)["x"].mean().dropna()
        k = len(g)
        if k < 3:
            return float("nan"), k
        return float(g.std(ddof=1) / np.sqrt(k)), k

    se_iid = float(d["x"].std(ddof=1) / np.sqrt(n))
    se_日, k日 = se_聚类(d["a"].values)
    se_月, k月 = se_聚类(d["a"].dt.to_period("M").astype(str).values)

    # ★★★ ④ 持有期重叠 → 连通块
    # ★★ 区间重叠图的连通块**不用并查集**：按进场排序后，
    #    只要「下一笔的进场 ≤ 当前块里最大的离场」就还在同一块 —— O(n log n)。
    #    ★ 原来我写的扫描线 + 并查集在「全部互相重叠」时是 O(n²)（10,405 笔会跑死）。
    o = d.sort_values("a").reset_index(drop=True)
    lab = np.empty(len(o), dtype=np.int64)
    块 = 0
    块内最大离场 = o.loc[0, "b"]
    for k in range(len(o)):
        if k > 0 and o.loc[k, "a"] > 块内最大离场:
            块 += 1
            块内最大离场 = o.loc[k, "b"]
        else:
            块内最大离场 = max(块内最大离场, o.loc[k, "b"])
        lab[k] = 块
    g4 = o["x"].groupby(lab).mean().dropna()
    k重 = len(g4)
    se_重 = float(g4.std(ddof=1) / np.sqrt(k重)) if k重 >= 3 else float("nan")

    # ★ 平均同时在场笔数（★★ 重叠有多重的直观量）
    ev = pd.concat([pd.Series(1, index=d["a"]), pd.Series(-1, index=d["b"] + pd.Timedelta(days=1))])
    ev = ev.groupby(level=0).sum().sort_index().cumsum()
    同时 = float(ev.reindex(pd.date_range(d["a"].min(), d["b"].max(), freq="D")).ffill().fillna(0).mean())

    def 有效n(se):
        return int(round(n * (se_iid / se) ** 2)) if np.isfinite(se) and se > 0 else None
    def tt(se):
        return round(float(m / se), 2) if np.isfinite(se) and se > 0 else None
    return {
        "①笔数": n, "②配对差均值pct": round(m * 100, 4),
        "③①朴素iid": {"标准误pct": round(se_iid * 100, 4), "t": tt(se_iid), "有效笔数": n},
        "③②按进场日聚类_现用": {"标准误pct": round(se_日 * 100, 4) if np.isfinite(se_日) else None,
                        "t": tt(se_日), "聚类数": k日, "有效笔数": 有效n(se_日)},
        "③③按进场月成块": {"标准误pct": round(se_月 * 100, 4) if np.isfinite(se_月) else None,
                     "t": tt(se_月), "块数": k月, "有效笔数": 有效n(se_月)},
        "★★★③④按持有期重叠连通块": {
            "标准误pct": round(se_重 * 100, 4) if np.isfinite(se_重) else None,
            "t": tt(se_重), "连通块数": k重, "有效笔数": 有效n(se_重),
            "★这是最保守的一种": "★★ 两笔持有期只要有一天重叠就归一组"},
        "★★★④平均同时在场笔数": round(同时, 1),
        "★读法": ("★ 四个 t 从上往下一般越来越小；★★★ 如果「现用」那个 t 过了 2 而"
                "「重叠连通块」那个没过，★★ 那条结论**只是重叠造出来的**"),
        "★出处档": "② 行业通行（聚类稳健标准误）；★ 连通块那一种是**③我们的**",
    }


# ══════════════════════════════════════════════════ #11 · 随机对照改分位数
def 随机对照_分位数(真: float, 随机: list, 最少: int = 100) -> dict:
    """★★★ 清单第 ⑪ 条：随机结果的分布**是偏的**，而我们用了「均值 ± 2 个标准差」。

    ★★ 现用的那一份（`probe/B路重测_1107/台_1107.py:232 噪声判()`）是
       `z=(真−mu)/sd` + `|z|<1 / <2 / ≥2` 分档，★★★ 并且 `len(a)<5` 才拒绝 ——
       ★ 规矩㊸v2（今天上午刚立）要求 **≥100 次**。
    ★★★ 这一份改成**经验分位数**：
       · 单边经验 p 值 = (1 + #{随机 ≥ 真}) / (1 + N)   ★ 加 1 修正，★★ 不会出现 p=0
       · 95% 范围 = 随机分布的 **2.5 / 97.5 分位**（★ 不是 mu ± 2sd）
       · 同时报**偏度**，★★★ 并在「sd 判法」和「分位数判法」**结论不一致时大声标出来**
    """
    a = np.array([x for x in 随机 if x is not None and np.isfinite(x)], float)
    N = len(a)
    if 真 is None or not np.isfinite(真):
        return {"★算不出": "实测值不是有限数"}
    if N < 最少:
        基 = {"★★★判": f"★ 算不出 —— 随机对照只有 {N} 次，规矩㊸v2 要求 ≥{最少} 次", "随机次数": N}
        if N >= 5:
            基["★仅供参考_不许进报告"] = {"分位p": float((1 + (a >= 真).sum()) / (1 + N))}
        return 基
    mu, sd = float(a.mean()), float(a.std(ddof=1))
    lo, hi = (float(v) for v in np.percentile(a, [2.5, 97.5]))
    p_右 = float((1 + (a >= 真).sum()) / (1 + N))
    p_左 = float((1 + (a <= 真).sum()) / (1 + N))
    p_双 = float(min(1.0, 2 * min(p_右, p_左)))
    # ★ 偏度（★★ 样本偏度，不做无偏修正 —— 只用来判「偏不偏」）
    偏 = float(((a - mu) ** 3).mean() / sd ** 3) if sd > 0 else float("nan")
    z = (真 - mu) / sd if sd > 0 else float("nan")
    判_sd = ("分不出" if abs(z) < 1 else ("🟡 只能当方向" if abs(z) < 2 else
             ("★ 超过随机 2 个标准差(偏好)" if z > 0 else "超过随机 2 个标准差(偏差)")))
    判_分 = ("★ 在随机分布之外(偏好)" if 真 > hi else
             ("在随机分布之外(偏差)" if 真 < lo else "分不出(落在随机的 95% 范围里)"))
    打架 = (("超过" in 判_sd) != ("之外" in 判_分))
    out = {
        "随机次数": N, "实测": round(float(真), 5),
        "随机均值": round(mu, 5), "随机标准差": round(sd, 5),
        "★★★随机95%范围_分位数": [round(lo, 5), round(hi, 5)],
        "对照_mu加减2sd": [round(mu - 2 * sd, 5), round(mu + 2 * sd, 5)],
        "★★★偏度": round(偏, 3),
        "★★★经验p_右尾": round(p_右, 4), "经验p_左尾": round(p_左, 4), "经验p_双尾": round(p_双, 4),
        "距随机几个标准差": round(float(z), 2) if np.isfinite(z) else None,
        "①旧判法_按标准差": 判_sd,
        "★★★②新判法_按分位数": 判_分,
    }
    if 打架:
        out["★★★★★两种判法打架"] = ("★ 分布是偏的（偏度 %.2f）→ ★★★ 以**分位数**那一行为准，"
                             "★★ 标准差那一行作废" % 偏)
    out["★出处档"] = "② 行业通行（经验分位数 / 置换检验）"
    return out


# ══════════════════════════════════════════════════ 替身：全收益口径
def 替身收益_两口径(d: pd.DataFrame, 基: dict) -> dict:
    """★★★ #76 下半截：大盘替身**同钱同进同出**买 SPY —— ★ 现用口径一个字的分红都没加。

    ★★ 时点完全照 `台_公共_1106.替身收益()`（★★★ 不许有第二套时点口径）：
       进场 = 进场日**开盘**；止损/退市/期末离场用离场日**收盘**，其余用离场日**开盘**；
       当天进当天出 = 当天开→收。
    ★★★ 全收益 = 价格收益 + 持有期内收到的每股分红 ÷ 进场价
       · PIT：**进场日 < 除息日 ≤ 离场日** 才算收到（★ 和 `engine/data.dividends` 的说明一致）。
    """
    cl, op, div = 基["_收盘"], 基["_开盘"], 基["_每股分红"]
    idx = cl.index
    o = op.to_numpy(float) if op is not None else cl.to_numpy(float)
    c = cl.to_numpy(float)
    i = idx.searchsorted(d["entry_date"].values)
    j = idx.searchsorted(d["exit_date"].values)
    ok = (i < len(idx)) & (j < len(idx)) & (j >= i)
    盘中 = d["reason"].astype(str).isin(["止损", "退市结算", "期末平仓"]).to_numpy()
    px_out = np.full(len(d), np.nan)
    ii, jj = i[ok], j[ok]
    v = np.where(盘中[ok], c[jj], o[jj])
    v = np.where(jj == ii, c[ii], v)
    px_out[ok] = v
    进价 = np.full(len(d), np.nan)
    进价[ok] = o[ii]
    价格收益 = px_out / 进价 - 1.0
    # ★ 累计分红：严格「进场日 < 除息日 ≤ 离场日」
    cum = div.cumsum().to_numpy(float)
    收到 = np.full(len(d), np.nan)
    收到[ok] = cum[jj] - cum[ii]        # ★ cum[ii] 含进场日那天 → 自动排除「除息日当天买」
    全收益 = 价格收益 + 收到 / 进价
    return {"_价格": pd.Series(价格收益, index=d.index),
            "_全收益": pd.Series(全收益, index=d.index),
            "_每笔分红率": pd.Series(收到 / 进价, index=d.index),
            "可配对": pd.Series(ok, index=d.index)}
