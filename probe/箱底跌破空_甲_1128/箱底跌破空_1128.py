# -*- coding: utf-8 -*-
"""《570》第四批 =《527 拍板》第 5 条（美股）：大跌后的横盘箱子，箱子里和箱顶都不空，只空跌破箱底之后那一段。引擎外，engine/ 没动；美股 2022 以后不读。
箱子：状态机第四版的「筑底期」。箱底 / 箱顶用没取整的原值，照 probe/筑底箱子重分_1128/箱子重分_1128.py 的取法：
      进筑底期那天往回找这段跌势的起点，起点到那天的最低价 = 箱底，最低点之后到那天的最高价 = 箱顶。
品种：主表 SPY、QQQ、SOXX（状态机档位是现成的 out4/）。扩大样本另表：IWM、DIA、XLB XLE XLF XLI XLK XLP XLU XLV XLY、SMH、KRE，
      用同一套状态机（P指数，箱宽 0.18）在内存里现算档位，参数没为它们调过。
小时线：ETF 2004 年起、SOXX 2003 年起（常规时段）。箱子在 2004 年以前的（例：SPY 2001-02）没有小时线，不做，不拿日线凑。
规则（拍板给的照拍板，没给的我定、写明、跑相邻三档）：
  盯的时段：进筑底期那天起，到离开筑底期后 20 个交易日（★我定的；如果离开时是往上走（涨势 / 转涨期），离开那天就停）。收盘站上箱顶 → 这个箱子停。
  ① 4 小时线收盘 < 箱底（拍板；另试「连续两根 4 小时收在箱底下」）。美股 4 小时线 = 每天两根（9:30–13:30、13:30–16:00），同《494》。
  ② 1 小时线反抽回不到箱底：跌破之后，1 小时最高 ≥ 箱底 − 0.5 × 4 小时 ATR（★我定的「反抽到了」，另试 0.25、1.0），期间 1 小时收盘没站回箱底；
     站回箱底 → 这次作废，等下一次 4 小时收盘跌破。跌破后 10 个交易日（65 根 1 小时线）内没走完就作废（★我定的）。
  ③ 反抽之后出现「1 小时收盘 < 前一根 1 小时最低」→ 下一根 1 小时开盘空。
  止损（★我定的，拍板没写）：反抽最高 + 0.3 × 4 小时 ATR；另试：max(反抽最高, 箱底) + 0.5 × 4 小时 ATR。
  出场：拍板 —— 进场后 8 根 1 小时线里最多只赚到不到 0.8R，就在第 8 根收盘走（根数另试 6、12；门槛另试 0.5R、1.0R）。
        另外（沿用之前做空脚本）：止损、3 倍风险目标、最多拿 30 个交易日（195 根 1 小时线）。另报一版加「1 小时收盘站回箱底就走」。
  一个箱子最多 3 笔，同一时间一笔。成本单边 0.05%。"""
