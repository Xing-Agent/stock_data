# -*- coding: utf-8 -*-
"""《571》第五批 · 财报（《527 拍板》第 2 条）· 引擎外 · 只读现成流水 + 本地缓存的日线
流水 = 成绩单_1122 里 34 个技术类策略版本 2015 年起的单子，按平仓日 ≤ 2021-12-31 挑（2022 年以后封存）。全是做多，没有空单。
财报日 = SEC 8-K 2.02 主公告的「首个可交易日」（effective_trade_date，2014 起）。「财报前一天」= 它前一个交易日。
「财报公布那一刻手里有这只票」= 进场日 ≤ 财报前一天，且平仓日 ≥ 财报首个可交易日（《527》工程第 3 件的新口径）。
规则（拍板原文，另试的档位都跑）：
  A 新开单：进场日到下一次财报首个可交易日隔 1..N 个交易日（N = 3，另试 1、5）的不开。
  B 手上的单子，财报前一天收盘：
     已经到过第一目标的 → 只留 q（25%，另试 0%、50%），其余按那天收盘平；
     没到过、浮盈不到 +k R（k = 1，另试 0.5、1.5）→ 按那天收盘全平；
     其余不动。
  ★「第一目标」我们的 34 个策略里都没有，这里取「进场后最高价碰到过 进场价 + 1.5 倍风险」（另试 1.0、2.0 倍）。拍板第 7 条 A 组用的就是 1.5R。
  一笔单子碰到不止一次财报：按顺序逐次套；已经减到 q 的不再减。平掉的那部分成本按 5 个基点单边扣（和引擎一样）。
报：每个策略加规则前后的 每笔平均 R、亏超过 1.5R 的占比、按同样风险累计的最深亏损（R）；少开 / 提前平掉的单子里本来会赚的有多少。
误差：同一天发财报的单子归成一组（按财报首个可交易日分组），用分组的标准误。"""
import os, sys, glob, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
CACHE = os.environ.get("XING_CACHE", "/tmp/w"); A = os.path.join(ROOT, "probe/成绩单_1122/out_手册/")
封 = pd.Timestamp("2021-12-31"); BPS = 5e-4

W = pd.read_parquet(os.path.join(CACHE, "股票日线_一.parquet")); Cl = W["close"]; Hi = W["high"]; del W
日 = Cl.index; pos = {d: i for i, d in enumerate(日)}
cal = pd.read_csv(os.path.join(ROOT, "probe/fund_expand_1103/earnings_calendar_8k202_1103.csv.gz"), usecols=["symbols", "effective_trade_date", "is_main_release"])
cal = cal[cal.is_main_release.astype(str).str.lower() == "true"]; cal["d"] = pd.to_datetime(cal.effective_trade_date)
cal = cal[cal.d <= 封 + pd.Timedelta(days=10)]
EI = {}   # 每只票：财报首个可交易日在交易日历上的位置（落在非交易日就往后挪到下一个交易日）
for s, g in cal.groupby("symbols"):
    k = np.unique(np.searchsorted(日.values, g.d.values.astype("datetime64[ns]")))
    EI[s] = k[k < len(日)]

L = []
for f in sorted(glob.glob(A + "流水_一_*.csv")):
    nm = os.path.basename(f)[5:-4]
    if nm.startswith("buy_and_hold"): continue
    t = pd.read_csv(f, parse_dates=["entry_date", "exit_date"]); t = t[t.exit_date <= 封]; t["策略"] = nm; L.append(t)
T = pd.concat(L, ignore_index=True)
去掉 = int(T.r_multiple_net.isna().sum()); T = T[T.r_multiple_net.notna()].reset_index(drop=True)   # 止损距离几乎为 0、引擎算不出 R 的 10 笔
assert (T.shares > 0).all()
T["有日历"] = T.symbol.isin(EI.keys()) & T.symbol.isin(Cl.columns)
T["ei"] = T.entry_date.map(pos); T["xi"] = T.exit_date.map(pos)
T["成本R"] = T.r_multiple - T.r_multiple_net
print("去掉算不出R的", 去掉, "单子", len(T), "策略", T.策略.nunique(), "有财报日历的", int(T.有日历.sum()), "进场", T.entry_date.min().date(), "~", T.entry_date.max().date())


def 下一财报(s, ei):
    e = EI.get(s)
    if e is None: return []
    return e[e >= ei]


