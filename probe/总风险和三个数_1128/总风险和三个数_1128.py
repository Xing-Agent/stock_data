# -*- coding: utf-8 -*-
"""《533》第六批 · 拍板第 8 条：总风险上限 + 报成绩三个数 + 期末浮盈单列 + 八折强平。引擎外，不重跑引擎。
单子、价格路径、同一天先后：全部照第一批 probe/槽位和抽样_1128/槽位和抽样_1128.py（直接 import 它的 准备()）。

口径（我定的，写明）：
  · 每笔风险 1R = 前一天收盘总资金的 1%。本钱 = 1R ÷ (进场价到初始止损的距离 ÷ 进场价)，单只本钱最多总资金的 1/4，现金不够用剩下的。
    —— 第一批是「每只八分之一资金」，不按风险定大小；这里改成按风险定，才谈得上「加起来几个 R」。
  · 技-2、技-12 流水里没有止损：名义风险用进场那天的 2 倍 ATR(20) 代替（只用来定仓位和算占几个 R，出场照流水不动）。
  · 最多同时 8 只（同第一批）。
  · 总风险上限：所有「还没保本」的单子，进场时的风险（以 R 计）加起来 ≤ 上限；超了新单不开。上限 3R，另试 2R、4R、不设。
    「保本」= 进场以后某天收盘已经离进场价至少 1 倍初始风险（流水里没有每天的止损位，用这个近似，写明）。保本后不占额度。
    当天进场判断用的是前一天收盘时的保本状态（不偷看当天）。
  · 只做多（这 34 个版本全是做多）；美股、加密合在一起算这一条没做：这批没有加密单子。
三个数：① 每笔净 R 的中位数（旁边并列平均数）；② 去掉总赚钱最多的 2% 的票（按这一版里每只票合计赚的钱排）之后重算的每年赚；
        ③ 随机抽一半票、1,000 次的每年赚 25%~75%（同第一批的抽法，只是换成这里的仓位口径）。
期末浮盈：期末还拿着的仓位，按最后一天收盘算的浮动盈亏，占期末总资金的比例，单独一行；
  八折强平 · 甲：期末所有还拿着的仓位按市值八折卖掉（字面意思）；八折强平 · 乙：只把浮盈打八折（浮亏照算）。两种都报；打完变成整段亏钱的单独标出。"""
import os, sys, glob, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
sp = importlib.util.spec_from_file_location("S1", os.path.join(ROOT, "probe/槽位和抽样_1128/槽位和抽样_1128.py")); S1 = importlib.util.module_from_spec(sp); sp.loader.exec_module(S1)
R_PCT = 0.01; 单只上限 = 0.25; CAP_N = 8
_HL = {}


def atr20(seg):
    if seg not in _HL:
        f = os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet" if seg == "一" else "probe/并池2004_1107/ohlcv_panel_newpool.parquet")
        W = pd.read_parquet(f); H, L, C = (W.xs(x, axis=1, level=0).astype("float32") for x in ("high", "low", "close"))
        pc = C.shift(1); tr = np.maximum(H - L, np.maximum((H - pc).abs(), (L - pc).abs())); _HL[seg] = tr.rolling(20, min_periods=10).mean()
    return _HL[seg]


def 风险比例(t, seg):
    rf = (t.risk_per_share / t.entry_price).to_numpy(float)
    bad = (t.initial_stop.to_numpy(float) <= 0) | (rf >= 0.999)
    if bad.any():
        A = atr20(seg); v = np.full(len(t), np.nan)
        for k in np.where(bad)[0]:
            s, d = t.symbol.iat[k], t.entry_date.iat[k]
            if s in A.columns:
                col = A[s]; i = col.index.searchsorted(d) - 1          # 进场前一天的 ATR
                if i >= 0: v[k] = 2 * col.iat[i] / t.entry_price.iat[k]
        rf = np.where(bad, v, rf); rf = np.where(np.isnan(rf), np.nanmedian(rf), rf)
    return np.clip(rf, 0.003, 0.9)


