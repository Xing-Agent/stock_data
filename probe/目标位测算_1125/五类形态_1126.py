# -*- coding: utf-8 -*-
"""《475》补五类形态再测目标位（照 手册 475 任务单；口径、对照、封存同《465》主脚本 目标位测算_1125.py）。日线。
五类：双顶/双底、旗形/三角旗、三角形（对称/上升/下降）、普通上升/下降楔形。定义是主 chat 补的（行业惯例），不是原著逐条核过。

══ 任务单没写死、我补的（报告里照实列）══
 Q1 双顶「两个顶」= 两个摆动高点，中间没有更高的摆动高点（中间最高价 < 两顶中较低的那个）；颈线 = 两顶之间最低价。从第二个顶确认（右边第 5 根）开始等跌破。
 Q2 旗杆 = 某根 K 线（杆顶）往前 10 根内的最低点到杆顶最高价；杆顶要是之后整个旗面里的最高。杆量 = 杆上各根平均量，和杆起点那天之前 20 日均量比。
 Q3 旗面边线 = 旗面里第一个和最后一个已确认的摆动高点连线（上边）、摆动低点连线（下边）。
    「大致平行」= 两条线都逆着旗杆方向斜，斜率之比在 0.5~2 之间（我补的；另报一版不要求平行、只要两条线都逆着斜）。
    画不出边线（摆动高点或低点不到 2 个）时，按任务单用旗面最高、最低收盘当边，单列成「旗面·收盘当边」，不分旗形还是三角旗。
 Q4 旗形止损 = 旗面最低价（做多）往外 0.5 ATR；三角形止损 = 另一条边线在进场那天的位置往外 0.5 ATR。
 Q5' 拐点不合并：连续两个同类摆动点（比如两个高点中间没有摆动低点）的那一段不算形态（合并要偷看后面的点）。
 Q5 三角形、楔形的边线 = 第一个和最后一个摆动高点（低点）连线；最宽处 = 形态起点（第一个摆动点）那天两条线的距离。
    同一个最后拐点只认最长的那组；从最后一个拐点确认起等突破，等到下一个拐点确认为止（那时候形态已经变了，交给下一组）。
 Q6 上升三角形「低点一个比一个高」、楔形「高点低点都在抬高」= 严格抬高（差 > 0），任务单没给最小差。
 Q7 楔形起点 = 形态里第一个摆动低点的价（上升楔形）；下降楔形镜像 = 第一个摆动高点。
 Q8 楔形「量越来越小」= 从第一个到最后一个拐点，后一半平均量 < 前一半。
 Q9 一个形态成立后，它用过的拐点不再算下一个形态。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sp = importlib.util.spec_from_file_location("主", os.path.join(HERE, "目标位测算_1125.py")); 主 = importlib.util.module_from_spec(sp); sp.loader.exec_module(主)
读, 段, 摆动, 走到, 随机对照 = 主.读, 主.段, 主.摆动, 主.走到, 主.随机对照


def arr(D, neg):
    h, l, c, v, atr, v20 = (D[x].to_numpy(float) for x in ("high", "low", "close", "volume", "atr", "v20"))
    if neg: h, l, c = -l, -h, -c
    return h, l, c, v, atr, v20


def 出(名, t, 方向, neg, E_s, stop_s, tg_s, extra=None):
    """把「顶空间」里的数翻回真价。E_s/stop_s/tg_s 都是在当前空间（neg 时是负价）。"""
    f = -1 if neg else 1
    d = {"形态": 名, "进场i": t, "方向": 方向, "止损": f * stop_s, "目标": {k: f * v for k, v in tg_s.items()}}
    if extra: d.update(extra)
    return d


# ---------- 一 双顶 / 双底 ----------
def 双顶(D, 顶=True, 差=1.0, 隔=(21, 65), 高下=2.5):
    neg = not 顶; h, l, c, v, atr, v20 = arr(D, neg); rc = D.close.to_numpy(float)
    lo120 = pd.Series(rc).rolling(120, min_periods=60).min().to_numpy(); hi120 = pd.Series(rc).rolling(120, min_periods=60).max().to_numpy()
    sh, _ = 摆动(h, l); H = np.where(sh)[0]; out = []; used = -1
    for q in range(1, len(H)):
        b = H[q]
        for p in range(q - 1, -1, -1):
            a = H[p]
            if b - a > 隔[1]: break
            if b - a < 隔[0] or a <= used: continue
            if h[a + 1:b].max() >= min(h[a], h[b]): continue                     # Q1
            A = atr[b]
            if np.isnan(A) or abs(h[a] - h[b]) > 差 * A: continue
            if 顶 and not (rc[a] >= lo120[a] * 1.15): continue
            if not 顶 and not (rc[a] <= hi120[a] / 1.15): continue
            neck = l[a:b + 1].min(); top = max(h[a], h[b]); 高 = top - neck
            if 高 < 高下 * A: continue
            for t in range(b + 5, min(b + 5 + 40, len(c))):
                if c[t] > top: break
                if c[t] < neck - 0.3 * atr[t]:
                    out.append(出("双顶" if 顶 else "双底", t, -1 if 顶 else 1, neg, c[t], top + 0.5 * atr[t], {f"{int(k*100)}%": neck - k * 高 for k in (1.0, 0.8, 0.75)}))
                    used = b; break
            break
    return out


# ---------- 二 旗形 / 三角旗 ----------
def 旗(D, 多=True, 杆=4.0, 面=(5, 15), 回撤=0.5, kk=2, 要平行=True):
    neg = not 多; h, l, c, v, atr, v20 = arr(D, neg); n = len(c)
    sh, sl = 摆动(h, l, kk); out = []; t0 = 30
    p = t0
    while p < n - 2:
        A = atr[p]
        if np.isnan(A) or h[p] < h[max(0, p - 10):p + 1].max():
            p += 1; continue
        s = p - 10 + int(np.argmin(l[p - 10:p + 1])); 杆长 = h[p] - l[s]
        if s >= p or 杆长 < 杆 * A or np.isnan(v20[s]) or v[s:p + 1].mean() < 1.3 * v20[s]:
            p += 1; continue
        杆量 = v[s:p + 1].mean(); done = False
        for t in range(p + 2, min(p + 1 + 面[1] + 1, n)):
            fl = slice(p + 1, t)                                                 # 旗面 = p+1 .. t-1
            L = t - 1 - p
            if h[fl].max() >= h[p] or l[fl].min() < h[p] - 回撤 * 杆长: break    # 旗面冲过杆顶、或回撤太深 → 不是旗
            if L < 面[0]: continue
            if v[fl].mean() >= 杆量: continue
            iH = [j for j in range(p + 1, t) if sh[j] and j + kk <= t - 1]; iL = [j for j in range(p + 1, t) if sl[j] and j + kk <= t - 1]
            if len(iH) >= 2 and len(iL) >= 2:
                su = (h[iH[-1]] - h[iH[0]]) / (iH[-1] - iH[0]); sl_ = (l[iL[-1]] - l[iL[0]]) / (iL[-1] - iL[0])
                up = h[iH[0]] + su * (t - iH[0])
                if su < 0 and sl_ < 0 and (not 要平行 or 0.5 <= su / sl_ <= 2): 名 = "旗形"
                elif su < 0 and sl_ > 0: 名 = "三角旗"
                else: continue
            else:
                up = c[fl].max(); 名 = "旗面·收盘当边"
            if c[t] > up + 0.3 * atr[t]:
                名2 = ("上涨" if 多 else "下跌") + 名
                out.append(出(名2, t, 1 if 多 else -1, neg, c[t], l[fl].min() - 0.5 * atr[t], {"100%": c[t] + 杆长, "80%": c[t] + 0.8 * 杆长, "75%": c[t] + 0.75 * 杆长, "61.8%": c[t] + 0.618 * 杆长, "50%": c[t] + 0.5 * 杆长}))
                p = t; done = True; break
        p += 1
    return out


# ---------- 三、四 共用：交替拐点 ----------
def 拐点(h, l):
    """全部摆动点按时间排好。不合并连续同类（合并要看后面的点，会偷看未来）；交替与否在用的时候查。"""
    sh, sl = 摆动(h, l); return sorted([(j, 1, h[j]) for j in np.where(sh)[0]] + [(j, -1, l[j]) for j in np.where(sl)[0]])


def 交替(seg): return all(seg[q][1] != seg[q + 1][1] for q in range(len(seg) - 1))


def 线(pts):
    (i0, p0), (i1, p1) = pts[0], pts[-1]; s = (p1 - p0) / (i1 - i0); return s, (lambda x: p0 + s * (x - i0))


def 三角(D, 长=(20, 60), 对称差=0.3, 平=0.5, 宽下=2.5, 前四分之三=True):
    h, l, c, v, atr, v20 = arr(D, False); n = len(c); Q = 拐点(h, l); out = []; used = -1
    for j in range(3, len(Q)):
        conf = Q[j][0] + 5; nxt = Q[j + 1][0] + 5 if j + 1 < len(Q) else n
        for i in range(0, j - 2):                                                   # 最长的先试（Q5）
            seg = Q[i:j + 1]
            if seg[0][0] <= used or Q[j][0] - seg[0][0] > 长[1] or not 交替(seg): continue
            Hs = [(x[0], x[2]) for x in seg if x[1] == 1]; Ls = [(x[0], x[2]) for x in seg if x[1] == -1]
            if len(Hs) < 2 or len(Ls) < 2: continue
            A = atr[Q[j][0]]
            if np.isnan(A): continue
            hp = [x[1] for x in Hs]; lp = [x[1] for x in Ls]
            dh = np.diff(hp); dl = np.diff(lp)
            if all(dh <= -对称差 * A) and all(dl >= 对称差 * A): 名 = "对称三角形"
            elif max(hp) - min(hp) <= 平 * A and all(dl > 0): 名 = "上升三角形"
            elif max(lp) - min(lp) <= 平 * A and all(dh < 0): 名 = "下降三角形"
            else: continue
            su, U = 线(Hs); sL, Lf = 线(Ls); x0 = seg[0][0]
            宽 = U(x0) - Lf(x0)
            if 宽 < 宽下 * A or su >= sL: continue
            apex = x0 + 宽 / (sL - su)
            for t in range(conf, min(nxt, n)):
                if t - x0 > 长[1] or t >= apex: break
                if 前四分之三 and t > x0 + 0.75 * (apex - x0): break
                if t - x0 < 长[0]: continue
                if c[t] > U(t) + 0.3 * atr[t]:
                    out.append(出(名 + "·向上", t, 1, False, c[t], Lf(t) - 0.5 * atr[t], {f"{int(k*100)}%": c[t] + k * 宽 for k in (1.0, 0.8, 0.75)})); used = Q[j][0]; break
                if c[t] < Lf(t) - 0.3 * atr[t]:
                    out.append(出(名 + "·向下", t, -1, False, c[t], U(t) + 0.5 * atr[t], {f"{int(k*100)}%": c[t] - k * 宽 for k in (1.0, 0.8, 0.75)})); used = Q[j][0]; break
            break                                                                   # 只认最长的那组（Q5）
    return out


def 楔(D, 上升=True, 长=(20, 60), 碰=5, 要量=True):
    neg = not 上升; h, l, c, v, atr, v20 = arr(D, neg); n = len(c); Q = 拐点(h, l); out = []; used = -1
    for j in range(碰 - 1, len(Q)):
        conf = Q[j][0] + 5; nxt = Q[j + 1][0] + 5 if j + 1 < len(Q) else n
        for i in range(0, j - 碰 + 2):
            seg = Q[i:j + 1]
            if seg[0][0] <= used or Q[j][0] - seg[0][0] > 长[1] or not 交替(seg): continue
            Hs = [(x[0], x[2]) for x in seg if x[1] == 1]; Ls = [(x[0], x[2]) for x in seg if x[1] == -1]
            if len(Hs) < 2 or len(Ls) < 2 or len(seg) < 碰: continue
            if not (all(np.diff([x[1] for x in Hs]) > 0) and all(np.diff([x[1] for x in Ls]) > 0)): continue
            su, U = 线(Hs); sL, Lf = 线(Ls); x0, x1 = seg[0][0], seg[-1][0]
            if not (sL > su > 0): continue                                            # 下边更陡、往右收敛
            if 要量:
                m = (x0 + x1) // 2
                if not (v[m:x1 + 1].mean() < v[x0:m].mean()): continue
            宽 = U(x0) - Lf(x0); 起 = Ls[0][1]; 末高 = Hs[-1][1]
            apex = x0 + 宽 / (sL - su) if sL > su else np.inf
            for t in range(conf, min(nxt, n)):
                if t - x0 > 长[1] or t >= apex: break
                if c[t] > 末高 + 0.5 * atr[t]: break
                if t - x0 < 长[0]: continue
                if c[t] < Lf(t) - 0.3 * atr[t]:
                    tg = {"回到起点": 起, "宽度100%": c[t] - 宽, "宽度80%": c[t] - 0.8 * 宽, "宽度75%": c[t] - 0.75 * 宽}
                    if 起 >= c[t]: tg.pop("回到起点")
                    out.append(出("上升楔形·跌破" if 上升 else "下降楔形·突破", t, -1 if 上升 else 1, neg, c[t], 末高 + 0.5 * atr[t], tg)); used = Q[j][0]; break
            break
    return out


def 测算(D, sym, pats):
    rows = []; sh, sl = 摆动(D.high.to_numpy(), D.low.to_numpy()); c = D.close.to_numpy(); hi = D.high.to_numpy(); lo = D.low.to_numpy()
    for p in pats:
        e = p["进场i"]; s = p["方向"]; E = c[e]; stop = p["止损"]; R = (stop - E) * (-s)
        if R <= 0: continue
        tg = {k: v for k, v in p["目标"].items() if (v - E) * s > 0}
        if not tg: continue
        主目标 = "100%" if "100%" in tg else ("宽度100%" if "宽度100%" in tg else list(tg)[0])
        prev = [x for j, x in enumerate(lo if s < 0 else hi) if (sl[j] if s < 0 else sh[j]) and j + 5 <= e and e - j <= 250 and (x < E if s < 0 else x > E)]
        if prev: tg["前低(407)"] = prev[-1]
        tg["2R(407)"] = E + s * 2 * R
        o, st = 走到(D, e, s, stop, tg); sg = 段(sym, D.index[e])
        row = {"sym": sym, "形态": p["形态"], "日": str(D.index[e].date()), "段": sg, "方向": s, "E": E, "止损": stop, "风险pct": R / E * 100, "主目标距离pct": abs(tg[主目标] - E) / E * 100, "止损第几天": (st - e) if st is not None else None}
        for k in p["目标"]: row[f"到{k}"] = (o[k] is not None) if k in o else np.nan
        row["到前低(407)"] = (o["前低(407)"] is not None) if "前低(407)" in o else np.nan; row["到2R(407)"] = o["2R(407)"] is not None
        近 = "75%" if "75%" in tg else ("宽度75%" if "宽度75%" in tg else None)
        row["没到75%先打止损"] = (st is not None) and (近 is None or o.get(近) is None)
        if sg != "封存":
            rr = 随机对照(D, sym, e, s, R / E, {k: abs(v - E) / E for k, v in tg.items()}, sg)
            for k, v in rr.items(): row[f"对照到{k}"] = v
        rows.append(row)
    return rows


配置 = {
    "双顶": [("默认", {}), ("差0.7", {"差": 0.7}), ("差1.5", {"差": 1.5}), ("隔上限45", {"隔": (21, 45)}), ("隔上限90", {"隔": (21, 90)}), ("高2.0", {"高下": 2.0}), ("高3.5", {"高下": 3.5})],
    "旗": [("默认", {}), ("杆3", {"杆": 3.0}), ("杆5", {"杆": 5.0}), ("面上限10", {"面": (5, 10)}), ("面上限20", {"面": (5, 20)}), ("回撤38", {"回撤": 0.382}), ("回撤62", {"回撤": 0.618}), ("摆动3根", {"kk": 3}), ("不要求平行", {"要平行": False})],
    "三角": [("默认", {}), ("长上限40", {"长": (20, 40)}), ("长上限90", {"长": (20, 90)}), ("对称差0.2", {"对称差": 0.2}), ("对称差0.5", {"对称差": 0.5}), ("平0.3", {"平": 0.3}), ("平0.8", {"平": 0.8}), ("宽2.0", {"宽下": 2.0}), ("宽3.5", {"宽下": 3.5}), ("不要前四分之三", {"前四分之三": False})],
    "楔": [("默认", {}), ("长上限40", {"长": (20, 40)}), ("长上限90", {"长": (20, 90)}), ("碰4次", {"碰": 4}), ("不要量", {"要量": False})],
}
函数 = {"双顶": lambda D, kw: 双顶(D, True, **kw) + 双顶(D, False, **kw), "旗": lambda D, kw: 旗(D, True, **kw) + 旗(D, False, **kw),
       "三角": lambda D, kw: 三角(D, **kw), "楔": lambda D, kw: 楔(D, True, **kw) + 楔(D, False, **kw)}

if __name__ == "__main__":
    syms = ["SPY", "SOXX", "BTC", "ETH"]; Ds = {s: 读(s) for s in syms}; rows = []
    for 类, cfgs in 配置.items():
        for 名, kw in cfgs:
            for s in syms:
                rows += [dict(r, 类别=类, 参数=名) for r in 测算(Ds[s], s, 函数[类](Ds[s], kw))]
            print(类, 名, len(rows), flush=True)
    T = pd.DataFrame(rows); T["品种类"] = np.where(T["sym"].isin(["BTC", "ETH"]), "币", "美股ETF")
    T[T["段"] == "封存"].to_csv(os.path.join(OUT, "封存_五类形态.csv"), index=False)
    T[T["段"] != "封存"].to_csv(os.path.join(OUT, "五类形态_逐笔.csv"), index=False)
    print("DONE", len(T))
