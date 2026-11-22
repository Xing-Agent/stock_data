# -*- coding: utf-8 -*-
"""《396》第一件 · 备数：把三类标的的日线压成一份份紧凑数组（引擎外，engine/ 不动）。
  · 大指数 SPY QQQ DIA IWM、行业 ETF 13 只：market_ext_1105/ETF和币_1120/日线，只折拆股的 *_adj 价（不算分红），
    坏高低价照 probe/波段做空_1121/圣杯空头版_日线_1121.py 的 load() 处理（离开收盘 20% 以上拉回）、XLF 2016-09-19 接缝照接。
  · 个股（研究库）：probe/两段时间_1120/环境2004_1120.py 的 install() 装好的面板（2004–2026，已折算拆股），
    只取《holdout_newpool_1106.json》的「研发池名单」（和《389》同口径），留出池 583 只一只不碰（断言）。
  · 个股（退市股）：market_ext_1105/退市股日线_1121/，用 *_adj 价；「高低价可疑的日子.csv」里那些天把最高 / 最低拉回到开收盘；
    已在面板里的代码、留出池代码都不要。
  · 个股另加一道通用坏点处理（同 probe/派发顶_1121/两段认法_1121.py）：最高 > 开收盘较高者 ×1.5、最低 < 较低者 ×0.5 的拉回。
  · 流动性池：每只票自己算，规则同 probe/两段时间_1120/环境2004_1120.py 的 流动性池()「中」档：
    季度第一个交易日调一次，用前一天的值：收盘 ≥ 5 美元、20 日平均成交额 ≥ 1000 万美元、至少 60 根；已在池里的放宽到 4 美元 / ×0.8。
    ★ 我补的：2015–2025 那份掩膜（probe/流动性池_1114/流动性池掩膜_中.parquet）不在仓库里，所以两段都用同一条规则现算；
      2005–2014 段和 流动性池掩膜2004_中.parquet 对过账（结果写在 cache/备数报告.json）。
输出：cache/{指数,行业,个股_研究库,个股_退市股}.npz（不入库）。
"""
import os, io, sys, json, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "cache"); os.makedirs(OUT, exist_ok=True)
指数 = ["SPY", "QQQ", "DIA", "IWM"]
行业 = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH", "KRE"]
D0 = np.datetime64("1970-01-01")


def 流动性(dates, c, v):
    """每只票自己的季度流动性池（中档）。dates: datetime64[D]；返回 bool 数组。"""
    n = len(c); adv = pd.Series(c * v).rolling(20, min_periods=20).mean().to_numpy()
    q = pd.DatetimeIndex(dates).year * 4 + pd.DatetimeIndex(dates).quarter
    out = np.zeros(n, bool); cur = False
    for i in range(1, n):
        if q[i] != q[i - 1]:
            cc, aa, nb = c[i - 1], adv[i - 1], i          # i 根 = 到前一天为止的根数
            if cur: cur = (cc >= 4.0) and (aa >= 0.8e7) and (nb >= 60)
            else: cur = (cc >= 5.0) and (aa >= 1e7) and (nb >= 60)
            cur = bool(cur) and np.isfinite(cc) and np.isfinite(aa)
        out[i] = cur
    return out


def 清坏点(o, h, l, c, 倍高=1.5, 倍低=0.5):
    top, bot = np.maximum(o, c), np.minimum(o, c)
    bh, bl = h > top * 倍高, l < bot * 倍低
    h = np.where(bh, top, h); l = np.where(bl, bot, l)
    return h, l, int(bh.sum() + bl.sum())


def 存(name, rows):
    syms = [r[0] for r in rows]; lens = np.array([len(r[1]) for r in rows]); off = np.concatenate([[0], np.cumsum(lens)])
    cat = lambda k: np.concatenate([r[k] for r in rows]) if rows else np.zeros(0)
    np.savez(os.path.join(OUT, name + ".npz"), syms=np.array(syms), off=off, d=cat(1).astype("int64"),
             o=cat(2), h=cat(3), l=cat(4), c=cat(5), v=cat(6), ok=cat(7), delisted=np.array([r[8] for r in rows]))
    return {"只数": len(rows), "行数": int(off[-1])}


