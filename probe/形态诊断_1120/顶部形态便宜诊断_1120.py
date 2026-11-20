#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顶部形态「便宜诊断」：是程序认错了，还是这些形态在美股本来就不赚（2026-11-20 · Lin 14:11 拍板《329》第 1 条）

大白话：不请 Lin 标一张图，先用数据分清两件事 —— 顶部形态做空不赚，是因为「没等跌破确认就进」，还是因为「在美股上本来就不赚」。
在研发池日线上，用不偷看未来的办法认四种顶，同一批形态分别按「不等确认就空」和「收盘跌破颈线才空」各做一遍，再加三个对照。

怎么认（全部只用当天及以前的 K 线）：
  高低点：照 TradingView pivothigh(5, 5) —— 一个高点要等右边 5 根走完才算数，信号记在确认那天。
  容差全部用 ATR(14) 的倍数，不用百分比。之前要涨过：第一个顶前 120 天内从最低到这个顶 ≥ 25%。
  双顶      两个顶相差 ≤ 1.0 ATR，相隔 10~120 天，形态高度（顶到中间最低）≥ 2.5 ATR。颈线 = 两顶之间的最低价
  三重顶    三个顶相差 ≤ 1.2 ATR，两个谷相差 ≤ 1.0 ATR，跨度 25~120 天，高度 ≥ 2.5 ATR。颈线 = 两个谷里较低的
  头肩顶    三个顶，中间那个比两边都高 ≥ 1.0 ATR，两肩相差 ≤ 1.5 ATR，跨度 25~150 天。颈线 = 两个谷里较低的
  顶部假突破 前高之后回调过 ≥ 2.5 ATR；某天最高价冲过前高 0.15~1.5 ATR、收盘回到前高下方、上影线 ≥ 当天振幅一半
两种进法：
  不等确认   最后一个顶被确认的那天收盘就空（假突破：信号那天收盘就空）—— 对应我们以前「右顶过几天就算」的做法
  等确认     之后 40 天内第一次「收盘跌破颈线 0.3 ATR」才空，期间收盘不能高过形态最高点（假突破：3 天内收盘跌破信号 K 线最低价）
大盘环境：不限 / 只在「SPY 收盘低于 200 日线，或这只票收盘低于自己的 50 日线」时才空（都用前一天的）。
出场（两种进法用同一套）：止损 = 形态最高点上方 0.5 ATR；目标 = 2 倍风险；最多拿 60 天，到期按收盘。跳空越过止损按开盘价。
三个对照：
  随机做空   同一只票、同一年，随机挑一天空，止损距离用同样的 ATR 倍数（取这一类形态的中位数），同样的出场，抽 20 轮
  拿掉止损   信号后 5 / 10 / 20 天的涨跌，和这 20 天里最多顺着走了几个 ATR、最多逆着走了几个 ATR
  逐个去掉   形态 / 背离（最后一个顶的 RSI 比第一个顶低 3 以上）/ 放量滞涨（最后一个顶那天成交量 ≥ 1.5 倍 20 日均量且收在当天下半截）
