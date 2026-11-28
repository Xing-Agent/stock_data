# -*- coding: utf-8 -*-
"""《571》第三批跑批入口。用法：python3 跑第三批_1128.py <版本>   版本：默认 / 缓冲0.35 / 缓冲0.65 / 拿40 / 拿120 / 斜率10 / 斜率20 / 照字面
每个版本一个 json（out/第三批_<版本>.json），已有就跳过（断点续跑）。候选根存 /tmp（不入库）。"""
import os, sys, json, time
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import 做多组合_1128 as K
CACHE = K.CACHE
版本 = sys.argv[1] if len(sys.argv) > 1 else "默认"
P = dict(缓冲=0.5, 拿=60, 斜率天=5, 照字面=False)
if 版本.startswith("缓冲"): P["缓冲"] = float(版本[2:])
elif 版本.startswith("拿"): P["拿"] = int(版本[1:])
elif 版本.startswith("斜率"): P["斜率天"] = int(版本[2:])
elif 版本 == "照字面": P["照字面"] = True
fo = os.path.join(K.OUT, f"第三批_{版本}.json")
if os.path.exists(fo): print("已有", fo); sys.exit(0)
t0 = time.time(); spy = K.M4.美股日线("SPY").close.loc[:K.封]
套名 = {0: "顺势回踩", 1: "V形反转"}; 全 = {}; 结果 = []


def 收(X, 品种, 段=None):
    if X is None: return None
    X["品种"] = 品种
    if 段: X["段"] = 段
    return X


for 套 in (0, 1):
    # ETF
    L = []
    for s in ("QQQ", "SPY", "SOXX"):
        D = (K.SC.soxx() if s == "SOXX" else K.M4.美股日线(s)).loc[:K.封]
        X = K.跑一只(D, 套, None, D.index[250], "2021-12-31", 缓冲=P["缓冲"], 拿=P["拿"], 斜率天=P["斜率天"], 照字面=P["照字面"])
        if X is not None: L.append(K.加大盘(收(X, s), spy))
    E = pd.concat(L, ignore_index=True)
    早 = lambda x: x["进日"] <= "2007-12-31"; 晚 = lambda x: x["进日"] >= "2008-01-01"; 都 = lambda x: np.ones(len(x), bool)
    for s in ("QQQ", "SPY", "SOXX"):
        结果 += K.报一组(E[E.品种 == s], f"{套名[套]}·{s}", [("全部", 都)])
    结果 += K.报一组(E, f"{套名[套]}·三只ETF合起来", [("全部", 都), ("1993–2007", 早), ("2008–2021", 晚)])
    # 个股
    L = []
    for 段, a, b in (("二", "2005-01-03", "2014-12-31"), ("一", "2015-01-02", "2021-12-31")):
        W = pd.read_parquet(os.path.join(CACHE, f"股票日线_{段}.parquet")); MK = pd.read_parquet(os.path.join(CACHE, f"股票掩膜_{段}.parquet"))
        syms = list(W["close"].columns)
        for s in syms:
            if not MK[s].loc[a:b].any(): continue
            D = pd.DataFrame({f: W[f][s] for f in ("open", "high", "low", "close", "volume")}).astype(float)
            X = K.跑一只(D, 套, MK[s], a, b, 缓冲=P["缓冲"], 拿=P["拿"], 斜率天=P["斜率天"], 照字面=P["照字面"])
            if X is not None: L.append(收(X, s + "@" + 段, "2005–2014" if 段 == "二" else "2015–2021"))
        del W, MK
    S = K.加大盘(pd.concat(L, ignore_index=True), spy); del L
    结果 += K.报一组(S, f"{套名[套]}·研发池个股", [("2005–2021", 都), ("2005–2014", lambda x: x["段"] == "2005–2014"), ("2015–2021", lambda x: x["段"] == "2015–2021")])
    # 币（7×24，不扣标普）
    L = []
    for s in ("BTC", "ETH"):
        D = K.M4.币日线(s)
        X = K.跑一只(D, 套, None, D.index[250], D.index[-1], 起等下限=0.5, 缓冲=P["缓冲"], 拿=P["拿"], 斜率天=P["斜率天"], 照字面=P["照字面"], 平=0.65 if s == "BTC" else 0.5)
        if X is not None: L.append(收(X, s))
    C = pd.concat(L, ignore_index=True)
    九十 = lambda x: (x["进日"] >= "2026-09-01") & (x["进日"] <= "2026-10-31")
    段们 = [("2017–2026 全部", 都), ("去掉 2026 年 9~10 月进场的", lambda x: ~九十(x)), ("2017–2021", lambda x: x["进日"] <= "2021-12-31"),
          ("2022–2025", lambda x: (x["进日"] >= "2022-01-01") & (x["进日"] <= "2025-12-31")), ("2026", lambda x: x["进日"] >= "2026-01-01")]
    for s in ("BTC", "ETH"): 结果 += K.报一组(C[C.品种 == s], f"{套名[套]}·{s}", 段们)
    结果 += K.报一组(C, f"{套名[套]}·BTC加ETH", 段们)
    if 版本 == "默认":
        for nm, X in (("ETF", E), ("个股", S), ("币", C)):
            X.to_parquet(os.path.join(CACHE, f"候选_{套名[套]}_{nm}.parquet"))
    del S, E, C
    import gc; gc.collect()
    print(套名[套], "完", round(time.time() - t0), "秒", flush=True)

json.dump(dict(版本=版本, 参数=P, 秒=round(time.time() - t0), 结果=结果), open(fo, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print("DONE", fo, round(time.time() - t0))
