# -*- coding: utf-8 -*-
"""《450 拍板》第 1 件先核：BTC 2026-09-21 ~ 10-08，4 小时线上的顶、底、量、RSI、ATR，对照拍板的每一条。引擎外，只读。"""
import os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
V1 = mod("v1", os.path.join(ROOT, "probe/核心压力位_1123/打分器_1123.py"))
def 四小时(sym):
    H = V1.小时线(sym); X = H.resample("4h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(); return X
def 指标(X):
    h, l, c = X.high, X.low, X.close; pc = c.shift(1)
    X = X.copy(); X["atr"] = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    d = c.diff(); up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean(); dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean(); X["rsi"] = 100 - 100 / (1 + up / dn); return X
def 摆动(X, N=3):
    h, l = X.high.to_numpy(), X.low.to_numpy(); out = []
    for j in range(N, len(X) - N):
        if h[j] == h[j - N:j + N + 1].max(): out.append((j, "顶"))
        if l[j] == l[j - N:j + N + 1].min(): out.append((j, "底"))
    return out
if __name__ == "__main__":
    X = 指标(四小时("BTC")); W = X.loc["2026-09-20":"2026-10-09"]
    for N in (2, 3):
        print(f"--- 左右各 {N} 根")
        for j, k in 摆动(W, N):
            r = W.iloc[j]; rng = r.high - r.low
            print(W.index[j].strftime("%m-%d %H:%M"), k, round(r.high if k == "顶" else r.low), "量", round(r.volume), "RSI", round(r.rsi, 1), "4小时ATR", round(r.atr), "收在振幅", round((r.close - r.low) / rng, 2) if rng else None)
    Z = W.loc["2026-09-21":"2026-10-07"]; print("形态内 阴线总量/阳线总量", round(Z.volume[Z.close < Z.open].sum() / Z.volume[Z.close >= Z.open].sum(), 2), "根数", len(Z))
    print(W.loc["2026-10-06 12:00":"2026-10-08 12:00", ["open", "high", "low", "close", "volume", "atr"]].round(0).to_string())
