# -*- coding: utf-8 -*-
"""美股大指数三层状态机 · 第一版 · 照《423 拍板》第 1~3 条 · 引擎外 · SPY / QQQ 1993（1999）至今
月线定大档（10 月线）、周线认派发顶和二次确认、日线只管突发急跌和跟进日。
★ 拍板没写死、我补的（报告里标出）：
  放量 = 当周量 > 前 10 周平均；「收盘在当周振幅下半截」= (收 − 低) ÷ (高 − 低) < 0.5
  AR 的箱底 = BC 之后 6 周内的最低价；箱顶被周线收盘站上 3% 连续 2 周 = 顶作废，重新找
  ST = BC 六周以后，某周最高到过箱顶 3% 以内、收盘在箱顶下；UTAD = 某周最高超过箱顶、收盘收回箱顶下
  反抽没过 = 首次跌破后第 3~16 周内，某周最高碰到（箱底的 2% 以内 / 40 周线 / 10 月线 / 这波跌幅的 0.382 以上），随后一周收盘跌破那周最低
  跟进日 = 新低之后第一根收阳算第 1 天；第 4~10 天里某天涨 ≥ 1.5% 且量大于前一天；期间盘中跌破起点低点就重数
  底部箱子上沿 = 这轮跌势最低点到跟进日之间的最高价；试仓止损 = 起点低点下 1%
  10 月线只用已走完的月份。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = importlib.util.spec_from_file_location("m4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); M4 = importlib.util.module_from_spec(sp); sp.loader.exec_module(M4)

def 跑(D, 横盘系数=0.40, 跌破=0.03, 急跌倍数=4.5, 要ST或UT=True, BC严=True, 固定横盘周=None, 跟进日要二次探底=False):
    W = D.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    wo, wh, wl, wc, wv = (W[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); nw = len(W); widx = W.index
    pc = np.roll(wc, 1); pc[0] = wc[0]
    watr = pd.Series(np.maximum(wh - wl, np.maximum(abs(wh - pc), abs(wl - pc)))).rolling(14).mean().to_numpy() / wc
    R = pd.Series(watr).rolling(104, min_periods=26).median().to_numpy()
    ma40 = pd.Series(wc).rolling(40).mean().to_numpy(); ma20 = pd.Series(wc).rolling(20).mean().to_numpy()
    mth = D.close.resample("ME").last(); m10 = mth.rolling(10).mean().shift(1)          # 已走完的月份
    m10w = m10.reindex(widx, method="ffill").to_numpy()
    v10 = pd.Series(wv).rolling(10).mean().shift(1).to_numpy(); hi52 = pd.Series(wh).rolling(52).max().shift(1).to_numpy()
    didx = D.index; dc, dh, dl, dv = (D[x].to_numpy(float) for x in ("close", "high", "low", "volume")); nd = len(D)
    d2w = np.searchsorted(widx.values, didx.values)          # 这一天属于第几周（那周周五才走完）
    lo252 = pd.Series(dc).rolling(252).min().shift(1).to_numpy(); hi20 = pd.Series(dc).rolling(20).max().to_numpy()
    放 = lambda k: (not (v10[k] > 0)) or wv[k] > v10[k]      # 没量当放量：早年没有成交量的周，放量这条算通过
    st = np.array(["涨势"] * nd, dtype=object); EV = []; state = "涨势"; box = None; brk = None; att = None; trial = None; 熊低 = np.inf; 熊低i = 0; 熊起 = 0; 熊高 = np.nan; last_w = -1; 旧熊 = None
    def ev(kind, di, **kw): EV.append({"事": kind, "日期": str(didx[di].date()), "收盘": round(float(dc[di]), 2), **kw})
    for di in range(nd):
        wi = d2w[di]; 周末 = (di == nd - 1) or (d2w[di + 1] != wi)
        i = wi if 周末 and wi < nw else wi - 1                 # 已走完的最后一周
        r = R[i] if i >= 0 and i < nw and R[i] > 0 else np.nan
        if state == "涨势":
            # 突发急跌（日线）
            if not np.isnan(r) and lo252[di] > 0 and dc[di] / hi20[di] - 1 < -急跌倍数 * r and dc[di] < lo252[di]:
                state = "跌势"; brk = {"底": lo252[di], "顶": hi20[di], "wi": i, "次": 1, "last": i, "急": True}; 熊低 = dl[di]; 熊低i = di; 熊起 = di; 熊高 = float(np.max(dc[max(0, di - 504):di + 1])); att = None
                ev("转空·突发急跌", di, 离顶pct=round((dc[di] / 熊高 - 1) * 100, 1))
            elif 周末 and i == wi and 旧熊 is not None and wc[i] < 旧熊["低"] and wc[i] < ma40[i] and wc[i] < m10w[i]:
                state = "跌势"; brk = {"底": 旧熊["底"], "顶": 旧熊["顶"], "wi": i, "次": 旧熊["次"] + 1, "last": i, "急": False}; 熊低 = wl[i]; 熊低i = di; 熊高 = 旧熊["顶"]; att = None
                ev("复跌·跌破上一轮低点", di, 上一轮低点=round(旧熊["低"], 2), 离顶pct=round((dc[di] / 熊高 - 1) * 100, 1)); 旧熊 = None
            elif 周末 and i == wi and i >= 30 and not np.isnan(r):
                if 旧熊 is not None and wc[i] > 旧熊["顶"]: 旧熊 = None
                Tmin = 固定横盘周 if 固定横盘周 else min(24, max(4, 横盘系数 / r))
                rng = wh[i] - wl[i]
                isBC = wh[i] > hi52[i] and ((放(i) and rng > 0 and (wc[i] - wl[i]) / rng < 0.5) if BC严 else True)
                if isBC and (box is None or wh[i] > box["顶"] * 1.03 or box.get("废")):
                    box = {"顶": wh[i], "t0": i, "底": None, "ST": False, "UT": False, "over": 0}
                elif box is not None:
                    if box["底"] is None and i - box["t0"] >= 6: box["底"] = float(wl[box["t0"] + 1:i + 1].min())
                    if wh[i] > box["顶"]:
                        if wc[i] <= box["顶"]: box["UT"] = True; box["顶"] = wh[i]
                    if wc[i] > box["顶"] * 1.03: box["over"] += 1
                    else: box["over"] = 0
                    if box["over"] >= 2: box = None
                    elif i - box["t0"] > 6 and wh[i] >= box["顶"] * 0.97 and wc[i] < box["顶"]: box["ST"] = True
                    if box is not None and box["底"] is not None and wc[i] < box["底"] * (1 - 跌破) and wc[i] < ma40[i] and wc[i] < m10w[i]:
                        够久 = i - box["t0"] >= Tmin; 有结构 = (box["ST"] or box["UT"]) or not 要ST或UT; 放量 = 放(i)
                        if 够久 and 有结构 and 放量:
                            state = "跌势"; brk = {"底": box["底"], "顶": box["顶"], "wi": i, "次": 1, "last": i, "急": False}; 熊低 = wl[i]; 熊低i = di; 熊起 = di; 熊高 = box["顶"]; att = None
                            ev("转空·大顶跌破", di, 箱底=round(box["底"], 2), 箱顶=round(box["顶"], 2), 顶部横了几周=int(i - box["t0"]), 离顶pct=round((dc[di] / box["顶"] - 1) * 100, 1))
                        elif not box.get("报过"):
                            box["报过"] = True
                            ev("小顶预警", di, 缺=("横盘不够久 " if not 够久 else "") + ("没有ST或UTAD " if not 有结构 else "") + ("没放量" if not 放量 else ""), 顶部横了几周=int(i - box["t0"]), 离顶pct=round((dc[di] / box["顶"] - 1) * 100, 1)); last_w = i
        elif state == "跌势":
            if dl[di] < 熊低: 熊低 = dl[di]; 熊低i = di
            # 跟进日（日线）
            if att is None or dl[di] < att["low"]: att = {"low": dl[di], "day": 0, "i": di, "探过": att is not None and dl[di] >= 熊低 * 0.999 and di - 熊低i >= 10}
            else:
                if att["day"] == 0:
                    if dc[di] > dc[di - 1]: att["day"] = 1
                else: att["day"] += 1
                if 4 <= att["day"] <= 10 and dc[di] / dc[di - 1] - 1 >= 0.015 and (not (dv[di - 1] > 0) or dv[di] > dv[di - 1]) and (not 跟进日要二次探底 or att["low"] > 熊低 or di - 熊低i >= 15):
                    trial = {"stop": att["low"] * 0.99, "top": float(dh[熊低i:di + 1].max()), "i": di}; state = "试仓"
                    ev("跟进日·解除跌势试仓", di, 离底pct=round((dc[di] / 熊低 - 1) * 100, 1), 离顶pct=round((dc[di] / 熊高 - 1) * 100, 1), 第几天=att["day"])
            if state == "跌势" and 周末 and i == wi:
                if i - brk["wi"] <= 2 and wc[i] > brk["底"] and not brk["急"] and i > brk["wi"]:
                    state = "涨势"; ev("2 周内收回·不算跌破", di); box = None; 旧熊 = {"低": 熊低, "底": brk["底"], "顶": 熊高, "次": brk["次"]}
                elif wc[i] > brk["底"] * 1.02 and wc[i] > m10w[i]:
                    state = "涨势"; ev("证伪·空单全平", di, 离底pct=round((dc[di] / 熊低 - 1) * 100, 1)); box = None; 旧熊 = {"低": 熊低, "底": brk["底"], "顶": 熊高, "次": brk["次"]}
                elif 3 <= i - brk["last"] <= 16 and i >= 1:
                    j = i - 1; lev = [brk["底"] * 0.98, ma40[j], m10w[j], 熊低 + 0.382 * (brk["顶"] - 熊低)]
                    if wh[j] >= min(x for x in lev if x > 0) and wc[i] < wl[j]:
                        brk["次"] += 1; brk["last"] = i; ev(f"反抽没过·第{brk['次']}次确认", di, 离顶pct=round((dc[di] / 熊高 - 1) * 100, 1))
        elif state == "试仓":
            if dl[di] < trial["stop"]:
                state = "跌势"; ev("跟进日失败·退回跌势", di); att = {"low": dl[di], "day": 0, "i": di, "探过": True}
                if dl[di] < 熊低: 熊低 = dl[di]; 熊低i = di
            elif 周末 and i == wi and wc[i] > trial["top"] and wc[i] > ma20[i]:
                state = "涨势"; box = None; ev("大底确认·加满", di, 离底pct=round((dc[di] / 熊低 - 1) * 100, 1)); 旧熊 = {"低": 熊低, "底": brk["底"], "顶": 熊高, "次": brk["次"]}
        st[di] = state
    return pd.DataFrame({"close": dc, "档": st}, index=didx), EV

色 = {"涨势": "#a8dab5", "跌势": "#d64545", "试仓": "#4a90d9"}
def 画(R, EV, 名):
    import matplotlib, glob; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in glob.glob("/usr/share/fonts/**/*", recursive=True):
        if os.path.isfile(f) and any(x in f.lower() for x in ("cjk", "wqy", "notosanssc")): fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    fig, ax = plt.subplots(figsize=(18, 8)); ax.plot(R.index, R.close, color="#222", lw=0.9); ax.set_yscale("log"); s = R["档"].values; a = 0
    for b in range(1, len(R) + 1):
        if b == len(R) or s[b] != s[a]: ax.axvspan(R.index[a], R.index[b - 1], color=色[s[a]], alpha=0.45, lw=0); a = b
    for e in EV:
        if e["事"] == "小顶预警": ax.plot(pd.Timestamp(e["日期"]), e["收盘"], "v", color="#f2b134", ms=7)
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=色[x], alpha=0.6) for x in 色] + [plt.Line2D([], [], marker="v", color="#f2b134", ls="")], labels=list(色) + ["小顶预警（只减仓不改档）"], loc="upper left", ncol=4, fontsize=12)
    ax.set_title(f"{名} 大周期三层状态机 · 第一版（照《423 拍板》）", fontsize=15); ax.grid(alpha=0.2); fig.tight_layout(); fig.savefig(os.path.join(HERE, "out", f"{名}_三层_第一版.png"), dpi=110); plt.close(fig)

if __name__ == "__main__":
    out = {}
    for 名 in ("SPY", "QQQ"):
        D = M4.美股日线(名); R, EV = 跑(D); out[名] = EV; R.to_csv(os.path.join(HERE, "out", f"{名}_每天的档.csv")); 画(R, EV, 名)
        print("==", 名, R["档"].value_counts().to_dict(), "今天", R["档"].iloc[-1])
        for e in EV: print("  ", e)
    json.dump(out, open(os.path.join(HERE, "out", "事件_主版.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
