# -*- coding: utf-8 -*-
"""《511》第 1 件：同一个行业的单子，限个数有没有用（引擎外，不重跑引擎）。
单子：probe/成绩单_1122/out_手册/流水_一_*.csv（技术类，2015 起），按平仓日 ≤ 2021-12-31 挑；buy_and_hold 不算。
每日净值：同目录 日线_一_*.parquet 的 eq，截到 2021-12-31。
行业：probe/行业_1120 的建表脚本现做（SEC SIC → GICS 11 个一级板块，只有最新分类）；对不上的记「没有行业」。
「不开」一笔单子 = 把它从原净值里减掉：持有期间按每天收盘逐日计价（shares ×（收盘 − 进场价）），平仓那天起按流水里的 net_pnl。
  ⚠ 这是近似：真重跑时，少开一笔会让后面的仓位大小、现金都跟着变，这里没跟着变（等于那笔钱一直放着现金）。
  逐日计价用 并池2004_1107 那份面板的收盘（不含分红）；平仓后按流水的 net_pnl 对齐。先拿「全部单子减回去 ≈ 0」核一遍对得上。
规则：按进场日先后，同一个行业同时最多拿 K 笔（K = 2 / 3 / 4），超了的新单不开。
对照：随机丢同样多的单子，200 次，取中间值。"""
import os, glob, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); SRC = os.path.join(ROOT, "probe/成绩单_1122/out_手册"); OUT = os.path.join(HERE, "out")
截 = pd.Timestamp("2021-12-31"); rng = np.random.default_rng(1128)
行 = pd.read_csv(os.path.join(OUT, "每只票的行业.csv"), encoding="utf-8-sig").set_index("代码")["一级行业"].to_dict()
W = pd.read_parquet(os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet"))
CL = W["close"] if "close" in W.columns.get_level_values(0) else W.xs("close", axis=1, level=0); CL = CL.loc["2014-12-01":截]; del W


def 指标(e):
    y = (e.index[-1] - e.index[0]).days / 365.25; return ((e.iloc[-1] / e.iloc[0]) ** (1 / y) - 1) * 100, ((e / e.cummax()) - 1).min() * 100


def 路径(t, dates):
    """每笔单子对净值的贡献（逐日），trades × dates。"""
    M = np.zeros((len(t), len(dates)), np.float32); pos = {d: i for i, d in enumerate(dates)}; miss = 0
    for k, r in enumerate(t.itertuples()):
        a = dates.searchsorted(r.entry_date); b = dates.searchsorted(r.exit_date)
        if r.symbol in CL.columns:
            px = CL[r.symbol].reindex(dates[a:b]).ffill().to_numpy()
            if np.isnan(px).all(): px = np.full(b - a, r.entry_price); miss += 1
            px = np.where(np.isnan(px), r.entry_price, px); M[k, a:b] = r.shares * (px - r.entry_price)
        else:
            M[k, a:b] = np.linspace(0, r.net_pnl, max(b - a, 1))[: b - a]; miss += 1
        M[k, b:] = r.net_pnl
    return M, miss


def 限(t, K):
    keep = np.ones(len(t), bool); open_ = []   # (exit, industry)
    for k, r in enumerate(t.itertuples()):
        open_ = [x for x in open_ if x[0] > r.entry_date]
        if sum(1 for x in open_ if x[1] == r.行业) >= K: keep[k] = False; continue
        open_.append((r.exit_date, r.行业))
    return keep


if __name__ == "__main__":
    rows, 现状, 核 = [], [], []
    for f in sorted(glob.glob(os.path.join(SRC, "流水_一_*.csv"))):
        名 = os.path.basename(f)[5:-4]
        if 名 == "buy_and_hold": continue
        t = pd.read_csv(f, parse_dates=["entry_date", "exit_date"]); t = t[t.exit_date <= 截].sort_values(["entry_date", "symbol"]).reset_index(drop=True)
        t["行业"] = t.symbol.map(行).fillna("没有行业")
        e = pd.read_parquet(os.path.join(SRC, f"日线_一_{名}.parquet"))["eq"].loc[:截]; dates = e.index
        M, miss = 路径(t, dates); eq0 = e.to_numpy()
        # 核：全部单子的贡献加起来，和净值的变化比（还拿着的单子没算进来，所以只核到最后一个平仓日）
        last = dates.searchsorted(t.exit_date.max()); 核.append(dict(策略=名, 单子=len(t), 对不上价格的=miss, 净值变化=round(eq0[last] - eq0[0]), 单子贡献合计=round(float(M[:, last].sum())), 日变化相关=round(float(np.corrcoef(np.diff(eq0[:last + 1]), np.diff(M[:, :last + 1].sum(0)))[0, 1]), 3)))
        # 现状
        d_open = np.zeros(len(dates), int); 行最多 = 0; 行日 = {}
        for r in t.itertuples():
            a = dates.searchsorted(r.entry_date); b = dates.searchsorted(r.exit_date); d_open[a:b] += 1
            行日.setdefault(r.行业, np.zeros(len(dates), int))[a:b] += 1
        行最多 = max(v.max() for v in 行日.values()); 哪行 = max(行日, key=lambda k: 行日[k].max())
        dpnl = np.diff(M, axis=1, prepend=0); de = np.diff(eq0, prepend=eq0[0]); worst = np.argsort(de)[:20]
        by = pd.DataFrame(dpnl[:, worst].T, columns=t.行业.to_numpy()).T.groupby(level=0).sum().T  # 20 天 × 行业
        亏 = by.clip(upper=0); 最大行占 = float((亏.min(axis=1) / 亏.sum(axis=1).replace(0, np.nan)).mean() * 100)
        stops = t[t.reason == "止损"].copy(); stops["周"] = stops.exit_date.dt.to_period("W"); g = stops.groupby(["行业", "周"]).size()
        现状.append(dict(策略=名, 单子=len(t), 没有行业占比=round((t.行业 == "没有行业").mean() * 100, 1), 同时最多=int(d_open.max()), 同一行业同时最多=int(行最多), 是哪个行业=哪行,
                       最差20天里最大那个行业亏的占比=round(最大行占, 1), 同行业同周一起止损的次数=int((g >= 2).sum()), 其中3笔以上=int((g >= 3).sum())))
        c0, d0 = 指标(e); rows.append(dict(策略=名, 规则="不限", 笔数=len(t), 每年赚=round(c0, 2), 最深亏损=round(d0, 1)))
        for K in (2, 3, 4):
            keep = 限(t, K); nd = int((~keep).sum())
            eqK = pd.Series(eq0 - M[~keep].sum(0), index=dates); cK, dK = 指标(eqK)
            if nd:
                R_ = []
                for _ in range(200):
                    drop = rng.choice(len(t), nd, replace=False); R_.append(指标(pd.Series(eq0 - M[drop].sum(0), index=dates)))
                R_ = np.array(R_); cr, dr = np.median(R_[:, 0]), np.median(R_[:, 1]); 比随机好 = float((R_[:, 1] < dK).mean() * 100)
            else: cr, dr, 比随机好 = c0, d0, None
            rows.append(dict(策略=名, 规则=f"同行业最多 {K} 笔", 笔数=int(keep.sum()), 丢掉=nd, 每年赚=round(cK, 2), 最深亏损=round(dK, 1), 随机丢同样多_每年赚中位=round(cr, 2), 随机丢同样多_最深亏损中位=round(dr, 1),
                             最深亏损比随机浅的比例=None if 比随机好 is None else round(比随机好)))
        print(名, len(t), flush=True)
    pd.DataFrame(核).to_csv(os.path.join(OUT, "核对_单子减回去.csv"), index=False); pd.DataFrame(现状).to_csv(os.path.join(OUT, "行业现状.csv"), index=False)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "行业限个数.csv"), index=False); print("DONE")
