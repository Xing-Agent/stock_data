# -*- coding: utf-8 -*-
"""《382 学做空高手》拍板【高1】第 1 类：破位 / 反抽空 · 美股个股 · 日线 · 引擎外
研发池（留出池排除）、流动性好（20 日均成交额 ≥ 1000 万美元、收盘 ≥ 5 美元）、2005–2014 和 2015–2025 分开。
⚠ 用的是研究库现有的票（含一部分已退市的），数据组新补的 7,721 只退市股还没并进来 —— 结论要等补齐后再定。
拍板没写死、我补的定义（报告里标出，这一轮只跑一个点）：
  - 30 周线 = 150 日均线；「走平或向下」= 比 20 个交易日前不高
  - 「第 3 阶段区间下沿」= 之前 60 个交易日的最低价（不含当天）；A 点 = 收盘跌破它、收在当天振幅下半段、前一天没破
  - A 点止损 = 最近 10 个交易日最高价（上一次反抽高点的近似）；止损距 > 20% 不做
  - B 点 = A 点之后 30 个交易日内，最高价反抽到「原下沿 − 0.5×ATR 以上」或「向下的 50 日线的 99% 以上」，反抽那几天缩量（5 日均量 < 20 日均量），
    然后某天收盘跌破前一天最低价 → 收盘空；止损 = 这次反抽的最高价 + 0.25×ATR
  - Brandt：进场后 1~3 天内收盘回到原下沿上面 → 当天收盘走（只对 A 点）
  - 移动止损 = 最近 10 个交易日最高价，只降不升；最长拿 120 个交易日
  - 成本：单边 0.15% + 借券年化 1%（个股实际借券费会更高，退市前的票尤其高，这里偏乐观）
  - 不算分红（做空的人要倒贴分红，偏乐观）
"""
import os, sys, json, io
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/两段时间_1120")); sys.path.insert(0, ROOT)

