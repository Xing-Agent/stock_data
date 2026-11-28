# -*- coding: utf-8 -*-
"""《570》第二批 · 做空组合 · 跑批入口 · 引擎外。美股 2022-01-01 以后不读（读进来立刻切到 2021-12-31）；加密不封。
用法：python 跑组合_1128.py 指数   → SPY/QQQ/IWM/SOXX 日线（各自上市起~2021）
      python 跑组合_1128.py 币     → BTC/ETH 日线 + 4 小时线（2017~2026-11）
      python 跑组合_1128.py 个股   → 2005~2021 每年按上一年成交额前 300 的普通股，日线（并池2004修接缝面板）
每个都跑「默认 + 相邻三档」，逐个形态写 csv，汇总另一个脚本做。"""
import os, sys, json, importlib.util, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
C = mod("核心", os.path.join(HERE, "组合核心_1128.py"))
封 = pd.Timestamp("2021-12-31 23:59")

档位 = [("默认", {}), ("容差0.5", {"容差": 0.5}), ("容差1.5", {"容差": 1.5}), ("κ0.6", {"κ": 0.6}), ("κ1.0", {"κ": 1.0}),
        ("LB120", {"LB": 120}), ("LB500", {"LB": 500}), ("止损反抽高", {"止损法": "反抽高"}), ("分形3", {"N": 3}), ("分形8", {"N": 8})]


def 美股日线(sym):
    if sym == "SOXX": f = os.path.join(ROOT, "market_ext_1105/SOXX_1123/日线/SOXX_日线.csv")
    elif sym in ("SPY", "QQQ"): f = os.path.join(ROOT, f"market_ext_1105/指数ETF_1993起_1122/{sym}_日线_1993起.csv")
    else: f = os.path.join(ROOT, f"market_ext_1105/ETF和币_1120/日线/{sym}_日线.csv")
    y = pd.read_csv(f, parse_dates=["date"]).set_index("date").loc[:封]
    D = pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna()
    if sym in ("SPY", "QQQ"):        # 1993 起那份到 2003-09，后面接 Polygon（同 五档状态机_第四版 的接法）
        z = pd.read_csv(os.path.join(ROOT, f"market_ext_1105/ETF和币_1120/日线/{sym}_日线.csv"), parse_dates=["date"]).set_index("date").loc[:封]
        b = pd.DataFrame({"open": z.open_adj, "high": z.high_adj, "low": z.low_adj, "close": z.close_adj, "volume": z.volume_adj}).dropna()
        D = pd.concat([D, b[b.index > D.index[-1]]]).sort_index()
    return D.loc[:封]


def 大势(D):
    """收在 200 日线下且 50 日线在 200 日线下；shift(1) = 用前一天收盘判。"""
    s50, s200 = D.close.rolling(50).mean(), D.close.rolling(200).mean()
    return ((D.close < s200) & (s50 < s200)).shift(1).fillna(False).astype(bool)


def 到根(日开关, idx):
    """日线开关 → 任意 K 线（4 小时）：这一根所在那天的开关（开关本身已是前一天收盘判的）。"""
    d = pd.DatetimeIndex(idx).normalize(); return pd.Series(日开关.reindex(d).fillna(False).to_numpy(bool), index=idx)


