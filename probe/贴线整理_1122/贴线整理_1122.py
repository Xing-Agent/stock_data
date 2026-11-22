# -*- coding: utf-8 -*-
"""测试单《贴线整理进场和第二目标区去留》第一组（进场）· 引擎外脚本
A = 卡现在的「等回踩到等待区 + 扳机」（考试 1119 的 run2：trig='C', rrmode='gem', 分票规则开）
B = 分界线破位后贴线整理 3 根再进
C = 破位那根收盘就追
测试单没写死、我自己补的定义（报告里要标出）：
  - 分界线 = 4 小时箱体的上沿 / 下沿：过去 20 根 4 小时线（不含当前）的最高 / 最低；箱高 2~6 倍 4 小时 ATR；上下各碰至少 2 次（离边不超过 0.1 倍箱高）
  - 破位那根「实体 K 线」= 实体 >= 整根振幅的一半
  - B、C 的目标位：第一目标 = 分界线外 1 倍箱高，第二目标 = 1.618 倍箱高；到第一目标平一半、止损推成本；最长 72 根
  - C 的止损 = 分界线往里 0.5 倍 ATR
  - 成本：单边 0.05%（三组一样）
SOXX 没有小时线，用 SMH 代替。
"""
import os, sys, glob, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
E1 = os.path.join(ROOT, "market_ext_1105/ETF和币_1120")
HERE = os.path.dirname(os.path.abspath(__file__))
OLD = os.path.join(ROOT, "probe/技术面大师考试_1119")
src = open(os.path.join(OLD, "trig.py"), encoding="utf-8").read().split("def run(")[0]
src = "\n".join(x for x in src.split("\n") if not x.startswith("exec(open("))   # 那一行读的是别的容器里的文件，这里自己定义 atr
def atr(d, n=14):
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1)
    return tr.rolling(n).mean()
exec(src)
src4 = open(os.path.join(OLD, "trig4.py"), encoding="utf-8").read()
exec("def h4info" + src4.split("def h4info")[1].split("\ndef stats")[0])
FEE = 0.0005

def load(sym):
    if sym in ("BTC", "ETH"):
        fs = sorted(glob.glob(os.path.join(E1, "币_小时线_Coinbase", "*.parquet")))
    else:
        fs = sorted(glob.glob(os.path.join(E1, "小时线_2004_2014", "*.parquet"))) + sorted(glob.glob(os.path.join(E1, "小时线_2015起", "*.parquet")))
    L = []
    for f in fs:
        x = pd.read_parquet(f); x = x[x.symbol == sym]
        if sym not in ("BTC", "ETH"): x = x[x.session == "regular"]
        L.append(x)
    d = pd.concat(L); d["t"] = pd.to_datetime(d.time_utc, utc=True)
    d = d.set_index("t").sort_index()
    d = pd.DataFrame({"open": d.open_adj, "high": d.high_adj, "low": d.low_adj, "close": d.close_adj, "volume": d.volume_adj}).dropna()
    d = d[~d.index.duplicated()]
    # 坏的高低价：影线超出开收盘 15% 的夹回去
    hi = d[["open", "close"]].max(axis=1); lo = d[["open", "close"]].min(axis=1)
    d.loc[d.high > hi * 1.15, "high"] = hi; d.loc[d.low < lo * 0.85, "low"] = lo
    return d

def boxes(d, N=20, K=0.1):
    h = d.resample("4h").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    a = pd.concat([h.high - h.low, (h.high - h.close.shift()).abs(), (h.low - h.close.shift()).abs()], axis=1).max(axis=1).rolling(14).mean()
    top = h.high.rolling(N).max(); bot = h.low.rolling(N).min(); H = top - bot
    hv, lv, tv, bv, Hv = h.high.values, h.low.values, top.values, bot.values, H.values
    tu = np.zeros(len(h)); td = np.zeros(len(h))
    for i in range(N - 1, len(h)):
        tu[i] = (hv[i - N + 1:i + 1] >= tv[i] - K * Hv[i]).sum(); td[i] = (lv[i - N + 1:i + 1] <= bv[i] + K * Hv[i]).sum()
    ok = (H >= 2 * a) & (H <= 6 * a) & (tu >= 2) & (td >= 2)
    f = pd.DataFrame({"top": top, "bot": bot, "ok": ok}).shift(1)
    f.index = f.index + pd.Timedelta(hours=4)
    return f.reindex(d.index, method="ffill")

def daily_state(d):
    dc = d.close.resample("1D").last().dropna(); m20 = dc.rolling(20).mean(); m50 = dc.rolling(50).mean()
    s = pd.Series("震荡", index=dc.index)
    s[(dc > m20) & (m20 > m50) & (m20 > m20.shift(3))] = "上涨"; s[(dc < m20) & (m20 < m50) & (m20 < m20.shift(3))] = "下跌"
    s = s.shift(1); return s.reindex(d.index, method="ffill").fillna("震荡").values

