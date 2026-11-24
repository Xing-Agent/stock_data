# -*- coding: utf-8 -*-
"""美股大指数三层状态机 · 第二版 · 照《431 拍板》（Lin 11-24 12:12~12:15）改三处 · 引擎外
认顶（转空）同第一版的默认版（Lin 11-24 10:12 放宽后）。改的是跌势里面：
 ① 「反抽没过」重写，三条同时满足：
    到位：反抽最高价进了箱底的 −2% ~ +1%，或碰到往下走的 40 周线（±1.5%）；跌破后最低已离箱底超过 8% 的，改成反弹到这波跌幅（箱顶 → 最低）的 0.5 ~ 0.618（放到 0.66 为止）。0.382 不再单独算到位。
    够久：从低点到反抽高点至少 3 根周线；只看上一次确认后的第 4 ~ 16 周。
    确认没过（二选一）：周线阴包阳，或周收盘跌破前 2 周最低收盘；或 日线收盘跌破反抽途中最后一个日线摆动低点、且收在 20 日线下。
 ② 平仓：跟进日只平 30%；剩下的要等 周线连续 2 周收在 20 周线上 / 单周收在 40 周线上 / 周收盘向上突破下降趋势线（箱顶连最近一次反抽高点）且这周最低高于上周最低 才全平。
    浮盈到过 1.5 倍 14 周 ATR 之后，止损移到成本价（日线收盘高于成本就平这一腿）。原有的「2 周内收回」「周线收回箱底 2% 并站上 10 月线」照旧全平。
 ③ 仓位：第 1 次 35%；第 2 次加到 65%；第 3 次及以后，手上的空单有浮盈才加满。
同时记一条「多头仓位」：第一次跌破降到 A（默认 50%），第二次确认降到 B（默认 20%），周线站回 20 周线买回 100%。
开关：旧反抽=True / 跟进日全平=True / 允许0382=True 用来做对照。
★ 我补的：阴包阳 = 上周收阳、这周开盘不低于上周收盘、这周收盘低于上周开盘；「往下走的 40 周线」= 比 4 周前低；下降趋势线的起点取箱顶那一周（突发急跌的取前 30 周最高那一周）。
"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
def 跑(D, 横盘系数=0.40, 跌破=0.03, 急跌倍数=4.5, 旧反抽=False, 跟进日全平=False, 允许0382=False, 多A=0.5, 多B=0.2, 仓=(0.35, 0.65, 1.0), 成本保护="成本", 级别="月"):
    W = D.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    wo, wh, wl, wc, wv = (W[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); nw = len(W); widx = W.index
    pc = np.roll(wc, 1); pc[0] = wc[0]
    watr_abs = pd.Series(np.maximum(wh - wl, np.maximum(abs(wh - pc), abs(wl - pc)))).rolling(14).mean().to_numpy(); watr = watr_abs / wc
    R = pd.Series(watr).rolling(104, min_periods=26).median().to_numpy()
    _ma = lambda k: pd.Series(wc).rolling(k).mean().to_numpy()
    _m10 = D.close.resample("ME").last().rolling(10).mean().shift(1).reindex(widx, method="ffill").to_numpy()
    # 级别：月 = 原样（40 周线 + 10 月线把关，20 周线 / 40 周线离场）；周 = 低一级（20 周 + 40 周把关，10 周 / 20 周离场）；日 = 再低一级（10 周 + 20 周把关，5 周 / 10 周离场）
    # ★ 低一级怎么换线、跌破门槛改成 1.25 倍周波幅，是我定的，拍板没给
    ma40, m10w, ma20 = {"月": (_ma(40), _m10, _ma(20)), "周": (_ma(20), _ma(40), _ma(10)), "日": (_ma(10), _ma(20), _ma(5))}[级别]      # 名字沿用：ma40 = 把关线甲兼慢离场线，m10w = 把关线乙，ma20 = 快离场线
    v10 = pd.Series(wv).rolling(10).mean().shift(1).to_numpy(); hi52 = pd.Series(wh).rolling(52).max().shift(1).to_numpy()
    didx = D.index; dc, dh, dl, dv = (D[x].to_numpy(float) for x in ("close", "high", "low", "volume")); nd = len(D)
    d2w = np.searchsorted(widx.values, didx.values); s20 = pd.Series(dc).rolling(20).mean().to_numpy()
    lo252 = pd.Series(dc).rolling(252).min().shift(1).to_numpy(); hi20 = pd.Series(dc).rolling(20).max().to_numpy()
    放 = lambda k: (not (v10[k] > 0)) or wv[k] > v10[k]
    st = np.array(["涨势"] * nd, dtype=object); 多 = np.ones(nd); EV = []; LEG = []; state = "涨势"; box = None; brk = None; att = None; 熊低 = np.inf; 熊低i = 0; 熊高 = np.nan; 旧熊 = None
    legs = []; covered = False; flat_ftd = None; long_w = 1.0; ral = None; ready = None; dsl = []
    def ev(kind, di, **kw): EV.append({"事": kind, "日期": str(didx[di].date()), "收盘": round(float(dc[di]), 2), **kw})
    def 开(di, 目标仓, 次):
        have = sum(x["size"] * x["rem"] for x in legs)
        if 目标仓 > have + 1e-9: legs.append({"size": 目标仓 - have, "rem": 1.0, "e": dc[di], "d": di, "次": 次, "real": 0.0, "be": False, "how": []})
    def 平(di, 比例, why):
        for x in legs:
            if x["rem"] > 0:
                q = x["rem"] * 比例; x["real"] += q * (x["e"] - dc[di]) / x["e"]; x["rem"] -= q; x["how"].append(why)
    def 收(di, why):
        nonlocal legs, covered, flat_ftd
        平(di, 1.0, why)
        for x in legs: LEG.append({"第几次": min(x["次"], 4), "开": str(didx[x["d"]].date()), "平": str(didx[x.get("out", di)].date()), "仓位": round(x["size"], 2), "这一腿pct": round(x["real"] * 100, 2), "占账户pct": round(x["real"] * x["size"] * 100, 3), "怎么平": "→".join(dict.fromkeys(x["how"])),
                                       "之后最多再跌pct": round((dc[x["d"]:di + 1].min() / x["e"] - 1) * 100, 1), "之后最多反弹pct": round((dc[x["d"]:di + 1].max() / x["e"] - 1) * 100, 1)})
        legs = []; covered = False; flat_ftd = None
    for di in range(nd):
        wi = d2w[di]; 周末 = (di == nd - 1) or (d2w[di + 1] != wi); i = wi if 周末 and wi < nw else wi - 1
        r = R[i] if 0 <= i < nw and R[i] > 0 else np.nan
        if di >= 6:
            j = di - 3
            if dl[j] == dl[j - 3:j + 4].min(): dsl.append((di, j, dl[j]))
        if state == "涨势":
            def 进(kind, 底, 顶, 次, 急, **kw):
                nonlocal state, brk, 熊低, 熊低i, 熊高, att, long_w, ral, ready
                state = "跌势"; t0 = int(np.argmax(wh[max(0, i - 30):i + 1])) + max(0, i - 30)
                brk = {"底": 底, "顶": 顶, "wi": i, "次": 次, "last": i, "急": 急, "t顶": (box["t0"] if (box and not 急) else t0), "up20": 0}
                熊低 = dl[di]; 熊低i = di; 熊高 = 顶; att = None; ral = {"iL": i, "L": wl[i] if i >= 0 else dl[di], "iH": i, "H": -np.inf, "ok": False}; ready = None
                ev(kind, di, 离顶pct=round((dc[di] / 顶 - 1) * 100, 1), **kw); 开(di, 仓[min(次, 3) - 1], 次); long_w = 多A if 次 == 1 else 多B
            if not np.isnan(r) and lo252[di] > 0 and dc[di] / hi20[di] - 1 < -急跌倍数 * r and dc[di] < lo252[di]:
                进("转空·突发急跌", lo252[di], float(np.max(dc[max(0, di - 504):di + 1])), 1, True)
            elif 周末 and i == wi and 旧熊 is not None and wc[i] < 旧熊["低"] and wc[i] < ma40[i] and wc[i] < m10w[i]:
                x = 旧熊; 旧熊 = None; 进("复跌·跌破上一轮低点", x["底"], x["顶"], x["次"] + 1, False)
            elif 周末 and i == wi and i >= 30 and not np.isnan(r):
                if 旧熊 is not None and wc[i] > 旧熊["顶"]: 旧熊 = None
                Tmin = min(24, max(4, 横盘系数 / r))
                if wh[i] > hi52[i] and (box is None or wh[i] > box["顶"] * 1.03): box = {"顶": wh[i], "t0": i, "底": None, "over": 0}
                elif box is not None:
                    if box["底"] is None and i - box["t0"] >= 6: box["底"] = float(wl[box["t0"] + 1:i + 1].min())
                    if wh[i] > box["顶"] and wc[i] <= box["顶"]: box["顶"] = wh[i]
                    box["over"] = box["over"] + 1 if wc[i] > box["顶"] * 1.03 else 0
                    if box["over"] >= 2: box = None
                    elif box["底"] is not None and wc[i] < box["底"] * (1 - (跌破 if 级别 == "月" else 1.25 * r)) and wc[i] < ma40[i] and wc[i] < m10w[i]:
                        if i - box["t0"] >= Tmin and 放(i): 进("转空·大顶跌破", box["底"], box["顶"], 1, False, 箱底=round(box["底"], 2), 顶部横了几周=int(i - box["t0"]))
                        elif not box.get("报过"): box["报过"] = True; ev("小顶预警", di)
            if long_w < 1 and 周末 and i == wi and wc[i] > ma20[i]: long_w = 1.0
        elif state == "跌势":
            if dl[di] < 熊低: 熊低 = dl[di]; 熊低i = di
            # 成本保护
            for x in legs:
                if x["rem"] > 0:
                    线 = x["e"] + (watr_abs[i] if 成本保护 == "成本加1ATR" else 0.0)
                    管 = 成本保护 in ("成本", "成本加1ATR") or (成本保护 == "只管第一腿" and x["次"] == 1)
                    if not x["be"] and i >= 0 and dc[di] <= x["e"] - 1.5 * watr_abs[i]: x["be"] = True
                    elif 管 and x["be"] and dc[di] > 线 and not 旧反抽: x["real"] += x["rem"] * (x["e"] - dc[di]) / x["e"]; x["rem"] = 0; x["how"].append("成本保护被打掉"); x["out"] = di
            # 跟进日
            if att is None or dl[di] < att["low"]:
                if flat_ftd is not None and att is not None and dl[di] < att["low"] * 0.99: 开(di, flat_ftd["仓"], brk["次"]); flat_ftd = None; ev("跟进日失败·重开", di)
                att = {"low": dl[di], "day": 0}
            else:
                att["day"] = att["day"] + 1 if att["day"] > 0 else (1 if dc[di] > dc[di - 1] else 0)
                if 4 <= att["day"] <= 10 and dc[di] / dc[di - 1] - 1 >= 0.015 and (not (dv[di - 1] > 0) or dv[di] > dv[di - 1]):
                    have = sum(x["size"] * x["rem"] for x in legs)
                    if 跟进日全平 and have > 0: flat_ftd = {"仓": have}; 平(di, 1.0, "跟进日全平"); ev("跟进日·全平", di)
                    elif not 跟进日全平 and not covered and have > 0: covered = True; 平(di, 0.30, "跟进日平三成"); ev("跟进日·平三成", di, 离底pct=round((dc[di] / 熊低 - 1) * 100, 1))
                    att["day"] = 99
            # 日线确认没过
            if ready is not None and not 旧反抽 and state == "跌势":
                lows = [p for (ci, j, p) in dsl if ready["d0"] <= j and ci <= di]
                if lows and dc[di] < lows[-1] and dc[di] < s20[di] and di > ready["dH"]:
                    brk["次"] += 1; brk["last"] = i if i == wi else i + 1; ev(f"反抽没过·第{brk['次']}次（日线确认）", di, 离顶pct=round((dc[di] / 熊高 - 1) * 100, 1))
                    浮盈 = sum(x["size"] * x["rem"] * (x["e"] - dc[di]) for x in legs) > 0
                    if brk["次"] == 2 or 浮盈: 开(di, 仓[min(brk["次"], 3) - 1], brk["次"])
                    long_w = min(long_w, 多B) if long_w < 1 else long_w; ready = None; ral = {"iL": brk["last"], "L": dl[di], "iH": brk["last"], "H": -np.inf, "ok": False}
            if 周末 and i == wi and state == "跌势":
                brk["up20"] = brk["up20"] + 1 if wc[i] > ma20[i] else 0
                tl = None
                if ral is not None and brk.get("rH") is not None and brk["rH"][0] > brk["t顶"]: tl = brk["顶"] + (brk["rH"][1] - brk["顶"]) / (brk["rH"][0] - brk["t顶"]) * (i - brk["t顶"])
                why = None
                if i - brk["wi"] <= 2 and i > brk["wi"] and wc[i] > brk["底"] and not brk["急"]: why = "2 周内收回"
                elif wc[i] > brk["底"] * 1.02 and wc[i] > m10w[i]: why = "周线收回箱底并站上 10 月线"
                elif not 旧反抽 and brk["up20"] >= 2: why = "连续 2 周收在 20 周线上"
                elif not 旧反抽 and wc[i] > ma40[i]: why = "收在 40 周线上"
                elif not 旧反抽 and tl is not None and wc[i] > tl and wl[i] > wl[i - 1]: why = "突破下降趋势线"
                if why:
                    收(di, why); state = "涨势"; ev("跌势结束·" + why, di, 离底pct=round((dc[di] / 熊低 - 1) * 100, 1)); 旧熊 = {"低": 熊低, "底": brk["底"], "顶": 熊高, "次": brk["次"]}; box = None; ready = None
                elif 旧反抽:
                    if 3 <= i - brk["last"] <= 16:
                        j = i - 1; lev = [brk["底"] * 0.98, ma40[j], m10w[j], 熊低 + 0.382 * (brk["顶"] - 熊低)]
                        if wh[j] >= min(x for x in lev if x > 0) and wc[i] < wl[j]:
                            brk["次"] += 1; brk["last"] = i; ev(f"反抽没过·第{brk['次']}次", di); 开(di, (0.35, 0.75, 1.0)[min(brk["次"], 3) - 1], brk["次"]); long_w = min(long_w, 多B) if long_w < 1 else long_w
                else:
                    if wl[i] < ral["L"] and not ral["ok"]: ral = {"iL": i, "L": wl[i], "iH": i, "H": -np.inf, "ok": False}
                    if wh[i] > ral["H"] and i > ral["iL"]: ral["H"] = wh[i]; ral["iH"] = i
                    H = ral["H"]; 底 = brk["底"]; 深 = 熊低 < 底 * 0.92
                    ret = (H - ral["L"]) / max(brk["顶"] - ral["L"], 1e-9)
                    碰线 = ma40[ral["iH"]] > 0 and ma40[ral["iH"]] < ma40[ral["iH"] - 4] and abs(H / ma40[ral["iH"]] - 1) <= 0.015
                    到位 = (0.5 <= ret <= 0.66) if 深 else ((0.98 <= H / 底 <= 1.01) or 碰线)
                    if 允许0382 and ret >= 0.382: 到位 = True
                    够久 = ral["iH"] - ral["iL"] + 1 >= 3; 窗 = 4 <= i - brk["last"] <= 16
                    if 到位 and 够久 and 窗:
                        ral["ok"] = True; brk["rH"] = (ral["iH"], H)
                        d0 = int(np.searchsorted(d2w, ral["iL"])); dH = int(np.searchsorted(d2w, ral["iH"] + 1)) - 1
                        ready = {"d0": d0, "dH": dH}
                        吞 = wc[i - 1] > wo[i - 1] and wo[i] >= wc[i - 1] and wc[i] < wo[i - 1]
                        if i > ral["iH"] - 1 and (吞 or wc[i] < min(wc[i - 1], wc[i - 2])) and i >= ral["iH"]:
                            brk["次"] += 1; brk["last"] = i; ev(f"反抽没过·第{brk['次']}次", di, 离顶pct=round((dc[di] / 熊高 - 1) * 100, 1))
                            浮盈 = sum(x["size"] * x["rem"] * (x["e"] - dc[di]) for x in legs) > 0
                            if brk["次"] == 2 or 浮盈: 开(di, 仓[min(brk["次"], 3) - 1], brk["次"])
                            long_w = min(long_w, 多B) if long_w < 1 else long_w; ready = None; ral = {"iL": i, "L": wl[i], "iH": i, "H": -np.inf, "ok": False}
                    elif not 窗 and i - brk["last"] > 16: ready = None
                if long_w < 1 and wc[i] > ma20[i]: long_w = 1.0
        st[di] = state; 多[di] = long_w
    if legs: 收(nd - 1, "数据到头")
    return pd.DataFrame({"close": dc, "档": st, "多头仓位": 多}, index=didx), EV, pd.DataFrame(LEG)

def 腿统计(T):
    out = {}
    if not len(T): return out
    for k, g in T.groupby("第几次"):
        r = g["这一腿pct"]
        out[int(k)] = {"腿数": int(len(g)), "每腿平均pct": round(float(r.mean()), 2), "中位pct": round(float(r.median()), 2), "赚的占比pct": round(float((r > 0).mean() * 100), 1),
                       "利润因子": round(float(r[r > 0].sum() / max(1e-9, -r[r < 0].sum())), 2), "最亏一腿pct": float(r.min()), "t": round(float(r.mean() / (r.std() / np.sqrt(len(r)))), 2) if len(r) > 2 and r.std() > 0 else None}
    out["合计占账户pct"] = round(float(T["占账户pct"].sum()), 1)
    s = T.sort_values("平")["占账户pct"].cumsum(); out["累计占账户_最深回落pct"] = round(float((s - s.cummax()).min()), 1)
    return out
def 多头(R, 年=252):
    c = R.close; ret = c.pct_change().fillna(0); w = R["多头仓位"].shift(1).fillna(1.0)
    def m(e):
        y = len(e) / 年; return {"每年pct": round((e.iloc[-1] ** (1 / y) - 1) * 100, 2), "最深亏损pct": round(float((e / e.cummax() - 1).min()) * 100, 1)}
    a = (1 + ret).cumprod(); b = (1 + ret * w).cumprod(); x = m(a); y = m(b)
    return {"一直满仓": {**x, "赚除以亏": round(x["每年pct"] / -x["最深亏损pct"], 3)}, "按规则减仓": {**y, "赚除以亏": round(y["每年pct"] / -y["最深亏损pct"], 3)}, "平均仓位pct": round(float(w.mean() * 100), 1), "减仓的天数占比pct": round(float((w < 1).mean() * 100), 1)}
