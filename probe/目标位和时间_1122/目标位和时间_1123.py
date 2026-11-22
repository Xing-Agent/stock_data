# -*- coding: utf-8 -*-
"""测试单《目标位到达率 + 突破后 5 天没站稳就撤》· 引擎外脚本 · 日线
测试单没写死、我自己补的定义（报告里标出）：
  箱体 = 过去 N 根（不含当天；基准 60，另跑 40 / 120）的最高、最低；上下沿各有至少 2 个已确认的摆动点（左右各 5 根）落在离沿 0.1 倍箱高以内
  突破 = 收盘越过沿 0.25 倍 ATR(14)、当天量 > 20 日均量 1.3 倍、前一天收盘还没越过；收盘价进
  止损 = 箱体里最后一个已确认的摆动低点（空 = 高点）外 1 倍 ATR
  前一段 = 箱体前 N 根的最低点到箱顶（多）；前 N 根是涨的 = 中继，否则 = 底部（空反过来）
  行情 = 这只票自己的 200 日均线：价在线上且线比 20 天前高 = 上涨；价在线下且线更低 = 下跌；其余 = 震荡
  成本单边 0.05%；跳空越过止损按开盘价
"""
import os, sys, glob, json, warnings
import numpy as np, pandas as pd
warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
E1 = os.path.join(ROOT, "market_ext_1105/ETF和币_1120"); FEE = 0.0005; K = 5; TMAX = 60
LEV = {"PSQ", "SH", "SOXL", "SOXS", "SQQQ", "TQQQ"}

def 全部():
    D = {}
    for f in sorted(glob.glob(os.path.join(E1, "日线", "*.csv"))):
        s = os.path.basename(f).split("_")[0]
        if s in LEV: continue
        x = pd.read_csv(f, parse_dates=["date"]).set_index("date")
        D[("ETF", s)] = pd.DataFrame({"open": x.open_adj, "high": x.high_adj, "low": x.low_adj, "close": x.close_adj, "volume": x.volume_adj}).dropna()
    for seg in "ab":
        x = pd.read_parquet(os.path.join(HERE, "out", f"个股日线_{seg}.parquet")); x["date"] = pd.to_datetime(x["date"])
        for s, g in x.groupby("symbol"): D[("个股" + seg, s)] = g.set_index("date")[["open", "high", "low", "close", "volume"]].sort_index()
    L = [pd.read_parquet(f) for f in sorted(glob.glob(os.path.join(E1, "币_小时线_Coinbase", "*.parquet")))]
    x = pd.concat(L); x["t"] = pd.to_datetime(x.time_utc, utc=True).dt.tz_localize(None)
    for s in ("BTC", "ETH"):
        g = x[x.symbol == s].set_index("t").sort_index()
        D[("币", s)] = g.resample("1D").agg({"open_adj": "first", "high_adj": "max", "low_adj": "min", "close_adj": "last", "volume_adj": "sum"}).dropna().set_axis(["open", "high", "low", "close", "volume"], axis=1)
    return D