def run_bc(d, name, mode, hold=72):
    B = boxes(d); A = atr(d).values
    O, H, L, C, V = [d[c].values for c in ["open", "high", "low", "close", "volume"]]
    top, bot, ok = B.top.values, B.bot.values, B.ok.fillna(False).values.astype(bool)
    vma = pd.Series(V).rolling(20).mean().shift(1).values; st8 = daily_state(d)
    T = []; i = 150; n = len(d); stat = {"破位": 0, "贴线成立": 0, "收回作废": 0, "实体过大作废": 0}
    while i < n - 8:
        if not ok[i] or np.isnan(A[i]) or np.isnan(vma[i]): i += 1; continue
        body = abs(C[i] - O[i]); rng = H[i] - L[i] + 1e-12
        up = C[i] > top[i] + 0.25 * A[i] and C[i - 1] <= top[i]; dn = C[i] < bot[i] - 0.25 * A[i] and C[i - 1] >= bot[i]
        if not (up or dn) or V[i] < 1.5 * vma[i] or body < 0.5 * rng: i += 1; continue
        Lg = up; line = top[i] if Lg else bot[i]; bh = top[i] - bot[i]; stat["破位"] += 1
        if mode == "C":
            ei = i; stp = line - 0.5 * A[i] if Lg else line + 0.5 * A[i]
        else:
            ei = None; why = None
            for k in range(1, 4):
                j = i + k
                if (C[j] <= line) if Lg else (C[j] >= line): why = "收回作废"; break
                if abs(C[j] - O[j]) >= 0.5 * A[j]: why = "实体过大作废"; break
            if why: stat[why] += 1; i += 1; continue
            ei = i + 3; stat["贴线成立"] += 1
            stp = (L[i + 1:ei + 1].min() - 0.5 * A[ei]) if Lg else (H[i + 1:ei + 1].max() + 0.5 * A[ei])
        e = C[ei]; risk = (e - stp) if Lg else (stp - e)
        if risk <= 0: i += 1; continue
        tp1 = line + bh if Lg else line - bh; tp2 = line + 1.618 * bh if Lg else line - 1.618 * bh
        rr1 = ((tp1 - e) if Lg else (e - tp1)) / risk; rr2 = ((tp2 - e) if Lg else (e - tp2)) / risk
        if rr1 <= 0: i += 1; continue
        half = False; res = None; Rm = 0; s = stp; jj = ei
        for j in range(ei + 1, min(ei + 1 + hold, n)):
            jj = j
            if not half:
                if (L[j] <= s) if Lg else (H[j] >= s): res = -1; break
                if (H[j] >= tp1) if Lg else (L[j] <= tp1): half = True; Rm = 0.5 * rr1; s = e
            else:
                if (L[j] <= s) if Lg else (H[j] >= s): res = Rm; break
                if (H[j] >= tp2) if Lg else (L[j] <= tp2): res = Rm + 0.5 * rr2; break
        if res is None:
            last = C[jj]; res = (Rm if half else 0) + (0.5 if half else 1) * (((last - e) if Lg else (e - last)) / risk)
        T.append({"票": name, "t": str(d.index[ei])[:16], "dir": "多" if Lg else "空", "R": res, "tp1": half, "riskp": risk / e, "日线": st8[ei]})
        i = jj + 1
    return pd.DataFrame(T), stat

def run_a(d, name):
    t = run2(d, name, trig="C", rrmode="gem", tk_rules=True)
    if len(t):
        st8 = pd.Series(daily_state(d), index=[str(x)[:16] for x in d.index]); st8 = st8[~st8.index.duplicated()]
        t["日线"] = st8.reindex(t.t).values
    return t

def S(t):
    if t is None or len(t) == 0: return {"笔数": 0}
    t = t.sort_values("t"); net = t.R - 2 * FEE / t.riskp
    w = net[net > 0].sum(); l = -net[net < 0].sum(); cum = net.cumsum()
    return {"笔数": int(len(t)), "每笔毛R": round(float(t.R.mean()), 3), "每笔净R": round(float(net.mean()), 3), "胜率pct": round(float((net > 0).mean() * 100), 1),
            "到第一目标pct": round(float(t.tp1.mean() * 100), 1), "利润因子": round(float(w / l), 2) if l > 0 else None, "累计净R": round(float(net.sum()), 1),
            "最大回撤R": round(float((cum - cum.cummax()).min()), 1), "止损宽中位pct": round(float(t.riskp.median() * 100), 2), "被直接打止损pct": round(float((t.R <= -1).mean() * 100), 1)}

if __name__ == "__main__":
    out = {}
    for sym in ["TQQQ", "SOXL", "QQQ", "SMH", "BTC", "ETH"]:
        d0 = load(sym)
        segs = {"2005–2014": d0["2005":"2014"], "2015–2025": d0["2015":"2025"]}
        for seg, d in segs.items():
            if len(d) < 3000: continue
            R = {}
            for arm in ("A", "B", "C"):
                if arm == "A": t = run_a(d, sym); stat = {}
                else: t, stat = run_bc(d, sym, arm)
                t.to_csv(os.path.join(HERE, "out", f"{sym}_{seg}_{arm}.csv"), index=False)
                R[arm] = {"全部": S(t), "多": S(t[t.dir == "多"]) if len(t) else {}, "空": S(t[t.dir == "空"]) if len(t) else {},
                          "分日线": {k: {"多": S(g[g.dir == "多"]), "空": S(g[g.dir == "空"])} for k, g in t.groupby("日线")} if len(t) else {}, "漏斗": stat}
                print(sym, seg, arm, R[arm]["全部"], stat, flush=True)
            out[f"{sym}|{seg}"] = R
            json.dump(out, open(os.path.join(HERE, "out", "贴线整理_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DONE")
