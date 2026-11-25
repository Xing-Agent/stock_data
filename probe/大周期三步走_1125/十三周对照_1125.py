# -*- coding: utf-8 -*-
"""《457》补 ·《459 拍板》附的对照：周收盘跌破过去 13 周最低点（另试 10 / 16 周），且 40 周线不再创新高 → 切跌势。
和日线对照版、原来那版并排报（标普、道指 1928 起，纳指 1971 起，SOXX 2001 起；2022 以后封存）。
══ 我补的定义 ══
 T1 「过去 13 周最低点」= 之前 13 周（不含本周）的最低周收盘（1962 年前只有收盘价，全历史统一用收盘）。
 T2 「40 周线不再创新高」= 本周的 40 周线低于它过去 52 周里的最高值（不在新高上）。
 T3 解除 = 连续 2 周收在 40 周线上方、且 40 周线拐头向上；解除后才重新认下一个顶（不要求收回什么箱底，避免《457》查出来的「卡在上一轮跌势里」）。
 T4 评分照 改写版_1125.py：认出 = 确认日落在「顶 → 收盘重新站上顶之前的最低点」之间；虚惊 = 不属于真顶的报警里，一年内最多再跌不到 10%。
"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("G", os.path.join(HERE, "改写版_1125.py")); G = importlib.util.module_from_spec(sp); sp.loader.exec_module(G)


def 十三周(D, N=13, ma_n=40, 看=52):
    W = G.周线(D); c = W.close.to_numpy(float); idx = W.index; n = len(c)
    ma = pd.Series(c).rolling(ma_n, min_periods=ma_n).mean().to_numpy()
    lowN = pd.Series(c).rolling(N, min_periods=N).min().shift(1).to_numpy()
    mahi = pd.Series(ma).rolling(看, min_periods=10).max().shift(1).to_numpy()
    ev = []; t = ma_n + 看
    while t < n:
        if c[t] < lowN[t] and ma[t] < mahi[t]:
            r = None
            for j in range(t + 1, n):
                if c[j] > ma[j] and c[j - 1] > ma[j - 1] and ma[j] > ma[j - 1]: r = j; break
            ev.append({"确认": idx[t], "路": f"跌破{N}周低", "解除": idx[r] if r is not None else None})
            t = (r + 1) if r is not None else n
        else: t += 1
    return ev


if __name__ == "__main__":
    out = {}
    for nm, D, 日kw in (("标普500指数", G.L.读("标普500指数"), {}), ("道琼斯工业指数", G.L.读("道琼斯工业指数"), {}),
                         ("纳斯达克综合指数", G.L.读("纳斯达克综合指数"), {}), ("SOXX", G.SC.soxx(), dict(箱=45, 破=0.03, 急=0.15))):
        原严 = G.原来(D, 要ST或UT=True, BC严=True); o = {}
        for k, ev in (("原来·严版", 原严), ("日线对照版(基准)", G.日线版(D, **日kw)), ("日线对照版·解除不要箱底", G.日线版(D, **日kw, 解除要箱底=False)),
                      ("13周低+40周线不创新高", 十三周(D, 13)), ("10周低+40周线不创新高", 十三周(D, 10)), ("16周低+40周线不创新高", 十三周(D, 16))):
            S, T, F = G.评(D, ev, 原=原严)
            o[k] = {"概要": S, "每个真顶": T.to_dict("records"), "别的报警": F.to_dict("records")}
            print(nm, k.ljust(18), f"认出 {S['认出']}/{S['真大顶']} 虚惊 {S['其中虚惊']}/{S['别的报警']} 离顶天中位 {S['离顶天中位']} 确认离顶中位 {S['确认时离顶pct中位']}", flush=True)
        out[nm] = o
    json.dump(out, open(os.path.join(HERE, "out", "十三周对照_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE")