def etf(sym):
    d = pd.read_csv(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线", sym + "_日线.csv"), parse_dates=["date"]).set_index("date").sort_index()
    x = pd.DataFrame({"o": d.open_adj, "h": d.high_adj, "l": d.low_adj, "c": d.close_adj, "v": d.volume_adj}).dropna()
    top, bot = x[["o", "c"]].max(axis=1), x[["o", "c"]].min(axis=1)
    bh, bl = x.h > top * 1.2, x.l < bot * 0.8
    x.loc[bh, "h"] = top[bh]; x.loc[bl, "l"] = bot[bl]
    if sym == "XLF":
        t = pd.Timestamp("2016-09-19"); i = x.index.get_loc(t); k = x.c.iloc[i] / x.c.iloc[i - 1]
        x.loc[x.index < t, ["o", "h", "l", "c"]] *= k
    dd = x.index.values.astype("datetime64[D]")
    return (sym, (dd - D0).astype("int64"), x.o.values, x.h.values, x.l.values, x.c.values, x.v.values, np.ones(len(x), bool), False)


def main():
    rep = {}
    rep["指数"] = 存("指数", [etf(s) for s in 指数]); rep["行业"] = 存("行业", [etf(s) for s in 行业])
    # ---- 研究库个股 ----
    sys.path.insert(0, os.path.join(ROOT, "probe/两段时间_1120")); sys.path.insert(0, ROOT)
    import 环境2004_1120 as E
    info = E.install()
    from engine import cache
    P = cache._PANEL
    hold = json.load(io.open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
    hs = set(hold["留出池名单"]); drop = set(info["拿掉"])
    dev = [s for s in hold["研发池名单"] if s in P["close"].columns and s not in drop]
    assert not (set(dev) & hs)
    idx = P["close"].index; last_day = idx[-1]
    F = {k: P[k][dev].astype("float64") for k in ("open", "high", "low", "close", "volume")}
    del cache._PANEL; import gc; gc.collect()
    rows = []; 坏 = 0; 对账 = []
    m04 = pd.read_parquet(os.path.join(ROOT, "probe/两段时间_1120/流动性池掩膜2004_中.parquet"))
    for s in dev:
        x = pd.DataFrame({k: F[k][s] for k in F}).dropna(subset=["close"])
        x = x[(x["close"] > 0)]
        if len(x) < 300: continue
        o, h, l, c, v = (x[k].to_numpy() for k in ("open", "high", "low", "close", "volume"))
        o = np.where(np.isfinite(o), o, c); h = np.where(np.isfinite(h), np.maximum(h, c), c); l = np.where(np.isfinite(l), np.minimum(l, c), c); v = np.nan_to_num(v)
        h, l, nb = 清坏点(o, h, l, c); 坏 += nb
        dd = x.index.values.astype("datetime64[D]"); ok = 流动性(dd, c, v)
        if s in m04.columns and len(对账) < 400:
            a = pd.Series(ok, index=x.index).reindex(m04.index).fillna(False).to_numpy(); b = m04[s].to_numpy()
            对账.append((a == b).mean())
        rows.append((s, (dd - D0).astype("int64"), o, h, l, c, v, ok, bool(x.index[-1] < last_day - pd.Timedelta(days=30))))
    rep["个股_研究库"] = {**存("个股_研究库", rows), "坏点拉回": 坏, "研发池名单": len(hold["研发池名单"]), "面板上有的": len(dev),
                       "流动性池和2004中档掩膜逐日一致率(抽400只)": round(float(np.mean(对账)), 4) if 对账 else None}
    have = set(P_cols := list(F["close"].columns)) | set(hold["研发池名单"]) | hs
    del F; gc.collect()
    # ---- 退市股 ----
    dl = os.path.join(ROOT, "market_ext_1105/退市股日线_1121")
    bad = pd.read_csv(os.path.join(dl, "高低价可疑的日子.csv")); badset = set(zip(bad["代码"], bad["日期"]))
    tb = pd.read_csv(os.path.join(dl, "总表.csv")); how = dict(zip(tb["代码"], tb["怎么退的"]))
    rows = []; 跳 = {"已在面板或池里": 0, "太短": 0}; 清 = 0
    for f in sorted(glob.glob(os.path.join(dl, "退市于*.parquet"))):
        t = pd.read_parquet(f, columns=["symbol", "date", "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"])
        for s, x in t.groupby("symbol", sort=False):
            base = s.split("__")[0]
            if s in have or base in hs: 跳["已在面板或池里"] += 1; continue
            x = x.dropna(subset=["close_adj"]).sort_values("date"); x = x[x.close_adj > 0]
            if len(x) < 300: 跳["太短"] += 1; continue
            o, h, l, c, v = (x[k].to_numpy(float) for k in ("open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"))
            ds = pd.to_datetime(x["date"]).dt.strftime("%Y-%m-%d").to_numpy()
            m = np.array([(s, d_) in badset for d_ in ds])
            if m.any():
                h = np.where(m, np.maximum(o, c), h); l = np.where(m, np.minimum(o, c), l); 清 += int(m.sum())
            o = np.where(np.isfinite(o), o, c); h = np.where(np.isfinite(h), np.maximum(h, c), c); l = np.where(np.isfinite(l), np.minimum(l, c), c); v = np.nan_to_num(v)
            h, l, _ = 清坏点(o, h, l, c)
            dd = pd.to_datetime(x["date"]).values.astype("datetime64[D]")
            rows.append((s, (dd - D0).astype("int64"), o, h, l, c, v, 流动性(dd, c, v), True))
    rep["个股_退市股"] = {**存("个股_退市股", rows), "跳过": 跳, "按清单拉回的天数": 清}
    json.dump(rep, io.open(os.path.join(OUT, "备数报告.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(rep, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
