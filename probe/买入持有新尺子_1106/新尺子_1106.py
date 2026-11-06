# -*- coding: utf-8 -*-
"""
★★★ 买入持有对比 —— **换指标重算**（★ Lin 1106 工单优先级 ②）

★★ 为什么要换:★ 原来那张对比表只有**利润因子**一个数,
   ★★★ 而《83》第三节自己就写明了它的四个毛病,其中最硬的一条是:
     **利润因子完全看不见回撤** —— ★ 买了不动在 2020 年跌掉约 34%,那个数里看不出来。
→ ★★ 所以这一份按 Lin 点的六个指标重算:
   信息比率 · 对 SPY 回归的 alpha 与 t 值(Newey-West) · 卡玛比率 · 溃疡指数
   · 最大回撤 · 回本天数。★ 利润因子**保留但降为辅助**。

★★★ **不跑回测** —— 只用已入库的流水逐日重建净值(和
  `probe/账户百分比_1106/按净值百分比_1106.py` **同一套重建逻辑**,★ 不另造一份)。

★★★★★ ⚠ 这一份里最要紧的一条诚实检查(★ 规矩⑥:凡是让我们数字变好看的,先当自己错了):
   ★ 回撤类指标**天然偏向「大部分时间空仓」的策略** ——
     ★★ 一条只投 10% 资金的策略,回撤当然小,★★★ 但那不是本事,是**没下场**。
   → ★ 所以每一行都**并排报「平均投入比例」**;
     ★★★ 投入比例差一个数量级的两行,**卡玛/溃疡不可直接比**。

engine/ 零改动。
"""
from __future__ import annotations
import os, sys, json, glob
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from engine import data  # noqa: E402

EQ0 = 1_000_000.0
OUT = "probe/买入持有新尺子_1106"
PERF0, PERF1 = pd.Timestamp("2018-01-01"), pd.Timestamp("2025-12-31")


# ---------------------------------------------------------------- 逐日净值
def 逐日净值(d: pd.DataFrame, cl: pd.DataFrame, 旧口径: bool = False):
    """★★★ 逐日重建净值。100万 + 已平仓累计 net_pnl + 持仓中按当日收盘的浮盈。

    ★★★★★ 1106 续记 · 第 54 处错(★ 本次查出,★★ 必须登记进《24》):
      ★ 《账户百分比》那一份写的是 `实现.shift(1)` + 浮盈只算到 `index < exit_date` ——
        ★★ 于是**离场那一天**,这笔仓位**两头都不算**:
          浮盈已经去掉了,已实现又还没落账 → ★★★ 净值上出现一个**一天的坑**。
      ★ 平时看不出来(离场日是散开的),★★★ 但买入持有有 **257 笔同一天离场** →
        ★ 净值从 1,759,563 一天掉到 1,011,331,★★ **凭空造出 −42.5% 的单日暴跌**。
      → ★★★ 后果:**最大回撤 / 卡玛 / 溃疡 / 回本天数 / 年化 全算错**
        (买入持有年化被压成 0.14%,最大回撤被打成 −42.97%)。
      → ★★ 修法:**已实现在离场日当天落账(不 shift)**,浮盈仍只算到离场日前一天 ——
        ★★★ 这样离场日由 net_pnl 接上,曲线连续。
      ★ `旧口径=True` 保留原算法,只为**出一张自证表**(新旧对比)。
    """
    idx = cl.index
    实现 = pd.Series(0.0, index=idx)
    g = d.dropna(subset=["exit_date"]).groupby("exit_date")["net_pnl"].sum()
    丢 = 0.0
    for t, v in g.items():
        if t in 实现.index:
            实现.loc[t] += float(v)
        else:
            丢 += float(v)
    if 丢:
        print(f"   ⚠ 有 {丢:,.0f} 的已实现盈亏落在日历外(没落账)—— 查!", flush=True)
    实现 = 实现.cumsum()
    浮 = pd.Series(0.0, index=idx)
    在场 = pd.Series(0.0, index=idx)
    缺票 = set()
    for _, r in d.iterrows():
        s = str(r["symbol"])
        if s not in cl.columns:
            缺票.add(s); continue
        a, b = r["entry_date"], r["exit_date"]
        if pd.isna(a):
            continue
        b = b if pd.notna(b) else idx[-1]
        seg = cl[s].loc[(cl.index >= a) & (cl.index < b)].dropna()
        if seg.empty:
            continue
        sh = float(r["shares"])
        浮.loc[seg.index] += (seg - float(r["entry_price"])) * sh
        在场.loc[seg.index] += seg * sh
    基 = 实现.shift(1).fillna(0.0) if 旧口径 else 实现
    eq = (EQ0 + 基 + 浮).rename("净值")
    return eq, 在场, 缺票