def 模拟(t, paths, n, rf, cap_r=3.0, 选=None, 序=None):
    idx = np.arange(len(t)) if 选 is None else np.where(选)[0]
    key = -t.adv20_at_entry.fillna(0).to_numpy() if 序 is None else 序
    aa = t.a.to_numpy(); bb = t.b.to_numpy(); 平 = t.平了.to_numpy()
    order = idx[np.lexsort((key[idx], aa[idx]))]; by_a = {}
    for k in order: by_a.setdefault(int(aa[k]), []).append(k)
    本钱 = {}; cash = 1.0; prev = 1.0; open_ = []; eq = np.empty(n); 在场 = np.zeros(n); 占R = np.zeros(n); taken = []; 拦 = 0
    for d in range(n):
        keep = []
        for p in open_:
            k = p[0]
            if bb[k] == d and 平[k]: cash += p[1] * paths[k][-1]
            else: keep.append(p)
        open_ = keep
        for k in by_a.get(d, ()):
            if len(open_) >= CAP_N: continue
            用 = sum(p[2] for p in open_ if not p[3])
            if cap_r is not None and 用 + 1.0 > cap_r + 1e-9: 拦 += 1; continue
            al = min(R_PCT * prev / rf[k], 单只上限 * prev, cash)
            if al <= 0: continue
            r_units = al * rf[k] / (R_PCT * prev); cash -= al; taken.append(k); 本钱[k] = al
            if bb[k] == d and 平[k]: cash += al * paths[k][-1]; continue
            open_.append([k, al, r_units, False])
        v = cash
        for p in open_:
            k = p[0]; m = paths[k][d - aa[k]]; v += p[1] * m
            if m >= 1 + rf[k]: p[3] = True                               # 今天收盘后才算保本，明天进场判断才用
        eq[d] = v; prev = v; 在场[d] = 1 - cash / v if v > 0 else 0; 占R[d] = sum(p[2] for p in open_ if not p[3])
    期末 = [(p[0], p[1], paths[p[0]][n - 1 - aa[p[0]]]) for p in open_]
    return eq, taken, dict(在场=在场, 占R=占R, 期末=期末, 拦=拦, 现金=cash, 本钱=本钱)


def 年化(v, yrs): return round((max(v, 1e-9) ** (1 / yrs) - 1) * 100, 2)


