# -*- coding: utf-8 -*-
"""
★★★ 环境卡 22 年版(省内存)—— 判法、差档登记、随机对照与 跑环境卡_1107.py **一字不差**(从那份 import),
只改「怎么算」:22 年面板上原版把每张卡的整条序列都存下来,7GB 内存被 OOM 杀了 4 次;
这一份逐只票算完**只取信号日那一格**就丢,状-11 用到的阶段二矩阵存成 0/1 小整数。
★ 每张卡的定义仍然调 probe/环境卡_1106/环境卡_1106.py 里同一个函数(道氏/温斯坦/区间/共振…),不重写算法。
"""
from __future__ import annotations
import gc, io, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 台_1107 as T                                                        # noqa: E402
assert T.窗 == "2004"
import 跑环境卡_1107 as E                                                  # noqa: E402  ★ 差档登记 / 调仓位效果 / 月内打乱 / 补两张
K, P = E.K, E.P

OUT = os.path.join(HERE, "环境卡结果_22年_1107.json")


def 算标签(L: dict, panel, idx) -> dict:
    """返回 {宿主: DataFrame[每笔 × 卡]}。"""
    D = {}
    for 名, led in L.items():
        d = P._键(led).reset_index(drop=True)
        d["sym"] = d["symbol"].astype(str)
        d["t"] = idx.searchsorted(pd.to_datetime(d["entry_date"]).values) - 1
        D[名] = d
    allt = pd.concat([d[["sym", "t"]].assign(h=n, r=d.index) for n, d in D.items()], ignore_index=True)
    syms = sorted(set(allt["sym"]) & set(panel["close"].columns))
    lab = {n: {} for n in D}
    def put(card, sub, vals):
        for (h, r), v in zip(zip(sub["h"], sub["r"]), vals):
            lab[h].setdefault(card, {})[r] = v
    spy = T.data.load_benchmark("SPY")["close"].reindex(idx).ffill().to_numpy()
    eps = []; pk_i, pk = 0, spy[0]; tr_i, tr = 0, spy[0]; inep = False
    for t in range(len(spy)):
        x = spy[t]
        if not np.isfinite(x):
            continue
        if not np.isfinite(pk):
            pk, pk_i, tr, tr_i = x, t, x, t
        if x >= pk:
            if inep:
                eps.append((pk_i, tr_i, t, tr / pk - 1)); inep = False
            pk, pk_i, tr, tr_i = x, t, x, t
        else:
            if x < tr:
                tr, tr_i = x, t
            if tr / pk - 1 <= -0.05:
                inep = True
    st2 = np.full((len(idx), len(syms)), np.nan, dtype=np.float32)
    g = allt.groupby("sym")
    for jj, s in enumerate(syms):
        sub = g.get_group(s); ts = sub["t"].to_numpy(); ok = ts >= 0
        sub = sub[ok]; ts = ts[ok]
        o, h, l, c, v = (panel[f][s].to_numpy(float) for f in ("open", "high", "low", "close", "volume"))
        a = K.atr(h, l, c)
        dow, piv3 = K.道氏(c, a, len(c)); put("状-1 道氏高低点排列", sub, dow[ts])
        ws = K.温斯坦(c); put("状-2 温斯坦四阶段", sub, ws[ts])
        st2[:, jj] = np.where(ws == None, np.nan, (ws == "阶段2").astype(np.float32))   # noqa: E711
        inr, age, fb, sp10, upth, _ = K.区间(c, h, l, a)
        put("状-8 区间年龄与假突破", sub, np.where(inr[ts], "在区间内", "不在区间"))
        put("状-5 相对强度", sub, [K.相对强度档(c, eps, int(t)) for t in ts])
        pc = np.r_[np.nan, c[:-1]]; ph = np.r_[np.nan, h[:-1]]; pl = np.r_[np.nan, l[:-1]]
        big = np.abs(o - pc) >= 0.5 * a
        gap = np.where(~np.isfinite(a), None, np.where((l > ph) & big, "向上缺口", np.where((h < pl) & big, "向下缺口", "无缺口")))
        put("状-7 跳空缺口", sub, gap[ts])
        rv = v / pd.Series(v).rolling(20, min_periods=20).mean().to_numpy()
        put("状-9 相对成交量", sub, np.where(~np.isfinite(rv[ts]), None, np.where(rv[ts] >= 2.5, "极值放量", np.where(rv[ts] <= 0.5, "干燥", "正常"))))
        adv = pd.Series(c * v).rolling(20, min_periods=20).mean().to_numpy()
        put("状-10 可交易性", sub, np.where(~np.isfinite(adv[ts]), None, np.where(adv[ts] < 1e7, "不合格", "可交易")))
        hi = pd.Series(c).rolling(252, min_periods=252).max().to_numpy(); lo = pd.Series(c).rolling(252, min_periods=252).min().to_numpy()
        pos = (c - lo) / np.where(hi - lo > 0, hi - lo, np.nan)
        put("状-12 空间位置", sub, np.where(~np.isfinite(pos[ts]), None, np.where(pos[ts] > 2/3, "上三分之一", np.where(pos[ts] < 1/3, "下三分之一", "中间"))))
        mas = {n: pd.Series(c).rolling(n, min_periods=n).mean().to_numpy() for n in (20, 50, 150, 200)}
        ks = [K.共振支撑(c, a, piv3, int(t), [mas[n][t] for n in mas]) for t in ts]
        put("状-6 共振计数(半)", sub, [None if not np.isfinite(k) else ("强支撑(≥3类)" if k >= 3 else ("弱支撑(≤1类)" if k <= 1 else "中(2类)")) for k in ks])
        if jj % 300 == 0:
            print(f"  … {jj}/{len(syms)}", flush=True); gc.collect()
    # 状-11:行业映射(每月重算,只用过去 252 日)+ 同行业阶段二比例(排除自己)
    E2 = pd.DataFrame({e: K.etf收盘(e) for e in K.SECT}).reindex(idx).ffill()
    er = np.log(E2).diff().to_numpy(); sr = np.log(panel["close"][syms]).diff().to_numpy(np.float32)
    me = pd.Series(idx).groupby(pd.Series(idx).dt.to_period("M")).last()
    M = np.full((len(idx), len(syms)), -1, dtype=np.int8)
    for d0 in me:
        t = idx.get_loc(d0)
        if t < 252:
            continue
        S = sr[t - 251:t + 1]; X = er[t - 251:t + 1]
        okx = np.isfinite(X).sum(0) >= 200
        Xs = (X - np.nanmean(X, 0)) / np.nanstd(X, 0); Ss = (S - np.nanmean(S, 0)) / np.nanstd(S, 0)
        cor = np.nan_to_num(Ss).T @ np.nan_to_num(Xs) / 251.0
        cor[:, ~okx] = -9
        best = cor.argmax(1).astype(np.int8); best[np.isfinite(S).sum(0) < 200] = -1
        M[t + 1:t + 23] = best
    del sr; gc.collect()
    for 名, d in D.items():
        vals = []
        for s, t in zip(d["sym"], d["t"]):
            if t < 0 or s not in syms:
                vals.append(None); continue
            j = syms.index(s); e = M[t, j]
            if e < 0:
                vals.append(None); continue
            sel = (M[t] == e); col = st2[t, sel]; fin = np.isfinite(col)
            if fin.sum() < 5:
                vals.append(None); continue
            own = st2[t, j] if np.isfinite(st2[t, j]) else 0.0
            v = (np.nansum(col) - own) / max(1, fin.sum() - (1 if np.isfinite(st2[t, j]) else 0))
            vals.append("高(≥0.5)" if v >= 0.5 else ("低(<0.25)" if v < 0.25 else "中"))
        lab[名]["状-11 板块趋势一致性"] = dict(enumerate(vals))
    out = {}
    for 名, d in D.items():
        f = pd.DataFrame({k: pd.Series(v) for k, v in lab[名].items()}).reindex(d.index)
        out[名] = (d, f)
    return out


