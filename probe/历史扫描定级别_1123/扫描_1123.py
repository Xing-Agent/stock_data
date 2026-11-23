# -*- coding: utf-8 -*-
"""先扫历史定级别（《423 拍板》第一节、要干啥 1）· 引擎外
每个标的：找出历史上的大顶大底（从顶到底跌幅 ≥ 门槛：大指数 20%、行业 ETF 25%、币 50%），量：
  顶部横了多久 = 最高点前后，收盘一直待在「最高点 × (1 − 带宽)」以上的那一段有多少天（带宽 = 2 × 过去 2 年周线波幅占价格比例的中位数 R）
  从顶到底跌多少、用了多少天；见顶后第一个月（21 个交易日，币 30 天）跌多少
  有没有二次确认 = 跌破顶部带下沿之后，有过一次反弹回到带下沿的 3% 以内（或收复这段跌幅的 38.2% 以上）、之后又创新低
  牛市里正常回调多深 = 没发展成大顶的那些回调（从新高回落 ≥ 5% 再创新高）的 90% 分位
定级别（Gemini 的规则，原样）：顶部横盘中位数 < 35 天 → 日线；35~80 → 周线；> 80 → 月线；见顶后第一个月跌超 20% 的降一级；牛市回调 90% 分位不到 12% 的升一级。
★ 「顶部横了多久」「二次确认」的量法是我定的，Gemini 没给；天数按日历天。"""
import os, sys, glob, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/大周期五档_1123"))
import importlib.util
sp = importlib.util.spec_from_file_location("m4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); M = importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
def etf(sym):
    y = pd.read_csv(os.path.join(ROOT, f"market_ext_1105/ETF和币_1120/日线/{sym}_日线.csv"), parse_dates=["date"]).set_index("date")
    return pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna()
def soxx():
    y = pd.read_csv(os.path.join(ROOT, "market_ext_1105/SOXX_1123/日线/SOXX_日线.csv"), parse_dates=["date"]).set_index("date")
    return pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna()
LV = ["日线", "周线", "月线"]

def 扫(D, 门槛, 币=False):
    c = D.close; idx = D.index
    W = D.resample("W").agg({"high": "max", "low": "min", "close": "last"}).dropna(); wpc = W.close.shift()
    watr = (pd.concat([W.high - W.low, (W.high - wpc).abs(), (W.low - wpc).abs()], axis=1).max(axis=1).rolling(14).mean() / W.close)
    R = watr.rolling(104, min_periods=40).median().reindex(idx, method="ffill")
    # 之字形：按收盘，从顶回落 ≥ 门槛 记一个大顶；从底反弹 ≥ 门槛 / (1 − 门槛) 记一个大底（也就是涨回到原来的位置）
    tops = []; pk = c.iloc[0]; pki = 0; tr = None; tri = None; mode = "up"
    for i in range(1, len(c)):
        x = c.iloc[i]
        if mode == "up":
            if x > pk: pk = x; pki = i
            elif x <= pk * (1 - 门槛): mode = "dn"; tr = x; tri = i
        else:
            if x < tr: tr = x; tri = i
            elif x >= tr * (1 + 门槛 / (1 - 门槛) * 0.5) or x > pk:
                tops.append((pki, tri)); mode = "up"; pk = x; pki = i
    if mode == "dn": tops.append((pki, tri))
    rows = []
    for pki, tri in tops:
        P = c.iloc[pki]; r = R.iloc[pki]; 
        if not (r > 0): r = float(watr.dropna().iloc[:60].median()) if len(watr.dropna()) else 0.03
        band = P * (1 - 2 * r)
        a = pki
        while a > 0 and c.iloc[a - 1] >= band: a -= 1
        b = pki
        while b < tri and c.iloc[b + 1] >= band: b += 1
        pre = c.iloc[max(0, pki - (730 if 币 else 504)):pki + 1]; a2 = pki - (len(pre) - 1 - int(np.argmax(pre.values >= band))) if (pre.values >= band).any() else pki
        post = c.iloc[pki:tri + 1]; b2 = pki + int(np.max(np.where(post.values >= band)[0]))
        是新高顶 = bool(P >= c.iloc[max(0, pki - (730 if 币 else 504)):pki + 1].max() * 0.999)
        seg = c.iloc[b:tri + 1]; low_sofar = seg.cummin()
        二次 = False
        for k in range(1, len(seg)):
            if (seg.iloc[k] >= band * 0.97 or (seg.iloc[k] - low_sofar.iloc[k - 1]) >= 0.382 * (P - low_sofar.iloc[k - 1])) and seg.iloc[k:].min() < low_sofar.iloc[k - 1] and (P - low_sofar.iloc[k - 1]) / P >= 门槛 * 0.4: 二次 = True; break
        m1 = min(len(c) - 1, pki + (30 if 币 else 21))
        rows.append({"顶": str(idx[pki].date()), "顶价": round(float(P), 2), "底": str(idx[tri].date()), "底价": round(float(c.iloc[tri]), 2), "跌幅pct": round((c.iloc[tri] / P - 1) * 100, 1),
                     "顶到底天": int((idx[tri] - idx[pki]).days), "顶部横了几天": int((idx[b] - idx[a]).days), "顶部横了几天_宽算": int((idx[b2] - idx[a2]).days), "是两年新高的顶": 是新高顶, "见顶后第一个月pct": round((c.iloc[m1] / P - 1) * 100, 1), "有二次确认": 二次, "带宽pct": round(2 * r * 100, 1)})
    # 牛市里的正常回调
    dd = c / c.cummax() - 1; ep = []; cur = 0.0
    for v in dd.values:
        if v == 0:
            if cur <= -0.05: ep.append(cur)
            cur = 0.0
        else: cur = min(cur, v)
    ep = [x for x in ep if x > -门槛]
    T0 = pd.DataFrame(rows); T = T0[T0["是两年新高的顶"]] if len(T0) else T0      # 只拿「两年新高的顶」定级别；熊市里的反弹高点不算大顶
    out = {"大顶次数": len(T), "顶部横盘天_宽算_中位": float(T["顶部横了几天_宽算"].median()) if len(T) else None, "顶部横盘天_中位": float(T["顶部横了几天"].median()) if len(T) else None, "见顶后第一个月pct_中位": float(T["见顶后第一个月pct"].median()) if len(T) else None,
           "有二次确认的占比": f"{int(T['有二次确认'].sum())}/{len(T)}" if len(T) else "", "跌幅pct_中位": float(T["跌幅pct"].median()) if len(T) else None, "顶到底天_中位": float(T["顶到底天"].median()) if len(T) else None,
           "牛市回调_次数": len(ep), "牛市回调_90分位pct": round(float(np.percentile(ep, 10)) * 100, 1) if ep else None, "R_周波幅pct_现在": round(float(R.iloc[-1]) * 100, 2)}
    if len(T):
        d = out["顶部横盘天_中位"]; lv = 0 if d < 35 else (1 if d <= 80 else 2); 基 = lv
        if out["见顶后第一个月pct_中位"] < -20: lv -= 1
        if out["牛市回调_90分位pct"] is not None and out["牛市回调_90分位pct"] > -12: lv += 1
        d2 = out["顶部横盘天_宽算_中位"]; lv2 = (0 if d2 < 35 else (1 if d2 <= 80 else 2)) + (lv - 基)
        out["按横盘天数"] = LV[基]; out["级别"] = LV[max(0, min(2, lv))]; out["级别_宽算"] = LV[max(0, min(2, lv2))]; out["最短横盘周_0.40除以R"] = round(min(24, max(4, 0.40 / (out["R_周波幅pct_现在"]))), 1) if out["R_周波幅pct_现在"] else None
    return out, T0

if __name__ == "__main__":
    S = {"SPY": (M.美股日线("SPY"), 0.20, False), "QQQ": (M.美股日线("QQQ"), 0.20, False), "DIA": (etf("DIA"), 0.20, False), "IWM": (etf("IWM"), 0.20, False), "SOXX": (soxx(), 0.25, False)}
    for s in ("SMH", "XLK", "XLF", "XLE", "XLV", "XLY", "XLI", "XLP", "XLU", "XLB", "KRE"): S[s] = (etf(s), 0.25, False)
    for s in ("BTC", "ETH", "SOL"):
        D = M.币日线(s)
        if s == "SOL":
            tc = [x for x in D.columns if x.lower() in ("date", "t", "time_utc", "time")][0] if not isinstance(D.index, pd.DatetimeIndex) else None
            if tc: D = D.set_index(pd.to_datetime(D[tc]).dt.tz_localize(None) if hasattr(pd.to_datetime(D[tc]).dt, "tz") and pd.to_datetime(D[tc]).dt.tz is not None else pd.to_datetime(D[tc]))
            D = D.rename(columns={x: x.replace("_adj", "") for x in D.columns})[["open", "high", "low", "close", "volume"]].astype(float).sort_index()
        S[s] = (D, 0.50, True)
    res = {}; allT = []
    for s, (D, th, coin) in S.items():
        try:
            o, T = 扫(D, th, coin); o["数据从"] = str(D.index[0].date()); res[s] = o; T.insert(0, "标的", s); allT.append(T)
        except Exception as e: res[s] = {"失败": repr(e)}
    json.dump(res, open(os.path.join(HERE, "out", "定级别.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    pd.concat(allT).to_csv(os.path.join(HERE, "out", "每个大顶.csv"), index=False)
    print(pd.DataFrame(res).T.drop(columns=["R_周波幅pct_现在"], errors="ignore").to_string())
    A = pd.concat(allT); print(A[A["标的"].isin(["SPY", "QQQ", "SOXX", "BTC"]) & A["是两年新高的顶"]].drop(columns=["是两年新高的顶","底价","带宽pct"]).to_string())
