# -*- coding: utf-8 -*-
"""打分器第二版原样搬到半导体 ETF（SOXX，1 小时线 2003-09 起）和 QQQ、SPY、SMH。规则、权重、扳机一个字没改。
档：用它自己的三层状态机第二版（涨势 / 跌势）；另记进场那天标普在不在跌势。
窗口 = 35 根 1 小时线（约 5 个交易日）和 70 根（约 10 个交易日）。锁数据：2022–2025 不看。
注意：美股一天只有 7 根常规时段的小时线，「拿满 240 小时」在这里 = 240 根 ≈ 34 个交易日，和币不是一个长度。"""
import os, sys, glob, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
V = mod("v2", os.path.join(HERE, "打分器_第二版_1124.py")); V1 = V.V1
S3 = mod("s3", os.path.join(ROOT, "probe/美股三层状态机_1123/三层状态机_第二版_1124.py")); LH = mod("lh", os.path.join(ROOT, "probe/美股三层状态机_1123/长历史_1124.py"))
def 小时(sym):
    d = os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线") if sym == "SOXX" else None
    fs = sorted(glob.glob(os.path.join(d, "*.parquet"))) if d else sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2004_2014/*.parquet")) + glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起/*.parquet")))
    x = pd.concat([pd.read_parquet(f) for f in fs]); x = x[x.symbol == sym] if "symbol" in x.columns else x
    if "session" in x.columns: x = x[x.session.astype(str).str.contains("regular|常规|RTH", case=False, regex=True)] if x.session.astype(str).str.contains("regular|常规|RTH", case=False, regex=True).any() else x
    x["t"] = pd.to_datetime(x.time_utc, utc=True).dt.tz_localize(None); x = x.set_index("t").sort_index()
    H = pd.DataFrame({"open": x.open_adj, "high": x.high_adj, "low": x.low_adj, "close": x.close_adj, "volume": x.volume_adj}).dropna(); return H[~H.index.duplicated()]
if __name__ == "__main__":
    spx = S3.跑(LH.读("标普500指数"))[0]["档"]; out = {}
    for sym in sys.argv[1:] or ["SOXX"]:
        H = 小时(sym); D = H.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
        st = S3.跑(D)[0]["档"]; 带 = V1.每天的带(H, D, st.reindex(D.index).fillna("涨势").to_numpy())
        # 每天的带 的键是「下一个自然日」，周五算出来的要挪到下周一用
        days = list(D.index); nxt = {days[i]: days[i + 1] for i in range(len(days) - 1)}
        带2 = {nxt[k - pd.Timedelta(days=1)]: v for k, v in 带.items() if (k - pd.Timedelta(days=1)) in nxt}
        o = {"小时线从": str(H.index[0].date()), "每天几根": round(len(H) / len(D), 1)}
        for N in (2, 3):
            nz = [sum(1 for z in b["zones"] if V.核心(z, N)) for b in 带2.values()]; o[f"跨{N}类_有核心带的天数占比pct"] = round(float(np.mean([x > 0 for x in nz]) * 100), 1)
            for trg, w in (("没过", 35), ("假突破", 35), ("假突破", 70)):
                T = V.开(V.回放(H, 带2, N=N, 扳机=trg, 窗=w)); C = V.开(pd.concat([V.回放(H, 带2, N=N, 扳机=trg, 窗=w, 挪=2.5), V.回放(H, 带2, N=N, 扳机=trg, 窗=w, 挪=-2.5)]))
                k = f"跨{N}类·{trg}" + (f"·窗{w}" if trg == "假突破" else "")
                if len(T):
                    T["大盘跌势"] = (spx.reindex(T.t.dt.normalize(), method="ffill") == "跌势").to_numpy(); T["段"] = np.where(T.t < "2015-01-01", "2003–2014", np.where(T.t < "2022-01-01", "2015–2021", "2026"))
                    T.to_csv(os.path.join(HERE, "out", f"美股_{sym}_{k}.csv"), index=False)
                o[k] = {"真": {c: V.S(T, c) for c in ("R_2R", "R_3R", "R_拿满")}, "对照": {c: V.S(C, c) for c in ("R_2R", "R_3R", "R_拿满")}}
                if len(T): o[k]["按段_3R"] = {a: V.S(g) for a, g in T.groupby("段")}; o[k]["按自己的档_3R"] = {a: V.S(g) for a, g in T.groupby("档")}; o[k]["按大盘_3R"] = {("大盘跌势" if a else "大盘不在跌势"): V.S(g) for a, g in T.groupby("大盘跌势")}
                a = o[k]["真"]["R_3R"]; print(sym, k, a.get("笔数"), a.get("每笔净R"), a.get("胜率pct"), a.get("去掉最赚3笔后"), a.get("t"), a.get("止损离进场pct_中位"), "|对照", o[k]["对照"]["R_3R"].get("笔数"), o[k]["对照"]["R_3R"].get("每笔净R"), "|段", {x: (v["笔数"], v.get("每笔净R")) for x, v in o[k].get("按段_3R", {}).items()}, "|档", {x: (v["笔数"], v.get("每笔净R")) for x, v in o[k].get("按自己的档_3R", {}).items()}, "|大盘", {x: (v["笔数"], v.get("每笔净R")) for x, v in o[k].get("按大盘_3R", {}).items()}, flush=True)
        out[sym] = o; json.dump(out, open(os.path.join(HERE, "out", f"美股_汇总_{'_'.join(sys.argv[1:] or ['SOXX'])}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
