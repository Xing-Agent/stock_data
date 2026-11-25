# -*- coding: utf-8 -*-
"""核心位置打分器 · 第三版 · 照《446 拍板》第 1 条（+《442》水平位打底、《411》≥3 样 ≥2 类）· 引擎外 · 只读数据
只做**上方压力**这一侧（做空要用的）。每天开始前只用前一天及以前已收盘的日线 / 周线 / 月线 / 4 小时线。
地基（至少一项，否则不算）：前高前低（分形，日线左右各 N 根；周线 3、月线 2 是我定的）· 密集成交区 POC（过去 W 根，分 50 格）· 没回补一半的缺口 · 币加 4 小时 FVG
只加分：趋势线（两个确认的降低摆动高点、隔 ≥10 根、中间没有收盘刺穿）· 均线（50 日 / 200 日 / 30 周，向下才算压力）· 0.5 / 0.618（最近一段 > 3 ATR 的下跌）
挨得近：并 × 日线 ATR 以内并成一个带。防泛滥：现价上方 8 ATR 以内；留最高分 2 个、相隔 ≥ 1.5 ATR；被碰一次 ×0.7；被收盘突破 0.5 ATR：
   前低（支撑）第一次被跌破 → 变压力，保留；压力被收盘站上 0.5 ATR → 作废。（「支撑变压力保留一次」是我的读法，拍板原文只说作废。）
到位时的「量价衰竭 +2」「小周期形态 +1」是扳机那一刻的事，这里不加；所以这里的及格是**偏严**的。
用法：python3 打分器_第三版_1125.py BTC|ETH|SOXX   → out/{sym}_带_{版}_{参数}.pkl + out/{sym}_占比.json
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def _imp(nm, p):
    sp = importlib.util.spec_from_file_location(nm, os.path.join(ROOT, p)); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = _imp("m4", "probe/大周期五档_1123/五档状态机_第四版_1123.py"); V1 = _imp("v1", "probe/核心压力位_1123/打分器_1123.py"); SC = _imp("sc", "probe/历史扫描定级别_1123/扫描_1123.py")
B = dict(名="B", 分={"前高前低": 3.0, "密集区": 3.0, "缺口": 2.5, "趋势线": 1.5, "斐波": 1.5, "均线": 1.0}, 乘={"4h": 1.1, "D": 2.0, "W": 3.5, "M": 5.0}, 并=0.25, 结构最低=None)
A = dict(名="A", 分={"前高前低": 2.0, "密集区": 2.5, "中轴": 1.0, "缺口": 1.5, "趋势线": 1.5, "斐波": 1.0, "均线": 1.5}, 乘={"4h": 0.8, "D": 1.0, "W": 1.3, "M": 1.6}, 并=0.4, 结构最低=2.0)
地基类 = {"前高前低", "密集区", "缺口"}
大类 = {"前高前低": "水平", "密集区": "水平", "中轴": "水平", "缺口": "缺口", "趋势线": "趋势线", "斐波": "斐波", "均线": "均线"}

def 重采(D, rule):
    return D.resample(rule).agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()

def 分形(X, N):
    """返回 [(确认时刻, 所在时刻, 价, '高'/'低')]；确认时刻 = 右边第 N 根收盘。"""
    h, l = X.high.to_numpy(float), X.low.to_numpy(float); out = []; t = X.index
    for j in range(N, len(X) - N):
        if h[j] == h[j - N:j + N + 1].max(): out.append((t[j + N], t[j], h[j], "高"))
        if l[j] == l[j - N:j + N + 1].min(): out.append((t[j + N], t[j], l[j], "低"))
    return out

def 每天的带(D, H4, P, N=5, 窗=60, 币=True, 起=None, 测试="固定"):
    """测试="固定"：每碰一次 ×0.7（《446》）。测试="分支"：照《450》第 2 条 —— 派发 +1.5（最多 +3）/ 吸收 ×0.7 / 其他 ×0.9；"分支B"：派发每次 ×1.15、封顶 10 分。
    一次「碰」= 当天最高进了位置下方 0.25 ATR 以内、收盘在位置下方。碰完等 3 天再定性（看这 3 天最多砸下多少）。"""
    o, h, l, c, v = (D[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); n = len(D); idx = D.index
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    wk = 7 if 币 else 5
    s50 = pd.Series(c).rolling(50).mean().to_numpy(); s200 = pd.Series(c).rolling(200).mean().to_numpy(); s30w = pd.Series(c).rolling(30 * wk).mean().to_numpy()
    W = 重采(D, "W-SUN" if 币 else "W-FRI"); Mo = 重采(D, "ME")
    # 各周期的分形；周 / 月的「确认时刻」再加一根自己的周期收盘（resample 的标签是期末）
    F = [("D", x) for x in 分形(D, N)] + [("W", x) for x in 分形(W, 3)] + [("M", x) for x in 分形(Mo, 2)]
    F = [(tf, pd.Timestamp(ct), pd.Timestamp(st), p, k) for tf, (ct, st, p, k) in F]; F.sort(key=lambda x: x[1])
    if H4 is not None:
        hh, hl, ht = H4.high.to_numpy(float), H4.low.to_numpy(float), H4.index
        FVG = [(ht[j + 1] + pd.Timedelta(hours=4), hh[j + 1], hl[j - 1], j) for j in range(1, len(H4) - 1) if hl[j - 1] > hh[j + 1]]   # 向下真空：(可用时刻, 下沿, 上沿)
    v20 = pd.Series(v).rolling(20).mean().to_numpy()
    活 = []; fi = 0; out = {}; dsh = []                       # 活 = 还没作废的水平位：dict(tf, 价, 类型, 碰, 生)
    gaps = []; fv = 0; 活F = []
    for i in range(n):
        day_end = idx[i] + pd.Timedelta(days=1)                # 第 i 天收盘后
        while fi < len(F) and F[fi][1] <= idx[i]:
            tf, ct, st, p, k = F[fi]; fi += 1
            活.append(dict(tf=tf, p=p, 原=k, 角色=("压力" if k == "高" else "支撑"), 碰=0, 生=i, 乘=1.0, 加=0.0, 待=[], 上次高=p, 首量=(v[D.index.get_loc(st)] if (tf == "D" and st in D.index) else v20[i])))
            if tf == "D" and k == "高": dsh.append((D.index.get_loc(st), p))
        a = atr[i]
        if not (a > 0): continue
        if i >= 1 and l[i - 1] > h[i] and not 币: gaps.append(dict(lo=h[i], hi=l[i - 1], 生=i))       # 日线向下缺口
        if H4 is not None:
            while fv < len(FVG) and FVG[fv][0] <= day_end: 活F.append(dict(lo=FVG[fv][1], hi=FVG[fv][2], 生=i)); fv += 1
        keep = []
        for L in 活:
            if L["生"] == i: keep.append(L); continue
            if L["角色"] == "支撑":
                if c[i] < L["p"] - 0.5 * a: L["角色"] = "压力"; L["碰"] = 0; L["乘"] = 1.0; L["加"] = 0.0; L["待"] = []; L["上次高"] = L["p"]; L["首量"] = v[i]           # 被跌破 → 变压力（只变一次）
                keep.append(L)
            else:
                if c[i] > L["p"] + 0.5 * a: continue                                  # 压力被站上 → 作废
                for T_ in list(L["待"]):                                         # 3 天后给上一次「碰」定性
                    if i - T_["i"] >= 3:
                        砸 = T_["高"] - l[T_["i"]:i + 1].min(); 派发 = T_["高"] <= T_["前高"] and T_["量"] < 0.85 * L["首量"] and 砸 >= 1.2 * T_["a"]
                        吸收 = T_["高"] > T_["前高"] or T_["量"] > 1.3 * T_["v20"] or 砸 < 0.8 * T_["a"]
                        if 测试 == "分支":
                            if 派发: L["加"] = min(3.0, L["加"] + 1.5)
                            elif 吸收: L["乘"] *= 0.7
                            else: L["乘"] *= 0.9
                        elif 测试 == "分支B": L["乘"] *= 1.15 if 派发 else (0.7 if 吸收 else 0.9)
                        L["待"].remove(T_)
                if h[i] >= L["p"] - 0.25 * a and c[i] < L["p"]:
                    L["碰"] += 1; L["待"].append(dict(i=i, 高=h[i], 前高=L["上次高"], 量=v[i], v20=v20[i], a=a)); L["上次高"] = h[i]
                keep.append(L)
        活 = keep
        gaps = [g for g in gaps if not (h[i] >= (g["lo"] + g["hi"]) / 2 and g["生"] < i)]
        活F = [g for g in 活F if not (h[i] >= (g["lo"] + g["hi"]) / 2 and g["生"] < i) and i - g["生"] <= 120]
        if i < 260 or (起 is not None and idx[i] < 起): continue
        px = c[i]; top = px + 8 * a; lv = []                   # (价, 样, tf, 分数乘子)
        for L in 活:
            if L["角色"] == "压力" and px < L["p"] <= top:
                if L["tf"] == "D" and i - L["生"] > 250: continue
                lv.append((L["p"], "前高前低", L["tf"], (0.7 ** L["碰"]) if 测试 == "固定" else L["乘"], L["加"] if 测试 == "分支" else 0.0))
        for tf, X in (("D", D.iloc[max(0, i - 窗 + 1):i + 1]), ("W", W[W.index <= idx[i]].iloc[-窗:])):
            if len(X) < 20: continue
            lo_, hi_ = X.low.min(), X.high.max()
            if hi_ <= lo_: continue
            ed = np.linspace(lo_, hi_, 51); tp = ((X.high + X.low + X.close) / 3).to_numpy(float); hist, _ = np.histogram(tp, bins=ed, weights=X.volume.to_numpy(float))
            b = int(np.argmax(hist)); poc = (ed[b] + ed[b + 1]) / 2
            if px < poc <= top: lv.append((poc, "密集区", tf, 1.0))
            mid = (lo_ + hi_) / 2
            if "中轴" in P["分"] and px < mid <= top: lv.append((mid, "中轴", tf, 1.0))
        for g in gaps:
            m = (g["lo"] + g["hi"]) / 2
            if px < m <= top and i - g["生"] <= 250: lv.append((m, "缺口", "D", 1.0))
        for g in 活F:
            m = (g["lo"] + g["hi"]) / 2
            if px < m <= top: lv.append((m, "缺口", "4h", 1.0))
        sh = [(j, p) for (j, p) in dsh if j >= i - 250]
        if len(sh) >= 2:
            (j1, p1), (j2, p2) = sh[-2], sh[-1]
            if p2 < p1 and j2 - j1 >= 10:
                k_ = (p2 - p1) / (j2 - j1)
                if not (c[j1 + 1:i + 1] > p1 + k_ * (np.arange(j1 + 1, i + 1) - j1)).any():
                    tl = p2 + k_ * (i + 1 - j2)
                    if px < tl <= top: lv.append((tl, "趋势线", "D", 1.0))
        if sh:
            jh, ph = max(sh, key=lambda x: x[1]); lo = l[jh:i + 1].min()
            if ph - lo > 3 * a:
                for f in (0.5, 0.618):
                    p = lo + f * (ph - lo)
                    if px < p <= top: lv.append((p, "斐波", "D", 1.0))
        for s, tf in ((s50, "D"), (s200, "D"), (s30w, "W")):
            if s[i] > 0 and px < s[i] <= top and s[i] < s[i - 10]: lv.append((s[i], "均线", tf, 1.0))
        lv.sort(); zones = []; cur = []
        for it in lv:
            if cur and it[0] - cur[0][0] > P["并"] * a: zones.append(cur); cur = []
            cur.append(it)
        if cur: zones.append(cur)
        Z = []
        for z in zones:
            best = {}
            for it_ in z:
                p, nm, tf, mul = it_[:4]; 加_ = it_[4] if len(it_) > 4 else 0.0
                s = P["分"].get(nm, 0) * P["乘"][tf] * mul + 加_
                if 测试 == "分支B" and nm == "前高前低": s = min(s, 10.0)
                if s > best.get((nm, tf), (0, 0))[0]: best[(nm, tf)] = (s, p)
            样 = {k[0] for k in best}; sc = sum(x[0] for x in best.values()); 原始最高 = max(P["分"].get(k[0], 0) for k in best)
            Z.append(dict(lo=z[0][0], hi=z[-1][0], 分=round(sc, 2), 样=sorted(样), 几样=len(样), 几类=len({大类[x] for x in 样}), 有地基=bool(样 & 地基类),
                          结构够=(P["结构最低"] is None or 原始最高 >= P["结构最低"]), 明细=sorted(f"{k[0]}@{k[1]}" for k in best)))
        Z.sort(key=lambda z: -z["分"]); 留 = []
        for z in Z:
            if not z["有地基"] or not z["结构够"]: continue
            if 留 and abs((z["lo"] + z["hi"]) / 2 - (留[0]["lo"] + 留[0]["hi"]) / 2) < 1.5 * a: continue
            留.append(z)
            if len(留) == 2: break
        out[day_end] = dict(zones=留, atr=a, px=px, 全部=len(Z))
    return out

def 占比(带, 及格, 要411):
    ok = lambda z: z["分"] >= 及格 and (not 要411 or (z["几样"] >= 3 and z["几类"] >= 2))
    ks = [k for k in 带 if not (pd.Timestamp("2022-01-01") <= k <= pd.Timestamp("2025-12-31"))]
    return round(float(np.mean([any(ok(z) for z in 带[k]["zones"]) for k in ks]) * 100), 1), len(ks)

def 读(sym):
    if sym in ("BTC", "ETH"):
        D = M4.币日线(sym); H = V1.小时线(sym); H = H[H.index < D.index[-1] + pd.Timedelta(days=1)]
        H4 = H.resample("4h").agg({"high": "max", "low": "min", "close": "last"}).dropna(); return D, H4, True
    y = pd.read_csv(os.path.join(ROOT, "market_ext_1105/SOXX_1123/日线/SOXX_日线.csv"), parse_dates=["date"]).set_index("date")
    D = pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna(); return D, None, False

if __name__ == "__main__":
    sym = sys.argv[1]; D, H4, 币 = 读(sym); res = {}
    for P, 及格们 in ((B, (7, 8, 9.5)), (A, (4, 5, 6))):
        for 并 in ((0.2, 0.25, 0.35) if P["名"] == "B" else (0.4,)):
            for N in (3, 5, 8):
                for 窗 in (40, 60, 90):
                    if (N != 5) + (窗 != 60) + (并 not in (0.25, 0.4)) > 1: continue          # 一次只挪一个参数
                    Q = dict(P); Q["并"] = 并; 带 = 每天的带(D, H4, Q, N=N, 窗=窗, 币=币)
                    tag = f"{P['名']}_并{并}_N{N}_窗{窗}"; pd.to_pickle(带, os.path.join(HERE, "out", f"{sym}_带_{tag}.pkl"))
                    res[tag] = {f"及格{g}": {"不要411": 占比(带, g, False)[0], "要411": 占比(带, g, True)[0]} for g in 及格们}; res[tag]["天数"] = 占比(带, 0, False)[1]
                    print(tag, res[tag], flush=True)
    json.dump(res, open(os.path.join(HERE, "out", f"{sym}_占比.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