# ---------------------------------------------------------------- 指标
def 牛顿西方差(x: np.ndarray, X: np.ndarray, resid: np.ndarray, L: int) -> np.ndarray:
    """★★ Newey-West(1987) HAC 协方差。★★★ 出处档:⑤ 外部模型说的·待核(《83》第三步)。"""
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    u = X * resid[:, None]
    S = u.T @ u
    for l in range(1, L + 1):
        w = 1.0 - l / (L + 1.0)
        G = u[l:].T @ u[:-l]
        S += w * (G + G.T)
    return XtX_inv @ S @ XtX_inv


def 一条指标(eq: pd.Series, 在场: pd.Series, spy: pd.Series) -> dict:
    """★ eq 已经截到绩效窗口;spy 是同窗口的 SPY 收盘。"""
    eq = eq.dropna()
    if len(eq) < 60:
        return {"★算不出": f"净值序列只有 {len(eq)} 天(<60)"}
    r = eq.pct_change().dropna()
    rb = spy.reindex(eq.index).pct_change().dropna()
    共 = r.index.intersection(rb.index)
    r, rb = r.loc[共], rb.loc[共]
    n = len(r)

    # ① 回撤族
    峰 = eq.cummax()
    dd = eq / 峰 - 1.0
    最大回撤 = float(dd.min())
    溃疡 = float(np.sqrt(np.mean((dd * 100.0) ** 2)))     # ★ Martin & McCann 1989,百分点
    # ★ 回本天数:水下最长连续段(★★ 以交易日计)
    水下 = (dd < -1e-12).to_numpy()
    最长, 跑 = 0, 0
    for v in 水下:
        跑 = 跑 + 1 if v else 0
        最长 = max(最长, 跑)
    回本天数 = int(最长)
    还在水下 = bool(水下[-1])

    # ② 收益族
    年数 = n / 252.0
    总倍 = float(eq.iloc[-1] / eq.iloc[0])
    年化 = float(总倍 ** (1.0 / 年数) - 1.0) if 年数 > 0 and 总倍 > 0 else float("nan")
    卡玛 = float(年化 / abs(最大回撤)) if 最大回撤 < -1e-12 else None

    # ③ 信息比率(对 SPY 的超额日收益)
    ex = (r - rb).to_numpy()
    信息比率 = float(ex.mean() / ex.std(ddof=1) * np.sqrt(252)) if ex.std(ddof=1) > 0 else None

    # ④ 对 SPY 回归 alpha + Newey-West t
    X = np.column_stack([np.ones(n), rb.to_numpy()])
    y = r.to_numpy()
    beta = np.linalg.pinv(X.T @ X) @ (X.T @ y)
    resid = y - X @ beta
    L = int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))     # ★ Newey-West 经验带宽
    V = 牛顿西方差(y, X, resid, L)
    se_a = float(np.sqrt(max(V[0, 0], 0.0)))
    alpha_日 = float(beta[0])
    alpha_t = float(alpha_日 / se_a) if se_a > 0 else None
    alpha_年 = float((1 + alpha_日) ** 252 - 1)

    # ⑤ 投入比例(★★★ 回撤类指标的必读旁注)
    投入 = (在场.reindex(eq.index) / eq).replace([np.inf, -np.inf], np.nan).dropna()
    return {
        "①交易日数": n,
        "①窗口": [str(eq.index[0].date()), str(eq.index[-1].date())],
        "②年化收益pct": round(年化 * 100, 3),
        "★★★③最大回撤pct": round(最大回撤 * 100, 2),
        "★★★④卡玛比率": (round(卡玛, 3) if 卡玛 is not None else None),
        "★★★⑤溃疡指数": round(溃疡, 3),
        "★★★⑥回本天数_交易日": 回本天数,
        "⑥期末还在水下": 还在水下,
        "★★★⑦信息比率_对SPY": (round(信息比率, 3) if 信息比率 is not None else None),
        "★★★⑧alpha年化pct": round(alpha_年 * 100, 3),
        "★★★⑧alpha_t_NeweyWest": (round(alpha_t, 2) if alpha_t is not None else None),
        "⑧NW滞后阶数": L,
        "⑧beta_对SPY": round(float(beta[1]), 3),
        "★★★⑨平均投入比例pct": round(float(投入.mean()) * 100, 1),
        "⑨最大投入比例pct": round(float(投入.max()) * 100, 1),
        "⑨空仓天数占比pct": round(float((投入 < 0.01).mean()) * 100, 1),
    }


