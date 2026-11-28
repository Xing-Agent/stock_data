# -*- coding: utf-8 -*-
"""《533》第六批 · 拍板第 6 条：位置打分反过来（碰得越多越容易破）、假突破反手只做第 1、2 次测试、打分只留三样、加「突破后第一次回踩」、ADX>25 不在阻力位反手空。引擎外。
数据、票池、两段、成本、出场写法同 probe/止损进场出场_1128/（直接 import 它的 指标() 和 跑一笔()）。美股个股日线，只读到 2021-12-31。

位置只留三样（拍板）：
  ① 前高前低：左右各 5 根的摆动高点 / 低点（第 6 根才确认，确认之后才能用）。
  ② 成交密集区：每 20 天用过去 120 天的成交量按价格分箱（箱宽 0.5 倍 ATR，用 (高+低+收)/3），取成交最多的那一箱的中间价，管接下来 20 天。
  ③ 没补的缺口：跳空 ≥ 0.3 倍 ATR；向上跳空取前一天最高价、向下跳空取前一天最低价；之后价格回到那里就算补了，作废。
  均线、整数关口不算。每个位置最多管 250 天。同一个位置在几样里都有（彼此 0.5 倍 ATR 以内），每样只算一次：分数 = 这一处有几样（1~3）。只用日线，所以「几个周期只算一次」这一条在这里不适用。
测试次数：价格从下面上来、最高价碰到位置下方 0.5 倍 ATR 以内，算碰一次（阻力）；支撑反过来。中间隔 3 天以上没碰才算新的一次。
  同一处有几个位置时，测试次数取其中最多的那个（同一个地方碰过几次）。
四种事件：
  · 阻力假突破反手空：从下面上来，最高价冲过位置 ≥ 0.1 倍 ATR，收盘收回位置下面。第二天开盘空，止损 = 当天最高 + 0.60 倍 ATR。
  · 支撑假跌破反手多：反过来，止损 = 当天最低 − 0.35 倍 ATR。
  · 突破后第一次回踩（多）：收盘站上阻力 ≥ 0.1 倍 ATR 之后 20 天内，第一次最低价回到位置上方 0.25 倍 ATR 以内、收盘还在位置上面 → 第二天开盘多，止损 = 当天最低 − 0.35 倍 ATR。
  · 跌破后第一次反抽（空）：反过来。
  出场统一用第 7 条的 A（1.5R 平一半、剩下挪到成本，最多 120 天）。同一只票同一种事件 5 天内只算第一个。
另报「碰了第几次之后，10 天内真突破（收盘越过位置 0.5 倍 ATR）的比例」—— 直接看「碰得越多越容易破」是不是真的。
对照：把所有位置整体挪开 2.5 倍 ATR（往上、往下各一次）再跑一遍同样的规则（同《437》的做法）。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out" if os.environ.get("PIVOT", "5") == "5" else f"out_摆动{os.environ['PIVOT']}"); os.makedirs(OUT, exist_ok=True)
sp = importlib.util.spec_from_file_location("Q7", os.path.join(ROOT, "probe/止损进场出场_1128/止损进场出场_1128.py")); Q7 = importlib.util.module_from_spec(sp); sp.loader.exec_module(Q7)
END = "2021-12-31"; LIFE = 250; K = int(os.environ.get("PIVOT", "5"))     # 摆动点左右各几根：默认 5，另试 20
COLS = ["票", "位置", "事件", "方向", "段", "ix", "分数", "几样", "第几次", "ADX强", "顺势", "大盘熊", "在200上", "R", "天", "末"]


def 读():
    hold = json.load(open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
    pool = pd.read_csv(os.path.join(ROOT, "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"), usecols=["year", "symbol"])
    pool = pool[(pool.year >= 2005) & (pool.year <= 2021) & pool.symbol.isin(set(hold["研发池名单"]))]; yrs = pool.groupby("symbol").year.apply(set).to_dict()
    f = os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet"); have = set(pq.read_schema(f).names)
    cols = [f"('{x}', '{s}')" for s in sorted(yrs) for x in ("open", "high", "low", "close", "volume") if f"('{x}', '{s}')" in have]
    W = pq.read_table(f, columns=cols + ["date"]).to_pandas(); W = W.set_index("date") if "date" in W.columns else W; W.index = pd.to_datetime(W.index); W = W.loc[:END].astype("float32")
    if not isinstance(W.columns, pd.MultiIndex): W.columns = pd.MultiIndex.from_tuples([tuple(x.strip("()' ").replace("'", "").split(", ")) for x in W.columns])
    spx = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数长历史_1123/标普500指数_日线.csv"), usecols=["date", "close"]); spx = spx.set_index(pd.to_datetime(spx.date)).close.astype(float)
    m2 = spx.rolling(200).mean(); m5 = spx.rolling(50).mean(); 熊 = ((spx < m2) & (m5 < m2)).reindex(W.index).ffill().fillna(False).to_numpy()
    return W, yrs, 熊


def 位置(h, l, c, v, atr):
    """返回 list of (价, 类, 起, 止)。类：1 前高前低、2 成交密集区、3 没补的缺口。起 = 第一天能用的下标。"""
    n = len(c); L = []
    hh = pd.Series(h).rolling(2 * K + 1, center=True).max().to_numpy(); ll = pd.Series(l).rolling(2 * K + 1, center=True).min().to_numpy()
    for t in np.where(np.isfinite(hh) & (h == hh))[0]: L.append((h[t], 1, t + K + 1, min(n, t + K + 1 + LIFE)))
    for t in np.where(np.isfinite(ll) & (l == ll))[0]: L.append((l[t], 1, t + K + 1, min(n, t + K + 1 + LIFE)))
    tp = (h + l + c) / 3
    for t in range(140, n, 20):
        a = atr[t - 1]
        if not np.isfinite(a) or a <= 0: continue
        p = tp[t - 120:t]; vv = v[t - 120:t]; okk = np.isfinite(p) & np.isfinite(vv)
        if okk.sum() < 60: continue
        b = np.floor(p[okk] / (0.5 * a)); u, inv = np.unique(b, return_inverse=True); s = np.bincount(inv, weights=vv[okk])
        L.append(((u[s.argmax()] + 0.5) * 0.5 * a, 2, t, min(n, t + 20)))
    for t in range(1, n):
        a = atr[t - 1]
        if not np.isfinite(a): continue
        if l[t] - h[t - 1] >= 0.3 * a: lv, up = h[t - 1], True
        elif l[t - 1] - h[t] >= 0.3 * a: lv, up = l[t - 1], False
        else: continue
        e = min(n, t + 1 + LIFE); seg = l[t + 1:e] <= lv if up else h[t + 1:e] >= lv; f = np.argmax(seg) if seg.any() else None
        L.append((lv, 3, t + 1, t + 1 + f if f is not None else e))
    return L


def 事件(L, o, h, l, c, atr, shift=0.0):
    """对每个位置在它的有效期里找测试、假突破、突破后回踩。返回事件 list 和「第 k 次测试后 10 天内破没破」list。"""
    ev = []; brk = []; n = len(c)
    for (p0, typ, s, e) in L:
        if s < 1 or s >= n: continue
        a0 = atr[s - 1]
        if not np.isfinite(a0): continue
        P = p0 + shift * a0; j = np.arange(s, e); A = atr[j]; pc = c[j - 1]
        for side in (1, -1):                                   # 1 = 阻力（价在下面），−1 = 支撑（价在上面）
            below = pc < P if side > 0 else pc > P
            test = below & ((h[j] >= P - 0.5 * A) if side > 0 else (l[j] <= P + 0.5 * A))
            tj = j[test]
            if len(tj) == 0: continue
            new = np.r_[True, np.diff(tj) > 3]; epi = np.cumsum(new); 次 = dict(zip(tj, epi))
            for k, jj in zip(epi[new], tj[new]):                # 每次测试开头：10 天内收盘越过 0.5 ATR 没有
                w = c[jj:min(n, jj + 10)]; 破 = ((w > P + 0.5 * atr[jj]) if side > 0 else (w < P - 0.5 * atr[jj])).any()
                brk.append((side, int(jj), int(k), typ, bool(破)))
            fake = below & ((h[j] > P + 0.1 * A) & (c[j] < P) if side > 0 else (l[j] < P - 0.1 * A) & (c[j] > P))
            for jj in j[fake]: ev.append(("假突破反手", -side, int(jj), P, typ, int(次.get(jj, 1))))
            br = below & ((c[j] > P + 0.1 * A) if side > 0 else (c[j] < P - 0.1 * A))
            for jb in j[br]:
                for k in range(jb + 1, min(n, jb + 21)):
                    if not np.isfinite(c[k]): break
                    if side > 0:
                        if c[k] < P: break
                        if l[k] <= P + 0.25 * atr[k]: ev.append(("突破后第一次回踩", 1, int(k), P, typ, int(次.get(jb, 1)))); break
                    else:
                        if c[k] > P: break
                        if h[k] >= P - 0.25 * atr[k]: ev.append(("跌破后第一次反抽", -1, int(k), P, typ, int(次.get(jb, 1)))); break
    return ev, brk


def 打分(ev, L, atr, shift):
    """同一天、同一种事件、同一方向：合成一处，分数 = 0.5 ATR 以内有几样，测试次数取最多的。"""
    if not ev: return []
    Ap = np.array([x[0] for x in L]); At = np.array([x[1] for x in L]); As = np.array([x[2] for x in L]); Ae = np.array([x[3] for x in L])
    a0 = np.array([atr[x - 1] if 1 <= x <= len(atr) else np.nan for x in As]); Ap = Ap + shift * np.nan_to_num(a0)
    E = pd.DataFrame(ev, columns=["事件", "方向", "ix", "价", "类", "第几次"]); out = []
    for (et, sd, ix), g in E.groupby(["事件", "方向", "ix"], sort=False):
        P = g.价.iloc[0]; m = (As <= ix) & (ix < Ae) & (np.abs(Ap - P) <= 0.5 * atr[ix]); ty = sorted(set(At[m].tolist())) or [int(g.类.iloc[0])]
        out.append((et, int(sd), int(ix), P, len(ty), "".join(str(x) for x in ty), int(g.第几次.max())))
    return out


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 and int(sys.argv[1]) > 0 else None
    W, yrs, 熊 = 读(); dates = W.index; yr = dates.year.to_numpy(); 段 = np.where(yr <= 2014, "2005-2014", "2015-2021")
    syms = sorted(set(W.columns.get_level_values(1)))[:lim]; rows = []; BR = []
    if lim: OUT = os.path.join(HERE, "out_试"); os.makedirs(OUT, exist_ok=True)
    import glob; 已有 = {int(os.path.basename(f)[4:6]) for f in glob.glob(os.path.join(OUT, "逐笔_块*.parquet"))}
    到 = int(sys.argv[2]) if len(sys.argv) > 2 else 99
    for si, s in enumerate(syms):
        if si // 200 in 已有 or si // 200 > 到: continue
        try: o, h, l, c, v = (W[(x, s)].to_numpy(float) for x in ("open", "high", "low", "close", "volume"))
        except KeyError: continue
        I = Q7.指标(o, h, l, c); atr = I["atr"]; ok = np.isin(yr, list(yrs[s])) & (yr >= 2005); L = 位置(h, l, c, v, atr)
        for shift, 名 in (((0.0, "真位置"), (2.5, "挪开+2.5ATR"), (-2.5, "挪开-2.5ATR")) if K == 5 else ((0.0, "真位置"), (2.5, "挪开+2.5ATR"))):
            ev, brk = 事件(L, o, h, l, c, atr, shift)
            if shift == 0.0: BR += [(s, 段[jj], sd, k, ty, b) for (sd, jj, k, ty, b) in brk if ok[jj]]
            last = {}
            for (et, sd, ix, P, sc, tys, 次) in sorted(打分(ev, L, atr, shift), key=lambda x: x[2]):
                if not ok[ix] or not np.isfinite(atr[ix]): continue
                if ix - last.get((et, sd), -99) < 5: continue
                last[(et, sd)] = ix
                stop = h[ix] + 0.60 * atr[ix] if sd < 0 else l[ix] - 0.35 * atr[ix]
                r = Q7.跑一笔(sd, ix, o, h, l, c, atr, stop, (1.0, 0.0), "A")
                if r: rows.append((s, 名, et, "多" if sd > 0 else "空", 段[ix], ix, sc, tys, 次, bool(I["adx"][ix] > 25), bool((I["pdi"][ix] > I["ndi"][ix]) == (sd > 0)),
                                   bool(熊[ix]), bool(c[ix] > I["ma200"][ix]), float(r[0]), int(r[1]), bool(r[2])))
        if (si + 1) % 200 == 0 or si == len(syms) - 1:
            pd.DataFrame(rows, columns=COLS).to_parquet(os.path.join(OUT, f"逐笔_块{si // 200:02d}.parquet")); pd.DataFrame(BR, columns=["票", "段", "方向", "第几次", "类", "破了"]).to_parquet(os.path.join(OUT, f"破没破_块{si // 200:02d}.parquet"))
            print(si, len(syms), len(rows), flush=True); rows = []; BR = []
    if 到 < 99: sys.exit(0)
    pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(os.path.join(OUT, "逐笔_块*.parquet")))]).to_parquet(os.path.join(OUT, "逐笔.parquet"))
    pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(os.path.join(OUT, "破没破_块*.parquet")))]).to_parquet(os.path.join(OUT, "测试后破没破.parquet")); print("DONE")
