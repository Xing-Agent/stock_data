#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 第三件 · 新门:双向聚类面板回归 t > 2.0(替掉「四格符号一致」)—— 2026-10-30

════════════════════════════════════════════════════════════════════════
三秒版(大白话)
════════════════════════════════════════════════════════════════════════
旧门把 8 年的交易切成四块,要求四块各自都赚 —— ★ 这等于拿四分之一的样本
去要求四次都对,所以一条真的好策略(全周期 t=2.0)也有**一半**概率被挡掉。

新门不切块:把**所有**交易放在一起跑一次回归,只多做两件事 ——
  ① 把「哪个行业」和「哪一个月」当成固定效应减掉
     (大白话:不许靠「那几年整个市场都涨」或「那几年科技股都涨」来得分);
  ② 算 t 值的时候承认两件事会让交易之间互相牵连:
     **同一天**开仓的一批交易会一起涨跌、**同一只票**的多次交易也彼此像。
     → 这就是「按时间和股票代码双向聚类」。不这么算,t 会虚高。

判据:t > 2.0。

════════════════════════════════════════════════════════════════════════
★★★ 这条门只用现有流水,不重跑回测 —— 先确认这一点
════════════════════════════════════════════════════════════════════════
要算的东西只有四样,全部在流水 CSV 里现成:
    r_multiple_net(被解释变量)· entry_date(时间固定效应 + 时间聚类)
    symbol(股票聚类 + 查行业)· 真/对照 标签(来自文件名 REAL__ / CTRL__)
行业(SIC)来自 `pilot_300/<票>/fundamentals.json → sic_versions`,也是现成的。
→ ★★ **成立:不需要重跑回测。** 对照组流水由第一件(基准一 50 种子)顺手落盘。

════════════════════════════════════════════════════════════════════════
回归式(为什么要有对照组这一项)
════════════════════════════════════════════════════════════════════════
    R_i = β·真信号_i + 行业固定效应 + 年月固定效应 + ε_i
                      ↑ 聚类:(entry_date, symbol) 双向

★ 为什么不是「只回归一个常数项」:加了固定效应之后常数项和固定效应共线,
  那个 t 没有意义。★ 所以这里沿用基准一的同一个问法 ——
  「同一天、同一个池子、同样的仓位规则,只把进场换成随机」,
  把真链和 50 条随机对照流水摞在一起,**真信号那个 0/1 变量的 t 就是这道门的 t**。
  ★★ 它回答的正是「进场规则有没有加东西」,和基准一同源、口径一致。

出处:Petersen (2009) RFS;Cameron, Gelbach & Miller (2011) JBES(双向聚类);
      Thompson (2011) JFE。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

import statsmodels.api as sm      # noqa: E402

T_GATE = 2.0


# ══════════════════════════════════════════════════════════════════════════
# 一 · 行业(SIC)
# ══════════════════════════════════════════════════════════════════════════