def 套规则(T, N=3, k=1.0, q=0.25, 目标=1.5, 用A=True, 用B=True):
    """返回每笔：新 R（被 A 拦掉的 = nan）、是否被 A 拦、是否被 B 动过、被 B 动的那次财报日。"""
    n = len(T); newR = T.r_multiple_net.to_numpy().copy(); 拦 = np.zeros(n, bool); 动 = np.zeros(n, bool); 哪天 = np.full(n, -1)
    for j, r in enumerate(T.itertuples()):
        if not r.有日历 or np.isnan(r.ei) or np.isnan(r.xi): continue
        ei, xi = int(r.ei), int(r.xi); ev = 下一财报(r.symbol, ei)
        if 用A and len(ev) and 1 <= ev[0] - ei <= N:
            拦[j] = True; newR[j] = np.nan; continue
        if not 用B: continue
        f = 1.0; got = 0.0; 减过 = False; c_ = Cl[r.symbol].to_numpy(); h_ = Hi[r.symbol].to_numpy(); E = r.entry_price; Rps = r.risk_per_share
        for e in ev:
            a = e - 1                           # 财报前一天
            if a < ei or e > xi: continue       # 进场前 / 已经平了
            fl = (c_[a] - E) / Rps; 到过 = np.nanmax(h_[ei:a + 1]) >= E + 目标 * Rps
            if 到过 and not 减过:
                卖 = f * (1 - q); got += 卖 * (fl - E * BPS * 2 / Rps); f -= 卖; 减过 = True; 动[j] = True; 哪天[j] = e if 哪天[j] < 0 else 哪天[j]
            elif (not 到过) and fl < k:
                got += f * (fl - E * BPS * 2 / Rps); f = 0.0; 动[j] = True; 哪天[j] = e if 哪天[j] < 0 else 哪天[j]
            if f <= 0: break
        if 动[j]: newR[j] = got + f * r.r_multiple_net
    return newR, 拦, 动, 哪天


def 最深(R, d):
    o = np.argsort(d.values, kind="stable"); cum = np.concatenate([[0], np.cumsum(R[o])]); return float((np.maximum.accumulate(cum) - cum).max())


def 每策略(T, newR):
    rows = []
    for s, g in T.groupby("策略"):
        o = g.r_multiple_net.to_numpy(); m = newR[g.index]; k = ~np.isnan(m)
        rows.append(dict(策略=s, 原笔数=len(o), 新笔数=int(k.sum()), 原每笔R=o.mean(), 新每笔R=m[k].mean(), 原亏超15R占比=(o < -1.5).mean() * 100, 新亏超15R占比=(m[k] < -1.5).mean() * 100,
                         原最深R=最深(o, g.exit_date), 新最深R=最深(m[k], g.exit_date[k]), 原合计R=o.sum(), 新合计R=m[k].sum()))
    return pd.DataFrame(rows)


def 分组误差(d, 组):
    """d = 每笔的变化，组 = 财报日（同一天归一组）。返回平均值和分组标准误。"""
    d = np.asarray(d, float); n = len(d)
    if n < 2: return np.nan, np.nan
    e = d - d.mean(); s = pd.Series(e).groupby(np.asarray(组)).sum().to_numpy()
    G = len(s); se = np.sqrt((s ** 2).sum() * G / max(G - 1, 1)) / n
    return float(d.mean()), float(se)