def 一组(nm, seg, 抽=0, rng=None):
    t, P, dates, e = S1.准备(nm, seg); n = len(dates); rf = 风险比例(t, seg); yrs = (dates[-1] - dates[0]).days / 365.25
    段 = "2015-2021" if seg == "一" else "2005-2014"; rows = []
    for cap in (None, 4.0, 3.0, 2.0):
        eq, tk, X = 模拟(t, P, n, rf, cap); m = S1.指标(eq, dates, t, tk); tkd = t.loc[tk]; 平单 = tkd[tkd.平了]
        Rk = t.ret.to_numpy(float) / rf                                   # 每笔 R 统一按「净收益 ÷ 名义风险」算（技-2、技-12 用 2 倍 ATR）
        浮 = sum(al * (mm - 1) for _, al, mm in X["期末"]); 市值 = sum(al * mm for _, al, mm in X["期末"])
        甲 = X["现金"] + 0.8 * 市值; 乙 = X["现金"] + sum(al * (1 + (0.8 if mm > 1 else 1.0) * (mm - 1)) for _, al, mm in X["期末"])
        r = dict(策略=nm, 段=段, 总风险上限="不设" if cap is None else f"{cap:g}R", 每年赚=m["每年赚"], 最深亏损=m["最深亏损"], 笔数=m["笔数"], 赚钱笔占比=m["赚钱笔占比"], 利润因子=m["利润因子"],
                 每笔R_平均=round(float(Rk[平单.index].mean()), 3) if len(平单) else None, 每笔R_中位=round(float(np.median(Rk[平单.index])), 3) if len(平单) else None,
                 因上限没开=X["拦"], 平均在场资金pct=round(float(X["在场"].mean()) * 100, 1), 未保本风险_平均R=round(float(X["占R"].mean()), 2), 未保本风险_最高R=round(float(X["占R"].max()), 2),
                 期末还拿着=len(X["期末"]), 期末浮盈占期末资金pct=round(浮 / eq[-1] * 100, 1) if eq[-1] > 0 else None,
                 不含浮盈_每年赚=年化(eq[-1] - 浮, yrs), 八折甲_每年赚=年化(甲, yrs), 八折甲_整段=round((甲 - 1) * 100, 1), 八折乙_每年赚=年化(乙, yrs), 八折乙_整段=round((乙 - 1) * 100, 1))
        # 去掉最好 2% 的票
        if len(tkd):
            pnl = {}
            for k, al in X["本钱"].items():                                   # 每只票在这一版里实际赚的钱（期末没平的按最后收盘）
                mm = P[k][-1] if t.平了.iat[k] else P[k][n - 1 - t.a.iat[k]]
                pnl[t.symbol.iat[k]] = pnl.get(t.symbol.iat[k], 0.0) + al * (mm - 1)
            syms = sorted(pnl, key=pnl.get, reverse=True); 去 = set(syms[:max(1, int(round(len(syms) * 0.02)))])
            sel = ~t.symbol.isin(去).to_numpy(); eq2, tk2, _ = 模拟(t, P, n, rf, cap, 选=sel)
            r["去掉最好2pct的票_每年赚"] = S1.指标(eq2, dates, t, tk2)["每年赚"]; r["去掉的票数"] = len(去); r["去掉的票"] = " ".join(syms[:min(5, len(去))])
        rows.append(r)
    if 抽:
        sy = t.symbol.to_numpy(); pool = sorted(set(sy) | set(S1.HOLD["研发池名单"])) if seg == "二" else list(S1.HOLD["研发池名单"]); res = []
        for _ in range(抽):
            pick = set(rng.choice(pool, len(pool) // 2, replace=False)); sel = np.fromiter((s in pick for s in sy), bool, len(sy))
            eq, tk, _ = 模拟(t, P, n, rf, 3.0, 选=sel); res.append(S1.指标(eq, dates, t, tk)["每年赚"])
        R = np.array(res); r = [x for x in rows if x["总风险上限"] == "3R"][0]
        for p in (5, 25, 50, 75, 95): r[f"抽一半{抽}次_每年赚_{p}"] = round(float(np.percentile(R, p)), 2)
        np.save(os.path.join(OUT, f"抽样_{nm}_{seg}.npy"), R)
    return rows


if __name__ == "__main__":
    抽 = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    only = sys.argv[2].split(",") if len(sys.argv) > 2 and sys.argv[2] else None
    names = sorted({os.path.basename(f)[5:-4] for f in glob.glob(os.path.join(S1.A, "流水_一_*.csv"))} - {"buy_and_hold"})
    if only: names = [x for x in names if x in only]
    segs = (sys.argv[3],) if len(sys.argv) > 3 else ("一", "二")
    f_out = os.path.join(OUT, f"总风险和三个数_{''.join(segs)}.csv"); done = set()
    if os.path.exists(f_out): done = set(map(tuple, pd.read_csv(f_out)[["策略", "段"]].values))
    rng = np.random.default_rng(5336)
    for seg in segs:
        for nm in names:
            段 = "2015-2021" if seg == "一" else "2005-2014"
            if (nm, 段) in done: continue
            rows = 一组(nm, seg, 抽, rng)
            pd.DataFrame(rows).to_csv(f_out, mode="a", header=not os.path.exists(f_out), index=False)
            r3 = [x for x in rows if x["总风险上限"] == "3R"][0]; print(段, nm, r3["每年赚"], r3["最深亏损"], r3.get("抽一半1000次_每年赚_25"), r3.get("抽一半1000次_每年赚_75"), flush=True)
    print("DONE")