# ---------------------------------------------------------------- 主流程
def 跑一份(f: str) -> dict:
    d = pd.read_csv(f)
    if d.empty:
        return {"★跑失败": "流水是空的"}
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("net_pnl", "shares", "entry_price", "r_multiple_net"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    n0 = len(d)
    d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
    # ★★★ 规矩⑰:跳过的要报「跳了多少」+「跳的那批成绩差多少」
    跳 = n0 - len(d)
    if d.empty:
        return {"★跑失败": f"{n0} 笔全部缺关键列"}
    syms = tuple(sorted(set(d["symbol"].astype(str))))
    cl = data.price_panel("close", syms)
    eq, 在场, 缺票 = 逐日净值(d, cl)
    spy = data.load_benchmark("SPY")["close"]
    win = (eq.index >= PERF0) & (eq.index <= PERF1)
    m = 一条指标(eq.loc[win], 在场.loc[win], spy)
    # ★★★ 自证表:同一批流水,只换「离场日那一天怎么记」
    eq旧, _, _ = 逐日净值(d, cl, 旧口径=True)
    m旧 = 一条指标(eq旧.loc[win], 在场.loc[win], spy)
    if "②年化收益pct" in m and "②年化收益pct" in m旧:
        m["★★★第54处错_旧口径对照"] = {
            "旧_年化pct": m旧["②年化收益pct"], "旧_最大回撤pct": m旧["★★★③最大回撤pct"],
            "旧_卡玛": m旧["★★★④卡玛比率"], "旧_溃疡": m旧["★★★⑤溃疡指数"],
            "★读法": "★★ 旧口径在离场日把仓位两头都不算 → 造出假的单日暴跌",
        }
    # ★ 辅助:利润因子(账户百分比口径,★ 降为辅助)
    分母 = eq.reindex(d["entry_date"]).to_numpy()
    ok = np.isfinite(分母) & (分母 > 0)
    pct = pd.Series(np.where(ok, d["net_pnl"].to_numpy() / 分母 * 100.0, np.nan)).dropna()
    赢, 亏 = pct[pct > 0], pct[pct < 0]
    m["辅助_笔数"] = int(len(pct))
    m["辅助_利润因子_账户pct口径"] = (round(float(赢.sum() / abs(亏.sum())), 3)
                             if len(亏) and 亏.sum() != 0 else None)
    m["辅助_胜率"] = round(float((pct > 0).mean()), 4) if len(pct) else None
    if 跳:
        被跳 = pd.read_csv(f)
        m["★⑰跳过笔数"] = int(跳)
    if 缺票:
        m["★⑰面板里没有的票"] = [len(缺票), sorted(缺票)[:5]]
    return m


def main() -> int:
    组 = []
    for p in sorted(glob.glob("engine/ledgers_1030_剔污染/*__剔除版.csv")):
        组.append(("剔污染", os.path.basename(p)[:-len("__剔除版.csv")], p))
    报 = {"★这一份是什么": {
        "来历": "★★ Lin 1106 工单优先级②:买入持有对比**换指标重算**",
        "跑没跑回测": "★★★ 没有 —— 只用已入库流水逐日重建净值",
        "流水来源": "engine/ledgers_1030_剔污染/*__剔除版.csv(★ 剔污染版,不用污染版)",
        "绩效窗口": [str(PERF0.date()), str(PERF1.date())],
        "★★★必读旁注": "★ 回撤类指标(③④⑤⑥)**天然偏向大部分时间空仓的策略** —— "
                  "★★ 必须和⑨平均投入比例并排读;★★★ 投入比例差一个数量级的两行不可直接比。",
        "出处档": {"卡玛比率": "②行业通行(Young 1991)",
                "溃疡指数": "②行业通行(Martin & McCann 1989)",
                "信息比率": "②行业通行(Grinold & Kahn)",
                "Newey-West": "★★★ ⑤外部模型说的·待核(《83》第三步同一条)",
                "回本天数": "③我们的(水下最长连续交易日数)"},
    }}
    失败 = []
    for 族, 名, p in 组:
        try:
            r = 跑一份(p)
        except Exception as e:
            r = {"★跑失败": repr(e)[:300]}
        if "★跑失败" in r:
            失败.append(名)
        报[名] = r
        print(("✗ " if "★跑失败" in r else "✓ ") + 名, flush=True)
    # ★★★ 规矩⑯:失败要大声报
    报["★★★跑失败的"] = {"条数": len(失败), "名单": 失败} if 失败 else {"条数": 0}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "新尺子_报告_1106.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"\n★ 写到 {OUT}/新尺子_报告_1106.json  |  跑失败 {len(失败)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
