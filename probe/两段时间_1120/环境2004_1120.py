# -*- coding: utf-8 -*-
"""第二段时间（2005–2014）的跑批环境（2026-11-20 · Lin：两段时间都要跑）

大白话：把回测搬到 2005-01-03 → 2014-12-31 这十年（里面有 2008 年的慢熊）。engine/ 没碰，全部是在内存里换数据：
  · 行情面板：probe/并池2004_1107（3,858 只，2004 年起，修过接缝的那张）
  · 指数：数据组 11-20 交的 SPY / RSP / QQQ / IWM 长历史（2003-09-10 起），内存里替换 data.load_benchmark；
          其它代码（VIX 等）走 11-07 那个「接新基准」
  · 拆股并股：按数据组全池版并股表在内存里折算（含正向拆股），代码断过档的票拿掉
  · 票的范围：并池里除了留出池 583 只以外的全部
  · 流动性池：和 2015–2025 同一条规则在这张面板上重建（收盘 ≥ 5 美元、20 日平均成交额 ≥ 门槛、≥ 60 根，季度调，留池缓冲 4 美元 / ×0.8）
⚠ 门槛的美元数没按年代调整：1000 万美元在 2005 年比在 2020 年更严，所以这一段的池子更小、更偏大票。
⚠ 热机：面板 2004-01-02 才开始，200 日线要一年才有，所以成绩从 2005-01-03 算起，是 10 年不是 11 年。
⚠ 这一段没有财报库，只能跑技术面策略。
"""
import io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PANEL = os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet")
POOLCSV = os.path.join(ROOT, "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv")
IDXDIR = os.path.join(ROOT, "market_ext_1105/指数ETF长历史_1120")
START, END = "2005-01-03", "2014-12-31"
门槛 = {"低": 5e6, "中": 1e7, "高": 2e7}


def install(只留测试期=False):
    sys.path.insert(0, ROOT)
    for d in ("probe/基本面跑批_1106", "probe/并池_1107", "probe/含分红重出_1116"):
        sys.path.insert(0, os.path.join(ROOT, d))
    import numpy as np, pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    from engine import cache, data, pool_scope
    wide = pd.read_parquet(PANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path=POOLCSV)
    data.PERF_START, data.PERF_END = START, END
    try:
        import 接新基准_1107 as BM; BM.install()
    except Exception as e:
        print("接新基准没装上：", repr(e)[:120])
    old = data.load_benchmark
    def lb(symbol):
        p = os.path.join(IDXDIR, f"{symbol}_日线.csv")
        if os.path.exists(p):
            d = pd.read_csv(p, parse_dates=["date"]).set_index("date")
            return pd.DataFrame({"open": d.open_adj, "high": d.high_adj, "low": d.low_adj, "close": d.close_adj, "volume": d.volume_adj})
        return old(symbol)
    data.load_benchmark = lb
    import 补分红_1107 as DIV
    try: DIV.install()
    except Exception as e: print("补分红没装上：", repr(e)[:120])
    import 按表折算_1118 as FIX
    FIX.窗口起 = "2003-01-01"
    rep = FIX.install(); drop = set(FIX.要拿掉的票())
    if 只留测试期:      # ★ 省内存：折算做完以后，把 2015 年以后的行情切掉（整张面板到 2025，全留着建矩阵会把 8G 内存撑爆）
        cut = pd.Timestamp(END)
        cache._PANEL = {f: df.loc[:cut] for f, df in cache._PANEL.items()}
        _pm = cache.panel_meta
        def pm():       # 退市结算日落在切掉的那一段里的，在这一段看来就是「还没退市」
            m_ = _pm().copy(); z = pd.to_datetime(m_["zero_bar"], errors="coerce"); m_["zero_bar"] = z.where(z <= cut, pd.NaT); return m_
        cache.panel_meta = pm
    hold = json.load(io.open(os.path.join(ROOT, B.HOLD), encoding="utf-8")); hs = set(hold["留出池名单"])
    close = cache._PANEL["close"]
    dev = sorted(s for s in close.columns if s not in hs and s not in drop)
    return {"RC": RC, "dev": dev, "留出池": hs, "折算": {k: len(v) for k, v in rep.items()}, "拿掉": sorted(drop)}