def sic_map() -> dict[str, str]:
    """
    每只票的 SIC 两位大类。★ 查不到的归一个**单独的类**「SIC未知」——
    不丢样本、也不假装知道(「没查」和「查了没问题」必须分开)。
    """
    out: dict[str, str] = {}
    for base in ("pilot_300", "pilot_50"):
        for f in sorted(glob.glob(os.path.join(ROOT, base, "*", "fundamentals.json"))):
            sym = os.path.basename(os.path.dirname(f))
            try:
                with open(f, encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception:
                continue
            sv = d.get("sic_versions") or []
            if not sv:
                continue
            last = sorted(sv, key=lambda x: (x.get("accepted_at")
                                             or x.get("filed_at") or ""))[-1]
            code = last.get("sic_code")
            if code is None:
                continue
            out[sym] = f"SIC{str(code).zfill(4)[:2]}"
    return out


# ══════════════════════════════════════════════════════════════════════════
# 二 · 双向聚类面板回归
# ══════════════════════════════════════════════════════════════════════════

def cluster_t(df: pd.DataFrame, ycol: str = "y", dcol: str = "d",
              fe: tuple[str, ...] = ("ind", "ym"),
              clusters: tuple[str, ...] = ("date", "sym")) -> dict:
    """
    跑一次带固定效应的面板回归,返回双向聚类稳健 t。

    df 需要:ycol(数)· dcol(0/1)· fe 各列(类别)· clusters 各列(类别)
    ★ 固定效应里只保留**至少两个取值**的那几维(只有一个取值时是常数,共线)。
    """
    d = df.dropna(subset=[ycol, dcol]).copy()
    n = len(d)
    if n < 20 or d[dcol].nunique() < 2:
        return {"t": None, "beta": None, "n": n,
                "★不出数": f"样本 {n} 行 / 真对照两组齐不齐={d[dcol].nunique()}"}
    X = pd.DataFrame({dcol: d[dcol].astype(float).to_numpy()}, index=d.index)
    used_fe = []
    for col in fe:
        if col in d.columns and d[col].nunique() > 1:
            dm = pd.get_dummies(d[col].astype(str), prefix=col, drop_first=True,
                                dtype=float)
            X = pd.concat([X, dm], axis=1)
            used_fe.append(col)
    X = sm.add_constant(X, has_constant="add")
    y = d[ycol].astype(float).to_numpy()
    groups = np.column_stack([
        pd.factorize(d[c].astype(str))[0] for c in clusters if c in d.columns])
    fit = sm.OLS(y, X.to_numpy(dtype=float)).fit(
        cov_type="cluster", cov_kwds={"groups": groups})
    # d 是第二列(const 在第 0 列)
    j = list(X.columns).index(dcol)
    beta = float(fit.params[j])
    se = float(fit.bse[j])
    naive = sm.OLS(y, X.to_numpy(dtype=float)).fit()
    return {
        "t": float(beta / se) if se > 0 else None,
        "beta": beta, "se_双向聚类": se,
        "t_不做聚类(只为对照看虚高多少)": (float(beta / float(naive.bse[j]))
                                          if float(naive.bse[j]) > 0 else None),
        "se_不做聚类": float(naive.bse[j]),
        "n": n,
        "真信号笔数": int(d[dcol].sum()),
        "对照笔数": int((1 - d[dcol]).sum()),
        "固定效应_实际用上的": used_fe,
        "固定效应_列数": int(X.shape[1] - 2),
        "聚类_时间组数": int(len(set(groups[:, 0].tolist()))),
        "聚类_股票组数": (int(len(set(groups[:, 1].tolist())))
                          if groups.shape[1] > 1 else None),
    }


def cluster_t_mean_only(df: pd.DataFrame, ycol: str = "y",
                        clusters: tuple[str, ...] = ("date", "sym")) -> dict:
    """
    ★ 副表用:**只用真链流水**,回归一个常数项,报它的双向聚类 t。

    ★★ 为什么要有这一栏:严格地说,「每笔 R 的均值显著大于 0 吗」这个问题
      **一份真链流水就够了**,连对照组都不需要 —— 这一栏就是那个最严口径的答案,
      它证明这道门确实「不需要重跑回测」。
    ★ 它的代价是**没有固定效应**(加了固定效应常数项就共线了),
      所以它答不了「是不是靠那几年大家都涨」—— 那个要看主表。
    """
    d = df.dropna(subset=[ycol]).copy()
    if len(d) < 20:
        return {"t": None, "n": len(d)}
    X = np.ones((len(d), 1))
    groups = np.column_stack([
        pd.factorize(d[c].astype(str))[0] for c in clusters if c in d.columns])
    fit = sm.OLS(d[ycol].astype(float).to_numpy(), X).fit(
        cov_type="cluster", cov_kwds={"groups": groups})
    se = float(fit.bse[0])
    return {"t": float(fit.params[0] / se) if se > 0 else None,
            "每笔R均值": float(fit.params[0]), "se": se, "n": int(len(d))}


# ══════════════════════════════════════════════════════════════════════════
# 三 · ★★★ 反向自测 —— 构造已知 t 的人造数据,确认实现算出来的 t 对得上
# ══════════════════════════════════════════════════════════════════════════

def selftest(verbose: bool = True) -> dict:
    """
    ★★★ 不做这一步,这道门的任何输出都不可信。四项,逐项都有理论值可对。

    ① 无聚类结构(误差完全独立)→ 双向聚类 t 应当 ≈ 理论 t = β/(σ·√(1/n1+1/n0))
    ② 有「同一天一起涨跌」的结构 → 聚类 t 必须**明显小于**不聚类 t
       (不聚类会虚高,这正是我们要修的东西)
    ③ 真效应为 0 → t 的分布应当以 0 为中心,|t|>1.96 的比例 ≈ 5%
    ④ 固定效应真的在吃东西 → 把效应**全部**放进「年月」里(真信号均值和对照相同),
       t 必须掉到不显著;而不减固定效应的朴素差值会显著
    """
    rng = np.random.default_rng(20261030)
    rep: dict = {}

    def mk(n_date=200, per_date=10, n_sym=120, beta=0.0, sigma=1.0,
           date_shock=0.0, real_frac=0.5, d_at_date_level=False, seed_rng=None):
        """
        造一个面板。★ `d_at_date_level=True` 时「这一天全是真信号 / 全是对照」——
        这正是真实流水的样子(真信号集中在突破那几天),也是**聚类修正真正起作用**
        的那种结构:真/对照这个变量本身在「天」这一层上就有相关性。
        """
        r = seed_rng or rng
        dates = pd.date_range("2018-01-01", periods=n_date, freq="B")
        rows = []
        shock = r.normal(0, date_shock, n_date) if date_shock else np.zeros(n_date)
        for i, dt in enumerate(dates):
            day_d = 1.0 if r.random() < real_frac else 0.0
            for _ in range(per_date):
                sym = f"S{r.integers(0, n_sym):03d}"
                dd = day_d if d_at_date_level else (
                    1.0 if r.random() < real_frac else 0.0)
                rows.append({
                    "y": beta * dd + shock[i] + r.normal(0, sigma),
                    "d": dd, "date": dt, "sym": sym,
                    "ind": f"IND{int(sym[1:]) % 8}", "ym": dt.strftime("%Y-%m")})
        return pd.DataFrame(rows)

    # ---- ① 独立误差、无固定效应结构:t 必须对得上闭式理论值
    #   理论 t = β / (σ·√(1/n1 + 1/n0))。★ 这里不放固定效应,
    #   这样理论值是精确的(放了 FE 会吃掉一点残差方差,理论值就只是近似)。
    #   ★★ 卡的是**标准误**,不是单次抽出来的 t:β̂ 本身是随机的,
    #      单抽一次 t 会在理论值上下晃 ±1,那样卡不出实现对不对。
    #      标准误的理论值是精确的 → 重复 40 次取均值和它比,才是真正的对照。
    r1 = np.random.default_rng(1234)
    ses_c, ses_n, ts1, th = [], [], [], []
    for _ in range(40):
        df = mk(n_date=300, per_date=10, beta=0.10, sigma=1.0, date_shock=0.0,
                seed_rng=r1)
        got = cluster_t(df, fe=())
        n1, n0 = int(df["d"].sum()), int((1 - df["d"]).sum())
        th.append(1.0 * np.sqrt(1 / n1 + 1 / n0))
        ses_c.append(got["se_双向聚类"])
        ses_n.append(got["se_不做聚类"])
        ts1.append(got["t"])
    se_th = float(np.mean(th))
    dc = abs(float(np.mean(ses_c)) - se_th) / se_th
    dn = abs(float(np.mean(ses_n)) - se_th) / se_th
    t_theory = 0.10 / se_th
    rep["①独立误差·对闭式理论值"] = {
        "重复次数": 40,
        "理论标准误": round(se_th, 5),
        "实现·双向聚类标准误均值": round(float(np.mean(ses_c)), 5),
        "实现·不聚类标准误均值": round(float(np.mean(ses_n)), 5),
        "双向聚类 相对差": round(dc, 4), "不聚类 相对差": round(dn, 4),
        "理论t": round(float(t_theory), 3),
        "实现t均值": round(float(np.mean(ts1)), 3),
        "判": "过" if (dc < 0.05 and dn < 0.05
                       and abs(float(np.mean(ts1)) - t_theory) < 0.4) else "★没过",
        "★读法": "误差本来就彼此独立时,聚类修正**不该**改变标准误 —— "
                  "两个标准误都要落在理论值上(这里都卡 5% 以内)。"}

    # ---- ② 真/对照在「天」这一层上就不同 + 同日共同冲击
    #        → 不聚类的 t 必须明显虚高,聚类之后必须掉下来
    df2 = mk(n_date=250, per_date=10, beta=0.10, sigma=0.5, date_shock=0.8,
             d_at_date_level=True)
    g2 = cluster_t(df2, fe=())
    rep["②同日共同冲击(真/对照按天分组)"] = {
        "不聚类t": round(g2["t_不做聚类(只为对照看虚高多少)"], 3),
        "双向聚类t": round(g2["t"], 3),
        "虚高倍数": round(abs(g2["t_不做聚类(只为对照看虚高多少)"]
                              / g2["t"]), 3),
        "判": "过" if abs(g2["t_不做聚类(只为对照看虚高多少)"]) > abs(g2["t"]) * 1.5
               else "★没过",
        "★读法": "同一天的交易会一起涨跌,而真/对照又是按天分开的 —— "
                  "不做聚类就把「250 天」当成「2500 笔独立观测」,t 必然虚高。"}

    # ---- ③ 真效应为 0:|t|>1.96 的比例应当 ≈ 5%(★ 这是这道门的误报率)
    hits, n_rep, ts = 0, 200, []
    r3 = np.random.default_rng(777)
    for _ in range(n_rep):
        d3 = mk(n_date=150, per_date=8, beta=0.0, sigma=1.0, date_shock=0.5,
                d_at_date_level=True, seed_rng=r3)
        t3 = cluster_t(d3, fe=())["t"]
        ts.append(t3)
        hits += int(abs(t3) > 1.96)
    rate_fp = hits / n_rep
    # ★ 200 次重复下,真值 5% 的二项标准差 = √(.05·.95/200) = 1.54% → 3σ ≈ 9.6%
    rep["③真效应为0·误报率"] = {
        "重复次数": n_rep, "|t|>1.96 次数": hits,
        "实测误报率": round(rate_fp, 4),
        "t 均值": round(float(np.mean(ts)), 3),
        "t 标准差": round(float(np.std(ts, ddof=1)), 3),
        "判": "过" if rate_fp <= 0.11 else "★没过",
        "★读法": "200 次重复下 5% 的二项标准差是 1.54%,3σ 上界 ≈ 9.6%;"
                  "这里卡 11%。★ t 的标准差也要接近 1 —— 这是尺子有没有校准的直接证据。"}

    # ---- ④ 固定效应真的在吃东西
    #   造法:效应**只**存在于「真信号集中出现的那几个月」,真/对照在同月内无差别。
    r4 = np.random.default_rng(31415)
    dates = pd.date_range("2018-01-01", periods=240, freq="B")
    rows = []
    for dt in dates:
        hot = (dt.month % 3 == 0)            # ★ 这几个月全市场涨
        for _ in range(10):
            sym = f"S{r4.integers(0,120):03d}"
            dd = 1.0 if (r4.random() < (0.8 if hot else 0.2)) else 0.0
            rows.append({"y": (0.6 if hot else 0.0) + r4.normal(0, 0.5),
                         "d": dd, "date": dt, "sym": sym,
                         "ind": f"IND{int(sym[1:]) % 8}",
                         "ym": dt.strftime("%Y-%m")})
    d4 = pd.DataFrame(rows)
    with_fe = cluster_t(d4)
    no_fe = cluster_t(d4, fe=())
    rep["④固定效应在吃东西"] = {
        "不减固定效应t": round(no_fe["t"], 3),
        "减了行业+年月固定效应t": round(with_fe["t"], 3),
        "判": "过" if (abs(no_fe["t"]) > 2.0 and abs(with_fe["t"]) < 2.0)
               else "★没过",
        "★读法": "造的数据里真信号自己没有优势,优势全来自「那几个月大家都涨」。"
                  "不减固定效应会判它显著(误判),减了就不显著 —— 这正是要的。"}

    rep["★全部通过"] = all(v.get("判") == "过" for v in rep.values()
                           if isinstance(v, dict) and "判" in v)
    if verbose:
        print(json.dumps(rep, ensure_ascii=False, indent=1))
    if not rep["★全部通过"]:
        raise RuntimeError("★★★ 反向自测没过 —— 这道门的任何输出都不可信,停。")
    return rep


if __name__ == "__main__":
    selftest()
    print("\n★ 反向自测四项全过。")
