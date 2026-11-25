# -*- coding: utf-8 -*-
"""《451》任务一 · 大周期认顶三步走（《446 拍板》第 2 条）· 引擎外
大白话：原来的状态机一跌破箱底就切「跌势」，虚惊多。现在改成三步：
  ① 预警：放量滞涨、冲高回落 —— 只标记，不切档；
  ② 破位：一根大阴线（实体 > 1.2 ATR）、放量（> 1.3 倍 20 根均量）、收盘跌破箱底；
  ③ 确认：破位后第 3~10 根之间出现反抽，反抽里连续 2 根（另试 1、3）收盘收不回箱底，且反抽段均量 < 破位段的 80% → 才切「跌势」。
做法：原来状态机报出的每一次转空（时间、箱底）原样拿来当候选，再用第 ② ③ 步去筛；②③ 在哪个周期的 K 线上判，按《446》已定：
  美股指数 = 月线（对照：周线），SOXX = 周线（对照：日线），BTC = 日线。

候选从哪来：
  · 美股三大指数：《429》的三层状态机第一版·主版（probe/美股三层状态机_1123/三层状态机_1123.py，默认参数）—— 就是「标普 1928–1992 年 17 次别的转空、12 次虚惊」那一版；
  · SOXX：三层状态机第二版（三层状态机_第二版_1124.py），级别 = 周（已定），对照 级别 = 日（主战场_1124.py 里「低一级」的用法）；
  · BTC：大周期五档第四版（五档状态机_第四版_1123.py）的「转空」。

══ 我补的定义（拍板没写死的）══
 S1 箱底：大顶跌破 = 状态机记的箱底；突发急跌 = 当天之前 252 个交易日的最低收盘（状态机里用的同一条线）；复跌 = 上一次转空的箱底（状态机里也是接着用上一轮的）；
    五档的转空 = 「见顶前最后一个摆动低点」（左右各 3 根，和五档里同一种找法）。
 S2 破位那根：候选报警所在那根 K 线，或它之后 1 根（邻点：只看那一根 / 之后 2 根）里，第一根同时满足「收阴、实体 > 1.2 × ATR14、量 > 1.3 × 前 20 根均量、收盘 < 箱底」的。都不满足 = 这次报警被筛掉。
 S3 破位段 = 从「最后一根收盘还在箱底之上的 K 线」之后、到破位那根（最多 5 根）；反抽 = 破位之后第一根收盘高于前一根收盘的 K 线开始；
    确认 = 破位后第 3~10 根里，第一次出现「反抽已开始、最近 N 根都在反抽里且收盘都 < 箱底、反抽段均量 < 0.8 × 破位段均量」的那根收盘；
    第 1~10 根里任何一根收盘回到箱底之上 = 筛掉（收回）；到第 10 根还没确认 = 筛掉（没确认）。
 S4 没有成交量的年份（标普、道指 1950 年以前；任何量 = 0 的 K 线）：量的两条直接算通过，报告里分开写。
 S5 虚惊 = 认定转空后，到原状态机回到「涨势」之前，最多再跌不到 10%（和《429》同一把尺子）。真大顶 = 两年新高之后收盘回落 ≥ 20%（同《429》）。
 S6 预警（只标记）：放量滞涨 = 离一年最高 3% 以内、量 > 1.3 × 20 根均量、实体 < 0.3 ATR；冲高回落 = 创一年新高、收在当根振幅下三分之一。只数次数和真顶前有没有，不参与筛。
 S7 宽度过滤（只有 2004 年起的标普）：报警前最后一次指数创一年新高那天，「站上 50 日线的股票占比」（10 日平均）比之前 1 年里的最高值低 10 个百分点以上（邻点 5 / 15）才算宽度走弱；
    宽度数据用 probe/减仓_1121/宽度_每日.csv（研究库流动性池，不是标普成分股）。
 S8 封存：2022-01-01 以后的报警单独存，不打印、不进统计；BTC 2023–2025 那三次只回答「还报不报」。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
P3 = os.path.join(ROOT, "probe/美股三层状态机_1123")
L = mod("L", os.path.join(P3, "长历史_1124.py")); V1 = L.M; V2 = mod("V2", os.path.join(P3, "三层状态机_第二版_1124.py"))
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
封存 = "2022-01-01"


def K线(D, tf):
    if tf == "D": return D.copy()
    rule = {"W": "W-FRI", "M": "ME"}[tf]
    return D.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(subset=["close"])


def 候选(D, 来源, **kw):
    """返回 [(日期, 箱底, 事, 原始R表)]：状态机原样报出的每一次转空。"""
    c = D.close; lo252 = c.rolling(252).min().shift(1)
    if 来源 == "三层一版":
        R, EV = V1.跑(D, **kw)
    elif 来源 == "三层二版":
        R, EV, _ = V2.跑(D, **kw)
    else:
        R, EV = M4.跑(D, M4.P币)
    out = []; 上一个底 = np.nan
    if 来源 in ("三层一版", "三层二版"):
        for e in EV:
            if not e["事"].startswith(("转空", "复跌")): continue
            t = pd.Timestamp(e["日期"])
            if "箱底" in e: 底 = e["箱底"]
            elif e["事"].startswith("转空·突发急跌"): 底 = float(lo252.loc[t])
            else: 底 = 上一个底
            out.append({"日期": t, "箱底": float(底), "事": e["事"], "收盘": e["收盘"]}); 上一个底 = 底
    else:
        h, l = D.high.to_numpy(), D.low.to_numpy(); idx = D.index; k = 3
        for e in EV:
            if e["事"] != "转空": continue
            t = pd.Timestamp(e["日期"]); i = idx.get_loc(t)
            pki = max(j for j in range(i + 1) if abs(h[j] - e["最高点"]) < 1e-9 * max(1, e["最高点"]))
            sl = [j for j in range(k, pki) if j + k <= i and l[j] == l[j - k:j + k + 1].min()]
            out.append({"日期": t, "箱底": float(l[sl[-1]]) if sl else float(e["收盘"]), "事": "转空", "收盘": e["收盘"]})
    return out, R


def 三步(D, tf, 候, N=2, 窗=1, 宽度=None, 实体=1.2, 量=1.3, 缩=0.8):
    """对每个候选做第 ② ③ 步。返回每个候选的结果。"""
    B = K线(D, tf); o, h, l, c, v = (B[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); idx = B.index
    pc = np.r_[c[0], c[:-1]]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14, min_periods=5).mean().to_numpy()
    v20 = pd.Series(v).rolling(20, min_periods=5).mean().shift(1).to_numpy()
    有量 = lambda j: v[j] > 0 and v20[j] > 0
    res = []
    for e in 候:
        r = dict(e); 底 = e["箱底"]
        bi0 = int(np.searchsorted(idx.values, np.datetime64(e["日期"])))        # 报警那天所在的那根（这根收盘时才走完）
        if bi0 >= len(c) or np.isnan(底): r["结果"] = "数据不够"; res.append(r); continue
        bi = None
        for j in range(bi0, min(bi0 + 窗 + 1, len(c))):
            大阴 = c[j] < o[j] and (o[j] - c[j]) > 实体 * atr[j] if atr[j] > 0 else False
            放量 = (v[j] > 量 * v20[j]) if 有量(j) else True
            if 大阴 and 放量 and c[j] < 底: bi = j; break
        if bi is None: r["结果"] = "筛掉·没有放量大阴线破位"; res.append(r); continue
        a = bi
        while a - 1 >= 0 and c[a - 1] < 底 and bi - a < 4: a -= 1
        vb = np.mean(v[a:bi + 1]); 无量 = not (vb > 0)
        r0 = None; 结 = None
        for j in range(bi + 1, min(bi + 11, len(c))):
            if c[j] >= 底: 结 = "筛掉·破位后收回箱底"; break
            if r0 is None and c[j] > c[j - 1]: r0 = j
            if j - bi >= 3 and r0 is not None and j - r0 + 1 >= N:
                if all(c[x] < 底 for x in range(j - N + 1, j + 1)):
                    vr = np.mean(v[r0:j + 1])
                    if 无量 or not (vr > 0) or vr < 缩 * vb:
                        结 = "确认"; r["确认日"] = idx[j]; r["确认收盘"] = float(c[j]); break
        if 结 is None: 结 = "筛掉·10根内没确认" if bi + 10 < len(c) else "数据不够"
        r["结果"] = 结; r["破位日"] = idx[bi]; r["量的条件跳过"] = 无量 or not 有量(bi); res.append(r)
    if 宽度 is not None:
        for r in res:
            r["宽度走弱"] = 宽度(r["日期"])
    return res


def 预警(D, tf):
    B = K线(D, tf); o, h, l, c, v = (B[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); idx = B.index
    pc = np.r_[c[0], c[:-1]]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14, min_periods=5).mean().to_numpy()
    v20 = pd.Series(v).rolling(20, min_periods=5).mean().shift(1).to_numpy(); per = {"M": 12, "W": 52, "D": 252}[tf]
    hi = pd.Series(h).rolling(per, min_periods=per // 2).max().shift(1).to_numpy(); out = []
    for j in range(per, len(c)):
        rg = h[j] - l[j]
        if v[j] > 0 and v20[j] > 0 and h[j] >= 0.97 * hi[j] and v[j] > 1.3 * v20[j] and abs(c[j] - o[j]) < 0.3 * atr[j]: out.append((idx[j], "放量滞涨"))
        elif h[j] > hi[j] and rg > 0 and (c[j] - l[j]) / rg < 1 / 3: out.append((idx[j], "冲高回落"))
    return out


def 虚惊之后跌(D, R, t, 收):
    seg = R.loc[t:]; end = seg[seg["档"] == "涨势"].index[:1]; end = end[0] if len(end) else R.index[-1]
    return round((D.close.loc[t:end].min() / 收 - 1) * 100, 1)


def 评指数(D, R, res, 认出键):
    """认出键 = '日期'（原来）或 '确认日'（三步走）。"""
    c = D.close; idx = D.index; tops = L.真顶(c); used = set(); rows = []
    ok = [r for r in res if (认出键 == "日期" or r.get("结果") == "确认") and str(r[认出键].date()) < 封存]
    for a, b in tops:
        ta, tb = idx[a], idx[b]
        if str(ta.date()) >= 封存: continue
        x = [r for r in ok if ta <= r[认出键] <= tb]
        row = {"顶": str(ta.date()), "底": str(tb.date()), "跌幅pct": round((c.iloc[b] / c.iloc[a] - 1) * 100, 1)}
        if x:
            r = x[0]; used |= {id(y) for y in x}; t = r[认出键]; px = float(c.loc[:t].iloc[-1])
            row.update({"认出": str(t.date()), "离顶天": int((t - ta).days), "离顶pct": round((px / c.iloc[a] - 1) * 100, 1), "离底还有pct": round((c.iloc[b] / px - 1) * 100, 1)})
        else: row["认出"] = "没认出"
        rows.append(row)
    虚 = []
    for r in ok:
        if id(r) in used: continue
        t = r[认出键]; px = float(c.loc[:t].iloc[-1])
        虚.append({"日期": str(t.date()), "原报警": str(r["日期"].date()), "事": r["事"], "之后最多再跌pct": 虚惊之后跌(D, R, t, px)})
    return pd.DataFrame(rows), pd.DataFrame(虚)


def 宽度函数(D, 差=10.0):
    w = pd.read_csv(os.path.join(ROOT, "probe/减仓_1121/宽度_每日.csv"), parse_dates=["date"]).set_index("date")["站上50日线pct"].rolling(10).mean()
    c = D.close; nh = c >= c.rolling(252).max()
    def f(t):
        if t < pd.Timestamp("2005-06-01"): return None
        s = nh.loc[t - pd.Timedelta(days=370):t]; s = s[s]
        if not len(s): return False
        t1 = s.index[-1]; b1 = w.loc[:t1].iloc[-1]; prev = w.loc[t1 - pd.Timedelta(days=365):t1 - pd.Timedelta(days=30)].max()
        return bool(b1 < prev - 差)
    return f


def 概(T, F):
    y = T[T["认出"] != "没认出"] if len(T) else T
    return {"真大顶": int(len(T)), "认出": int(len(y)), "认出时离顶pct中位": float(y["离顶pct"].median()) if len(y) else None,
            "认出离顶天中位": float(y["离顶天"].median()) if len(y) and "离顶天" in y else None,
            "别的转空": int(len(F)), "其中虚惊(之后再跌不到10pct)": int((F["之后最多再跌pct"] > -10).sum()) if len(F) else 0}


if __name__ == "__main__":
    OUTJ = {"指数": {}, "SOXX": {}, "BTC": {}}
    # ===== 美股三大指数 =====
    for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
        D = L.读(nm); 候, R = 候选(D, "三层一版"); 封 = [x for x in 候 if str(x["日期"].date()) >= 封存]
        pd.DataFrame(封).to_csv(os.path.join(OUT, f"封存_{nm}_报警.csv"), index=False); 候 = [x for x in 候 if str(x["日期"].date()) < 封存]
        Ta, Fa = 评指数(D, R, 候, "日期")
        段 = lambda T, F, a, b: (T[(T["顶"] >= a) & (T["顶"] < b)] if len(T) else T, F[(F["日期"] >= a) & (F["日期"] < b)] if len(F) else F)
        o = {"原来": {s: 概(*段(Ta, Fa, a, b)) for s, (a, b) in (("1928–1992", ("1900", "1993")), ("1993–2021", ("1993", 封存)))}}
        Ta.to_csv(os.path.join(OUT, f"{nm}_原来_每个大顶.csv"), index=False); Fa.to_csv(os.path.join(OUT, f"{nm}_原来_别的转空.csv"), index=False)
        for tf, tfn in (("M", "月线"), ("W", "周线")):
            for N in (1, 2, 3):
                for 窗 in ((0, 1, 2) if N == 2 else (1,)):
                    res = 三步(D, tf, 候, N=N, 窗=窗); T, F = 评指数(D, R, res, "确认日")
                    key = f"{tfn}·连续{N}根·破位窗{窗}"
                    o[key] = {s: 概(*段(T, F, a, b)) for s, (a, b) in (("1928–1992", ("1900", "1993")), ("1993–2021", ("1993", 封存)))}
                    o[key]["报警去向"] = pd.Series([r["结果"] for r in res]).value_counts().to_dict()
                    if N == 2 and 窗 == 1:
                        T.to_csv(os.path.join(OUT, f"{nm}_{tfn}_每个大顶.csv"), index=False); F.to_csv(os.path.join(OUT, f"{nm}_{tfn}_别的转空.csv"), index=False)
                        pd.DataFrame(res).to_csv(os.path.join(OUT, f"{nm}_{tfn}_每次报警.csv"), index=False)
        # 宽度过滤（只有标普 2004 起）
        if nm == "标普500指数":
            for 差 in (5.0, 10.0, 15.0):
                f = 宽度函数(D, 差); 候2 = [x for x in 候 if x["日期"] >= pd.Timestamp("2005-06-01")]
                for tf, tfn in (("M", "月线"), ("W", "周线")):
                    res = 三步(D, tf, 候2, N=2, 窗=1, 宽度=f)
                    o[f"宽度过滤·差{int(差)}·{tfn}"] = [{"报警": str(r["日期"].date()), "事": r["事"], "三步走": r["结果"], "确认日": str(r["确认日"].date()) if "确认日" in r else "", "宽度走弱": r["宽度走弱"]} for r in res]
                o[f"宽度过滤·差{int(差)}·原报警"] = [{"报警": str(x["日期"].date()), "事": x["事"], "宽度走弱": f(x["日期"])} for x in 候2]
        # 预警
        for tf, tfn in (("M", "月线"), ("W", "周线")):
            w = 预警(D, tf); tops = Ta
            o[f"预警·{tfn}"] = {"次数_到2021": int(sum(1 for t, _ in w if str(t.date()) < 封存)),
                               "真顶前12个月内有预警": [{"顶": r["顶"], "有": any(pd.Timestamp(r["顶"]) - pd.Timedelta(days=365) <= t <= pd.Timestamp(r["顶"]) + pd.Timedelta(days=31) for t, _ in w)} for _, r in tops.iterrows()]}
        OUTJ["指数"][nm] = o; print("==", nm, json.dumps({k: v for k, v in o.items() if not k.startswith(("宽度", "预警"))}, ensure_ascii=False), flush=True)
    # ===== SOXX：周线（已定）对日线 =====
    D = SC.soxx()
    for 级, tf, nm in (("周", "W", "周线版"), ("日", "D", "日线版")):
        候, R = 候选(D, "三层二版", 级别=级); 封 = [x for x in 候 if str(x["日期"].date()) >= 封存]; 候 = [x for x in 候 if str(x["日期"].date()) < 封存]
        pd.DataFrame(封).to_csv(os.path.join(OUT, f"封存_SOXX_{nm}_报警.csv"), index=False)
        Ta, Fa = 评指数(D, R, 候, "日期"); res = 三步(D, tf, 候, N=2, 窗=1); T, F = 评指数(D, R, res, "确认日")
        OUTJ["SOXX"][nm] = {"原来": {"每个大顶": Ta.to_dict("records"), "别的转空": Fa.to_dict("records")}, "三步走": {"每个大顶": T.to_dict("records"), "别的转空": F.to_dict("records"), "报警去向": pd.Series([r["结果"] for r in res]).value_counts().to_dict()}}
        for N in (1, 3):
            res2 = 三步(D, tf, 候, N=N, 窗=1); T2, F2 = 评指数(D, R, res2, "确认日"); OUTJ["SOXX"][nm][f"连续{N}根"] = 概(T2, F2)
        print("== SOXX", nm, json.dumps(OUTJ["SOXX"][nm]["三步走"]["报警去向"], ensure_ascii=False), flush=True)
    # ===== BTC：日线 =====
    D = M4.币日线("BTC"); 候, R = 候选(D, "五档")
    for N in (1, 2, 3):
        res = 三步(D, "D", 候, N=N, 窗=1)
        OUTJ["BTC"][f"连续{N}根"] = [{"报警": str(r["日期"].date()), "箱底": round(r["箱底"]), "三步走": r["结果"], "确认日": str(r["确认日"].date()) if "确认日" in r else "",
                                    "确认时离周期最高pct": None} for r in res]
    # 报警时 / 确认时离周期最高（用五档事件里的最高点）
    _, EV = M4.跑(D, M4.P币); 最高 = {e["日期"]: e["最高点"] for e in EV if e["事"] == "转空"}
    for k_ in OUTJ["BTC"]:
        for r in OUTJ["BTC"][k_]:
            pk = 最高[r["报警"]]; r["报警时离最高pct"] = round((D.close.loc[r["报警"]] / pk - 1) * 100, 1)
            if r["确认日"]: r["确认时离最高pct"] = round((D.close.loc[r["确认日"]] / pk - 1) * 100, 1); r["比报警晚几天"] = int((pd.Timestamp(r["确认日"]) - pd.Timestamp(r["报警"])).days)
    print("== BTC", json.dumps(OUTJ["BTC"]["连续2根"], ensure_ascii=False), flush=True)
    json.dump(OUTJ, open(os.path.join(OUT, "三步走_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE")