if __name__ == "__main__":
    res = {"口径": dict(单子=len(T), 策略=int(T.策略.nunique()), 有日历=int(T.有日历.sum()), 进场起=str(T.entry_date.min().date()), 进场止=str(T.entry_date.max().date()))}
    # 一、新口径分组：财报公布那一刻手里有没有
    held = np.zeros(len(T), bool); evd = np.full(len(T), -1)
    for j, r in enumerate(T.itertuples()):
        if not r.有日历: continue
        ev = 下一财报(r.symbol, int(r.ei))
        ev = ev[(ev - 1 >= r.ei) & (ev <= r.xi)]
        if len(ev): held[j] = True; evd[j] = ev[0]
    T["拿着过财报"] = held; T["财报日"] = evd
    def 概(x):
        r = x.r_multiple_net; return dict(笔数=len(x), 每笔R=round(r.mean(), 3), 赚钱笔占比=round((r > 0).mean() * 100, 1), 亏超15R占比=round((r < -1.5).mean() * 100, 2),
                                          跳空打穿止损占比=round(x.gap_through.astype(str).str.lower().eq("true").mean() * 100, 2), 持仓天中位=int(x.holding_days.median()))
    X = T[T.有日历]
    res["一_新口径分组"] = {"财报公布时拿着": 概(X[X.拿着过财报]), "没拿着过财报": 概(X[~X.拿着过财报])}
    for a, b in (("2015", "2018"), ("2019", "2021")):
        y = X[(X.entry_date >= a) & (X.entry_date <= b + "-12-31")]
        res["一_新口径分组"][f"{a}–{b}"] = {"拿着": 概(y[y.拿着过财报]), "没拿着": 概(y[~y.拿着过财报])}
    tail = (X.r_multiple_net < -1.5).astype(float)
    m1, se1 = 分组误差(tail[X.拿着过财报].to_numpy() * 100, X.财报日[X.拿着过财报].to_numpy())
    res["一_新口径分组"]["拿着那组亏超15R占比_分组标准误"] = dict(平均=round(m1, 2), 标准误=round(se1, 2), 财报日组数=int(X[X.拿着过财报].财报日.nunique()))
    # 二、规则
    档 = [("默认 N3 k1 q25 目标1.5", {}), ("N1", dict(N=1)), ("N5", dict(N=5)), ("k0.5", dict(k=0.5)), ("k1.5", dict(k=1.5)), ("q0", dict(q=0.0)), ("q50", dict(q=0.5)),
         ("目标1.0R", dict(目标=1.0)), ("目标2.0R", dict(目标=2.0)), ("只A", dict(用B=False)), ("只B", dict(用A=False))]
    for N_, kw in 档:
        newR, 拦, 动, 哪天 = 套规则(T, **kw); P = 每策略(T, newR)
        o = T.r_multiple_net.to_numpy(); k = ~np.isnan(newR)
        d = dict(被A拦掉的笔数=int(拦.sum()), 被拦里本来会赚的=int((o[拦] > 0).sum()), 被拦的本来每笔R=round(float(o[拦].mean()), 3) if 拦.any() else None,
                 被B动过的笔数=int(动.sum()), 被B动里本来会赚的=int((o[动] > 0).sum()), 被B动里原来亏超15R的=int((o[动] < -1.5).sum()), 被B动后亏超15R的=int((newR[动] < -1.5).sum()), 其中提前平反而少赚的=int((o[动] > newR[动]).sum()), 其中提前平少亏了的=int((o[动] < newR[动]).sum()),
                 被B动的本来每笔R=round(float(o[动].mean()), 3) if 动.any() else None, 被B动的新每笔R=round(float(newR[动].mean()), 3) if 动.any() else None,
                 全部_原每笔R=round(float(o.mean()), 4), 全部_新每笔R=round(float(newR[k].mean()), 4), 全部_原亏超15R占比=round(float((o < -1.5).mean() * 100), 2), 全部_新亏超15R占比=round(float((newR[k] < -1.5).mean() * 100), 2),
                 策略里每笔R变好的个数=int((P.新每笔R > P.原每笔R).sum()), 策略里最深亏损变浅的个数=int((P.新最深R < P.原最深R).sum()),
                 每笔R变化_34策略中位=round(float((P.新每笔R - P.原每笔R).median()), 4), 亏超15R占比变化_34策略中位=round(float((P.新亏超15R占比 - P.原亏超15R占比).median()), 2),
                 最深亏损R变化_34策略中位=round(float((P.新最深R - P.原最深R).median()), 2), 合计R变化_34策略中位=round(float((P.新合计R - P.原合计R).median()), 1))
        if 动.any():
            mm, se = 分组误差(newR[动] - o[动], 哪天[动]); d["被B动的每笔R变化_分组标准误"] = dict(平均=round(mm, 3), 标准误=round(se, 3), 财报日组数=int(len(set(哪天[动]))))
        for a, b in (("2015", "2018"), ("2019", "2021")):
            w = ((T.entry_date >= a) & (T.entry_date <= b + "-12-31")).to_numpy()
            d[f"{a}–{b}"] = dict(原每笔R=round(float(o[w].mean()), 4), 新每笔R=round(float(newR[w & k].mean()), 4), 原亏超15R=round(float((o[w] < -1.5).mean() * 100), 2), 新亏超15R=round(float((newR[w & k] < -1.5).mean() * 100), 2))
        res[N_] = d
        if N_.startswith("默认"): P.round(3).to_csv(os.path.join(OUT, "财报_默认_每个策略.csv"), index=False)
        print(N_, {k_: d[k_] for k_ in list(d)[:12]}, flush=True)
    json.dump(res, open(os.path.join(OUT, "财报规则_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
