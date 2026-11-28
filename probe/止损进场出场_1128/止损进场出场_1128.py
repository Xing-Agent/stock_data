# -*- coding: utf-8 -*-
"""《533》第六批 · 拍板第 7 条：止损缓冲（空单比多单宽）、两笔进场、出场 A/B/C（强趋势个股）、做空到前低先平多少。引擎外。
数据：probe/并池2004_1107/ohlcv_panel_newpool.parquet（修接缝那张），只读到 2021-12-31（2022 年以后封存）。
票：研发池（留出池不用）里、当年在池子排名表 pool_MERGED2004_ALL_1107.csv 里的票（按年初前 60 天成交额动态选，含后来退市的）。
两段分开报：2005–2014、2015–2021（信号日落在哪段算哪段；单子可以拿过段尾，到 2021-12-31 还没走的按那天收盘平，单独数）。

我定的写法（拍板没给死的地方，全部写明）：
  · 强上涨趋势：ADX(14) > 25、+DI > −DI、收盘 > 200 日线、50 日线 > 200 日线。强下跌反过来，另加大盘开关（标普收在 200 日线下且 50 日线在 200 日线下，拍板第 4 条）。
  · 进场信号（多）：信号 K 线最低价碰到 20 日线（≤ 20 日线）且收盘收在 20 日线上面；空单反过来（最高价碰到、收盘收在下面）。
    同一只票 10 天内只算第一个信号。所有版本用同一批信号，只换止损 / 进场 / 出场，方便直接比。
  · 止损 = 信号 K 线最低价 − 缓冲 × ATR(14)（空单：最高价 + 缓冲 × ATR）。缓冲：多 0.25 / 0.35 / 0.50，空 0.35 / 0.50 / 0.60 / 0.75。
  · 一笔进场（对照）：信号下一根开盘买满 1R。份数按「信号那天收盘到止损」的计划风险定（收盘后挂单），所以跳空成交会让实际风险偏离 1R，照实算；开盘已经穿过止损的不做。
  · 两笔进场：下一根开盘先买 0.3R；之后 5 根以内价格突破「信号 K 线高点，且离第一笔至少 0.5 倍 ATR」那个价，再加 0.7R（按挂单价算份数，跳空高开按开盘成交，所以合计可能略超 1R，照实算）。
    5 根内没触发就只有第一笔。另试 0.5 + 0.5、0.25 + 0.75。
  · 出场：A 到 1.5R（按第一笔进场价算）平一半，剩下止损移到成本；B 一直不平，3 倍 ATR 吊灯止损（持仓以来最高价 − 3ATR，只往上挪，收盘后更新）；
    C 到 1.5R 平 30%，剩下用吊灯。三组都最多拿 120 天。同一根里先算止损再算目标（日线分不出先后，按对我们不利的算）。
  · 做空到前低先平：前低 = 信号前 20 天的最低价；离进场不到 1R 的用 1.5R 代替。到了平 50% / 65% / 75%，剩下止损移到成本 + 3ATR 吊灯。
  · 成本：单边 5 个基点（同引擎），换成 R 扣掉。
  · 对照：同一只票、同一段里「强趋势成立的任意一天」随机进场，笔数和真信号一样，多单缓冲 0.35、空单 0.60，一笔 1R，出场 A/B/C，抽 20 次。
  · 每笔结果以 R 计（1R = 计划的整笔风险）。"""
import os, sys, json, numpy as np, pandas as pd, pyarrow.parquet as pq
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
FEE = 0.0005; END = "2021-12-31"; MAXH = 120