import os, sys, json, glob, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
封 = pd.Timestamp("2021-12-31 23:59"); FEE = 0.0005
主 = ["SPY", "QQQ", "SOXX"]; 扩 = ["IWM", "DIA", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY", "SMH", "KRE"]
默认 = dict(破法="一根", 碰=0.5, 止损法="反抽高", 时N=8, 时门=0.8, 站回走=False, 等=65, 最长=195, 目标=3.0, 每箱=3, 盯=20)


def 日线(sym):
    f = os.path.join(ROOT, "market_ext_1105/SOXX_1123/日线/SOXX_日线.csv") if sym == "SOXX" else os.path.join(ROOT, f"market_ext_1105/ETF和币_1120/日线/{sym}_日线.csv")
    if sym in ("SPY", "QQQ"): return M4.美股日线(sym).loc[:封]
    y = pd.read_csv(f, parse_dates=["date"]).set_index("date").loc[:封]
    return pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna()


def 档(sym, D):
    if sym in 主:
        R = pd.read_csv(os.path.join(ROOT, f"probe/大周期五档_1123/out4/{sym}_四版_每天的档.csv"), index_col=0, parse_dates=True).loc[:封]
    else:
        R, _ = M4.跑(D, M4.P指数)
    return R.reindex(D.index)


def 箱子(D, R):
    l, h = D.low.to_numpy(float), D.high.to_numpy(float); st = R["档"].fillna("").to_numpy(); why = R["切换原因"].fillna("").to_numpy(); idx = D.index; out = []; b = None
    for i in range(1, len(D)):
        if str(why[i]).startswith("进筑底期"):
            s0 = max([q for q in range(i) if st[q] == "跌势" and st[q - 1] != "跌势"] or [0]); li = s0 + int(np.argmin(l[s0:i + 1]))
            b = dict(进箱=idx[i], 箱底=float(l[li]), 箱顶=float(h[li + 1:i + 1].max() if li < i else h[i]))
        if b is not None and st[i] != "筑底期":
            b.update(出箱=idx[i], 出箱后=st[i]); out.append(b); b = None
    if b is not None: b.update(出箱=idx[-1], 出箱后="还在箱里"); out.append(b)
    return out


def 小时(sym):
    if sym == "SOXX": fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线/*.parquet")))
    else: fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2004_2014/*.parquet")) + glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起/*.parquet")))
    fs = [f for f in fs if int(os.path.basename(f)[-12:-8]) <= 2021]
    cols = ["time_utc", "session", "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"]
    x = pd.concat([pd.read_parquet(f, columns=cols + (["symbol"] if sym != "SOXX" else []), filters=[("symbol", "==", sym)] if sym != "SOXX" else None) for f in fs])
    x = x[x.session == "regular"]; t = pd.to_datetime(x.time_utc).dt.tz_convert("America/New_York").dt.tz_localize(None)
    H = pd.DataFrame({"open": x.open_adj.to_numpy(), "high": x.high_adj.to_numpy(), "low": x.low_adj.to_numpy(), "close": x.close_adj.to_numpy(), "volume": x.volume_adj.to_numpy()}, index=t.to_numpy()).sort_index()
    H = H[~H.index.duplicated()].loc[:封]
    # 4 小时：每天两根（9:30–13:30、13:30–16:00）；每根 1 小时线记下它属于哪根 4 小时线、那根是否已收完
    mm = H.index.hour * 60 + H.index.minute; half = np.where(mm < 13 * 60 + 30, 0, 1); key = np.asarray((H.index.normalize() - pd.Timestamp("1970-01-01")).days) * 2 + half
    g = pd.DataFrame({"k": key, "h": H.high.to_numpy(), "l": H.low.to_numpy(), "c": H.close.to_numpy()}, index=H.index).groupby("k")
    F = pd.DataFrame({"high": g.h.max(), "low": g.l.min(), "close": g.c.last()}); pc = F.close.shift(1)
    F["atr"] = pd.concat([F.high - F.low, (F.high - pc).abs(), (F.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    H["k"] = key; H["末"] = np.r_[key[1:] != key[:-1], True]            # 这根 1 小时线是它那根 4 小时线的最后一根 → 收完时才能用 4 小时收盘
    return H, F


def 出(o, h, l, c, i, e, st, P, 箱底=None):
    r = st - e; n = len(c); end = min(n - 1, i + P["最长"] - 1); best = 0.0
    for j in range(i, end + 1):
        if h[j] >= st: px = max(o[j], st) if j > i else st; return (e - px) / r, j, px, "止损"
        if l[j] <= e - P["目标"] * r: return P["目标"], j, e - P["目标"] * r, "目标"
        best = max(best, (e - l[j]) / r)
        if P["站回走"] and 箱底 is not None and c[j] > 箱底: return (e - c[j]) / r, j, c[j], "站回箱底"
        if j - i + 1 == P["时N"] and best < P["时门"]: return (e - c[j]) / r, j, c[j], f"{P['时N']}根没到{P['时门']}R"
    return (e - c[end]) / r, end, c[end], "拿满"


def 跑一只(sym, D, R, H, F, P):
    o, h, l, c = (H[x].to_numpy(float) for x in ("open", "high", "low", "close")); k = H.k.to_numpy(); 末 = H["末"].to_numpy(); t = H.index; n = len(H)
    F4c = F.close.reindex(k).to_numpy(); A4 = F.atr.shift(1).reindex(k).to_numpy()          # 用前一根 4 小时线收完时的 ATR
    trades = []; boxes = 箱子(D, R); didx = D.index
    for b in boxes:
        if b["进箱"] < t[0]: b["备注"] = "没有小时线"; continue
        向上 = b["出箱后"] in ("涨势", "涨势·中继", "转涨期")
        p_end = didx.get_loc(b["出箱"]); 止日 = b["出箱"] if 向上 else didx[min(len(didx) - 1, p_end + P["盯"])]
        i0 = t.searchsorted(b["进箱"] + pd.Timedelta(hours=23)); i1 = t.searchsorted(止日 + pd.Timedelta(hours=23)); 底 = b["箱底"]; 顶 = b["箱顶"]
        i = i0; 次 = 0; 连 = 0
        while i < min(i1, n - 2) and 次 < P["每箱"]:
            if c[i] > 顶: break
            if 末[i]:                                                   # 4 小时线收完
                连 = 连 + 1 if F4c[i] < 底 else 0
                if 连 >= (2 if P["破法"] == "两根" else 1):
                    j = i + 1; 碰 = None; lo = np.inf; m = None
                    while j < min(n - 1, i + 1 + P["等"]):
                        if c[j] > 底: break
                        a = A4[j]
                        if 碰 is None and h[j] >= 底 - P["碰"] * a: 碰 = j
                        if 碰 is not None and j > 碰 and c[j] < l[j - 1]: m = j; break
                        j += 1
                    if m is not None and m + 1 < n:
                        e = o[m + 1]; hi = h[碰:m + 1].max(); a = A4[m]
                        st = hi + 0.3 * a if P["止损法"] == "反抽高" else max(hi, 底) + 0.5 * a
                        if st > e and (st - e) / e >= 0.001:
                            rr, jx, px, how = 出(o, h, l, c, m + 1, e, st, P, 底)
                            trades.append(dict(sym=sym, 进箱=b["进箱"], 箱底=底, 箱顶=顶, 出箱后=b["出箱后"], t=t[m + 1], 进=e, 止损=st, 风险ATR=(st - e) / a, R=rr - 2 * FEE * e / (st - e),
                                               pct=(e - px) / e * 100 - 0.1, 出=t[jx], 怎么走=how)); 次 += 1; i = jx + 1; 连 = 0; continue
                    i = max(i + 1, j); 连 = 0; continue
            i += 1
    return trades, boxes


档位 = [("默认", {}), ("两根跌破", {"破法": "两根"}), ("碰0.25", {"碰": 0.25}), ("碰1.0", {"碰": 1.0}), ("止损宽", {"止损法": "宽"}),
        ("时N6", {"时N": 6}), ("时N12", {"时N": 12}), ("门0.5", {"时门": 0.5}), ("门1.0", {"时门": 1.0}), ("不加8根规则", {"时N": 10 ** 6}), ("加站回箱底走", {"站回走": True}),
        ("盯10天", {"盯": 10}), ("盯40天", {"盯": 40})]

if __name__ == "__main__":
    allT = {nm: [] for nm, _ in 档位}; 箱表 = []; 池 = {}
    for sym in 主 + 扩:
        D = 日线(sym); R = 档(sym, D); H, F = 小时(sym)
        for nm, P in 档位:
            T, B = 跑一只(sym, D, R, H, F, {**默认, **P}); allT[nm] += T
            if nm == "默认": 箱表 += [dict(b, sym=sym, 组="主" if sym in 主 else "扩") for b in B]
        # 随机对照的池：盯的时段里、1 小时收盘已在箱底下面的根
        o, hh, ll, cc = (H[x].to_numpy(float) for x in ("open", "high", "low", "close")); A4 = F.atr.shift(1).reindex(H.k.to_numpy()).to_numpy(); ok = np.zeros(len(H), bool); t = H.index; didx = D.index
        for b in 箱子(D, R):
            if b["进箱"] < t[0]: continue
            向上 = b["出箱后"] in ("涨势", "涨势·中继", "转涨期"); p_end = didx.get_loc(b["出箱"]); 止日 = b["出箱"] if 向上 else didx[min(len(didx) - 1, p_end + 默认["盯"])]
            a_ = t.searchsorted(b["进箱"] + pd.Timedelta(hours=23)); z = t.searchsorted(止日 + pd.Timedelta(hours=23)); seg = np.arange(a_, min(z, len(H) - 2))
            ok[seg] |= cc[seg] < b["箱底"]
        ok &= np.nan_to_num(A4) > 0; 池[sym] = (o, hh, ll, cc, A4, np.where(ok)[0], H.index)
        print(sym, "小时线", str(H.index[0].date()), "~", str(H.index[-1].date()), "箱子", sum(1 for b in 箱表 if b["sym"] == sym), "默认笔数", sum(1 for x in allT["默认"] if x["sym"] == sym), flush=True)
    for nm, T in allT.items(): pd.DataFrame(T).to_csv(os.path.join(OUT, f"逐笔_{nm}.csv"), index=False)
    pd.DataFrame(箱表).to_csv(os.path.join(OUT, "箱子.csv"), index=False); pd.to_pickle(池, os.path.join(OUT, "池.pkl")); print("DONE")
