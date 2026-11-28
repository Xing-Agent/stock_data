# -*- coding: utf-8 -*-
"""《533》第一批：① 资金槽位（最多同时 8 只、先到先做）；② 随机抽一半票、抽 1,000 次。引擎外，不重跑引擎。
单子：probe/成绩单_1122/ 原来那次的流水（第一段 out_手册/流水_一_*，第二段用修过坏点的 out_手册_修/流水_二_*，缺的回退原版）。
槽位口径（我定的，写明）：
  · 每只票占一个槽，最多 8 个；新单进场那天，用前一天收盘的总资金 ÷ 8 当这一笔的本钱（现金不够就用剩下的现金）；不加仓、不按风险定大小。
    —— 这和原来引擎的仓位大小不一样（原来按每笔风险 / 波动算，同时最多常常 10 只以上），所以是「换了一种仓位算法」，不只是「少开几笔」。
  · 同一天来了好几个信号：默认按进场那天的 20 日成交额从大到小；另试随机排 20 次取中间值。
    ⚠ 不能用流水里的先后：流水是按平仓日排的（同一天进场的，先平的排前面），用它排等于偷看了谁先走——第一版就这么错了，已改。
  · 持有期间按每天收盘计价（收盘 ÷ 进场价），平仓那天按流水里的扣费后收益（net_pnl ÷ notional_in）落袋；现金不计利息。
  · 第一段：净值截到 2021-12-31；2021 年底还拿着的仓位按当天收盘计价，不算进笔数（同主 chat 改过的口径：按平仓日挑）。
随机抽：每次从研发池全部票里随机抽一半，只留这些票的单子，再按 8 个槽位重算；1,000 次，报 5%/25%/50%/75%/95% 分位。四类各挑一条代表。"""
import os, sys, glob, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
A = os.path.join(ROOT, "probe/成绩单_1122/out_手册"); B = os.path.join(ROOT, "probe/成绩单_1122/out_手册_修")
HOLD = json.load(open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
代表 = {"趋势跟随": "trend_following", "突破": "技-5-XING", "均值回归": "技-12", "假突破反手": "技-11-XING"}
_CL = {}


def 收盘(seg):
    if seg not in _CL:
        f = os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet" if seg == "一" else "probe/并池2004_1107/ohlcv_panel_newpool.parquet")
        W = pd.read_parquet(f); C = W.xs("close", axis=1, level=0); C = C.loc["2014-12-01":"2021-12-31"] if seg == "一" else C.loc["2004-06-01":"2014-12-31"]; _CL[seg] = C.astype("float32")
    return _CL[seg]


def 准备(name, seg):
    d = B if seg == "二" and os.path.exists(os.path.join(B, f"流水_二_{name}.csv")) else A
    t = pd.read_csv(os.path.join(d, f"流水_{seg}_{name}.csv"), parse_dates=["entry_date", "exit_date"]); t = t.reset_index().rename(columns={"index": "原序"})
    e = pd.read_parquet(os.path.join(d, f"日线_{seg}_{name}.parquet"))["eq"]
    if seg == "一": e = e[:"2021-12-31"]
    dates = e.index; C = 收盘(seg); t = t[t.entry_date <= dates[-1]].copy()
    a = dates.searchsorted(t.entry_date.to_numpy()); b = dates.searchsorted(t.exit_date.to_numpy()); 平了 = t.exit_date.to_numpy() <= dates[-1]
    b = np.where(平了, b, len(dates) - 1)
    paths = []
    for k, r in enumerate(t.itertuples()):
        if r.symbol in C.columns:
            px = C[r.symbol].reindex(dates[a[k]:b[k] + 1]).ffill().to_numpy(dtype=float)
            m = np.where(np.isnan(px), 1.0, px / r.entry_price)
        else: m = np.ones(b[k] - a[k] + 1)
        if 平了[k]: m[-1] = 1 + r.net_pnl / r.notional_in
        paths.append(m)
    t["a"], t["b"], t["平了"] = a, b, 平了; t["ret"] = t.net_pnl / t.notional_in
    return t.reset_index(drop=True), paths, dates, e


def 模拟(t, paths, n, cap=8, 序=None, 选=None):
    """返回 (每日净值 np.array, 进场了的单子下标)。序 = 同一天的先后键；选 = 布尔数组，哪些单子可用。"""
    idx = np.arange(len(t)) if 选 is None else np.where(选)[0]
    key = -t.adv20_at_entry.fillna(0).to_numpy() if 序 is None else 序          # 默认：当天成交额大的先做（进场那天就知道的数）。⚠ 不能用流水里的先后：流水是按平仓日排的，用它等于先挑走得快的单子
    order = idx[np.lexsort((key[idx], t.a.to_numpy()[idx]))]
    by_a = {}
    for k in order: by_a.setdefault(int(t.a.iat[k]), []).append(k)
    bb = t.b.to_numpy(); cash = 1.0; open_ = []; eq = np.empty(n); 仓 = np.zeros(n); prev = 1.0; taken = []
    for d in range(n):
        keep = []
        for (k, al) in open_:
            if bb[k] == d and t.平了.iat[k]: cash += al * paths[k][-1]
            else: keep.append((k, al))
        open_ = keep
        for k in by_a.get(d, ()):
            if len(open_) >= cap: continue
            al = min(prev / cap, cash)
            if al <= 0: continue
            cash -= al; open_.append((k, al)); taken.append(k)
            if bb[k] == d and t.平了.iat[k]: cash += al * paths[k][-1]; open_.pop()
        v = cash + sum(al * paths[k][d - t.a.iat[k]] for k, al in open_)
        eq[d] = v; prev = v; 仓[d] = 1 - cash / v if v > 0 else 0
    模拟.仓位 = 仓
    return eq, taken


def 指标(eq, dates, t, taken):
    yrs = (dates[-1] - dates[0]).days / 365.25; tk = t.loc[taken]; 平 = tk[tk.平了]
    w = 平.ret[平.ret > 0].sum(); lo = -平.ret[平.ret < 0].sum()
    return dict(每年赚=round((eq[-1] ** (1 / yrs) - 1) * 100, 2), 最深亏损=round((eq / np.maximum.accumulate(eq) - 1).min() * 100, 1), 笔数=len(平), 截止时还拿着=int((~tk.平了).sum()),
                每笔平均R=round(平.r_multiple_net.mean(), 2) if len(平) else None, 赚钱笔占比=round((平.r_multiple_net > 0).mean() * 100, 1) if len(平) else None, 利润因子=round(w / lo, 2) if lo > 0 else None)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "槽位"
    names = sorted({os.path.basename(f)[5:-4] for f in glob.glob(os.path.join(A, "流水_一_*.csv"))})
    rng = np.random.default_rng(533)
    if which == "槽位":
        rows = []; f_out = os.path.join(OUT, "槽位8只.csv"); done = set()
        if os.path.exists(f_out): done = set(map(tuple, pd.read_csv(f_out)[["策略", "段"]].values))
        for seg in ("一", "二"):
            for nm in names:
                if (nm, "2015-2021" if seg == "一" else "2005-2014") in done: continue
                t, P, dates, e = 准备(nm, seg); n = len(dates)
                eq, tk = 模拟(t, P, n); r = dict(策略=nm, 段="2015-2021" if seg == "一" else "2005-2014", 同时最多=0, **{f"8只_{k}": v for k, v in 指标(eq, dates, t, tk).items()})
                # 原来同时最多拿几只
                cnt = np.zeros(n, int)
                for k in range(len(t)): cnt[t.a.iat[k]:t.b.iat[k] + (0 if t.平了.iat[k] else 1)] += 1
                r["同时最多"] = int(cnt.max()); r["8只_平均仓位pct"] = round(float(模拟.仓位.mean()) * 100, 1) if False else None
                _, _ = 模拟(t, P, n); 仓a = 模拟.仓位.mean()
                # 另一版：仓位大小照原来引擎的，只是第 9 只起不开（从原净值里把没开的单子减掉，同《512》的近似）
                eqo = e.to_numpy(float); sub = np.zeros(n); 没开 = sorted(set(range(len(t))) - set(tk))
                for k in 没开:
                    nv = t.notional_in.iat[k]; sub[t.a.iat[k]:t.a.iat[k] + len(P[k])] += nv * (P[k] - 1)
                    if t.平了.iat[k] and t.b.iat[k] + 1 < n: sub[t.b.iat[k] + 1:] += t.net_pnl.iat[k]
                eqb = (eqo - sub) / eqo[0]; mb = 指标(eqb, dates, t, tk)
                r.update({"8只_平均仓位pct": round(float(仓a) * 100, 1), "原仓位只限8只_每年赚": mb["每年赚"], "原仓位只限8只_最深亏损": mb["最深亏损"], "没开的笔数": len(没开)})
                rs = []
                for _ in range(20):
                    eq2, tk2 = 模拟(t, P, n, 序=rng.random(len(t))); rs.append(指标(eq2, dates, t, tk2))
                r["随机排_每年赚中位"] = float(np.median([x["每年赚"] for x in rs])); r["随机排_最深亏损中位"] = float(np.median([x["最深亏损"] for x in rs])); r["随机排_每年赚范围"] = f"{min(x['每年赚'] for x in rs)} ~ {max(x['每年赚'] for x in rs)}"
                pd.DataFrame([r]).to_csv(f_out, mode="a", header=not os.path.exists(f_out), index=False); print(seg, nm, r["8只_每年赚"], r["8只_最深亏损"], flush=True)
    if which == "抽样":
        rows = []
        pool = {"一": list(HOLD["研发池名单"])}
        for 类, nm in 代表.items():
            for seg in ("一", "二"):
                t, P, dates, e = 准备(nm, seg); n = len(dates)
                syms = pool["一"] if seg == "一" else sorted(set(t.symbol) | set(pool["一"]))
                sy = t.symbol.to_numpy(); res = []
                for it in range(1000):
                    pick = set(rng.choice(syms, len(syms) // 2, replace=False)); sel = np.fromiter((s in pick for s in sy), bool, len(sy))
                    eq, tk = 模拟(t, P, n, 选=sel); m = 指标(eq, dates, t, tk); res.append((m["每年赚"], m["最深亏损"], m["笔数"]))
                R = np.array(res, float); q = lambda c: [round(float(np.percentile(R[:, c], p)), 2) for p in (5, 25, 50, 75, 95)]
                rows.append(dict(类=类, 策略=nm, 段="2015-2021" if seg == "一" else "2005-2014", 次数=1000, 每年赚_5_25_50_75_95=q(0), 最深亏损_5_25_50_75_95=q(1), 笔数_5_50_95=[int(np.percentile(R[:, 2], p)) for p in (5, 50, 95)]))
                print(rows[-1], flush=True); np.save(os.path.join(OUT, f"抽样_{nm}_{seg}.npy"), R)
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "抽样1000次.csv"), index=False)
    print("DONE")
