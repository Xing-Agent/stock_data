# -*- coding: utf-8 -*-
"""《487 拍板》第 4 条 B 版（对照），以及 A、B 两版加跑「拿 20 天或打止损」（拍板里问 Gemini 线粗跑用的出场）。只在状态机筑底期里开。
B 版：200 日线向下（比 20 天前低，我补的写法）；某天最高价碰进下降的 150 日线 ±1.5%（另试 50 日线 ±1%、100 日线 ±2%；「下降」= 比 20 天前低）；
      碰到之后 3 天内收盘跌破 10 日线 → 那天收盘空；止损 = 碰线那天到进场之间的最高价 + 1 倍 ATR；半仓。
出场两种：① 打止损 / 到 3 倍风险 / 最多 60 天（同 A 版默认，我补的）；② 拿 20 天或打止损（拍板里粗跑用的）。同一时间只拿一笔；单边 0.05%。"""
import os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("Z", os.path.join(HERE, "箱子重分_1128.py")); Z = importlib.util.module_from_spec(sp); sp.loader.exec_module(Z)
FEE = 0.0005
def 出(o, h, l, c, i, E, S, 目标R, 拿):
    Rk = S - E; n = len(c); end = min(i + 拿, n - 1)
    for j in range(i + 1, end + 1):
        if h[j] >= S: return -(max(o[j], S) - E) / Rk, j
        if 目标R and l[j] <= E - 目标R * Rk: return 目标R, j
    return (E - c[end]) / Rk, end
def 箱of(B):
    m = {}
    for b in B:
        for i in range(b["起"], b["止"]): m[i] = b
    return m
def 跑B(sym, 线=150, 带=0.015, 目标R=3.0, 拿=60):
    D, R, B, _, atr = Z.箱子们(sym); o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(c); idx = D.index; st = R["档"].to_numpy()
    ma = pd.Series(c).rolling(线).mean().to_numpy(); s200 = pd.Series(c).rolling(200).mean().to_numpy(); s10 = pd.Series(c).rolling(10).mean().to_numpy(); M = 箱of(B); out = []; busy = -1
    for t in range(220, n - 1):
        if t <= busy or st[t] != "筑底期" or t not in M: continue
        if not (s200[t] < s200[t - 20] and ma[t] < ma[t - 20]): continue
        if not (h[t] >= ma[t] * (1 - 带) and h[t] <= ma[t] * (1 + 带)): continue
        for i in range(t, min(t + 4, n - 1)):
            if st[i] != "筑底期": break
            if c[i] < s10[i]:
                E = c[i]; S = h[t:i + 1].max() + atr[i]; r, j = 出(o, h, l, c, i, E, S, 目标R, 拿); Rk = S - E; b = M[t]
                out.append(dict(品种=sym, 版="B", 日=str(idx[i].date()), 进箱=b["进箱"], 箱子方向=b["方向"], R=r - 2 * FEE * E / Rk, 收益pct=(r * Rk - 2 * FEE * E) / E * 100)); busy = j; break
    return out
def 跑A20(sym):
    D, R, B, _, atr = Z.箱子们(sym); o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(c); idx = D.index; st = R["档"].to_numpy()
    s50 = pd.Series(c).rolling(50).mean().to_numpy(); s150 = pd.Series(c).rolling(150).mean().to_numpy(); e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy(); M = 箱of(B); out = []; busy = -1
    for i in range(160, n - 1):
        if st[i] != "筑底期" or i <= busy or i not in M: continue
        if not (s50[i] < s50[i - 10] and c[i] < s150[i]): continue
        lo_b = min(e20[i], s50[i]) - 0.2 * atr[i]; hi_b = max(e20[i], s50[i]) + 0.2 * atr[i]; hh = max(h[i], h[i - 1])
        if not (lo_b <= hh <= hi_b) or not (c[i] < o[i] and c[i] < l[i - 1]): continue
        E = c[i]; S = h[i - 4:i + 1].max() + 0.4 * atr[i]; r, j = 出(o, h, l, c, i, E, S, None, 20); Rk = S - E; b = M[i]
        out.append(dict(品种=sym, 版="A", 日=str(idx[i].date()), 进箱=b["进箱"], 箱子方向=b["方向"], R=r - 2 * FEE * E / Rk, 收益pct=(r * Rk - 2 * FEE * E) / E * 100)); busy = j
    return out
if __name__ == "__main__":
    rows = []
    for s in ("BTC", "ETH", "SPY", "QQQ", "SOXX"):
        for nm, kw in (("150日线±1.5%", {}), ("50日线±1%", {"线": 50, "带": 0.01}), ("100日线±2%", {"线": 100, "带": 0.02})):
            rows += [dict(r, 参数=nm, 出场="3R或60天") for r in 跑B(s, **kw)]; rows += [dict(r, 参数=nm, 出场="拿20天或止损") for r in 跑B(s, 目标R=None, 拿=20, **kw)]
        rows += [dict(r, 参数="A默认", 出场="拿20天或止损") for r in 跑A20(s)]
    T = pd.DataFrame(rows); T.to_csv(os.path.join(HERE, "out", "均线退路B和A20天_逐笔.csv"), index=False)
    T["箱型"] = np.where(T.箱子方向 == "向上", "真筑底", np.where(T.箱子方向 == "破位", "熊市中段", "还在箱里(BTC2026)"))
    def 统(x):
        s = (x.R < 0).astype(int).to_numpy(); mx = cur = 0
        for v in s: cur = cur + 1 if v else 0; mx = max(mx, cur)
        return pd.Series({"笔": len(x), "赚钱笔": f"{(x.R > 0).sum()}/{len(x)}", "合计R": round(x.R.sum(), 1), "最大连亏": mx, "最深%": round(x.收益pct.min(), 1)})
    pd.set_option("display.width", 250); print(T.groupby(["版", "参数", "出场", "箱型"]).apply(统).to_string())
    print(T[(T.版 == "A")].round(2).to_string(index=False))
    print(T[(T.版 == "B") & (T.参数 == "150日线±1.5%")].round(2).to_string(index=False))