def main() -> int:
    t0 = time.time()
    T.装池()
    panel = T.cache._PANEL; idx = panel["close"].index
    L = {}
    for 名 in E.宿主:
        p = T.臂文件(os.path.join(HERE, "arms_2004"), f"{名}|不装")
        if os.path.exists(p):
            L[名] = pd.read_csv(p)
    if len(L) < len(E.宿主):
        print(f"⚠⚠⚠ 宿主流水只有 {len(L)}/{len(E.宿主)}", flush=True)
    if not L:
        raise SystemExit("★★★ 一条宿主流水都没有")
    labs = 算标签(L, panel, idx)
    print(f"★ 卡算完 {time.time()-t0:.0f}s", flush=True)
    报 = {"★预先登记": E.__doc__.strip(), "★这一份": __doc__.strip(), "★差档登记": {k: [sorted(v[0]), v[1]] for k, v in E.差档.items()},
          "★卡定义(逐张标档)": K.卡定义, "★宿主": list(L), "★★★失败": [], "随机次数": 100}
    n检 = 0; 过 = []
    for 名, (d, lab) in labs.items():
        d = d.copy()
        d["x"] = d["ret"] - P.替身收益(d).to_numpy(); d["R"] = d["r_multiple_net"].astype(float)
        er, up, fb = E.补两张(d, idx, panel)
        for th in (0.5, 0.6, 0.7):
            lab[f"状-3 ER(10)·门槛{th}"] = np.where(np.isnan(er), None, np.where(er >= th, "趋势", "震荡"))
        lab["状-4 威科夫区间结构(半)"] = up
        lab["状-8 区间年龄与假突破"] = np.where(np.isnan(fb), "不在区间", np.where(fb >= 2, "区间内·假突破≥2", "区间内·假突破<2"))
        月 = d["entry_date"].dt.to_period("M").astype(str)
        日 = d["entry_date"].dt.strftime("%Y-%m-%d")
        h = {"笔数": len(d)}
        for 卡, (bset, _) in E.差档.items():
            try:
                g = pd.Series(lab[卡].to_numpy() if hasattr(lab[卡], "to_numpy") else lab[卡], index=d.index)
                bad = g.isin(bset); nb = int(bad.sum())
                r = {"各档笔数": {str(k): int(v) for k, v in g.value_counts(dropna=False).items()},
                     "减半笔数": nb, "减半占比": round(nb / len(d), 4)}
                if nb < 30 or nb > len(d) - 30:
                    r["★判"] = "★算不出(减半那档 <30 笔或几乎全部)"; h[卡] = r; continue
                g2 = pd.Series(np.where(bad, "差档", "其余"), index=d.index)
                r["①配对检验·差档减其余·比大盘"] = K.对比(d["x"], g2, 日, "差档", "其余")
                for 量, col in (("比大盘pct", "x"), ("每笔净R", "R")):
                    mul = 100 if col == "x" else 1
                    真 = E.调仓位效果(d[col], bad) * mul
                    随 = [E.调仓位效果(d[col], E.月内打乱(bad, 月, sd)) * mul for sd in range(100)]
                    r[f"调仓位效果·{量}"] = T.噪声判(真, 随)
                    r[f"差档减其余·{量}"] = round(float(d.loc[bad, col].mean() - d.loc[~bad, col].mean()) * mul, 4)
                n检 += 1
                j = r["调仓位效果·比大盘pct"]["★判"]
                if "超过随机" in j:
                    过.append(f"{名} · {卡}:{j} 真 {r['调仓位效果·比大盘pct']['真']}")
                h[卡] = r
            except Exception as e:
                报["★★★失败"].append(f"{名}·{卡}: {type(e).__name__}: {e}")
        报[名] = h
        print("✓", 名, flush=True)
    报["★★★对账"] = {"有效检验数": n检, "超过随机 2 个标准差的": 过}
    报["耗时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("★ 写到", OUT, "失败", len(报["★★★失败"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