def 读():
    hold = json.load(open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
    pool = pd.read_csv(os.path.join(ROOT, "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"), usecols=["year", "symbol"])
    pool = pool[(pool.year >= 2005) & (pool.year <= 2021)]; dev = set(hold["研发池名单"]); pool = pool[pool.symbol.isin(dev)]
    yrs = pool.groupby("symbol").year.apply(set).to_dict(); syms = sorted(yrs)
    f = os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet"); have = set(pq.read_schema(f).names)
    cols = [f"('{x}', '{s}')" for s in syms for x in ("open", "high", "low", "close") if f"('{x}', '{s}')" in have]
    W = pq.read_table(f, columns=cols + ["date"]).to_pandas(); W = W.set_index("date") if "date" in W.columns else W; W.index = pd.to_datetime(W.index); W = W.loc[:END].astype("float32")
    if not isinstance(W.columns, pd.MultiIndex): W.columns = pd.MultiIndex.from_tuples([tuple(x.strip("()' ").replace("'", "").split(", ")) for x in W.columns])
    spx = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数长历史_1123/标普500指数_日线.csv"))
    dc = [c for c in spx.columns if "date" in c.lower() or "日期" in c][0]; cc = [c for c in spx.columns if c.lower() in ("close", "收盘", "adj_close")][0]
    spx = spx.set_index(pd.to_datetime(spx[dc]))[cc].astype(float).sort_index(); m200 = spx.rolling(200).mean(); m50 = spx.rolling(50).mean()
    熊 = ((spx < m200) & (m50 < m200)).reindex(W.index).ffill().fillna(False).to_numpy()
    return W, yrs, 熊


def 指标(o, h, l, c):
    pc = np.r_[np.nan, c[:-1]]; tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    s = lambda x, n: pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()
    w = lambda x: pd.Series(x).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean().to_numpy()
    up = h - np.r_[np.nan, h[:-1]]; dn = np.r_[np.nan, l[:-1]] - l
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    atr_w = w(tr); pdi = 100 * w(pdm) / atr_w; ndi = 100 * w(ndm) / atr_w; dx = 100 * np.abs(pdi - ndi) / (pdi + ndi); adx = w(np.nan_to_num(dx))
    return dict(atr=s(tr, 14), ma20=s(c, 20), ma50=s(c, 50), ma200=s(c, 200), adx=adx, pdi=pdi, ndi=ndi, low20=pd.Series(l).shift(1).rolling(20).min().to_numpy(),
                high20=pd.Series(h).shift(1).rolling(20).max().to_numpy())


def 跑一笔(side, i, o, h, l, c, atr, stop, 分笔, 出场, 前低=None, 平比例=None):
    """side=+1 多 / −1 空。返回 (R, 持有天数, 是否到期末还拿着, 是否5天内打止损, 第二笔有没有进)。"""
    n = len(c); j0 = i + 1
    if j0 >= n or not np.isfinite(o[j0]): return None
    E1 = o[j0]; risk1 = (c[i] - stop) * side                              # 计划风险：按信号那天收盘到止损定份数（收盘后挂单）
    if risk1 <= 0 or (E1 - stop) * side <= 0: return None                  # 第二天开盘已经穿过止损的不做
    w1, w2 = 分笔; q1 = w1 / risk1; legs = [[q1, E1]]; trig = None
    if w2 > 0:
        trig = max(h[i], E1 + 0.5 * atr[i]) if side > 0 else min(l[i], E1 - 0.5 * atr[i]); q2 = w2 / ((trig - stop) * side)
    费 = q1 * E1 * FEE; 目标 = E1 + side * 1.5 * risk1; 剩 = 1.0; 已 = 0.0; st = stop; ext = E1; 到目标 = False; 二进 = False; 早停 = False
    if 前低 is not None:
        tp = 前低 if (E1 - 前低) * side >= risk1 else E1 + side * 1.5 * risk1; 目标 = tp
    for j in range(j0, min(n, j0 + MAXH)):
        oj, hj, lj, cj = o[j], h[j], l[j], c[j]
        if not np.isfinite(cj): continue
        if trig is not None and not 二进 and j <= i + 5 and j > j0 - 1 and ((hj >= trig) if side > 0 else (lj <= trig)) and not 到目标:
            fp = max(oj, trig) if side > 0 else min(oj, trig)
            if (fp - st) * side > 0: legs.append([q2, fp]); 费 += q2 * fp * FEE; 二进 = True
        Q = sum(q for q, _ in legs) * 剩; avg = sum(q * p for q, p in legs) / sum(q for q, _ in legs)
        hit = (lj <= st) if side > 0 else (hj >= st)
        if hit:
            fp = min(oj, st) if side > 0 else max(oj, st); 已 += Q * (fp - avg) * side; 费 += Q * fp * FEE
            if j - j0 < 5 and not 到目标: 早停 = True
            return 已 - 费, j - j0 + 1, False, 早停, 二进
        if not 到目标 and 出场 in ("A", "C", "前低") and ((hj >= 目标) if side > 0 else (lj <= 目标)):
            fp = max(oj, 目标) if side > 0 else min(oj, 目标); 比 = {"A": 0.5, "C": 0.3, "前低": 平比例}[出场]
            已 += Q * 比 * (fp - avg) * side; 费 += Q * 比 * fp * FEE; 剩 *= (1 - 比); 到目标 = True
            if 出场 in ("A", "前低"): st = avg if side > 0 and avg > st or side < 0 and avg < st else st
        ext = max(ext, hj) if side > 0 else min(ext, lj)
        if 出场 == "B" or (出场 == "C" and 到目标) or (出场 == "前低" and 到目标):
            ch = ext - side * 3 * atr[j]
            if np.isfinite(ch): st = max(st, ch) if side > 0 else min(st, ch)
        if 出场 == "前低" and 到目标: st = max(st, avg) if side > 0 else min(st, avg)
    jj = min(n, j0 + MAXH) - 1
    while jj > j0 and not np.isfinite(c[jj]): jj -= 1                     # 退市 / 停牌：按最后一个有效收盘平
    Q = sum(q for q, _ in legs) * 剩; avg = sum(q * p for q, p in legs) / sum(q for q, _ in legs)
    已 += Q * (c[jj] - avg) * side; 费 += Q * c[jj] * FEE
    return 已 - 费, jj - j0 + 1, jj >= n - 1 or not np.isfinite(c[min(n - 1, jj + 1)]), False, 二进


def 汇总(df, keys):
    def f(g):
        r = g.R.to_numpy(); w = r[r > 0].sum(); lo = -r[r < 0].sum(); cs = np.cumsum(r[np.argsort(g.exit_ix.to_numpy(), kind="stable")])
        return pd.Series(dict(笔数=len(r), 每笔R_平均=round(r.mean(), 3), 每笔R_中位=round(np.median(r), 3), 胜率=round((r > 0).mean() * 100, 1), 利润因子=round(w / lo, 2) if lo > 0 else np.nan,
                              t值=round(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))), 2) if len(r) > 2 else np.nan, 最深回撤_R=round(float((cs - np.maximum.accumulate(np.r_[0, cs])[1:]).min()), 1),
                              五天内打止损pct=round(g.早停.mean() * 100, 1), 第二笔进了pct=round(g.二进.mean() * 100, 1), 平均持有天=round(g.天.mean(), 1), 期末还拿着=int(g.末.sum())))
    return df.groupby(keys).apply(f, include_groups=False).reset_index()