范围：研发池，信号当天在流动性池中档里。环境变量 XING_WIN=2004 时跑 2005–2014。没扣成本。engine/ 没碰。
"""
import io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
WIN = os.environ.get("XING_WIN", "2015"); rng = np.random.default_rng(20261120)
if WIN == "2004":
    P = pd.read_parquet(os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet")); MK = pd.read_parquet(os.path.join(ROOT, "probe/两段时间_1120/流动性池掩膜2004_中.parquet"))
    spy = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数ETF长历史_1120/SPY_日线.csv"), parse_dates=["date"]).set_index("date")["close_adj"]
else:
    P = pd.read_parquet(os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet")); MK = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet"))
    sys.path.insert(0, ROOT); from engine import data; spy = data.load_benchmark("SPY")["close"].astype(float)
syms = [s for s in MK.columns if s in P["close"].columns and MK[s].any()]
idx = P["close"].index; spy = spy.reindex(idx).ffill(); spy_dn = (spy < spy.rolling(200, min_periods=200).mean()).shift(1).fillna(False).to_numpy()
mkA = MK.reindex(idx).fillna(False); t0 = idx.get_loc(MK.index[0]); t1 = idx.get_loc(MK.index[-1])

def 出场(O, H, L, C, j, stop, n=60, tgt_r=2.0):
    e = C[j]; risk = stop - e
    if not (risk > 0): return np.nan
    tp = e - tgt_r * risk
    for m in range(j + 1, min(j + n + 1, len(C))):
        if not np.isfinite(C[m]): continue
        if O[m] >= stop: return (e - O[m]) / risk
        if H[m] >= stop: return -1.0
        if L[m] <= tp: return tgt_r
    m = min(j + n, len(C) - 1); return (e - C[m]) / risk if np.isfinite(C[m]) else np.nan

rows = []; 随机池 = {}
for s in syms:
    O, H, L, C, V = [P[k][s].to_numpy(float) for k in ("open", "high", "low", "close", "volume")]
    if np.isfinite(C).sum() < 400: continue
    n = len(C); pc = np.roll(C, 1); pc[0] = np.nan
    tr = np.nanmax(np.vstack([H - L, np.abs(H - pc), np.abs(L - pc)]), axis=0); A = pd.Series(tr).rolling(14).mean().to_numpy()
    cs = pd.Series(C); d = cs.diff(); up = d.clip(lower=0).rolling(14).mean(); dn = (-d.clip(upper=0)).rolling(14).mean(); RSI = (100 - 100 / (1 + up / dn)).to_numpy()
    v20 = pd.Series(V).rolling(20).mean().shift(1).to_numpy(); ma50_dn = (cs < cs.rolling(50).mean()).shift(1).fillna(False).to_numpy()
    inpool = mkA[s].to_numpy()
    ph = [i for i in range(5, n - 5) if np.isfinite(H[i]) and H[i] == np.nanmax(H[i - 5:i + 6])]
    def 涨过(i): 
        a = max(0, i - 120); lo = np.nanmin(L[a:i + 1]) if i > a else np.nan; return np.isfinite(lo) and lo > 0 and H[i] / lo - 1 >= 0.25
    def 属性(tops):
        f, l = tops[0], tops[-1]
        return bool(RSI[l] < RSI[f] - 3), bool(np.isfinite(v20[l]) and V[l] >= 1.5 * v20[l] and C[l] <= (H[l] + L[l]) / 2)
    cand = []      # (形态, 确认日, 最高点, 颈线, 背离, 放量滞涨)
    for k in range(1, len(ph)):
        b = ph[k]; a = ph[k - 1]; c = b + 5
        if c >= n or not np.isfinite(A[b]) or A[b] <= 0: continue
        if 10 <= b - a <= 120 and abs(H[a] - H[b]) <= 1.0 * A[b] and 涨过(a):
            neck = np.nanmin(L[a:b + 1]); top = max(H[a], H[b])
            if top - neck >= 2.5 * A[b]: cand.append(("双顶", c, top, neck, *属性([a, b])))
        if k >= 2:
            z = ph[k - 2]
            if 25 <= b - z <= 150 and 涨过(z):
                v1, v2 = np.nanmin(L[z:a + 1]), np.nanmin(L[a:b + 1]); top = max(H[z], H[a], H[b]); neck = min(v1, v2)
                if b - z <= 120 and max(H[z], H[a], H[b]) - min(H[z], H[a], H[b]) <= 1.2 * A[b] and abs(v1 - v2) <= 1.0 * A[b] and top - neck >= 2.5 * A[b]:
                    cand.append(("三重顶", c, top, neck, *属性([z, a, b])))
                if H[a] - max(H[z], H[b]) >= 1.0 * A[b] and abs(H[z] - H[b]) <= 1.5 * A[b]:
                    cand.append(("头肩顶", c, top, neck, *属性([z, b])))
    for k in range(len(ph)):
        a = ph[k]; ca = a + 5
        for t in range(ca + 1, min(a + 121, n - 1)):
            if not np.isfinite(A[t]) or A[t] <= 0 or not np.isfinite(H[t]): continue
            if np.nanmax(C[a + 1:t]) > H[a] if t > a + 1 else False: break
            if H[a] - np.nanmin(L[a:t]) < 2.5 * A[t]: continue
            ex = H[t] - H[a]
            if 0.15 * A[t] <= ex <= 1.5 * A[t] and C[t] < H[a] and (H[t] - max(O[t], C[t])) >= 0.5 * (H[t] - L[t]) and 涨过(a):
                cand.append(("顶部假突破", t, H[t], L[t], bool(RSI[t] < RSI[a] - 3), bool(np.isfinite(v20[t]) and V[t] >= 1.5 * v20[t]))); break
    for 形, c, top, neck, div, churn in cand:
        if not (t0 <= c <= t1 - 61) or not inpool[c]: continue
        stopx = top + 0.5 * A[c]
        # 不等确认
        jA = c
        # 等确认
        jB = None; lim = 3 if 形 == "顶部假突破" else 40; buf = 0.0 if 形 == "顶部假突破" else 0.3 * A[c]
        for j in range(c + 1, min(c + lim + 1, t1 - 60)):
            if not np.isfinite(C[j]): continue
            if C[j] > top: break
            if C[j] < neck - buf: jB = j; break
        for 进法, j in (("不等确认", jA), ("等确认", jB)):
            if j is None: continue
            r = 出场(O, H, L, C, j, stopx)
            if not np.isfinite(r): continue
            e = C[j]; f = lambda k: (C[min(j + k, n - 1)] / e - 1) if np.isfinite(C[min(j + k, n - 1)]) else np.nan
            seg_h, seg_l = np.nanmax(H[j + 1:j + 21]), np.nanmin(L[j + 1:j + 21])
            rows.append({"票": s, "形态": 形, "进法": 进法, "日": str(idx[j].date()), "年": idx[j].year, "R": r, "风险ATR": (stopx - e) / A[j], "背离": div, "放量滞涨": churn,
                         "环境弱": bool(spy_dn[j] or ma50_dn[j]), "标普在200日线下": bool(spy_dn[j]), "后5天": f(5), "后10天": f(10), "后20天": f(20),
                         "顺着走ATR": (e - seg_l) / A[j], "逆着走ATR": (seg_h - e) / A[j]})
    随机池[s] = (O, H, L, C, A, inpool)
X = pd.DataFrame(rows); tag = "_2004" if WIN == "2004" else ""
X.to_parquet(os.path.join(HERE, f"顶部形态_逐笔{tag}_1120.parquet"), index=False)

def st(g):
    r = g.R; w = r[r > 0].sum(); l = -r[r < 0].sum()
    return {"笔": int(len(g)), "每笔R": round(float(r.mean()), 3), "利润因子": round(float(w / l), 2) if l > 0 else None, "赚钱pct": round(float((r > 0).mean() * 100), 1),
            "后20天涨跌pct": round(float(g["后20天"].mean() * 100), 2), "顺着走ATR中位": round(float(g["顺着走ATR"].median()), 2), "逆着走ATR中位": round(float(g["逆着走ATR"].median()), 2)}
def 随机(g, 轮=20):
    med = float(g["风险ATR"].median()); out = []
    for _ in range(轮):
        rs = []
        for (s, y), c in g.groupby(["票", "年"]).size().items():
            O, H, L, C, A, ip = 随机池[s]; ok = np.where(ip & (idx.year == y) & np.isfinite(C) & np.isfinite(A))[0]; ok = ok[(ok >= t0) & (ok <= t1 - 61)]
            if len(ok) == 0: continue
            for j in rng.choice(ok, size=c): rs.append(出场(O, H, L, C, j, C[j] + med * A[j]))
        out.append(np.nanmean(rs))
    return {"随机做空每笔R_中位": round(float(np.median(out)), 3), "随机_最低": round(float(np.min(out)), 3), "随机_最高": round(float(np.max(out)), 3)}
res = {"窗口": f"{MK.index[0].date()} → {MK.index[-1].date()}", "票数": len(syms), "主表": [], "逐个去掉": [], "分年": {}}
for (形, 进), g in X.groupby(["形态", "进法"]):
    for 环, gg in (("不限", g), ("只在环境弱时", g[g["环境弱"]]), ("只在标普低于200日线时", g[g["标普在200日线下"]])):
        if len(gg) < 30: continue
        res["主表"].append({"形态": 形, "进法": 进, "大盘环境": 环, **st(gg), **(随机(gg) if 环 == "不限" else {})})
    for lab, gg in (("只要形态", g), ("形态+背离", g[g["背离"]]), ("形态+放量滞涨", g[g["放量滞涨"]]), ("形态+背离+放量滞涨", g[g["背离"] & g["放量滞涨"]]), ("形态但没有背离", g[~g["背离"]])):
        if len(gg) >= 30: res["逐个去掉"].append({"形态": 形, "进法": 进, "条件": lab, **st(gg)})
    res["分年"][f"{形}_{进}"] = {int(y): round(float(v), 3) for y, v in g.groupby("年").R.mean().items()}
io.open(os.path.join(HERE, f"顶部形态诊断_结果{tag}_1120.json"), "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
pd.set_option("display.width", 250); print(pd.DataFrame(res["主表"]).to_string(index=False)); print(pd.DataFrame(res["逐个去掉"]).to_string(index=False))