def 装():
    import 环境2004_1120 as E
    E.install()
    from engine import cache
    P = cache._PANEL
    hold = json.load(io.open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
    dev = [s for s in hold["研发池名单"] if s in P["close"].columns]
    assert not (set(dev) & set(hold["留出池名单"]))
    f = {k: P[k][dev].astype(float) for k in ("open", "high", "low", "close", "volume")}
    spy = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数ETF长历史_1120/SPY_日线.csv"), parse_dates=["date"]).set_index("date")
    return f, spy["close_adj"].reindex(f["close"].index).ffill() if "close_adj" in spy else spy["adjusted_close"].reindex(f["close"].index).ffill()

def 信号(f, spy):
    C, H, L, V = f["close"], f["high"], f["low"], f["volume"]
    pc = C.shift(1); tr = np.maximum(H - L, np.maximum((H - pc).abs(), (L - pc).abs())); atr = tr.rolling(14).mean()
    m150 = C.rolling(150).mean(); m50 = C.rolling(50).mean()
    s150 = spy.rolling(150).mean(); 大盘四 = (spy < s150) & (s150 <= s150.shift(20))
    liq = ((C * V).rolling(20).mean() >= 1e7) & (C >= 5)
    弱线 = m150 <= m150.shift(20)
    rs = C.div(spy, axis=0); 比大盘弱 = (rs < rs.rolling(20).mean()) & (rs < rs.shift(10))
    领涨 = (H.rolling(90).max() / L.rolling(180).min()) >= 1.4
    low60 = L.rolling(60).min().shift(1)
    A = (C < low60) & (pc >= low60.shift(1)) & (C <= (H + L) / 2)
    return dict(C=C, H=H, L=L, V=V, O=f["open"], atr=atr, m50=m50, 大盘四=大盘四, liq=liq, 弱线=弱线, 比大盘弱=比大盘弱, 领涨=领涨, low60=low60, A=A)

def 跑(S, 用=("大盘", "弱线", "弱", "领涨"), 点="A", brandt=True, fee=0.0015, borrow=0.01):
    idx = S["C"].index; T = []
    g4 = S["大盘四"].values
    for sym in S["C"].columns:
        c = S["C"][sym].values; 
        if np.isnan(c).all(): continue
        h, l, o, v = S["H"][sym].values, S["L"][sym].values, S["O"][sym].values, S["V"][sym].values
        a, m50, low60, A = S["atr"][sym].values, S["m50"][sym].values, S["low60"][sym].values, S["A"][sym].values
        ok = S["liq"][sym].values.copy()
        if "大盘" in 用: ok &= g4
        if "弱线" in 用: ok &= S["弱线"][sym].values
        if "弱" in 用: ok &= S["比大盘弱"][sym].values
        if "领涨" in 用: ok &= S["领涨"][sym].values
        n = len(c); i = 200
        v5 = pd.Series(v).rolling(5).mean().values; v20 = pd.Series(v).rolling(20).mean().values
        while i < n - 2:
            if not (A[i] and ok[i]) or np.isnan(a[i]): i += 1; continue
            lvl = low60[i]; ei = None; stop = None
            if 点 == "A":
                ei = i; stop = np.nanmax(h[i - 9:i + 1])
            else:
                rh = -np.inf; touched = False
                for j in range(i + 1, min(i + 31, n - 1)):
                    rh = max(rh, h[j])
                    if (h[j] >= lvl - 0.5 * a[j]) or (m50[j] < m50[j - 5] and h[j] >= 0.99 * m50[j]):
                        if v5[j] < v20[j]: touched = True
                    if c[j] > lvl + 1.0 * a[j]: break                       # 反抽直接站回去了，作废
                    if touched and c[j] < l[j - 1]: ei = j; stop = rh + 0.25 * a[j]; break
                if ei is None: i += 1; continue
            E = c[ei]; R = stop - E
            if R <= 0 or R / E > 0.20: i = ei + 1; continue
            s = stop; why = "到时间"; x = None; jj = ei
            for j in range(ei + 1, min(ei + 121, n)):
                jj = j
                if np.isnan(c[j]): x = c[j - 1] if not np.isnan(c[j - 1]) else E; why = "停牌/退市"; break
                if o[j] >= s: x = o[j]; why = "止损"; break
                if h[j] >= s: x = s; why = "止损"; break
                if 点 == "A" and brandt and j - ei <= 3 and c[j] > lvl: x = c[j]; why = "收回形态里(Brandt)"; break
                s = min(s, np.nanmax(h[j - 9:j + 1]))
            if x is None: x = c[jj]
            days = jj - ei; gross = (E - x) / R; cost = (fee * (E + x) + borrow * days / 252 * E) / R
            T.append({"票": sym, "进": idx[ei], "年": idx[ei].year, "毛R": gross, "净R": gross - cost, "怎么出": why, "拿了几天": days, "止损距pct": R / E * 100, "大盘第四阶段": bool(g4[ei])})
            i = jj + 1
    return pd.DataFrame(T)

def 汇(t):
    if len(t) == 0: return {"笔数": 0}
    r = t["净R"]; w = r[r > 0].sum(); ls = -r[r < 0].sum(); e = t.sort_values("进")["净R"].cumsum()
    return {"笔数": int(len(t)), "每笔毛R": round(float(t["毛R"].mean()), 3), "每笔净R": round(float(r.mean()), 3), "胜率pct": round(float((r > 0).mean() * 100), 1),
            "利润因子": round(float(w / ls), 2) if ls > 0 else None, "最大回撤R(按进场日排)": round(float((e - e.cummax()).min()), 1), "平均拿几天": round(float(t["拿了几天"].mean()), 1), "止损距中位pct": round(float(t["止损距pct"].median()), 1)}

if __name__ == "__main__":
    f, spy = 装(); S = 信号(f, spy); out = {}
    全 = ("大盘", "弱线", "弱", "领涨")
    组 = {"全部条件": 全, "去掉大盘第四阶段": ("弱线", "弱", "领涨"), "去掉30周线": ("大盘", "弱", "领涨"), "去掉比大盘弱": ("大盘", "弱线", "领涨"), "去掉前领涨股": ("大盘", "弱线", "弱"), "什么条件都不加(只要流动性)": ()}
    for 点 in ("A", "B"):
        for nm, 用 in 组.items():
            t = 跑(S, 用, 点); t.to_csv(os.path.join(HERE, "out", f"{点}点_{nm}.csv"), index=False)
            seg = {"2005–2014": t[(t["年"] >= 2005) & (t["年"] <= 2014)], "2015–2025": t[(t["年"] >= 2015) & (t["年"] <= 2025)]}
            out[f"{点}点｜{nm}"] = {k: {"全部": 汇(g), "分年": {int(y): 汇(x) for y, x in g.groupby("年")}, "怎么出": g["怎么出"].value_counts().to_dict(),
                                       "大盘第四阶段内": 汇(g[g["大盘第四阶段"]]), "大盘第四阶段外": 汇(g[~g["大盘第四阶段"]])} for k, g in seg.items()}
            print(点, nm, {k: (v["全部"].get("笔数"), v["全部"].get("每笔净R")) for k, v in out[f"{点}点｜{nm}"].items()}, flush=True)
            json.dump(out, io.open(os.path.join(HERE, "out", "第一类_美股_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
        if 点 == "A":
            t = 跑(S, 全, "A", brandt=False); seg = {"2005–2014": t[(t["年"] >= 2005) & (t["年"] <= 2014)], "2015–2025": t[(t["年"] >= 2015) & (t["年"] <= 2025)]}
            out["A点｜全部条件｜不用Brandt提前走"] = {k: {"全部": 汇(g)} for k, g in seg.items()}
    json.dump(out, io.open(os.path.join(HERE, "out", "第一类_美股_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE")