def 事件(cls, sym, d, N):
    o, h, l, c, v = (d[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume")); n = len(d)
    if n < 2 * N + 260: return []
    pc = np.roll(c, 1); pc[0] = c[0]
    atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    vma = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    ma = pd.Series(c).rolling(200).mean().to_numpy()
    ph = np.zeros(n, bool); pl = np.zeros(n, bool)
    for i in range(K, n - K):
        if h[i] == h[i - K:i + K + 1].max(): ph[i] = True
        if l[i] == l[i - K:i + K + 1].min(): pl[i] = True
    R = []
    for i in range(2 * N + 1, n - 1):
        a = atr[i]
        if not (a > 0 and vma[i] > 0 and ma[i] > 0 and ma[i - 20] > 0): continue
        w0, w1 = i - N, i                      # 箱体窗口 [w0, w1)
        top = h[w0:w1].max(); bot = l[w0:w1].min(); H = top - bot
        if H <= 0: continue
        up = c[i] > top + 0.25 * a and c[i - 1] <= top + 0.25 * a
        dn = c[i] < bot - 0.25 * a and c[i - 1] >= bot - 0.25 * a
        if not (up or dn) or v[i] <= 1.3 * vma[i]: continue
        ok = np.arange(w0, w1) + K <= i - 1    # 已确认
        hi_idx = np.where(ph[w0:w1] & ok)[0] + w0; lo_idx = np.where(pl[w0:w1] & ok)[0] + w0
        if (h[hi_idx] >= top - 0.1 * H).sum() < 2 or (l[lo_idx] <= bot + 0.1 * H).sum() < 2: continue
        sg = 1 if up else -1; e = c[i]; edge = top if up else bot
        if up:
            if len(lo_idx) == 0: continue
            stop = l[lo_idx[-1]] - a; leg = top - l[w0 - N:w0].min()
        else:
            if len(hi_idx) == 0: continue
            stop = h[hi_idx[-1]] + a; leg = h[w0 - N:w0].max() - bot
        r = (e - stop) * sg
        if r <= 0: continue
        前涨 = c[w0] > c[w0 - N]; 型 = "中继" if (前涨 == up) else "底部"
        # 前高前低：过去 250 根里已确认、在进场价外侧最近的摆动点
        j0 = max(0, i - 250); cand = (h[j0:i - K][ph[j0:i - K]] if up else l[j0:i - K][pl[j0:i - K]])
        cand = cand[(cand - e) * sg > 0]
        T = {"前高前低": (cand.min() if up else cand.max()) if len(cand) else np.nan,
             "1倍等距": edge + sg * leg if leg > 0 else np.nan,
             "形态高度1倍": edge + sg * H, "形态高度0.7倍": edge + sg * 0.7 * H,
             "斐波1.272": (bot + 1.272 * H) if up else (top - 1.272 * H), "斐波1.618": (bot + 1.618 * H) if up else (top - 1.618 * H)}
        T = {k: (x if (np.isfinite(x) and (x - e) * sg > 0) else np.nan) for k, x in T.items()}
        end = min(n - 1, i + TMAX); fh = h[i + 1:end + 1]; fl = l[i + 1:end + 1]; fo = o[i + 1:end + 1]; fc = c[i + 1:end + 1]
        if len(fc) < 6: continue
        adv = fl <= stop if up else fh >= stop
        ks = int(np.argmax(adv)) if adv.any() else 10 ** 6
        rec = {"类": cls, "票": sym, "日期": d.index[i], "方向": "多" if up else "空", "型": 型, "N": N, "箱高除ATR": H / a, "止损R占价pct": r / e * 100,
               "行情": "上涨" if (c[i] > ma[i] and ma[i] > ma[i - 20]) else ("下跌" if (c[i] < ma[i] and ma[i] < ma[i - 20]) else "震荡"), "整理比前段": np.nan}
        for k, x in T.items():
            if not np.isfinite(x): rec["果_" + k] = None; continue
            fav = fh >= x if up else fl <= x
            kt = int(np.argmax(fav)) if fav.any() else 10 ** 6
            rec["果_" + k] = "目标" if kt < ks else ("止损" if ks < 10 ** 6 else "到时间"); rec["距_" + k] = (x - e) * sg / r; rec["天_" + k] = kt + 1 if kt < ks else np.nan
        vals = sorted(x for x in T.values() if np.isfinite(x)); 
        zone = [k for k, x in T.items() if np.isfinite(x) and sum(abs(x - y) <= 0.5 * a for y in vals) >= 2]
        rec["成区的目标"] = "|".join(zone)
        # ② A：止损 / 形态高度1倍 / 60 天；B：5 天规则
        tgt = T["形态高度1倍"]; cost = 2 * FEE * e / r
        def 走(用B):
            for k in range(len(fc)):
                if (fl[k] <= stop) if up else (fh[k] >= stop):
                    px = fo[k] if ((fo[k] < stop) if up else (fo[k] > stop)) else stop; return (px - e) * sg / r, k + 1, "止损"
                if np.isfinite(tgt) and ((fh[k] >= tgt) if up else (fl[k] <= tgt)): return (tgt - e) * sg / r, k + 1, "目标"
                if 用B and k < 5:
                    if (fc[k] - edge) * sg < 0: return (fc[k] - e) * sg / r, k + 1, "收回去撤"
                    if k == 4 and (fc[k] - edge) * sg <= 0.5 * a: return (fc[k] - e) * sg / r, k + 1, "没走开撤"
            return (fc[-1] - e) * sg / r, len(fc), "到时间"
        ra, da, wa = 走(False); rb, db, wb = 走(True)
        rec.update({"A_R": ra, "A_天": da, "A_怎么出": wa, "B_R": rb, "B_天": db, "B_怎么出": wb, "成本R": cost})
        R.append(rec)
    return R

def S(x, col):
    r = x[col] - x["成本R"]; g = x[col]
    return {"笔数": int(len(x)), "毛R": round(float(g.mean()), 3), "净R": round(float(r.mean()), 3), "胜率pct": round(float((r > 0).mean() * 100), 1),
            "利润因子": round(float(r[r > 0].sum() / max(1e-9, -r[r < 0].sum())), 2), "平均拿几天": round(float(x[col.replace("_R", "_天")].mean()), 1)} if len(x) else {"笔数": 0}

if __name__ == "__main__":
    D = 全部(); print("品种", len(D), flush=True)
    for N in (60, 40, 120):
        L = []
        for (cls, s), d in D.items(): L += 事件(cls, s, d, N)
        ev = pd.DataFrame(L); ev["段"] = np.where(ev["日期"] < "2015-01-01", "2005–2014", "2015–2025")
        ev = ev[(ev["日期"] >= "2005-01-01") & (ev["日期"] <= "2025-12-31")]
        ev = ev[~((ev["类"] == "个股a") & (ev["段"] != "2005–2014")) & ~((ev["类"] == "个股b") & (ev["段"] != "2015–2025"))]
        ev["类"] = ev["类"].str.replace("个股a", "个股").str.replace("个股b", "个股")
        ev.to_parquet(os.path.join(HERE, "out", f"事件_N{N}.parquet")); print(N, len(ev), ev.groupby(["类", "段", "方向"]).size().to_dict(), flush=True)
