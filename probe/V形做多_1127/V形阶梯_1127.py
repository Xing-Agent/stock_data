# -*- coding: utf-8 -*-
"""《488》第 1 项 · V 形做多阶梯（《464》要干啥第 5 件 +《465 拍板》第 1、5 条）· 引擎外 · 日线（③ 用 4 小时线）
品种：QQQ（1999 起）、纳斯达克综合指数（1971 起；1985 年以前只有收盘价）。美股 2022 年以后封存不读。
MSFT 在考卷（留出池 exam_1042）里，不碰。

V 形事件 =《465》第 2 条转涨触发（不套状态机：纳指综合没有状态机档位，两只用同一套，便于比）：
  上一波大跌：日线 ZigZag（拐点间 ≥3 倍 ATR）；回看 180 天里的最高点之后的最低点 = L；L 之前 90 天内最近的 ZigZag 高点 H，跌到 L ≥ 门槛、途中反弹 ≤ 0.5×跌幅。
  门槛三种：8%、4 倍日线 ATR（拍板给的两种）、20%（拍板个股口径，对照）。
  次高点 = H 之后、L 之前最近的日线摆动高点（左右 5 根）。触发 =（收盘过次高点且过 0.5）或过 0.618，连续 2 天，EMA20 比 3 天前高。同一个 L 只算一次。

第一次回踩：从 L 起的 ZigZag（拐点间 ≥2 倍 ATR，另试 1.5、3）第一个高点 H1、之后的低点 P1，深度 =(H1−P1)/(H1−L)。

四种进场（都在 L 之后 60 根以内）：
 ① 关键位 1 回踩确认：关键位 1 = H 到 L 之间最后一个「连续 ≥5 天（另试 4、7）收盘高低差 ≤1 倍 ATR」平台的下沿（平台判法是我补的，另试 0.75、1.5 倍）；
    没有平台 = 这段急跌的 50%。收盘站回关键位 1 + 0.25 ATR（另试 0.15、0.35）后，第一次最低价回到关键位 1 + 0.5 ATR 以内（我补的）、且收盘没跌破关键位 1 − 0.25 ATR，
    之后 5 天内收盘高过回踩那天最高价 → 收盘进。止损 = min(回踩最低, EMA10) − 0.4 ATR（另试 0.3、0.5）。
 ② 小阴线突破：前 8 天满足盘涨（拍板四条），出第一根小阴线（收 < 开、实体 ≤0.5 ATR，我补的）或十字星（实体 ≤ 当天振幅 10%，我补的），
    次日最高 ≥ 它的最高 + 0.1 ATR → 在那个价进（跳空高开就按开盘）。止损 = min(那根 K 线低点, EMA10) − 0.4 ATR（另试 0.3、0.5）。需要开盘价，纳指综合 1985 年以前做不了。
 ③ 4 小时小旗形：QQQ 2004–2021 正常时段小时线拼 4 小时（每天两根：9:30–13:30、13:30–16:00）。旗形用《475》旗的识别（旗杆 ≥3 倍 4 小时 ATR、旗面 5~15 根、回撤 ≤50%），
    向上突破收盘进，止损 = 旗面最低 − 0.5 倍 4 小时 ATR。没有 4 小时数据的年份和品种不做。
 ④ 确认后一次满仓：触发那天收盘进，止损 = 触发前 10 天最低 − 0.25 ATR（《465》第 3 条撤销线）。

结果：进场后打止损（跳空按开盘）或拿满 60 天（另试 40、120）收盘走；单边成本 0.05%。报每笔 %、按风险算的 R、赚钱笔占比、最深亏损。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
封 = pd.Timestamp("2021-12-31"); FEE = 0.0005


def 读(sym):
    if sym == "纳指综合":
        x = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数长历史_1123/纳斯达克综合指数_日线.csv"), parse_dates=["date"]).set_index("date")
        D = pd.DataFrame({"open": x.open_adj, "high": x.high_adj, "low": x.low_adj, "close": x.close_adj})
        D["high"] = D.high.fillna(D.close); D["low"] = D.low.fillna(D.close)        # 只有收盘的年份：高低 = 收盘；开盘留空
    else:
        D = M4.美股日线(sym)[["open", "high", "low", "close"]]
    D = D.loc[:封].dropna(subset=["close"]).copy()
    return D


def 指标(D):
    h, l, c = D.high.to_numpy(float), D.low.to_numpy(float), D.close.to_numpy(float)
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().bfill().to_numpy()
    e10 = pd.Series(c).ewm(span=10, adjust=False).mean().to_numpy(); e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    return h, l, c, atr, e10, e20


def 之字(h, l, atr, 倍):
    Z = []; d = 0; eh = el = 0
    for i in range(1, len(h)):
        if h[i] > h[eh]: eh = i
        if l[i] < l[el]: el = i
        if d >= 0 and h[eh] - l[i] >= 倍 * atr[i] and eh < i: Z.append((eh, h[eh], "高", i)); d = -1; el = i
        elif d <= 0 and h[i] - l[el] >= 倍 * atr[i] and el < i: Z.append((el, l[el], "低", i)); d = 1; eh = i
    return Z


def 事件(D, 门槛="8%"):
    h, l, c, atr, e10, e20 = 指标(D); n = len(c); Z = 之字(h, l, atr, 3.0)
    SH = [j for j in range(5, n - 5) if h[j] == h[j - 5:j + 6].max()]
    out = []; done_j0 = set()
    for i in range(185, n):
        pk = i - 180 + int(np.argmax(h[i - 180:i + 1])); j0 = pk + int(np.argmin(l[pk:i + 1])); L = l[j0]
        if j0 in done_j0 or j0 >= i: continue
        H = None
        for (zp, p, k, zc) in reversed(Z):
            if k != "高" or zp >= j0 or zc > i or j0 - zp > 90: continue
            dd = p - L
            ok = (dd / p >= 0.08) if 门槛 == "8%" else (dd / p >= 0.20) if 门槛 == "20%" else (dd >= 4 * atr[j0])
            if not ok: continue
            lo = np.minimum.accumulate(l[zp:j0 + 1])
            if (h[zp:j0 + 1] - lo).max() > 0.5 * dd: continue
            H, Hp = p, zp; break
        if H is None: continue
        pr = [j for j in SH if Hp < j < j0 and j + 5 <= i]; lh = h[pr[-1]] if pr else H
        cond = lambda q: (c[q] > lh and c[q] > L + 0.5 * (H - L)) or c[q] > L + 0.618 * (H - L)
        if cond(i) and cond(i - 1) and e20[i] > e20[i - 3]:
            out.append(dict(t=i, j0=j0, Hp=Hp, H=H, L=L, 次高点=lh)); done_j0.add(j0)
    return out


def 走(D, e_i, E, S, N, 当天价进=False):
    """e_i 那天以 E 进；之后打 S 或拿满 N 天。当天价进=True 表示 E 是盘中价（当天收盘之后才开始看止损）。"""
    o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(c); R = E - S
    if R <= 0: return None
    end = min(e_i + N, n - 1)
    for j in range(e_i + 1, end + 1):
        if l[j] <= S:
            px = min(S, o[j]) if not np.isnan(o[j]) else S
            return px / E - 1 - 2 * FEE, (px - E) / R, j - e_i, True
    px = c[end]; return px / E - 1 - 2 * FEE, (px - E) / R, end - e_i, False


def 关键位1(h, l, c, atr, Hp, j0, 天=5, 宽=1.0):
    k1 = None
    for s in range(j0 - 天, Hp - 1, -1):                                          # 从 L 往回找最后一个平台
        w = c[s:s + 天]
        if w.max() - w.min() <= 宽 * atr[s + 天 - 1] and l[s:s + 天].min() > l[j0]:
            k1 = l[s:s + 天].min(); break
    return k1 if k1 is not None else l[j0] + 0.5 * (h[Hp] - l[j0]), k1 is not None


def 盘涨(o, h, l, c, atr, e10, i):
    w = slice(i - 7, i + 1); cc = c[w]
    if np.isnan(o[w]).any(): return False
    dd = (np.maximum.accumulate(cc) - cc).max()
    return (dd <= 1.2 * atr[i] and (cc > e10[w]).sum() >= 7 and e10[i] > e10[i - 1] and (c[w] > o[w]).sum() >= 5 and not ((o[w] - c[w]) > 1.5 * atr[i]).any())


def 进场们(D, ev, 平台天=5, 平台宽=1.0, 收回=0.25, 止损=0.4, D4=None):
    o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); _, _, _, atr, e10, e20 = 指标(D); n = len(c)
    j0, t, Hp, L = ev["j0"], ev["t"], ev["Hp"], ev["L"]; win = min(j0 + 60, n - 1); r = {}
    # ① 关键位 1 回踩确认
    k1, 有平台 = 关键位1(h, l, c, atr, Hp, j0, 平台天, 平台宽); r["关键位1"] = k1; r["有平台"] = 有平台
    rc = next((i for i in range(j0 + 1, win) if c[i] > k1 + 收回 * atr[i]), None)
    if rc is not None:
        for p in range(rc + 1, win):
            if c[p] < k1 - 0.25 * atr[p]: break
            if l[p] <= k1 + 0.5 * atr[p]:
                q = next((q for q in range(p + 1, min(p + 6, n)) if c[q] > h[p]), None)
                if q is not None and q <= t: continue                                   # 1128 修：进场必须在触发日之后（触发那天才知道这是 V 形），早于触发的回踩不算
                if q is not None and min(c[p:q + 1]) >= k1 - 0.25 * atr[q]:
                    r["①"] = (q, c[q], min(l[p:q + 1].min(), e10[q]) - 止损 * atr[q], False)
                break
    # ② 小阴线 / 十字星次日突破
    for i in range(max(j0 + 8, 10, t), win):                                          # 1128 修：从触发日起找（原来从最低点后第 8 根起找，会在触发之前就进场 = 偷看）
        if np.isnan(o[i]) or not 盘涨(o, h, l, c, atr, e10, i - 1): continue
        body = c[i] - o[i]
        if (body < 0 and -body <= 0.5 * atr[i]) or abs(body) <= 0.1 * (h[i] - l[i]):
            trig = h[i] + 0.1 * atr[i]
            if i + 1 < n and h[i + 1] >= trig:
                E = max(trig, o[i + 1]) if not np.isnan(o[i + 1]) else trig
                r["②"] = (i + 1, E, min(l[i], e10[i]) - 止损 * atr[i], True)
            break
    # ③ 4 小时小旗形
    if D4 is not None:
        d0, d1 = D.index[j0], D.index[win]
        hit = [p for p in D4["旗"] if d0 < p[0] <= d1]
        if hit:
            ts, E4, S4 = hit[0]; day = ts.normalize()
            if day in D.index: r["③"] = (D.index.get_loc(day), E4, S4, True)
    # ④ 确认后一次满仓
    r["④"] = (t, c[t], l[t - 10:t].min() - 0.25 * atr[t], False)
    return r


def 四小时(sym):
    fs = sorted([os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2004_2014", f) for f in os.listdir(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2004_2014")) if f.endswith(".parquet")] +
                [os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起", f) for f in os.listdir(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起")) if f.endswith(".parquet") and int(f[:4]) <= 2021])
    X = pd.concat([pd.read_parquet(f, filters=[("symbol", "=", sym)]) for f in fs]); X = X[X.session == "regular"].copy()
    X["t"] = pd.to_datetime(X.time_utc).dt.tz_convert("America/New_York"); X = X[X.t.dt.year <= 2021]
    mm = X.t.dt.hour * 60 + X.t.dt.minute; X["块"] = X.t.dt.strftime("%Y-%m-%d") + np.where(mm < 13 * 60 + 30, "a", "b")
    g = X.sort_values("t").groupby("块")
    B = pd.DataFrame({"open": g.open_adj.first(), "high": g.high_adj.max(), "low": g.low_adj.min(), "close": g.close_adj.last(), "volume": g.volume_adj.sum(), "t": g.t.last()}).sort_values("t")
    B.index = B.t.dt.tz_localize(None); B = B.drop(columns="t")
    pc = B.close.shift(1); B["atr"] = pd.concat([B.high - B.low, (B.high - pc).abs(), (B.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean(); B["v20"] = B.volume.rolling(20).mean().shift(1)
    F5 = mod("F5", os.path.join(ROOT, "probe/目标位测算_1125/五类形态_1126.py"))
    fl = F5.旗(B, True, 杆=3.0)
    return {"旗": [(B.index[p["进场i"]], float(B.close.iloc[p["进场i"]]), float(p["止损"])) for p in fl], "根数": len(B), "起": str(B.index[0]), "止": str(B.index[-1])}


def 段(sym, t):
    y = t.year
    return "1971–1992" if y < 1993 else "1993–2007" if y < 2008 else "2008–2021"


if __name__ == "__main__":
    pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    syms = ["QQQ", "纳指综合"]; Ds = {s: 读(s) for s in syms}
    D4 = {"QQQ": 四小时("QQQ")}; print("QQQ 4 小时", D4["QQQ"]["根数"], D4["QQQ"]["起"], D4["QQQ"]["止"], "旗形突破", len(D4["QQQ"]["旗"]), flush=True)
    回踩, 单 = [], []
    for s in syms:
        D = Ds[s]; h, l, c, atr, e10, e20 = 指标(D)
        for 门 in ("8%", "4ATR", "20%"):
            EV = 事件(D, 门)
            for k_ in (1.5, 2.0, 3.0):
                Z = 之字(h, l, atr, k_)
                for ev in EV:
                    zs = [z for z in Z if z[0] > ev["j0"]]
                    if len(zs) >= 2 and zs[0][2] == "高" and zs[1][2] == "低":
                        H1, P1 = zs[0][1], zs[1][1]; 成 = (h[ev["j0"]:min(ev["j0"] + 250, len(h))] >= ev["H"]).any()
                        回踩.append(dict(品种=s, 门槛=门, 回踩尺子=k_, L日=str(D.index[ev["j0"]].date()), 触发日=str(D.index[ev["t"]].date()), 段=段(s, D.index[ev["j0"]]), 深度=(H1 - P1) / (H1 - ev["L"]),
                                        回踩发生在触发后=zs[1][0] > ev["t"], 一年内收复大跌起点=bool(成)))
            for kw_name, kw in (("默认", {}), ("平台4天", {"平台天": 4}), ("平台7天", {"平台天": 7}), ("平台宽0.75", {"平台宽": 0.75}), ("平台宽1.5", {"平台宽": 1.5}), ("收回0.15", {"收回": 0.15}), ("收回0.35", {"收回": 0.35}), ("止损0.3", {"止损": 0.3}), ("止损0.5", {"止损": 0.5})):
                for ev in EV:
                    r = 进场们(D, ev, D4=D4.get(s), **kw)
                    for k in ("①", "②", "③", "④"):
                        for N in ((40, 60, 120) if kw_name == "默认" else (60,)):
                            base = dict(品种=s, 门槛=门, 参数=kw_name, 拿天=N, L日=str(D.index[ev["j0"]].date()), 触发日=str(D.index[ev["t"]].date()), 段=段(s, D.index[ev["j0"]]), 进场=k, 有平台=r["有平台"])
                            if k not in r: 单.append(dict(base, 有进场=False)); continue
                            ei, E, S, _ = r[k]; w = 走(D, ei, E, S, N)
                            if w is None: 单.append(dict(base, 有进场=False, 备注="止损在进场价上方")); continue
                            单.append(dict(base, 有进场=True, 进场日=str(D.index[ei].date()), 进场价=E, 止损=S, 风险pct=(E - S) / E * 100, 进场离L涨了pct=(E / ev["L"] - 1) * 100,
                                          收益pct=w[0] * 100, R=w[1], 拿了几天=w[2], 打止损=w[3]))
            print(s, 门, len(EV), "个事件", flush=True)
    pd.DataFrame(回踩).to_csv(os.path.join(OUT, "第一次回踩.csv"), index=False); pd.DataFrame(单).to_csv(os.path.join(OUT, "四种进场_逐笔.csv"), index=False)
    print("DONE")