def 币日线(sym):
    fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/币_小时线_Coinbase/*.parquet")))
    d = pd.concat([pd.read_parquet(f, filters=[("symbol", "==", sym)]) for f in fs]); d["t"] = pd.to_datetime(d.time_utc, utc=True).dt.tz_localize(None)
    H = d.set_index("t").sort_index(); H = pd.DataFrame({"open": H.open_adj, "high": H.high_adj, "low": H.low_adj, "close": H.close_adj, "volume": H.volume_adj}).dropna(); H = H[~H.index.duplicated()]
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    n = H.resample("1D").size(); D = H.resample("1D").agg(agg).dropna(); D = D[n.reindex(D.index) >= 20]
    X4 = H.resample("4h").agg(agg).dropna(); return D, X4


def 跑一组(名单, 档名, P, tag):
    """名单：[(sym, X(已指标), 大势布尔, 大盘收盘序列)]"""
    rows = []
    for sym, X, reg, mk in 名单:
        df = C.扫(sym, X, reg, P)
        if len(df): rows.append(df)
    df = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()
    df.to_csv(os.path.join(OUT, f"{tag}_{档名}_形态.csv"), index=False); return df


def 池(名单, 额外=None):
    """随机对照的池：满足大势向下（个股另加自己在 200 日线下）的根。"""
    p = {}
    for sym, X, reg, mk in 名单:
        ok = reg.to_numpy(bool) & (X.atr.to_numpy() > 0)
        if 额外 is not None: ok &= 额外[sym]
        ok[:30] = False; ok[-2:] = False; ix = np.where(ok)[0]
        if len(ix): p[sym] = (X.open.to_numpy(float), X.high.to_numpy(float), X.low.to_numpy(float), X.close.to_numpy(float), X.atr.to_numpy(float), ix)
    return p


if __name__ == "__main__":
    which = sys.argv[1]
    if which == "指数":
        spy = 美股日线("SPY"); 势 = 大势(spy); 名单 = []
        for s in ("SPY", "QQQ", "IWM", "SOXX"):
            X = C.指标(美股日线(s)); 名单.append((s, X, 势.reindex(X.index).fillna(False).astype(bool), spy.close))
        for nm, P in 档位: 跑一组(名单, nm, P, "指数日线"); print("指数", nm, flush=True)
        json.dump({"改掉的坏点根数": C.坏点["根数"]}, open(os.path.join(OUT, "指数_坏点.json"), "w"))
        pd.to_pickle(池(名单), os.path.join(OUT, "指数日线_池.pkl")); spy.close.to_pickle(os.path.join(OUT, "SPY收盘.pkl"))
    if which == "币":
        BD, B4 = 币日线("BTC"); ED, E4 = 币日线("ETH"); 势 = 大势(BD)
        for 级, 名单 in (("币日线", [("BTC", C.指标(BD), 势.reindex(BD.index).fillna(False).astype(bool), BD.close), ("ETH", C.指标(ED), 势.reindex(ED.index).fillna(False).astype(bool), BD.close)]),
                         ("币4小时", [("BTC", C.指标(B4), 到根(势, B4.index), B4.close), ("ETH", C.指标(E4), 到根(势, E4.index), B4.close)])):
            for nm, P in 档位:
                P2 = dict(P)
                if 级 == "币4小时": P2["N"] = {"分形3": 2, "分形8": 5}.get(nm, 3)     # 4 小时线分形默认左右各 3 根（同之前币的脚本），另试 2、5
                跑一组(名单, nm, P2, 级); print(级, nm, flush=True)
            pd.to_pickle(池(名单), os.path.join(OUT, f"{级}_池.pkl"))
        BD.close.to_pickle(os.path.join(OUT, "BTC日收盘.pkl")); B4.close.to_pickle(os.path.join(OUT, "BTC4小时收盘.pkl"))
    if which == "个股":
        import pyarrow.parquet as pq
        PAN = os.path.join(ROOT, "probe/基本面跑批_1106/并池2004修接缝_1108/ohlcv_panel_newpool.parquet")   # 本机用 烤并池2004修接缝_A路_1108.py 重烤（约 2 分钟，不入库）
        名单 = {}
        for y in range(2005, 2022):
            u = pd.read_csv(os.path.join(ROOT, f"universe_1107/universe_{y}.csv.gz")); u = u[u.type == "CS"].sort_values("avg_dollar_volume_60d_close", ascending=False); 名单[y] = list(u.ticker)
        cols = [c for c in pq.ParquetFile(PAN).schema_arrow.names if c != "date"]; 有 = {eval(c)[1] for c in cols}
        名单 = {y: [s for s in v if s in 有][:300] for y, v in 名单.items()}; 全 = sorted(set(sum(名单.values(), [])))
        print("个股名单合计", len(全), flush=True)
        want = [c for c in cols if eval(c)[0] in ("open", "high", "low", "close", "volume") and eval(c)[1] in set(全)]
        W = pd.read_parquet(PAN, columns=want + ["date"]) if "date" in pq.ParquetFile(PAN).schema_arrow.names else pd.read_parquet(PAN, columns=want)
        if "date" in W.columns: W = W.set_index("date")
        W.index = pd.to_datetime(W.index); W = W.loc[:封]; W.columns = pd.MultiIndex.from_tuples([eval(c) if isinstance(c, str) else c for c in W.columns])
        PANEL = {f: W[f].copy() for f in ("open", "high", "low", "close", "volume")}; del W
        sys.path.insert(0, ROOT); from engine import cache; cache._PANEL = PANEL          # 只借它的「内存里的面板」位置给折算脚本用，engine/ 文件不动
        FIX = mod("FIX", os.path.join(ROOT, "probe/含分红重出_1116/按表折算_1118.py")); FIX.窗口起 = "2003-01-01"; rep = FIX.install(); 拿 = set(FIX.要拿掉的票())
        json.dump({"折算了": len(rep["折算了"]), "拿掉的票": sorted(拿 & set(全))}, open(os.path.join(OUT, "个股_折算报告.json"), "w", encoding="utf-8"), ensure_ascii=False)
        spy = 美股日线("SPY"); 势 = 大势(spy); L = []; 额外 = {}
        for s in 全:
            if s in 拿: continue
            D = pd.DataFrame({f: PANEL[f][s] for f in ("open", "high", "low", "close", "volume")}).dropna()
            if len(D) < 260: continue
            X = C.指标(D); 自 = (X.close < X.s200).shift(1).fillna(False).astype(bool)
            yrs = [y for y, v in 名单.items() if s in v]; 在 = X.index.year.isin(yrs)
            reg = (势.reindex(X.index).fillna(False).astype(bool) & 自); L.append((s, X, reg, spy.close)); 额外[s] = np.asarray(在)
        print("能跑的", len(L), flush=True)
        for nm, P in 档位:
            df = 跑一组(L, nm, P, "个股日线_全")
            yrs = {s: set(y for y, v in 名单.items() if s in v) for s in 全}
            df = df[[pd.Timestamp(a).year in yrs[s] for s, a in zip(df.sym, df.确认)]] if len(df) else df
            df.to_csv(os.path.join(OUT, f"个股日线_{nm}_形态.csv"), index=False); print("个股", nm, len(df), flush=True)
        json.dump({"改掉的坏点根数": C.坏点["根数"]}, open(os.path.join(OUT, "个股_坏点.json"), "w"))
        pd.to_pickle(池(L, 额外), os.path.join(OUT, "个股日线_池.pkl")); json.dump(名单, open(os.path.join(OUT, "个股_每年名单.json"), "w"), ensure_ascii=False)
    print("DONE")
