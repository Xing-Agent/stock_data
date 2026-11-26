# -*- coding: utf-8 -*-
"""《问 Gemini 线 464 拍板》第 1、2、3 条 · 6 个考题重跑 · BTC 日线 · 引擎外 · 没改状态机本身，只在它每天的档上叠一层。
第 2 条「上一波大跌」：周线 ZigZag（拐点间 ≥ 倍 × 周线 ATR14，默认 3.5）。当前最低点 L = 过去 365 天的最低价；
       从 L 往前找最近的一个 ZigZag 高点 H：跌到 L ≥ 25%，且 H 到 L 之间没有超过这段跌幅 0.618 的反弹。
第 3 条 V 形提前切转涨（只在状态机标着「跌势」时起作用）：
   B 版：① 收盘 ≥ L + 0.618 ×（H − L）；② 日线收盘突破下跌途中最后一个次高点（L 之前最近的日线摆动高点，左右各 5 根）；
        ③ 之后连续 3 根收在它上方且最低价逐日抬高；④ 20 日 EMA 比 3 天前高。四条都满足的那天起算「转涨」，直到收盘跌破 L。
   A 版：连续 5 天收在 120 日线上且 120 日线不低于 5 天前 + EMA10 > EMA20 > SMA50 + 10 天里 ≥ 6 天收阳（或 10 天涨 > 20%）。
第 1 条 箱顶假突破（只在「筑底期」）：进筑底期以来收盘冲出过箱顶；冲出后最高 ≤ 箱顶 + 0.25 × 箱高（否则算有效突破，不空）；
        冲出后 窗 天内（默认 20）有一根收盘 < 箱顶 − 0.3 × 日线 ATR → 从那天起可空，直到收盘重新站上箱顶或离开筑底期。
开关表：涨势、转涨期、提前转涨 → 禁空；筑底期 → 只有假突破确认后可空；见顶、跌势 → 可空。"""
import os, re, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = importlib.util.spec_from_file_location("m4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); M4 = importlib.util.module_from_spec(sp); sp.loader.exec_module(M4)
def zigzag(W, 倍):
    h, l, c = W.high.to_numpy(float), W.low.to_numpy(float), W.close.to_numpy(float); pc = np.roll(c, 1); pc[0] = c[0]
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().bfill().to_numpy(); piv = []; d = 0; eh, el = 0, 0
    for i in range(1, len(W)):
        if h[i] > h[eh]: eh = i
        if l[i] < l[el]: el = i
        if d >= 0 and h[eh] - l[i] >= 倍 * atr[i] and eh < i: piv.append((W.index[eh], h[eh], "高", W.index[i])); d = -1; el = i
        elif d <= 0 and h[i] - l[el] >= 倍 * atr[i] and el < i: piv.append((W.index[el], l[el], "低", W.index[i])); d = 1; eh = i
    return piv                                                                  # (拐点所在周, 价, 高/低, 确认那周)
DBG = set(pd.to_datetime(["2019-04-05", "2019-04-10", "2019-05-12", "2020-04-30", "2020-05-08", "2019-02-20"]))
def 跑(sym="BTC", 倍=3.5, 连=3, ema=20, 窗=20, 破=0.3):
    D = M4.币日线(sym); R = pd.read_csv(os.path.join(ROOT, f"probe/大周期五档_1123/out4/{sym}_四版_每天的档.csv"), index_col=0, parse_dates=True)
    D = D.loc[D.index.isin(R.index)]; o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(D); idx = D.index; 档 = R["档"].reindex(idx).to_numpy(); why = R["切换原因"].reindex(idx).fillna("").to_numpy()
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    E = lambda k: pd.Series(c).ewm(span=k, adjust=False).mean().to_numpy(); e10, e20, eN = E(10), E(20), E(ema); s50 = pd.Series(c).rolling(50).mean().to_numpy(); m120 = pd.Series(c).rolling(120).mean().to_numpy()
    W = D.resample("W-SUN").agg({"high": "max", "low": "min", "close": "last"}).dropna(); Z = zigzag(W, 倍)
    sh = [(j, h[j]) for j in range(5, n - 5) if h[j] == h[j - 5:j + 6].max()]
    提前B = np.zeros(n, bool); 提前A = np.zeros(n, bool); 假突破 = np.zeros(n, bool); 波段 = {}; logB = []; logA = []; logF = []
    stB = None; stA = None; box = None
    for i in range(400, n):
        j0 = i - 365 + int(np.argmin(l[i - 365:i + 1])); L = l[j0]; H = None
        for (wt, p, k, ct) in reversed(Z):
            if k != "高" or wt > idx[j0] or ct > idx[i]: continue
            if (p - L) / p < 0.25: continue
            a_ = D.index.searchsorted(wt); seg_lo = np.minimum.accumulate(l[a_:j0 + 1]); reb = (h[a_:j0 + 1] - seg_lo).max() if j0 > a_ else 0
            if reb > 0.618 * (p - L): continue
            H = p; Ht = wt; break
        # ---- V 形提前切转涨
        新跌势 = 档[i] == "跌势" and 档[i - 1] != "跌势"                              # 状态机新切进跌势 → 上一轮的「提前转涨」清掉
        if stB is not None and (c[i] < stB or 档[i] in ("涨势",) or 新跌势): stB = None
        if stA is not None and (c[i] < stA or 档[i] in ("涨势",) or 新跌势): stA = None
        if 档[i] == "跌势" and H is not None:
            波段[idx[i]] = (Ht, H, idx[j0], L)
            prior = [p for (j, p) in sh if j < j0 and j + 5 <= i and idx[j] >= Ht]
            if stB is None and prior:
                lh = prior[-1]; ok = c[i] >= L + 0.618 * (H - L) and i - 连 > j0 and all(c[i - q] > lh for q in range(连)) and all(l[i - q] > l[i - q - 1] for q in range(连 - 1)) and eN[i] > eN[i - 3]
                if idx[i] in DBG: print("  调试", idx[i].date(), "收", round(c[i]), "H", round(H), Ht.date(), "L", round(L), idx[j0].date(), "0.618线", round(L + 0.618 * (H - L)), "次高点", round(lh), "①", c[i] >= L + 0.618 * (H - L), "②③", all(c[i - q] > lh for q in range(连)), all(l[i - q] > l[i - q - 1] for q in range(连 - 1)), "④", eN[i] > eN[i - 3])
                if ok: stB = L; logB.append((str(idx[i].date()), round(c[i]), f"上一波大跌 {Ht.date()} {round(H)} → {idx[j0].date()} {round(L)}，0.618 在 {round(L + 0.618 * (H - L))}，最后一个次高点 {round(lh)}"))
            if stA is None:
                up = (c[i - 9:i + 1] > o[i - 9:i + 1]).sum()
                if all(c[i - q] > m120[i - q] for q in range(5)) and m120[i] >= m120[i - 5] and e10[i] > e20[i] > s50[i] and (up >= 6 or c[i] / c[i - 10] - 1 > 0.2): stA = L; logA.append((str(idx[i].date()), round(c[i])))
        if stB is not None: 提前B[i] = True
        if stA is not None: 提前A[i] = True
        # ---- 筑底期箱顶假突破
        m = re.search(r"箱底 ([\d,]+)、箱顶 ([\d,]+)", why[i])
        if why[i].startswith("进筑底期") and m: box = dict(底=float(m.group(1).replace(",", "")), 顶=float(m.group(2).replace(",", "")), 冲=None, 高=0, 确认=False, 有效=False)
        if 档[i] != "筑底期": box = None
        if box is not None:
            if box["冲"] is None and c[i] > box["顶"]: box["冲"] = i; box["高"] = h[i]
            if box["冲"] is not None:
                box["高"] = max(box["高"], h[i])
                if box["高"] > box["顶"] + 0.25 * (box["顶"] - box["底"]): box["有效"] = True
                if not box["确认"] and not box["有效"] and i - box["冲"] <= 窗 and c[i] < box["顶"] - 破 * atr[i]:
                    box["确认"] = True; logF.append((str(idx[i].date()), round(c[i]), f"箱顶 {round(box['顶'])}，冲出第 {i - box['冲']} 天，冲出段最高 {round(box['高'])}，有效突破线 {round(box['顶'] + 0.25 * (box['顶'] - box['底']))}"))
                elif box["确认"] and c[i] > box["顶"]: box.update(确认=False, 冲=i, 高=h[i])       # 又站上去了，重新数
                elif not box["确认"] and i - box["冲"] > 窗 and c[i] < box["顶"]: box.update(冲=None, 高=0)
            if box["确认"]: 假突破[i] = True
    def 可空(提前):
        return np.array([(档[i] in ("跌势", "见顶") and not 提前[i]) or (档[i] == "筑底期" and 假突破[i]) for i in range(n)])
    return idx, 档, 可空(提前B), 可空(提前A), logB, logA, logF, 波段
if __name__ == "__main__":
    idx, 档, cB, cA, logB, logA, logF, 波段 = 跑()
    S = lambda a: pd.Series(a, index=idx)
    T = pd.DataFrame({"档": 档, "可空_B": cB, "可空_A": cA}, index=idx); T.to_csv(os.path.join(HERE, "out", "BTC_每天能不能空.csv"))
    print("B 版提前切转涨:", [x for x in logB if "2022" > x[0] or x[0] >= "2026"]); print("A 版提前切转涨:", [x for x in logA if "2022" > x[0] or x[0] >= "2026"]); print("箱顶假突破确认:", logF)
    rows = []
    for nm, a, b, 应 in (("2019-04（形态 04-03 起、04-09 成立）", "2019-04-03", "2019-04-14", "挡住"), ("2020-04~05（04-30 起、05-07 成立）", "2020-04-30", "2020-05-10", "挡住"), ("2020-08", "2020-08-01", "2020-08-10", "挡住"), ("2020-11", "2020-11-05", "2020-11-13", "挡住"),
                          ("2026-09-21~10-07（Lin 那个顶）", "2026-09-21", "2026-10-07", "左侧另算"), ("2026-10-08~11-20（Lin 三次反弹空）", "2026-10-08", "2026-11-20", "放行"), ("对照：2018 年全年", "2018-01-01", "2018-12-31", "大部分能空"), ("对照：2019 年全年", "2019-01-01", "2019-12-31", ""), ("对照：2021-05~07", "2021-05-19", "2021-07-20", "能空")):
        x = T.loc[a:b]; rows.append(dict(考题=nm, 应该=应, 当时的档=dict(x["档"].value_counts()), B版可空天数占比=round(float(x.可空_B.mean()), 2), A版可空天数占比=round(float(x.可空_A.mean()), 2)))
    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 60); print(pd.DataFrame(rows).to_string(index=False))
    json.dump(dict(B=logB, A=logA, 假突破=logF, 考题=rows), open(os.path.join(HERE, "out", "考题重跑.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
