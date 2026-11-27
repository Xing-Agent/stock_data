# -*- coding: utf-8 -*-
"""《488》第 3 项 ·《464 拍板》第 4 条：筑底期冲出箱顶后、确认假突破之前，有「急拉后高位派发区」形态 → 第 3 或第 4 个顶冲高回落、1 小时线跌破最近一个抬高的低点时左侧开 30%；确认假突破补满 70%。
对照 = 只等确认、一次 100%。箱顶冲出事件用第 2 项的结果（probe/箱顶假突破_1127/out/冲出逐次.csv，窗 20 默认）；形态用 派发楔形_1125 的识别结果（默认和相邻参数四组）。
左侧止损 = 冲出段最高（到进场那时）+ 0.5 倍日线 ATR（同第 1 条）；目标、拿法同第 2 项（中轴 50%、箱底 35%、尾仓 15% 到箱底 − 1 倍箱高，最多 120 天）。
4 小时顶 = 左右各 3 根的分形高点、离区间最高 ≤1 倍 4 小时 ATR（同识别脚本）；1 小时「抬高的低点」= 左右各 3 根的分形低点、比前一个分形低点高（我补的）。左侧单在进场那天之后按日线走。"""
import os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
K = mod("k", os.path.join(ROOT, "probe/派发楔形_1125/看九月那段_1125.py")); M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); FEE = 0.0005
EV = pd.read_csv(os.path.join(ROOT, "probe/箱顶假突破_1127/out/冲出逐次.csv")); EV = EV[(EV.窗 == 20) & (EV.参数 == "默认") & EV.品种.isin(["BTC", "ETH"])]
def 空(D, t_in, E, S, 底, 顶):
    o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); i = D.index.searchsorted(pd.Timestamp(t_in).normalize(), side="right"); n = len(c)
    高 = 顶 - 底; parts = [(0.5, (顶 + 底) / 2), (0.35, 底), (0.15, 底 - 高)]; 剩 = [True] * 3; pnl = 0.0; end = min(i + 119, n - 1)
    for q in range(i, end + 1):
        if h[q] >= S: px = max(S, o[q]); pnl += sum(parts[p][0] * (E - px) for p in range(3) if 剩[p]); return pnl / E * 100 - 0.1
        for p in range(3):
            if 剩[p] and l[q] <= parts[p][1]: pnl += parts[p][0] * (E - parts[p][1]); 剩[p] = False
        if not any(剩): return pnl / E * 100 - 0.1
    pnl += sum(parts[p][0] * (E - c[end]) for p in range(3) if 剩[p]); return pnl / E * 100 - 0.1
rows = []
for tag in ("默认", "急拉2.0", "急拉3.0", "跌破0.2", "跌破0.45"):
    P = pd.concat([pd.read_csv(os.path.join(ROOT, f"probe/派发楔形_1125/out/{f}派发区形态_{tag}.csv")) for f in ("", "封存_")]); P["首顶"] = pd.to_datetime(P["首顶"])
    for _, e in EV.iterrows():
        s = e.品种; D = M4.币日线(s); a = pd.Timestamp(e.冲出日); b = pd.Timestamp(e.判的日子) + pd.Timedelta(hours=23)
        pc = D.close.shift(1); datr = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
        右 = 空(D, e.判的日子, e.进场, e.止损, e.箱底, e.箱顶) if e.规则判 == "假" else None
        x = P[(P.sym == s) & (P.首顶 >= a - pd.Timedelta(days=3)) & (P.首顶 <= b)]
        左 = None; 左说明 = "没有派发区形态"
        if len(x):
            f0 = x.首顶.iloc[0]; X = K.指标(K.四小时(s)); X.index = X.index.tz_localize(None) if X.index.tz is not None else X.index
            H1 = K.V1.小时线(s); H1.index = H1.index.tz_localize(None) if H1.index.tz is not None else H1.index
            h4, a4 = X.high.to_numpy(), X.atr.to_numpy(); i0 = X.index.get_loc(f0); tops = [i0]; 左说明 = "有形态，没等到第 3/4 个顶加 1 小时跌破"
            for j in range(i0 + 1, len(X)):
                if X.index[j] > b: break
                k = j - 3
                if k > i0 + 3 and h4[k] == h4[k - 3:k + 4].max() and h4[k] >= h4[i0:j + 1].max() - a4[i0] and k not in tops:
                    tops.append(k)
                    if len(tops) in (3, 4):
                        H = H1.loc[X.index[j]:b]; hl, hc, ho = H.low.to_numpy(), H.close.to_numpy(), H.open.to_numpy()
                        lows = [q for q in range(3, len(H) - 3) if hl[q] == hl[q - 3:q + 4].min()]
                        for q in range(4, len(H) - 1):
                            conf = [z for z in lows if z + 3 <= q]
                            if len(conf) >= 2 and hl[conf[-1]] > hl[conf[-2]] and hc[q] < hl[conf[-1]]:
                                t_in = H.index[q + 1]; E = ho[q + 1]; 段高 = D.high.loc[a:t_in.normalize()].max(); S = 段高 + 0.5 * datr.loc[:t_in.normalize()].iloc[-2]
                                左 = 空(D, t_in, E, S, e.箱底, e.箱顶); 左说明 = f"第 {len(tops)} 个顶后 {t_in} 进 {E:,.0f}，止损 {S:,.0f}"; break
                        if 左 is not None: break
        A = 右 if 右 is not None else 0.0
        B = (0.3 * 左 if 左 is not None else 0.0) + (0.7 * 右 if 右 is not None else 0.0) if 左 is not None else A
        rows.append(dict(识别参数=tag, 品种=s, 冲出日=e.冲出日, 规则判=e.规则判, 只等确认=round(A, 2) if 右 is not None else None, 左侧单=round(左, 2) if 左 is not None else None, 左三成加确认补满=round(B, 2) if (右 is not None or 左 is not None) else None, 说明=左说明))
T = pd.DataFrame(rows); T.to_csv(os.path.join(HERE, "out_逐次.csv"), index=False); pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 80); print(T.to_string(index=False))
