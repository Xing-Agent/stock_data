# -*- coding: utf-8 -*-
"""《465》目标位测算回测（照 手册/问Gemini线460-拍板和要干啥-形态和点数图和波浪的目标位测算-Lin三条都同意-1125.md）· 引擎外 · 日线
品种：SPY（标普，1993 起）、SOXX（2001 起）、BTC、ETH（2017 起）。2022-01-01 ~ 2025-12-31 封存：单子单独存 out/封存_*.csv，不打印、不进统计。
统计段：美股 1993–2007、2008–2021；币 2017–2021（2026 年只用于第 5 件 BTC 那一笔的核对）。

五件：
 1 形态测算：头肩顶/底、三重顶/底、箱体（卡里形态库第 3、4、7 种的文字定义；底部形态按顶的定义镜像）；
   楔形变体（急拉后顶压平）用 probe/派发楔形_1125 现成识别结果（BTC、ETH 4 小时线）。
   每笔报：120 根日线内先到测算位的 100% / 80% / 75% / 70%，还是先打止损；对照 = 同一品种、同一段、同方向随机进场，止损和目标离进场一样远（按百分比）。
 2 点数图：日线大箱子（≥ 40 根，约 2 个月）跌破 / 突破，按 0.4 / 0.5 / 0.6 倍 ATR 格值、3 格反转数列，目标 = 基准价 ∓ 列数 × 格值 × 3，基准价取箱顶（箱底）和箱子中轴。
 3 波浪等距：ZigZag（拐点间至少 3 倍 ATR，另试 2.5、4）。最近三个拐点是「高 → 低 → 更低的高」且从这个更低的高回落 k 倍 ATR 确认时做空；做多反过来。
   目标 = 从反弹高点量上一段的 1 倍 / 1.618 倍，按点数、按百分比两种；同时报《407》的「前低」「2R」。
 4 合成目标区：形态单子上，把测算位（75%、100%）和结构位（之前 250 天的摆动低点 / 高点）在 1 倍 ATR 内的合成一个区（另试 0.8 / 1.2），由近到远 T1、T2；
   出场：对照 = 卡里「T1 平一半 + 止损移到成本，T2 走完」；新 = T1 平 35%（另试 25% / 50%），剩下 ① 止损移到成本拿到 T2 ② 吊灯 3 倍日 ATR；另跑 T1 ≥ 1.5 / 1.8 倍风险才开仓。
 5 BTC 2026-09-21 那一笔：单独脚本 BTC九月那笔_1125.py。

══ 我补的定义（卡里和拍板没写死的）══
 P1 摆动高低点 = 比左右各 5 根都高（低）的那根，要到右边第 5 根收盘才看得出来；形态只用已经看得出来的点。
 P2 头肩：连着三个摆动高点，头比两肩中较高的那个高 ≥ 1 ATR（卡：不到 1 ATR 更像三重顶），两肩高差 ≤ 1 ATR（卡写「差不多高」）；颈线 = 头两侧两个摆动低点的连线；
    右肩确认后 30 根内收盘跌破颈线 0.3 ATR、量 > 20 日均量 = 成立（卡：放量）；之前收盘高过右肩 = 作废。目标 = 头到颈线的高度，从跌破点的颈线往下量。止损 = 右肩 + 0.3 ATR（卡）。
 P3 三重顶：连着三个摆动高点相差 ≤ 1 ATR（卡），中间两个摆动低点相差 ≤ 1 ATR（卡写「差不多高」）；「大涨后」= 第一个顶比之前 120 天最低收盘高 15% 以上（我补的）；
    颈线 = 两个中间低点里较低的那个；30 根内收盘跌破颈线 0.25 ATR = 成立（卡）。目标 = 最高顶到颈线的高度。止损 = 最高顶 + 0.3 ATR（卡）。
 P4 箱体：前 20 根的最高、最低当上下沿（另试 15、30 根），箱高 2~6 ATR（卡），上下沿各被碰到 ≥ 2 次（离线 0.25 ATR 以内算碰）；
    收盘越过上沿 0.3 ATR（卡）且量 > 20 日均量 = 突破（向下同理）。目标 = 箱高，从沿量。止损 = 沿往回 1 ATR（卡写 1~1.5，取 1）。同一只票同一时间只算一笔。
 P5 底部形态（头肩底、三重底）、向下跌破的箱体：卡里只写了顶 / 做多为主，这里按同样的数镜像，单列报。
 P6 双顶双底、旗形、三角旗、对称 / 上升 / 下降三角形：卡里形态库没有定义，没写（任务单要求不自己另定）。
 P7 拿多久：120 根日线；同一根既碰止损又碰目标按先止损。成本：这一项只看「到没到」，不扣成本；第 4 件按 R 算，单边 0.05%（币）/ 0.05%（ETF）。
 P8 随机对照：每笔抽 20 个同品种、同统计段的随机日子，同方向，止损和目标按进场价的同样百分比，同样 120 根。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py")); M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
HOLD = 120; FEE = 0.0005
封起, 封止 = pd.Timestamp("2022-01-01"), pd.Timestamp("2025-12-31")
RNG = np.random.default_rng(20261125)


def 读(sym):
    if sym == "SPY":
        d = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数ETF_1993起_1122/SPY_日线_1993起.csv"), parse_dates=["date"]).set_index("date")
        D = d[["open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"]].copy(); D.columns = ["open", "high", "low", "close", "volume"]
    elif sym == "SOXX": D = SC.soxx()
    else: D = M4.币日线(sym)
    D = D.dropna(subset=["close"]).copy()
    pc = D.close.shift(1); D["atr"] = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    D["v20"] = D.volume.rolling(20).mean().shift(1)
    return D


def 段(sym, t):
    if t >= 封起 and t <= 封止: return "封存"
    if sym in ("BTC", "ETH"): return "2017–2021" if t < 封起 else "2026"
    if t >= 封起: return "2026"
    return "1993–2007" if t < pd.Timestamp("2008-01-01") else "2008–2021"


def 摆动(h, l, k=5):
    n = len(h); sh = np.zeros(n, bool); sl = np.zeros(n, bool)
    for j in range(k, n - k):
        if h[j] == h[j - k:j + k + 1].max() and h[j] > h[j - k:j].max(): sh[j] = True
        if l[j] == l[j - k:j + k + 1].min() and l[j] < l[j - k:j].min(): sl[j] = True
    return sh, sl


def 走到(D, e, 方向, stop, targets, hold=HOLD):
    """从第 e 根收盘进场，看之后先碰哪个。返回 {目标: (到没到, 第几天到, 到之前碰没碰止损)}，以及止损第几天。"""
    h, l = D.high.to_numpy(), D.low.to_numpy(); n = len(h); end = min(e + hold, n - 1)
    st = None
    for j in range(e + 1, end + 1):
        if (h[j] >= stop) if 方向 < 0 else (l[j] <= stop): st = j; break
    out = {}
    for k_, tg in targets.items():
        hit = None
        for j in range(e + 1, (st if st is not None else end + 1)):
            if (l[j] <= tg) if 方向 < 0 else (h[j] >= tg): hit = j; break
        out[k_] = hit
    return out, st


_SEG = {}
def 随机对照(D, sym, e, 方向, stop_p, tgt_p, 段名, m=20):
    idx = D.index; c = D.close.to_numpy()
    if sym not in _SEG: _SEG[sym] = np.array([段(sym, t) for t in idx])
    segs = _SEG[sym]
    cand = np.where((segs == 段名) & (np.arange(len(c)) < len(c) - 2) & D.atr.notna().to_numpy())[0]
    if len(cand) == 0: return {k: np.nan for k in tgt_p}
    pick = RNG.choice(cand, size=min(m, len(cand)), replace=False); res = {k: [] for k in tgt_p}
    for e2 in pick:
        E = c[e2]; stop = E * (1 + stop_p) if 方向 < 0 else E * (1 - stop_p)
        tg = {k: (E * (1 - p) if 方向 < 0 else E * (1 + p)) for k, p in tgt_p.items()}
        o, _ = 走到(D, e2, 方向, stop, tg)
        for k in tg: res[k].append(o[k] is not None)
    return {k: float(np.mean(v)) for k, v in res.items()}


# ---------------- 形态识别 ----------------
def 头肩(D, 顶=True):
    h, l, c, v, atr, v20 = (D[x].to_numpy(float) for x in ("high", "low", "close", "volume", "atr", "v20"))
    if not 顶: h, l, c = -l, -h, -c       # 底 = 把价格翻过来当顶找（P5）
    sh, sl = 摆动(h, l); H = np.where(sh)[0]; L = np.where(sl)[0]; out = []; used = -1
    for q in range(2, len(H)):
        a, b, r = H[q - 2], H[q - 1], H[q]
        if r <= used: continue
        A = atr[r]
        if np.isnan(A) or h[b] - max(h[a], h[r]) < 1.0 * A or abs(h[a] - h[r]) > 1.0 * A: continue
        t1 = [x for x in L if a < x < b]; t2 = [x for x in L if b < x < r]
        if not t1 or not t2: continue
        t1 = min(t1, key=lambda x: l[x]); t2 = min(t2, key=lambda x: l[x])
        slope = (l[t2] - l[t1]) / (t2 - t1); neck = lambda x: l[t1] + slope * (x - t1)
        高 = h[b] - neck(b)
        for t in range(r + 5, min(r + 5 + 30, len(c))):        # 右肩要到 r+5 才看得出来
            if c[t] > h[r]: break
            if c[t] < neck(t) - 0.3 * atr[t] and v[t] > v20[t]:
                E = c[t]; nk = neck(t); stop = h[r] + 0.3 * atr[t]
                sgn = 1 if 顶 else -1
                out.append({"形态": "头肩顶" if 顶 else "头肩底", "进场i": t, "方向": -1 if 顶 else 1, "E": sgn * E, "颈线": sgn * nk, "高度": 高, "止损": sgn * stop, "ATR": atr[t]})
                used = r; break
    return out


def 三重(D, 顶=True):
    h, l, c, v, atr, v20 = (D[x].to_numpy(float) for x in ("high", "low", "close", "volume", "atr", "v20"))
    rc = c.copy(); lo120 = pd.Series(rc).rolling(120, min_periods=60).min().to_numpy(); hi120 = pd.Series(rc).rolling(120, min_periods=60).max().to_numpy()
    if not 顶: h, l, c = -l, -h, -c
    sh, sl = 摆动(h, l); H = np.where(sh)[0]; L = np.where(sl)[0]; out = []; used = -1
    for q in range(2, len(H)):
        a, b, r = H[q - 2], H[q - 1], H[q]
        if r <= used: continue
        A = atr[r]; tops = h[[a, b, r]]
        if np.isnan(A) or tops.max() - tops.min() > 1.0 * A: continue
        t1 = [x for x in L if a < x < b]; t2 = [x for x in L if b < x < r]
        if not t1 or not t2: continue
        t1 = min(t1, key=lambda x: l[x]); t2 = min(t2, key=lambda x: l[x])
        if abs(l[t1] - l[t2]) > 1.0 * A: continue
        if 顶 and not (rc[a] >= lo120[a] * 1.15): continue          # 大涨后（我补的）
        if not 顶 and not (rc[a] <= hi120[a] / 1.15): continue      # 大跌后（镜像）
        neck = min(l[t1], l[t2]); 高 = tops.max() - neck
        for t in range(r + 5, min(r + 5 + 30, len(c))):
            if c[t] > tops.max() + 0.5 * atr[t]: break
            if c[t] < neck - 0.25 * atr[t]:
                sgn = 1 if 顶 else -1
                out.append({"形态": "三重顶" if 顶 else "三重底", "进场i": t, "方向": -1 if 顶 else 1, "E": sgn * c[t], "颈线": sgn * neck, "高度": 高, "止损": sgn * (tops.max() + 0.3 * atr[t]), "ATR": atr[t]})
                used = r; break
    return out


def 箱体(D, N=20, 高下=2.0, 高上=6.0, 碰=2):
    h, l, c, v, atr, v20 = (D[x].to_numpy(float) for x in ("high", "low", "close", "volume", "atr", "v20"))
    out = []; t = N + 20; n = len(c)
    while t < n - 1:
        A = atr[t - 1]; top = h[t - N:t].max(); bot = l[t - N:t].min(); hh = top - bot
        if np.isnan(A) or not (高下 * A <= hh <= 高上 * A) or (h[t - N:t] >= top - 0.25 * A).sum() < 碰 or (l[t - N:t] <= bot + 0.25 * A).sum() < 碰 or not (v[t] > v20[t]):
            t += 1; continue
        if c[t] > top + 0.3 * atr[t]:
            out.append({"形态": "箱体向上突破", "进场i": t, "方向": 1, "E": c[t], "颈线": top, "高度": hh, "止损": top - 1.0 * atr[t], "ATR": atr[t]}); t += N; continue
        if c[t] < bot - 0.3 * atr[t]:
            out.append({"形态": "箱体向下跌破", "进场i": t, "方向": -1, "E": c[t], "颈线": bot, "高度": hh, "止损": bot + 1.0 * atr[t], "ATR": atr[t]}); t += N; continue
        t += 1
    return out


def 楔形变体():
    """派发楔形（急拉后顶压平、底抬高）现成识别结果里已跌破的；目标 = 急拉起涨点（急拉日前一天收盘）。"""
    f = os.path.join(ROOT, "probe/派发楔形_1125/out/形态_默认.csv"); X = pd.read_csv(f); X = X[X["跌破"].notna()]
    out = []
    for _, r in X.iterrows():
        D = 读(r["sym"]); 急 = pd.Timestamp(r["急拉日"]); 破 = pd.Timestamp(r["跌破"]).normalize()
        if 破 not in D.index: continue
        i = D.index.get_loc(破); j0 = D.index.get_loc(急)
        起涨 = float(D.close.iloc[j0 - 1]); E = float(D.close.iloc[i]); 首顶 = float(r["首顶价"])
        out.append({"sym": r["sym"], "形态": "派发楔形(急拉后顶压平)", "进场i": i, "方向": -1, "E": E, "颈线": E, "高度": E - 起涨, "止损": 首顶 + 0.3 * float(D.atr.iloc[i]), "ATR": float(D.atr.iloc[i]), "起涨点": 起涨})
    return out


def 测算表(D, sym, pats, 级=(1.0, 0.8, 0.75, 0.7)):
    rows = []; sh, sl = 摆动(D.high.to_numpy(), D.low.to_numpy()); c = D.close.to_numpy()
    for p in pats:
        e = p["进场i"]; s = 1 if p["方向"] > 0 else -1; E = abs(p["E"]) if p["E"] < 0 else p["E"]
        E = c[e]; stop = abs(p["止损"]); 颈 = abs(p["颈线"]); 高 = p["高度"]
        if "起涨点" in p:
            tg = {f"{int(k*100)}%": E - k * (E - p["起涨点"]) for k in 级}
        else:
            tg = {f"{int(k*100)}%": 颈 + s * k * 高 for k in 级}
        R = abs(stop - E)
        if R <= 0 or any((tg[k] - E) * s <= 0 for k in tg): continue
        # 《407》的前低 / 2R
        prev = [c_ for j, c_ in enumerate(D.low.to_numpy() if s < 0 else D.high.to_numpy()) if (sl[j] if s < 0 else sh[j]) and j + 5 <= e and e - j <= 250 and (c_ < E if s < 0 else c_ > E)]
        if prev: tg["前低(407)"] = prev[-1]
        tg["2R(407)"] = E + s * 2 * R
        o, st = 走到(D, e, s, stop, tg)
        sg = 段(sym, D.index[e])
        row = {"sym": sym, "形态": p["形态"], "日": str(D.index[e].date()), "段": sg, "方向": s, "E": E, "止损": stop, "风险pct": R / E * 100, "测算100%距离pct": abs(tg["100%"] - E) / E * 100,
               "止损第几天": (st - e) if st is not None else None}
        for k, j in o.items(): row[f"到{k}"] = j is not None; row[f"到{k}天"] = (j - e) if j is not None else None
        if sg not in ("封存",):
            rr = 随机对照(D, sym, e, s, R / E, {k: abs(v - E) / E for k, v in tg.items()}, sg)
            for k, v in rr.items(): row[f"对照到{k}"] = v
        rows.append(row)
    return rows


# ---------------- 波浪等距 ----------------
def 之字(D, k=3.0):
    h, l, c, atr = (D[x].to_numpy(float) for x in ("high", "low", "close", "atr")); n = len(c)
    piv = []; dirn = 0; s0 = 20; hi, hii, lo, loi = h[s0], s0, l[s0], s0
    for t in range(s0 + 1, n):
        A = atr[t]
        if np.isnan(A): continue
        if dirn >= 0:
            if h[t] > hi: hi, hii = h[t], t
            if l[t] <= hi - k * A and (dirn == 1 or hii < t):
                piv.append(("H", hii, hi, t)); dirn = -1; lo, loi = l[t], t; continue
        if dirn <= 0:
            if l[t] < lo: lo, loi = l[t], t
            if h[t] >= lo + k * A:
                piv.append(("L", loi, lo, t)); dirn = 1; hi, hii = h[t], t
    return piv          # (类型, 拐点下标, 价, 确认下标)


def 波浪表(D, sym, k=3.0):
    piv = 之字(D, k); rows = []; c = D.close.to_numpy(); atr = D.atr.to_numpy()
    for q in range(2, len(piv)):
        a, b, x = piv[q - 2], piv[q - 1], piv[q]
        if a[0] == "H" and b[0] == "L" and x[0] == "H" and x[2] < a[2]: s = -1
        elif a[0] == "L" and b[0] == "H" and x[0] == "L" and x[2] > a[2]: s = 1
        else: continue
        e = x[3]                                      # 从第三个拐点回头 k 倍 ATR 那天确认（第四个拐点的确认 = 这一段开始）
        if e >= len(c) - 2: continue
        E = c[e]; seg = abs(a[2] - b[2]); ratio = abs(b[2] / a[2] - 1)
        stop = x[2] - s * 0.5 * atr[e]
        tg = {"点数1倍": x[2] + s * seg, "点数1.618倍": x[2] + s * 1.618 * seg, "百分比1倍": x[2] * (1 + s * ratio), "百分比1.618倍": x[2] * (1 + s * min(1.618 * ratio, 0.95)),
              "前低(407)": b[2], "2R(407)": E + s * 2 * abs(E - stop)}
        tg = {kk: v for kk, v in tg.items() if (v - E) * s > 0 and v > 0}
        if abs(E - stop) <= 0 or not tg: continue
        o, st = 走到(D, e, s, stop, tg); sg = 段(sym, D.index[e])
        row = {"sym": sym, "拐点倍": k, "日": str(D.index[e].date()), "段": sg, "方向": s, "E": E, "止损": stop, "风险pct": abs(E - stop) / E * 100}
        for kk, j in o.items(): row[f"到{kk}"] = j is not None; row[f"距离{kk}pct"] = abs(tg[kk] - E) / E * 100
        for kk in ("点数1倍", "点数1.618倍", "百分比1倍", "百分比1.618倍", "前低(407)", "2R(407)"):
            row.setdefault(f"到{kk}", np.nan)
        if sg != "封存":
            rr = 随机对照(D, sym, e, s, abs(E - stop) / E, {kk: abs(v - E) / E for kk, v in tg.items()}, sg)
            for kk, v in rr.items(): row[f"对照到{kk}"] = v
        rows.append(row)
    return rows


# ---------------- 点数图 ----------------
def 数列(h, l, box):
    cols = 0; dirn = 0; cur = None
    for j in range(len(h)):
        if cur is None: cur = h[j]; dirn = 0; cols = 1; continue
        if dirn >= 0:
            if h[j] >= cur + box: cur = cur + box * np.floor((h[j] - cur) / box); dirn = 1
            elif l[j] <= cur - 3 * box: cols += 1; dirn = -1; cur = cur - box * np.floor((cur - l[j]) / box)
        else:
            if l[j] <= cur - box: cur = cur - box * np.floor((cur - l[j]) / box)
            elif h[j] >= cur + 3 * box: cols += 1; dirn = 1; cur = cur + box * np.floor((h[j] - cur) / box)
    return cols


def 点数图表(D, sym, N=40):
    h, l, c, atr = (D[x].to_numpy(float) for x in ("high", "low", "close", "atr")); n = len(c); rows = []; t = N + 20
    while t < n - 1:
        A = atr[t - 1]; top = h[t - N:t].max(); bot = l[t - N:t].min(); hh = top - bot
        ok = not np.isnan(A) and 3 * A <= hh <= 12 * A and (h[t - N:t] >= top - 0.25 * A).sum() >= 2 and (l[t - N:t] <= bot + 0.25 * A).sum() >= 2
        s = 1 if ok and c[t] > top + 0.3 * atr[t] else (-1 if ok and c[t] < bot - 0.3 * atr[t] else 0)
        if s == 0: t += 1; continue
        E = c[t]; stop = (top - 1.0 * atr[t]) if s > 0 else (bot + 1.0 * atr[t]); mid = (top + bot) / 2; sg = 段(sym, D.index[t])
        for q in (0.4, 0.5, 0.6):
            box = q * A; Nc = 数列(h[t - N:t], l[t - N:t], box); 量 = Nc * box * 3
            近 = (bot + 量) if s > 0 else (top - 量)       # 基准价取箱底（向上）/箱顶（向下）
            远 = (mid + 量) if s > 0 else (mid - 量)
            近, 远 = (min(近, 远), max(近, 远)) if s > 0 else (max(近, 远), min(近, 远))
            tg = {"点数图近端": 近, "点数图远端": 远}
            if (近 - E) * s <= 0: tg = {"点数图远端": 远} if (远 - E) * s > 0 else {}
            if not tg: continue
            o, st = 走到(D, t, s, stop, tg)
            fut = D.iloc[t + 1:min(t + 1 + HOLD, n)]; ext = (fut.high.max() if s > 0 else fut.low.min()) if len(fut) else np.nan
            row = {"sym": sym, "格值倍": q, "日": str(D.index[t].date()), "段": sg, "方向": s, "列数": Nc, "E": E, "近端": 近, "远端": 远, "风险pct": abs(E - stop) / E * 100,
                   "120天实际最远": ext, "实际落点离近端pct": (ext / 近 - 1) * 100 if 近 else np.nan}
            for kk, j in o.items(): row[f"到{kk}"] = j is not None; row[f"距离{kk}pct"] = abs(tg[kk] - E) / E * 100
            if sg != "封存":
                rr = 随机对照(D, sym, t, s, abs(E - stop) / E, {kk: abs(v - E) / E for kk, v in tg.items()}, sg)
                for kk, v in rr.items(): row[f"对照到{kk}"] = v
            rows.append(row)
        t += N
    return rows


# ---------------- 合成目标区 + 出场 ----------------
def 出场(D, e, s, E, stop, T1, T2, 平, 剩, k吊=3.0, hold=HOLD):
    h, l, c, o, atr = (D[x].to_numpy(float) for x in ("high", "low", "close", "open", "atr")); n = len(c); R = abs(E - stop)
    pnl = lambda px: s * (px - E) / R
    got = 0.0; w = 1.0; st = stop; half = False; best = E; end = min(e + hold, n - 1)
    for j in range(e + 1, end + 1):
        if (h[j] >= st) if s < 0 else (l[j] <= st):
            px = (o[j] if ((o[j] >= st) if s < 0 else (o[j] <= st)) else st); return got + w * pnl(px), j - e
        if not half and ((l[j] <= T1) if s < 0 else (h[j] >= T1)):
            got += 平 * pnl(T1); w = 1 - 平; half = True; st = E
        if half:
            if 剩 == "T2" and T2 is not None and ((l[j] <= T2) if s < 0 else (h[j] >= T2)): return got + w * pnl(T2), j - e
            if 剩 == "吊灯":
                best = min(best, l[j]) if s < 0 else max(best, h[j]); ns = best + k吊 * atr[j] if s < 0 else best - k吊 * atr[j]
                if (ns < st) if s < 0 else (ns > st): st = ns
    return got + w * pnl(c[end]), end - e


def 合成(D, sym, pats, 并=1.0, 门槛=1.3):
    sh, sl = 摆动(D.high.to_numpy(), D.low.to_numpy()); lo, hi = D.low.to_numpy(), D.high.to_numpy(); c = D.close.to_numpy(); rows = []
    for p in pats:
        e = p["进场i"]; s = 1 if p["方向"] > 0 else -1; E = c[e]; stop = abs(p["止损"]); 颈 = abs(p["颈线"]); 高 = p["高度"]; A = p["ATR"]; R = abs(stop - E)
        if R <= 0: continue
        cand = [颈 + s * 0.75 * 高, 颈 + s * 1.0 * 高] if "起涨点" not in p else [E - 0.75 * (E - p["起涨点"]), p["起涨点"]]
        结构 = [(lo if s < 0 else hi)[j] for j in range(max(0, e - 250), e - 4) if (sl[j] if s < 0 else sh[j])]
        结构 = [x for x in 结构 if (x - E) * s > 0]
        # 测算位落在大前低外侧不远（< 1.5 ATR）→ 挪到前低里侧一点
        adj = []
        for x in cand:
            near = [y for y in 结构 if 0 < (x - y) * s < 1.5 * A]
            adj.append((near[0] - s * 0.25 * A) if near else x)
        pts = sorted(set(adj + 结构), key=lambda x: abs(x - E))
        zones = []
        for x in pts:
            if zones and abs(x - zones[-1][-1]) <= 并 * A: zones[-1].append(x)
            else: zones.append([x])
        zs = [float(np.mean(z)) for z in zones if (np.mean(z) - E) * s > 0]
        zs = [z for z in zs if abs(z - E) >= 0.5 * R]          # 太近的不算目标（我补的）
        if not zs: continue
        T1 = zs[0]; T2 = zs[1] if len(zs) > 1 else None
        if abs(T1 - E) / R < 门槛: continue
        sg = 段(sym, D.index[e]); row = {"sym": sym, "形态": p["形态"], "日": str(D.index[e].date()), "段": sg, "T1倍风险": abs(T1 - E) / R}
        fee = 2 * FEE * E / R
        for nm, 平, 剩 in (("对照·T1平一半+保本拿T2", 0.5, "T2"), ("T1平35%+保本拿T2", 0.35, "T2"), ("T1平25%+保本拿T2", 0.25, "T2"), ("T1平50%+保本拿T2", 0.5, "T2"),
                         ("T1平35%+吊灯3ATR", 0.35, "吊灯"), ("T1平35%+吊灯2.5ATR", 0.35, "吊灯2.5")):
            r, held = 出场(D, e, s, E, stop, T1, T2, 平, "吊灯" if 剩.startswith("吊灯") else 剩, k吊=2.5 if 剩 == "吊灯2.5" else 3.0)
            row[nm] = r - fee
        rows.append(row)
    return rows


def 汇总(T, keys, by):
    out = {}
    for g, x in T.groupby(by):
        g = g if isinstance(g, tuple) else (g,)
        out["｜".join(map(str, g))] = {"笔数": int(len(x)), **{k: round(float(x[k].mean()) * 100, 1) for k in keys if k in x and x[k].notna().any()}}
    return out


if __name__ == "__main__":
    syms = ["SPY", "SOXX", "BTC", "ETH"]; Ds = {s: 读(s) for s in syms}
    # 1 形态
    P = []; pats_all = {}
    for s in syms:
        D = Ds[s]; ps = 头肩(D, True) + 头肩(D, False) + 三重(D, True) + 三重(D, False) + 箱体(D, 20)
        pats_all[s] = ps; P += 测算表(D, s, ps)
    楔 = 楔形变体()
    for s in ("BTC", "ETH"):
        P += 测算表(Ds[s], s, [p for p in 楔 if p["sym"] == s])
    箱邻 = []
    for N in (15, 30):
        for s in syms: 箱邻 += [dict(r, 形态=f"箱体{N}根·" + r["形态"][2:]) for r in 测算表(Ds[s], s, 箱体(Ds[s], N))]
    T = pd.DataFrame(P + 箱邻); T["类"] = np.where(T["sym"].isin(["BTC", "ETH"]), "币", "美股ETF")
    T[T["段"] == "封存"].to_csv(os.path.join(OUT, "封存_形态.csv"), index=False); T = T[T["段"] != "封存"]; T.to_csv(os.path.join(OUT, "形态_逐笔.csv"), index=False)
    # 2 点数图
    PF = pd.DataFrame(sum((点数图表(Ds[s], s) for s in syms), [])); PF[PF["段"] == "封存"].to_csv(os.path.join(OUT, "封存_点数图.csv"), index=False); PF = PF[PF["段"] != "封存"]; PF.to_csv(os.path.join(OUT, "点数图_逐笔.csv"), index=False)
    # 3 波浪
    WV = pd.DataFrame(sum((波浪表(Ds[s], s, k) for s in syms for k in (2.5, 3.0, 4.0)), [])); WV[WV["段"] == "封存"].to_csv(os.path.join(OUT, "封存_波浪.csv"), index=False); WV = WV[WV["段"] != "封存"]; WV.to_csv(os.path.join(OUT, "波浪_逐笔.csv"), index=False)
    # 4 合成 + 出场
    CB = []
    for 并 in (0.8, 1.0, 1.2):
        for 门 in (1.3, 1.5, 1.8):
            for s in syms:
                ps = pats_all[s] + ([p for p in 楔 if p["sym"] == s] if s in ("BTC", "ETH") else [])
                CB += [dict(r, 合并ATR=并, 门槛=门) for r in 合成(Ds[s], s, ps, 并, 门)]
    CB = pd.DataFrame(CB); CB[CB["段"] == "封存"].to_csv(os.path.join(OUT, "封存_合成.csv"), index=False); CB = CB[CB["段"] != "封存"]; CB.to_csv(os.path.join(OUT, "合成_逐笔.csv"), index=False)
    print("形态", len(T), "点数图", len(PF), "波浪", len(WV), "合成", len(CB))
    print("DONE")
