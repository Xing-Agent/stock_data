# -*- coding: utf-8 -*-
"""V 形反转：收回关键位 + 回踩确认（Lin 11-26 11:05 讲的做法）· 引擎外 · 只读 · 日线
Lin 原话大意：V 转的时候是小波快上扬（盘涨），关键是过关键位。没过关键位之前可以小额试空；一旦过了关键位，就要考虑回踩做多。
     做多的位置：先跌破、再收回，站上之前平台的低点；回踩确认时进第一单；盘涨往上过了下一个重要压力位再加仓。
我写成能算的（★ = 我补的数，不是 Lin 说的，要跑相邻三点）：
  摆动高低点：左右各 N 根（★ N=5，另试 3、8），要等右边第 N 根收盘才算数。
  关键位 K：价格创这一轮新低之前，最后一个被「收盘跌破」的摆动低点（= 被跌破的平台低点）。
  最低点 L0：跌破 K 之后的最低价。跌破要够深才算一轮（★ K 比 L0 高 ≥ 1 ATR，另试 0.5、2）。
  收回：收盘重新站上 K。收回那天记为 t1。
  回踩确认：t1 之后出现回落（至少 ★1 根收盘低于前一根），回落的最低点不低于 L0（没创新低），
           之后某天收盘高过回落前的最高收盘 → 确认，记为 t2。回踩最深可以回到 K 下方，只要不破 L0。
           t1 后 ★30 个交易日内没确认就作废（另试 20、45）。
  作废：任何时候收盘跌破 L0 → 这一轮作废，等下一轮。
  「V 转禁空」= 从 t1（收回关键位）起，到作废或到「这一轮结束」（★确认后 60 个交易日）为止。
做多测试：t2 那天收盘进；止损 = 回踩最低点 − 0.5 ATR；出场 = 止损 / 3R / 最多 60 根；成本单边 0.05%。
  对照：同品种、同时间段随机挑日子做多，止损距离用同样的百分比，各抽 20 个。
2022-01-01 ~ 2025-12-31 封存：单子单独存 out/封存_*.csv，不打印、不进统计。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, os.path.join(ROOT, f)); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
def 读(sym):
    if sym in ("BTC", "ETH"): return mod("m4", "probe/大周期五档_1123/五档状态机_第四版_1123.py").币日线(sym)[["open", "high", "low", "close"]]
    p = "market_ext_1105/SOXX_1123/日线/SOXX_日线.csv" if sym == "SOXX" else f"market_ext_1105/ETF和币_1120/日线/{sym}_日线.csv"
    y = pd.read_csv(os.path.join(ROOT, p), parse_dates=["date"]).set_index("date"); return pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj}).dropna()
def 找(D, N=5, 深=1.0, 等=30):
    o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(D); idx = D.index
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    lows = []; ev = []; 禁空 = np.zeros(n, bool); st = None                      # st: dict(K, L0, 阶段, t1, 回落低, 回落前高)
    for i in range(N * 2 + 20, n):
        k = i - N
        if l[k] == l[k - N:k + N + 1].min(): lows.append((k, l[k]))
        a = atr[i]
        if not (a > 0): continue
        if st is None:
            # 找最近一个被今天收盘跌破的摆动低点
            for (j, p) in reversed(lows[-6:]):
                if c[i] < p and c[i - 1] >= p: st = dict(K=p, Kj=j, L0=l[i], 阶段="跌破", 破=i); break
            continue
        if st["阶段"] == "跌破":
            st["L0"] = min(st["L0"], l[i])
            for (j, p) in reversed(lows[-6:]):                                   # 跌的过程中又跌破了更晚的平台低点 → 关键位换成更晚（更低）的那个
                if j > st["Kj"] and p < st["K"] and c[i] < p: st.update(K=p, Kj=j); break
            if c[i] > st["K"]:
                if st["K"] - st["L0"] >= 深 * a: st.update(阶段="收回", t1=i, 高=c[i], 回落=False, 回落低=np.inf)
                else: st = None
            elif i - st["破"] > 250: st = None
            continue
        if c[i] < st["L0"]: st = None; continue                                 # 创新低，作废
        if st["阶段"] == "收回":
            禁空[i] = True
            if c[i] < c[i - 1]: st["回落"] = True
            if st["回落"]: st["回落低"] = min(st["回落低"], l[i])
            if st["回落"] and c[i] > st["高"]:
                ev.append(dict(t1=idx[st["t1"]], t2=idx[i], K=st["K"], L0=st["L0"], 回踩低=st["回落低"], 进=c[i], atr=a, i=i)); st.update(阶段="确认", t2=i); continue
            if not st["回落"]: st["高"] = max(st["高"], c[i])
            if i - st["t1"] > 等: st = None
            continue
        if st["阶段"] == "确认":
            禁空[i] = True
            if i - st["t2"] >= 60: st = None
    return ev, pd.Series(禁空, index=idx), (o, h, l, c, atr)
def 做多(ev, arr, idx, sym, FEE=0.0005):
    o, h, l, c, atr = arr; n = len(c); R = []
    for e in ev:
        i = e["i"]; ent = c[i]; stop = e["回踩低"] - 0.5 * e["atr"]; r = ent - stop
        if r <= 0 or i + 1 >= n: continue
        out = None; end = min(n - 1, i + 60)
        for j in range(i + 1, end + 1):
            if l[j] <= stop: out = -(ent - min(o[j], stop)) / r; break
            if h[j] >= ent + 3 * r: out = 3.0; break
        if out is None: out = (c[end] - ent) / r
        R.append(dict(sym=sym, t=idx[i], t1=e["t1"], K=e["K"], L0=e["L0"], 进=ent, 止损=stop, 风险pct=r / ent * 100, R=out - 2 * FEE * ent / r, 后20天pct=(c[min(n - 1, i + 20)] / ent - 1) * 100, 后60天pct=(c[min(n - 1, i + 60)] / ent - 1) * 100,
                      收回到确认几天=i - list(idx).index(e["t1"]) if False else None))
    return pd.DataFrame(R)
def 随机(arr, idx, T, sym, 段, rng):
    o, h, l, c, atr = arr; n = len(c); out = []
    if not len(T): return np.nan, np.nan
    med = T.风险pct.median() / 100
    for (a, b) in 段:
        cand = [i for i in range(60, n - 61) if a <= idx[i] <= b]
        if not cand: continue
        for i in rng.choice(cand, size=min(len(cand), 20 * max(1, int(((T.t >= a) & (T.t <= b)).sum()))), replace=True):
            ent = c[i]; stop = ent * (1 - med); r = ent - stop; res = None
            for j in range(i + 1, i + 61):
                if l[j] <= stop: res = -(ent - min(o[j], stop)) / r; break
                if h[j] >= ent + 3 * r: res = 3.0; break
            if res is None: res = (c[i + 60] - ent) / r
            out.append(res - 2 * 0.0005 / med)
    return (float(np.mean(out)), float(np.mean(np.array(out) > 0))) if out else (np.nan, np.nan)
def S(x):
    if not len(x): return {"笔": 0}
    w = x.R; return {"笔": int(len(w)), "每笔R": round(float(w.mean()), 2), "胜率": round(float((w > 0).mean()), 2), "利润因子": round(float(w[w > 0].sum() / max(1e-9, -w[w <= 0].sum())), 2), "t": round(float(w.mean() / w.std() * np.sqrt(len(w))), 1) if len(w) > 2 and w.std() > 0 else None, "后20天中位pct": round(float(x.后20天pct.median()), 1), "后60天中位pct": round(float(x.后60天pct.median()), 1)}
if __name__ == "__main__":
    kw = {}
    for a in sys.argv[1:]:
        k_, v_ = a.split("="); kw[k_] = float(v_) if "." in v_ else int(v_)
    tag = "_".join(f"{k}{v}" for k, v in kw.items()) or "默认"; rng = np.random.default_rng(1126); res = {}; 全 = []
    for sym in ("QQQ", "SPY", "SOXX", "IWM", "BTC", "ETH"):
        D = 读(sym); ev, 禁, arr = 找(D, **kw); T = 做多(ev, arr, D.index, sym)
        禁.rename("V转禁空").to_csv(os.path.join(HERE, "out", f"禁空_{sym}_{tag}.csv"))
        lock = (T.t >= "2022-01-01") & (T.t <= "2025-12-31"); T[lock].to_csv(os.path.join(HERE, "out", f"封存_{sym}_{tag}.csv"), index=False); T = T[~lock]; T.to_csv(os.path.join(HERE, "out", f"单子_{sym}_{tag}.csv"), index=False); 全.append(T)
        币 = sym in ("BTC", "ETH"); segs = {"2017-2021": [(pd.Timestamp("2017-01-01"), pd.Timestamp("2021-12-31"))]} if 币 else {"2005-2014": [(pd.Timestamp("2005-01-01"), pd.Timestamp("2014-12-31"))], "2015-2021": [(pd.Timestamp("2015-01-01"), pd.Timestamp("2021-12-31"))]}
        o_ = {}
        for nm, sg in segs.items():
            x = T[(T.t >= sg[0][0]) & (T.t <= sg[0][1])]; m, w = 随机(arr, D.index, x, sym, sg, rng); o_[nm] = S(x); o_[nm]["随机对照每笔R"] = round(m, 2) if m == m else None; o_[nm]["随机对照胜率"] = round(w, 2) if w == w else None
        res[sym] = o_; print(sym, json.dumps(o_, ensure_ascii=False), flush=True)
    json.dump(res, open(os.path.join(HERE, "out", f"汇总_{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if tag == "默认":
        # 考题：Lin 的三张 QQQ 图（只看认没认出，不拿来调参数）
        D = 读("QQQ"); ev, 禁, arr = 找(D)
        for a, b in (("2024-04-10", "2024-06-15"), ("2025-03-25", "2025-06-15"), ("2026-03-01", "2026-05-15")):
            x = [(str(e["t1"].date()), str(e["t2"].date()), round(e["K"], 1), round(e["L0"], 1), round(e["进"], 1)) for e in ev if pd.Timestamp(a) <= e["t2"] <= pd.Timestamp(b)]; print("QQQ 考题", a, b, "（收回日, 确认日, 关键位, 最低点, 确认收盘）", x)
        for sym in ("BTC",):
            D = 读(sym); ev, 禁, arr = 找(D)
            for nm, a, b in (("2019-04-03~04-14", "2019-04-03", "2019-04-14"), ("2020-04-30~05-10", "2020-04-30", "2020-05-10"), ("2020-08", "2020-08-01", "2020-08-10"), ("2020-11", "2020-11-05", "2020-11-13"), ("2026-09-21~10-07", "2026-09-21", "2026-10-07"), ("2026-10-08~11-20", "2026-10-08", "2026-11-20"), ("2018 全年", "2018-01-01", "2018-12-31")):
                x = 禁.loc[a:b]; print(sym, nm, "V转禁空的天数占比", round(float(x.mean()), 2), "天数", len(x))