if __name__ == "__main__":
    W, yrs, 熊 = 读(); dates = W.index; yr = dates.year.to_numpy(); 段 = np.where(yr <= 2014, "2005-2014", "2015-2021"); rows = []
    多缓冲 = (0.25, 0.35, 0.50); 空缓冲 = (0.35, 0.50, 0.60, 0.75); 分笔们 = {"一笔1R": (1.0, 0.0), "0.3+0.7": (0.3, 0.7), "0.5+0.5": (0.5, 0.5), "0.25+0.75": (0.25, 0.75)}
    syms = sorted(set(W.columns.get_level_values(1))); 随 = []; RNG = np.random.default_rng(5337); N随 = 20
    if len(sys.argv) > 1: syms = syms[: int(sys.argv[1])]; OUT = os.path.join(HERE, "out_试"); os.makedirs(OUT, exist_ok=True)
    for si, s in enumerate(syms):
        try: o, h, l, c = (W[(x, s)].to_numpy(float) for x in ("open", "high", "low", "close"))
        except KeyError: continue
        I = 指标(o, h, l, c); ok = np.isin(yr, list(yrs[s])) & (yr >= 2005)
        强多 = ok & (I["adx"] > 25) & (I["pdi"] > I["ndi"]) & (c > I["ma200"]) & (I["ma50"] > I["ma200"]) & (l <= I["ma20"]) & (c > I["ma20"])
        强空 = ok & 熊 & (I["adx"] > 25) & (I["ndi"] > I["pdi"]) & (c < I["ma200"]) & (I["ma50"] < I["ma200"]) & (h >= I["ma20"]) & (c < I["ma20"])
        趋多 = ok & (I["adx"] > 25) & (I["pdi"] > I["ndi"]) & (c > I["ma200"]) & (I["ma50"] > I["ma200"]) & np.isfinite(I["atr"])
        趋空 = ok & 熊 & (I["adx"] > 25) & (I["ndi"] > I["pdi"]) & (c < I["ma200"]) & (I["ma50"] < I["ma200"]) & np.isfinite(I["atr"])
        for side, sig, 趋 in ((1, 强多, 趋多), (-1, 强空, 趋空)):         # 对照：强趋势的日子里随便哪天进，每段每只票笔数和真信号一样，抽 N随 次
            for sg in ("2005-2014", "2015-2021"):
                m_sig = sig & (段 == sg); pool_ix = np.where(趋 & (段 == sg))[0]; k = 0; lastk = -99
                for i in np.where(m_sig)[0]:
                    if i - lastk >= 10: k += 1; lastk = i
                if k == 0 or len(pool_ix) == 0: continue
                for it in range(N随):
                    for i in RNG.choice(pool_ix, min(k, len(pool_ix)), replace=False):
                        b = 0.35 if side > 0 else 0.60; stop = l[i] - b * I["atr"][i] if side > 0 else h[i] + b * I["atr"][i]
                        for ex in ("A", "B", "C"):
                            r = 跑一笔(side, i, o, h, l, c, I["atr"], stop, (1.0, 0.0), ex)
                            if r: 随.append((side, sg, it, ex, r[0]))
        for side, sig in ((1, 强多), (-1, 强空)):
            last = -99
            for i in np.where(sig)[0]:
                if i - last < 10 or not np.isfinite(I["atr"][i]): continue
                last = i; base = dict(票=s, 方向="多" if side > 0 else "空", 段=段[i], sig_ix=i)
                for b in (多缓冲 if side > 0 else 空缓冲):
                    stop = l[i] - b * I["atr"][i] if side > 0 else h[i] + b * I["atr"][i]
                    for fn, fb in (分笔们.items() if b in (0.35, 0.60) else [("一笔1R", (1.0, 0.0))]):
                        for ex in (("A", "B", "C") if side > 0 or fn == "一笔1R" else ("A",)):
                            r = 跑一笔(side, i, o, h, l, c, I["atr"], stop, fb, ex)
                            if r: rows.append(dict(base, 缓冲=b, 进场=fn, 出场=ex, R=r[0], 天=r[1], 末=r[2], 早停=r[3], 二进=r[4], exit_ix=i + r[1]))
                    if side < 0:
                        for pct in (0.50, 0.65, 0.75):
                            r = 跑一笔(side, i, o, h, l, c, I["atr"], stop, (1.0, 0.0), "前低", 前低=I["low20"][i], 平比例=pct)
                            if r: rows.append(dict(base, 缓冲=b, 进场="一笔1R", 出场=f"前低平{int(pct*100)}%", R=r[0], 天=r[1], 末=r[2], 早停=r[3], 二进=r[4], exit_ix=i + r[1]))
        if si % 200 == 0: print(si, len(syms), len(rows), flush=True)
    df = pd.DataFrame(rows); df.to_parquet(os.path.join(OUT, "逐笔.parquet"))
    T = 汇总(df, ["方向", "段", "缓冲", "进场", "出场"]); T.to_csv(os.path.join(OUT, "汇总.csv"), index=False)
    T2 = 汇总(df.assign(段="2005-2021"), ["方向", "段", "缓冲", "进场", "出场"]); T2.to_csv(os.path.join(OUT, "汇总_全段.csv"), index=False)
    R = pd.DataFrame(随, columns=["side", "段", "次", "出场", "R"]); R["方向"] = np.where(R.side > 0, "多", "空")
    g = R.groupby(["方向", "段", "出场", "次"]).R.agg(["mean", "count"]).reset_index()
    q = g.groupby(["方向", "段", "出场"])["mean"].quantile([0.05, 0.5, 0.95]).unstack().round(3); q["每次笔数"] = g.groupby(["方向", "段", "出场"])["count"].median(); q.to_csv(os.path.join(OUT, "随机对照_强趋势随便哪天进.csv"))
    print(q)
    # 信号个数、每年多少笔
    print(df.drop_duplicates(["票", "sig_ix", "方向"]).groupby(["方向", "段"]).size()); print("DONE")
