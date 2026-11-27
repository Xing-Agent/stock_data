# -*- coding: utf-8 -*-
"""《问 Gemini 线 465 拍板》第 2、3、4 条 · 引擎外 · 不改状态机，只在它每天的档上叠一层。
第 2 条 上一波大跌（日线）：先找过去 回看L 天的最高点，L = 那之后的最低价；H = L 之前 段长 天以内、日线 ZigZag（拐点间 ≥ 倍×ATR14）的高点里，
        最近的一个满足「跌到 L ≥ 跌幅门槛、途中反弹 ≤ 0.5×这段跌幅」的。次高点 = H 之后、L 之前最近的日线摆动高点（左右各 5 根），没有就用 H。
        转涨触发 =（收盘过次高点 且 过 0.5）或 收盘过 0.618；连续 连 天成立；EMA20 比 3 天前高。
第 3 条 撤销（任一）：收盘 < 触发前 10 天最低 − 撤a×ATR；连续 撤b 天收在 EMA20 下且 EMA20 比 3 天前低；触发后 撤c 天里没创新高也没站上 50 日线。
第 4 条 筑底期里看箱内高点：最新摆动高点比箱内最高摆动高点低 ≥ 派×ATR 且 150 日线（30 周线）向下 → 再派发，可空；
        新的摆动高点比上一个高、或摆动低点比上一个高 → 回到筑底。
箱顶假突破沿用 1126 那版（冲出箱顶后 20 天内收回箱顶下 0.3×ATR，且冲出段最高没超过箱顶 + 0.25×箱高）。
开关：涨势、转涨期、提前转涨 → 禁空；筑底期 → 假突破确认 或 再派发 才可空；见顶、跌势 → 可空。"""
import os, re, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = importlib.util.spec_from_file_location("m4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); M4 = importlib.util.module_from_spec(sp); sp.loader.exec_module(M4)
封存 = pd.Timestamp("2021-12-31")
def 读(sym):
    币 = sym in ("BTC", "ETH"); D = M4.币日线(sym) if 币 else M4.美股日线(sym)
    R = pd.read_csv(os.path.join(ROOT, f"probe/大周期五档_1123/out4/{sym}_四版_每天的档.csv"), index_col=0, parse_dates=True)
    if not 币: D = D.loc[:封存]; R = R.loc[:封存]                                  # 美股 2022 年以后封存，不读
    return D.loc[D.index.isin(R.index)], R
def 跑(sym="BTC", 倍=3.0, 段长=90, 回看L=180, 跌幅=0.20, 连=2, 撤a=0.25, 撤b=2, 撤c=20, 派=1.5, 窗=20, 破=0.3):
    D, R = 读(sym); o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(D); idx = D.index
    档 = R["档"].reindex(idx).to_numpy(); why = R["切换原因"].reindex(idx).fillna("").to_numpy()
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().bfill().to_numpy()
    e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy(); s50 = pd.Series(c).rolling(50).mean().to_numpy(); s150 = pd.Series(c).rolling(150).mean().to_numpy()
    Z = []; d = 0; eh = el = 0                                                     # 日线 ZigZag：(拐点位置, 价, 高/低, 确认位置)
    for i in range(1, n):
        if h[i] > h[eh]: eh = i
        if l[i] < l[el]: el = i
        if d >= 0 and h[eh] - l[i] >= 倍 * atr[i] and eh < i: Z.append((eh, h[eh], "高", i)); d = -1; el = i
        elif d <= 0 and h[i] - l[el] >= 倍 * atr[i] and el < i: Z.append((el, l[el], "低", i)); d = 1; eh = i
    SH = [j for j in range(5, n - 5) if h[j] == h[j - 5:j + 6].max()]; SL = [j for j in range(5, n - 5) if l[j] == l[j - 5:j + 6].min()]
    提前 = np.zeros(n, bool); 假突破 = np.zeros(n, bool); 再派发 = np.zeros(n, bool); st = None; 冷却 = False; box = None; 触发表 = []; 箱表 = []
    for i in range(max(回看L, 160), n):
        pk = i - 回看L + int(np.argmax(h[i - 回看L:i + 1])); j0 = pk + int(np.argmin(l[pk:i + 1])); L = l[j0]; H = None   # 先找回看期里的最高点，L = 那之后的最低点（这一轮下跌的低点，不是更早的旧低点）
        for (zp, p, k, zc) in reversed(Z):
            if k != "高" or zp >= j0 or zc > i or j0 - zp > 段长: continue
            if (p - L) / p < 跌幅: continue
            lo = np.minimum.accumulate(l[zp:j0 + 1]); reb = (h[zp:j0 + 1] - lo).max()
            if reb > 0.5 * (p - L): continue
            H = p; Hp = zp; break
        # ---- 第 3 条：撤销
        if st is not None:
            t0 = st["t0"]; 因 = None
            if c[i] < st["low10"] - 撤a * atr[i]: 因 = "跌破触发前 10 天最低"
            elif all(c[i - q] < e20[i - q] for q in range(撤b)) and e20[i] < e20[i - 3]: 因 = f"连续 {撤b} 天收在 20 日线下且线掉头"
            elif i - t0 == 撤c and h[t0 + 1:i + 1].max() <= st["高"] and not (c[t0:i + 1] > s50[t0:i + 1]).any(): 因 = f"{撤c} 天没创新高也没站上 50 日线"
            elif 档[i] in ("涨势", "涨势·中继", "转涨期"): 因 = "状态机自己转涨了（交接，不算撤销）"
            if 因:
                st.update(撤销日=str(idx[i].date()), 撤销价=round(c[i], 2), 原因=因, 隔了几天=i - t0)
                for k_ in (10, 20, 40):
                    if i + k_ < n: st[f"撤后{k_}天涨跌"] = round(c[i + k_] / c[i] - 1, 3)
                st.pop("low10"); st.pop("高"); 触发表.append(st); st = None; 冷却 = True
        # ---- 第 2 条：转涨触发（只在状态机没说涨的时候起作用）
        if H is not None and i > j0:
            pr = [j for j in SH if Hp < j < j0 and j + 5 <= i]; lh = h[pr[-1]] if pr else H
            cond = lambda q: (c[q] > lh and c[q] > L + 0.5 * (H - L)) or c[q] > L + 0.618 * (H - L)
            now = all(cond(i - q) for q in range(连)) and e20[i] > e20[i - 3]
            if not cond(i): 冷却 = False                                              # 条件掉下去过，才允许再触发
            if st is None and not 冷却 and now and 档[i] in ("跌势", "见顶", "筑底期"):
                st = dict(t0=i, 触发日=str(idx[i].date()), 触发价=round(c[i], 2), 当时的档=档[i], 大跌起=f"{idx[Hp].date()} {round(H, 2)}", 大跌止=f"{idx[j0].date()} {round(L, 2)}", 跌幅=round((H - L) / H, 3),
                          次高点=round(lh, 2), 线0618=round(L + 0.618 * (H - L), 2), low10=l[i - 10:i].min(), 高=h[i])
        else: 冷却 = False
        if st is not None: 提前[i] = True
        # ---- 筑底期：箱顶假突破 + 第 4 条再派发
        m = re.search(r"箱底 ([\d,\.]+)、箱顶 ([\d,\.]+)", why[i])
        if why[i].startswith("进筑底期") and m:
            box = dict(起=i, 底=float(m.group(1).replace(",", "")), 顶=float(m.group(2).replace(",", "")), 冲=None, 高=0, 确认=False, 有效=False, 派=False, 派天=0, 首派=None)
        if 档[i] != "筑底期" and box is not None:
            箱表.append(dict(品种=sym, 进箱=str(idx[box["起"]].date()), 出箱=str(idx[i].date()), 天数=i - box["起"], 箱底=box["底"], 箱顶=box["顶"], 出箱后的档=档[i], 判再派发的天数=box["派天"], 第一次判再派发=box["首派"],
                           出箱方向="向上" if 档[i] in ("涨势", "涨势·中继", "转涨期") else "向下" if 档[i] in ("跌势",) else 档[i])); box = None
        if box is not None:
            hs = [j for j in SH if box["起"] - 60 <= j and j + 5 <= i]; ls = [j for j in SL if box["起"] - 60 <= j and j + 5 <= i]
            if len(hs) >= 2:
                top = max(h[j] for j in hs); last = h[hs[-1]]
                if last <= top - 派 * atr[i] and s150[i] < s150[i - 20]: box["派"] = True
                if h[hs[-1]] > h[hs[-2]] or (len(ls) >= 2 and l[ls[-1]] > l[ls[-2]] and ls[-1] > hs[-1]): box["派"] = False
            if box["派"]:
                再派发[i] = True; box["派天"] += 1
                if box["首派"] is None: box["首派"] = str(idx[i].date())
            if box["冲"] is None and c[i] > box["顶"]: box["冲"] = i; box["高"] = h[i]
            if box["冲"] is not None:
                box["高"] = max(box["高"], h[i])
                if box["高"] > box["顶"] + 0.25 * (box["顶"] - box["底"]): box["有效"] = True
                if not box["确认"] and not box["有效"] and i - box["冲"] <= 窗 and c[i] < box["顶"] - 破 * atr[i]: box["确认"] = True
                elif box["确认"] and c[i] > box["顶"]: box.update(确认=False, 冲=i, 高=h[i])
                elif not box["确认"] and i - box["冲"] > 窗 and c[i] < box["顶"]: box.update(冲=None, 高=0)
            if box["确认"]: 假突破[i] = True
    if st is not None: st.update(撤销日="还挂着", 隔了几天=n - 1 - st["t0"]); st.pop("low10"); st.pop("高"); 触发表.append(st)
    if box is not None: 箱表.append(dict(品种=sym, 进箱=str(idx[box["起"]].date()), 出箱="还在箱里", 天数=n - 1 - box["起"], 箱底=box["底"], 箱顶=box["顶"], 出箱后的档="", 判再派发的天数=box["派天"], 第一次判再派发=box["首派"], 出箱方向=""))
    可空 = np.array([(档[i] in ("跌势", "见顶") and not 提前[i]) or (档[i] == "筑底期" and (假突破[i] or 再派发[i]) and not 提前[i]) for i in range(n)])
    T = pd.DataFrame({"close": c, "档": 档, "提前转涨": 提前, "箱顶假突破": 假突破, "再派发": 再派发, "可空": 可空}, index=idx)
    for x in 触发表: x.pop("t0", None); x["品种"] = sym
    return T, 触发表, 箱表
考题 = (("2019-04-03~04-30", "2019-04-03", "2019-04-30", "挡住"), ("2020-04-30~05-15", "2020-04-30", "2020-05-15", "挡住"), ("2020-08-01~08-10", "2020-08-01", "2020-08-10", "挡住"), ("2020-11-05~11-13", "2020-11-05", "2020-11-13", "挡住"),
        ("2026-09-21~10-07（顶，左侧另算）", "2026-09-21", "2026-10-07", "—"), ("2026-10-08~11-20", "2026-10-08", "2026-11-20", "放行"), ("对照 2018 全年", "2018-01-01", "2018-12-31", "大部分能空"), ("对照 2019 全年", "2019-01-01", "2019-12-31", "—"),
        ("对照 2020-03-01~03-13 暴跌", "2020-03-01", "2020-03-13", "能空"), ("对照 2021-05-19~07-20", "2021-05-19", "2021-07-20", "能空"), ("2026-06-01~07-31（箱内高点下移）", "2026-06-01", "2026-07-31", "能空"), ("2026-08-01~09-20（高点抬高）", "2026-08-01", "2026-09-20", "不能空"))
def 考(T):
    rows = []
    for nm, a, b, 应 in 考题:
        x = T.loc[a:b]
        if len(x): rows.append(dict(考题=nm, 应该=应, 可空天数占比=round(float(x.可空.mean()), 2), 提前转涨占比=round(float(x.提前转涨.mean()), 2), 再派发占比=round(float(x.再派发.mean()), 2), 当时的档=" ".join(f"{k}{v}" for k, v in x["档"].value_counts().items())))
    return pd.DataFrame(rows)
if __name__ == "__main__":
    pd.set_option("display.width", 260); pd.set_option("display.max_colwidth", 70); pd.set_option("display.max_rows", 300)
    what = sys.argv[1] if len(sys.argv) > 1 else "主"
    if what == "主":
        T, 触, 箱 = 跑("BTC"); T.to_csv(os.path.join(HERE, "out", "BTC_每天能不能空_日线版.csv")); print(考(T).to_string(index=False))
        A = pd.DataFrame(触); A.to_csv(os.path.join(HERE, "out", "BTC_转涨触发和撤销.csv"), index=False); print(A.to_string(index=False)); print(pd.DataFrame(箱).to_string(index=False))
    elif what == "相邻":
        out = []
        for kw in (dict(), dict(倍=2.5), dict(倍=3.5), dict(段长=60), dict(段长=120), dict(连=3), dict(撤a=0.2), dict(撤a=0.5), dict(撤b=1), dict(撤b=3), dict(撤c=15), dict(撤c=30), dict(派=1.0), dict(派=2.0), dict(回看L=120), dict(回看L=365)):
            T, 触, 箱 = 跑("BTC", **kw); k = 考(T).set_index("考题")["可空天数占比"]; out.append(dict(参数=str(kw) if kw else "默认", 触发次数=len(触), **k.to_dict()))
        O = pd.DataFrame(out); O.to_csv(os.path.join(HERE, "out", "BTC_相邻参数.csv"), index=False); print(O.T.to_string())
    elif what == "全品种":
        触all, 箱all = [], []
        for s in ("BTC", "ETH", "QQQ", "SPY"):
            for kw in ((dict(),) if s in ("BTC", "ETH") else (dict(跌幅=0.08),)):
                T, 触, 箱 = 跑(s, **kw); 触all += 触; 箱all += 箱; T.to_csv(os.path.join(HERE, "out", f"{s}_每天能不能空_日线版.csv"))
        pd.DataFrame(触all).to_csv(os.path.join(HERE, "out", "全品种_转涨触发和撤销.csv"), index=False); pd.DataFrame(箱all).to_csv(os.path.join(HERE, "out", "全品种_筑底箱子.csv"), index=False)
        print(pd.DataFrame(触all).to_string(index=False)); print(pd.DataFrame(箱all).to_string(index=False))
