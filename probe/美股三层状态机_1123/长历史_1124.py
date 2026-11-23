# -*- coding: utf-8 -*-
"""三层状态机放到长历史上（标普 1928 起、道指 1928 起、纳指综指 1971 起）—— 规则一个字没改，只是换了没见过的年份。
「真大顶」用客观办法找：两年新高之后，收盘从高点回落 ≥ 20%（和《425》的扫描同一个量法）。
早年只有收盘价的：高 = 低 = 开 = 收；没有成交量的周，「放量」这条算通过。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = importlib.util.spec_from_file_location("m", os.path.join(HERE, "三层状态机_1123.py")); M = importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
def 读(nm):
    x = pd.read_csv(os.path.join(ROOT, f"market_ext_1105/指数长历史_1123/{nm}_日线.csv"), parse_dates=["date"]).set_index("date")
    D = pd.DataFrame({"open": x.open, "high": x.high, "low": x.low, "close": x.close, "volume": x.volume})
    for c in ("open", "high", "low"): D[c] = D[c].fillna(D.close)
    D["volume"] = D.volume.fillna(0.0); D = D[D.index.dayofweek < 5]; return D.dropna(subset=["close"])
def 真顶(c, th=0.20):
    T = []; pk = c.iloc[0]; pki = 0; mode = "up"; tr = None; tri = None
    for i in range(1, len(c)):
        x = c.iloc[i]
        if mode == "up":
            if x > pk: pk = x; pki = i
            elif x <= pk * (1 - th): mode = "dn"; tr = x; tri = i
        else:
            if x < tr: tr = x; tri = i
            elif x > pk or x >= tr * (1 + th / (1 - th) * 0.5):
                T.append((pki, tri)); mode = "up"; pk = x; pki = i
    if mode == "dn": T.append((pki, tri))
    return [(a, b) for a, b in T if c.iloc[a] >= c.iloc[max(0, a - 504):a + 1].max() * 0.999]
def 评(D, 段=None, **kw):
    R, EV = M.跑(D, **kw); c = D.close; idx = D.index; tops = 真顶(c)
    转空 = [e for e in EV if e["事"].startswith(("转空", "复跌"))]; used = set(); rows = []
    for a, b in tops:
        ta, tb = str(idx[a].date()), str(idx[b].date()); x = [e for e in 转空 if ta <= e["日期"] <= tb]
        r = {"顶": ta, "底": tb, "跌幅pct": round((c.iloc[b] / c.iloc[a] - 1) * 100, 1), "顶到底天": int((idx[b] - idx[a]).days)}
        if x:
            e = x[0]; used |= {y["日期"] for y in x}; r.update({"认出": e["日期"], "怎么认的": e["事"], "离顶pct": round((e["收盘"] / c.iloc[a] - 1) * 100, 1), "离底还有pct": round((c.iloc[b] / e["收盘"] - 1) * 100, 1)})
        else: r.update({"认出": "没认出"})
        y = [e for e in EV if e["事"].startswith("跟进日·") and e["日期"] >= tb][:1]; g = [e for e in EV if e["事"].startswith("大底确认") and e["日期"] >= tb][:1]
        lim = str((idx[b] + pd.Timedelta(days=500)).date())
        r["底·试仓"] = f"{y[0]['日期']}（+{y[0]['收盘'] / c.iloc[b] * 100 - 100:.0f}%）" if y and y[0]["日期"] < lim and x else ""
        r["底·加满"] = f"{g[0]['日期']}（+{g[0]['收盘'] / c.iloc[b] * 100 - 100:.0f}%）" if g and g[0]["日期"] < lim and x else ""
        rows.append(r)
    虚 = []
    for e in 转空:
        if e["日期"] in used: continue
        t = pd.Timestamp(e["日期"]); seg = R.loc[t:]; end = seg[seg["档"] == "涨势"].index[:1]; end = end[0] if len(end) else R.index[-1]
        虚.append({"日期": e["日期"], "怎么认的": e["事"], "之后最多再跌pct": round((c.loc[t:end].min() / e["收盘"] - 1) * 100, 1)})
    ft = sum(1 for e in EV if e["事"].startswith("跟进日·")); fl = sum(1 for e in EV if e["事"].startswith("跟进日失败"))
    return pd.DataFrame(rows), pd.DataFrame(虚), {"跟进日": ft, "失败": fl, "小顶预警": sum(1 for e in EV if e["事"] == "小顶预警")}, R, EV
if __name__ == "__main__":
    out = {}
    for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
        D = 读(nm); out[nm] = {}
        for v, kw in (("主版", {}), ("两样都放宽", {"要ST或UT": False, "BC严": False})):
            T, F, o, R, EV = 评(D, **kw)
            旧 = T[T["顶"] < "1993"]; 新 = T[T["顶"] >= "1993"]
            def 概(x): 
                y = x[x["认出"] != "没认出"]
                return {"真大顶": int(len(x)), "认出": int(len(y)), "认出时离顶pct_中位": float(y["离顶pct"].median()) if len(y) else None, "认出时离底还有pct_中位": float(y["离底还有pct"].median()) if len(y) else None}
            Fo = F[F["日期"] < "1993"] if len(F) else F; Fn = F[F["日期"] >= "1993"] if len(F) else F
            out[nm][v] = {"1993以前": {**概(旧), "别的转空": int(len(Fo)), "其中之后再跌不到10pct": int((Fo["之后最多再跌pct"] > -10).sum()) if len(Fo) else 0}, "1993以后": {**概(新), "别的转空": int(len(Fn)), "其中之后再跌不到10pct": int((Fn["之后最多再跌pct"] > -10).sum()) if len(Fn) else 0}, **o}
            T.to_csv(os.path.join(HERE, "out", f"长历史_{nm}_{v}_每个大顶.csv"), index=False); F.to_csv(os.path.join(HERE, "out", f"长历史_{nm}_{v}_别的转空.csv"), index=False)
            print("==", nm, v, json.dumps(out[nm][v], ensure_ascii=False)); 
            if v == "主版" or nm == "标普500指数": print(T.to_string()); 
            if nm == "标普500指数": print(F.to_string())
            if nm == "标普500指数": M.画(R, EV, f"标普1928起_{v[:2]}")
    json.dump(out, open(os.path.join(HERE, "out", "长历史_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