def 流动性池(dev, 档="中"):
    """和 probe/流动性池_1114/建流动性池_1114.py 同一条规则，在这张面板上重建。返回 [日 × 票] 的布尔表（只含测试期）。"""
    import numpy as np, pandas as pd
    from engine import cache
    close = cache._PANEL["close"][dev].astype(float); vol = cache._PANEL["volume"][dev].astype(float)
    adv = (close * vol).rolling(20, min_periods=20).mean(); bars = close.notna().cumsum()
    idx = close.index; perf = idx[(idx >= pd.Timestamp(START)) & (idx <= pd.Timestamp(END))]
    q = pd.Series(perf.quarter, index=perf)
    调 = [perf[0]] + [d for d, a, b in zip(perf[1:], q.values[1:], q.values[:-1]) if a != b]
    T = 门槛[档]; mask = pd.DataFrame(False, index=perf, columns=dev); 在 = np.zeros(len(dev), bool); ns = []
    for k, d in enumerate(调):
        i = idx.get_loc(d); c, a, n = close.iloc[i - 1].to_numpy(), adv.iloc[i - 1].to_numpy(), bars.iloc[i - 1].to_numpy()
        进 = (c >= 5.0) & (a >= T) & (n >= 60); 留 = (c >= 4.0) & (a >= T * 0.8) & (n >= 60)
        在 = np.where(在, 留, 进) & np.isfinite(c)
        end = 调[k + 1] if k + 1 < len(调) else None
        seg = perf[(perf >= d) & ((perf < end) if end is not None else True)]
        mask.loc[seg] = 在; ns.append(int(在.sum()))
    return mask, {"调仓次数": len(调), "成分只数_最少_中位_最多": [min(ns), int(np.median(ns)), max(ns)]}


def 宽基(dev, mask):
    """同池子全买不动：季度等权、季内不动、含分红、不扣成本。"""
    import numpy as np, pandas as pd
    from engine import cache, data
    close = cache._PANEL["close"][dev].astype(float); idx = close.index; perf = mask.index
    dv = pd.DataFrame(0.0, index=idx, columns=dev)
    for s in dev:
        try:
            d = data.dividends(s)
            if len(d): dv[s] = d[~d.index.duplicated()].reindex(idx).fillna(0.0)
        except Exception: pass
    prev = close.shift(1); tr = ((close - prev + dv) / prev).replace([np.inf, -np.inf], np.nan).where(close.notna(), 0.0).fillna(0.0)
    chg = mask.ne(mask.shift()).any(axis=1); 调 = list(perf[chg.to_numpy()])
    eq = pd.Series(np.nan, index=perf); v = 1.0
    for k, d in enumerate(调):
        mem = mask.columns[mask.loc[d].to_numpy()]; end = 调[k + 1] if k + 1 < len(调) else None
        seg = perf[(perf >= d) & ((perf < end) if end is not None else True)]
        if len(mem) == 0: eq.loc[seg] = v; continue
        g = (1 + tr.loc[seg, mem]).copy(); g.iloc[0] = 1.0
        eq.loc[seg] = v * g.cumprod().mean(axis=1).values
        v = v * float((g.cumprod().iloc[-1] * (1 + tr.loc[end, mem])).mean()) if end is not None else float(eq.loc[seg].iloc[-1])
    yrs = (perf[-1] - perf[0]).days / 365.25; ann = float(eq.iloc[-1]) ** (1 / yrs) - 1; dd = float((eq / eq.cummax() - 1).min())
    return eq, {"复合年化pct": round(ann * 100, 2), "最大回撤pct": round(dd * 100, 2)}


if __name__ == "__main__":
    import numpy as np, pandas as pd
    env = install(); dev = env["dev"]; print("票", len(dev), "折算", env["折算"], "拿掉", len(env["拿掉"]))
    out = {"窗口": f"{START} → {END}", "票数": len(dev), "折算": env["折算"], "拿掉的票": env["拿掉"]}
    from engine import data
    perf = None
    for 档 in ("低", "中", "高"):
        mask, info = 流动性池(dev, 档); mask.to_parquet(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"流动性池掩膜2004_{档}.parquet"))
        eq, b = 宽基(dev, mask); out[f"池_{档}"] = {**info, "同池子全买不动": b}; perf = mask.index
        if 档 == "中": eq.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "宽基2004_中_日净值.csv"))
        print(档, info, b, flush=True)
    yrs = (perf[-1] - perf[0]).days / 365.25
    for s in ("SPY", "RSP"):
        d = pd.read_csv(os.path.join(IDXDIR, f"{s}_日线.csv"), parse_dates=["date"]).set_index("date")["adjusted_close"].reindex(perf).ffill()
        out[s] = {"复合年化pct": round(((d.iloc[-1] / d.iloc[0]) ** (1 / yrs) - 1) * 100, 2), "最大回撤pct": round(float((d / d.cummax() - 1).min()) * 100, 2)}
        print(s, out[s])
    io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "环境2004_报告_1120.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
