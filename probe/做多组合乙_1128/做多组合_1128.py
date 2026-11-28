# -*- coding: utf-8 -*-
"""《571》第三批 · 做多组合（《527 拍板》第 1 条后半）· 引擎外 · 日线 · 只读
四样同时满足才做：大方向 + 等待区 + 扳机 + 盈亏比够。两套：顺势回踩、V 形反转。四个条件逐个加上去，每加一个报一次。
对照：① 在「同样满足大方向和等待区」的 K 线里随机进场，笔数一样，止损目标同一套，抽 1,000 次，报我们排在第几分位；
      ② 每笔减去同期标普（SPY，含分红）的涨幅。

定义（技术面大师卡 skills_v2/xing-ta-master/SKILL.md「一点五」「二、五道闸」「三、计划表」「六、定义」；卡里按 4 小时 / 1 小时写，
这里按卡里「取不到 4 小时、1 小时线时」那一节整体换成日线来做 —— 个股 2005–2014 和 ETF 1993–2014 都没有小时线，两段要用同一把尺子）：
  大方向（回踩套）：卡里的「日线上涨」= 收盘 > 20 日线 > 50 日线、20 日线比 3 天前高。★ 回踩到 0.5 以下时收盘几乎都会落到 20 日线下面，
                   照字面要求「进场那天也是上涨」就几乎没有单子。所以 ★ 取「这一段上涨的高点那天是日线上涨」+「进场那天 50 日线比 5 天前高」（另试 10、20 天）；
                   照字面那版也跑了，单列。
  大方向（V 套）：《465》第 2 条转涨触发（跌幅门槛 8%，照《491》的认法）之后 60 个交易日内，且没跌破这一轮 V 的最低点。
  这一段上涨：起点 = 最近一个确认过的摆动低点（左右各 5 根，卡「先算再说」第 2 步），终点 = 起点之后到昨天的最高价。V 套的起点固定是 V 的最低点。
  等待区：卡里原文。强弱三项（回踩用时 ≤ 上涨用时、回踩缩量、回踩期间收盘守住 20 日线）三项 = 从 0.382 起等，两项 = 0.5，一项或没有 = 0.618；
          最低价碰到起等那一档就算进区；回踩期间最低价跌破 0.786 = 这一段作废。BTC、ETH 至少从 0.5 起（卡里分票默认值）。
  扳机：卡里原文，等待区里出现 ① 长下影收回（下影 ≥ 实体 2 倍、收在这根 K 线上半截）或 ② 看涨吞没（阳线实体包住前一根阴线实体），那根收盘进。
  硬止损：扳机那根最低价 − 0.5 × ATR（卡里原文；另试 0.35、0.65）。
  第一目标：这一段的高点（卡：顺势回踩的第一目标就是前高）。第二目标：★ 上方最近一个确认过的摆动高点；没有就用「回踩低点 + 这一段的长度」（卡里依据第 2 条，1 倍等距）。
  盈亏比够：卡里闸③ 两道都要过 —— 到第一目标 ≥ 1.3 倍风险；一半在第一目标、一半在第二目标加权 ≥ 2 倍风险。
  出场：到第一目标平 50%（BTC 65%、ETH 50%，卡里分票默认值），剩下的止损移到成本；到第二目标全平；★ 最多拿 60 个交易日（另试 40、120）收盘走。
        同一根里既碰止损又碰目标，按先碰止损算（对我们不利的方向）。跳空越过止损按开盘价。单边成本 0.05%。
  一个结构只打一枪（闸④）：同一段上涨只进一次。同一只票同时只拿一笔。闸⑤「只做前两次回踩」和闸①（只管区间打法）没加。
逐个加：第 1 步只要大方向（空仓就进，止损同一套，第一目标取这一段高点，已经在高点上就用 1.5 倍风险）；第 2 步 + 等待区（进区那根收盘进）；第 3 步 + 扳机；第 4 步 + 盈亏比。
品种：QQQ 1999–2021、SPY 1993–2021、SOXX 2001–2021；研发池个股（流动性池中档的日子才进场）2005–2014、2015–2021；BTC、ETH 2017-01 ~ 2026-11（币不封）另报。
美股 2022 年以后的行情在取数时就切掉了（取数_1128.py）。"""
import os, sys, json, importlib.util, time
import numpy as np, pandas as pd
from numba import njit
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
CACHE = os.environ.get("XING_CACHE", "/tmp/w")
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
封 = pd.Timestamp("2021-12-31"); FEE = 0.0005


@njit(cache=True)
def 指标(h, l, c, v):
    n = len(c); atr = np.full(n, np.nan); tr = np.empty(n)
    for i in range(n):
        pc = c[i - 1] if i > 0 else c[i]
        tr[i] = max(h[i] - l[i], abs(h[i] - pc), abs(l[i] - pc))
    for i in range(13, n): atr[i] = tr[i - 13:i + 1].mean()
    ma20 = np.full(n, np.nan); ma50 = np.full(n, np.nan)
    for i in range(19, n): ma20[i] = c[i - 19:i + 1].mean()
    for i in range(49, n): ma50[i] = c[i - 49:i + 1].mean()
    e20 = np.empty(n); e20[0] = c[0]; a = 2.0 / 21
    for i in range(1, n): e20[i] = a * c[i] + (1 - a) * e20[i - 1]
    return atr, ma20, ma50, e20


@njit(cache=True)
def 之字(h, l, atr, 倍):
    n = len(h); zp = np.empty(n, np.int64); zv = np.empty(n); zk = np.empty(n, np.int64); zc = np.empty(n, np.int64); m = 0
    d = 0; eh = 0; el = 0
    for i in range(1, n):
        if h[i] > h[eh]: eh = i
        if l[i] < l[el]: el = i
        a = atr[i] if not np.isnan(atr[i]) else 1e18
        if d >= 0 and h[eh] - l[i] >= 倍 * a and eh < i:
            zp[m] = eh; zv[m] = h[eh]; zk[m] = 1; zc[m] = i; m += 1; d = -1; el = i
        elif d <= 0 and h[i] - l[el] >= 倍 * a and el < i:
            zp[m] = el; zv[m] = l[el]; zk[m] = 0; zc[m] = i; m += 1; d = 1; eh = i
    return zp[:m], zv[:m], zk[:m], zc[:m]


@njit(cache=True)
def V事件(h, l, c, atr, e20):
    """照《491》V形阶梯_1127.py 的「事件」（门槛 8%）逐行搬过来，只是换成 numba。返回每个事件的 (触发 t, 最低点 j0)。"""
    n = len(c); zp, zv, zk, zc = 之字(h, l, atr, 3.0)
    sh = np.zeros(n, np.bool_)
    for j in range(5, n - 5):
        if h[j] == h[j - 5:j + 6].max(): sh[j] = True
    T = np.empty(n, np.int64); J = np.empty(n, np.int64); m = 0; done = np.zeros(n, np.bool_); zi = 0
    for i in range(185, n):
        while zi < len(zc) and zc[zi] <= i: zi += 1
        pk = i - 180 + np.argmax(h[i - 180:i + 1]); j0 = pk + np.argmin(l[pk:i + 1]); L = l[j0]
        if done[j0] or j0 >= i: continue
        H = -1.0; Hp = -1
        for q in range(zi - 1, -1, -1):
            if zk[q] != 1 or zp[q] >= j0 or j0 - zp[q] > 90: continue
            p = zv[q]; dd = p - L
            if dd / p < 0.08: continue
            lo = 1e18; mx = 0.0
            for k in range(zp[q], j0 + 1):
                lo = min(lo, l[k]); mx = max(mx, h[k] - lo)
            if mx > 0.5 * dd: continue
            H = p; Hp = zp[q]; break
        if Hp < 0: continue
        lh = H
        for j in range(j0 - 1, Hp, -1):
            if sh[j] and j + 5 <= i:
                lh = h[j]; break
        ok1 = (c[i] > lh and c[i] > L + 0.5 * (H - L)) or c[i] > L + 0.618 * (H - L)
        ok0 = (c[i - 1] > lh and c[i - 1] > L + 0.5 * (H - L)) or c[i - 1] > L + 0.618 * (H - L)
        if ok1 and ok0 and e20[i] > e20[i - 3]:
            T[m] = i; J[m] = j0; m += 1; done[j0] = True
    return T[:m], J[:m]


@njit(cache=True)
def 逐根(o, h, l, c, v, 可进, 套, Vt, Vj, 起等下限, 斜率天, 照字面):
    """每一根 K 线算：大方向 / 等待区 / 扳机 / 盈亏比 四个标记，以及这一段的起点、高点、第一第二目标（-1 / nan = 没有）。"""
    n = len(c); atr, ma20, ma50, e20 = 指标(h, l, c, v)
    dir_ = np.zeros(n, np.bool_); zone = np.zeros(n, np.bool_); trig = np.zeros(n, np.bool_)
    Li = np.full(n, -1, np.int64); Hi = np.full(n, -1, np.int64); Pl = np.full(n, np.nan); T2 = np.full(n, np.nan)
    up = np.zeros(n, np.bool_)
    for i in range(53, n):
        up[i] = c[i] > ma20[i] and ma20[i] > ma50[i] and ma20[i] > ma20[i - 3]
    sl = np.zeros(n, np.bool_); shh = np.zeros(n, np.bool_)
    for j in range(5, n - 5):
        if l[j] == l[j - 5:j + 6].min(): sl[j] = True
        if h[j] == h[j - 5:j + 6].max(): shh[j] = True
    lastL = -1; vk = 0; curV = -1; curJ = -1
    for i in range(60, n):
        if i - 5 >= 0 and sl[i - 5]: lastL = i - 5
        if 套 == 1:
            while vk < len(Vt) and Vt[vk] < i:
                curV = Vt[vk]; curJ = Vj[vk]; vk += 1
            if curV < 0 or i - curV > 60: continue
            L0 = curJ
            broke = False
            for k in range(L0, i + 1):
                if l[k] < l[L0]: broke = True; break
            if broke: continue
        else:
            L0 = lastL
            if L0 < 0: continue
        # 这一段的高点：起点之后到昨天
        Hx = -1; hv = -1.0
        for k in range(L0 + 1, i):
            if h[k] > hv: hv = h[k]; Hx = k
        if Hx < 0: continue
        Li[i] = L0; Hi[i] = Hx
        if 套 == 1: d = True
        elif 照字面: d = up[i]
        else: d = up[Hx] and ma50[i] > ma50[i - 斜率天]
        dir_[i] = d
        leg = hv - l[L0]
        if leg <= 0 or i <= Hx: continue
        # 强弱三项
        t_up = Hx - L0; t_dn = i - Hx
        vu = v[L0 + 1:Hx + 1].mean(); vd = v[Hx + 1:i + 1].mean()
        hold = True; mn = 1e18
        for k in range(Hx + 1, i + 1):
            if c[k] < ma20[k]: hold = False
            mn = min(mn, l[k])
        sc = (t_dn <= t_up) + (vd < vu) + hold
        st = 0.382 if sc == 3 else (0.5 if sc == 2 else 0.618)
        st = max(st, 起等下限)
        top = hv - st * leg; bot = hv - 0.786 * leg
        Pl[i] = mn
        if mn >= bot and l[i] <= top and c[i] < hv: zone[i] = True
        # 第二目标：上方最近一个确认过的摆动高点（500 根内），没有就 1 倍等距
        t2 = 1e18
        for k in range(max(0, i - 500), i - 4):
            if shh[k] and h[k] > hv and h[k] < t2: t2 = h[k]
        if t2 == 1e18: t2 = mn + leg
        if t2 <= hv: t2 = hv + 0.5 * leg
        T2[i] = t2
        body = abs(c[i] - o[i]); lw = min(o[i], c[i]) - l[i]
        a1 = (h[i] > l[i]) and lw >= 2 * body and c[i] >= (h[i] + l[i]) / 2
        a2 = c[i] > o[i] and o[i - 1] > c[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1]
        trig[i] = a1 or a2
    return dir_, zone, trig, Li, Hi, Pl, T2, atr


@njit(cache=True)
def 一笔(o, h, l, c, i, E, S, T1, T2, 平, 拿, fee):
    """i 那根收盘以 E 进。返回（按风险的 R、%、最后平仓那根、是否期末没走完）。"""
    n = len(c); R = E - S
    left = 1.0; got = 0.0; stop = S; hit1 = False; end = min(i + 拿, n - 1); j = i
    for j in range(i + 1, end + 1):
        if o[j] <= stop:
            got += left * (o[j] - E); left = 0.0; break
        if l[j] <= stop:
            got += left * (stop - E); left = 0.0; break
        if (not hit1) and h[j] >= T1:
            px = max(T1, o[j]); got += 平 * (px - E); left -= 平; hit1 = True; stop = E
            if h[j] >= T2:
                got += left * (max(T2, o[j]) - E); left = 0.0; break
            continue
        if hit1 and h[j] >= T2:
            got += left * (max(T2, o[j]) - E); left = 0.0; break
    open_end = False
    if left > 0:
        got += left * (c[j] - E)
        open_end = (j == n - 1) and (end == n - 1) and (i + 拿 > n - 1)
    pct = got / E - 2 * fee
    return pct * E / R, pct, j, open_end


@njit(cache=True)
def 全部候选(o, h, l, c, dir_, zone, trig, Li, Hi, Pl, T2, atr, 可进, 起, 止, 缓冲, 平, 拿, fee):
    """对每一根能进场的 K 线（大方向成立）都假设在那根收盘进一笔，算结果；这样随机对照直接从里面抽。"""
    n = len(c); out = np.full((n, 9), np.nan)
    for i in range(起, 止 + 1):
        if not (dir_[i] and 可进[i]) or np.isnan(atr[i]): continue
        E = c[i]; S = l[i] - 缓冲 * atr[i]; R = E - S
        if R <= 0: continue
        hv = h[Hi[i]]
        if zone[i] or hv > E + 0.25 * atr[i]:
            T1 = hv; t2 = T2[i] if not np.isnan(T2[i]) else hv + (hv - E)
        else:
            T1 = E + 1.5 * R; t2 = E + 3 * R
        if T1 <= E: T1 = E + 1.5 * R; t2 = E + 3 * R
        rr = (T1 - E) >= 1.3 * R and (0.5 * (T1 - E) + 0.5 * (t2 - E)) >= 2.0 * R
        r, p, j, oe = 一笔(o, h, l, c, i, E, S, T1, t2, 平, 拿, fee)
        out[i, 0] = r; out[i, 1] = p; out[i, 2] = j; out[i, 3] = zone[i]; out[i, 4] = trig[i]; out[i, 5] = rr; out[i, 6] = Li[i] * 100000.0 + Hi[i]; out[i, 7] = oe; out[i, 8] = R / E
    return out


def 跑一只(D, 套, 可进, 起日, 止日, 起等下限=0.0, 斜率天=5, 照字面=False, 缓冲=0.5, 平=0.5, 拿=60):
    D = D.dropna(subset=["open", "high", "low", "close"])
    if len(D) < 120: return None
    o, h, l, c = (D[x].to_numpy(np.float64) for x in ("open", "high", "low", "close"))
    v = D["volume"].fillna(0).to_numpy(np.float64) if "volume" in D else np.ones(len(c))
    atr0, _, _, e20 = 指标(h, l, c, v)
    Vt, Vj = V事件(h, l, c, atr0, e20) if 套 == 1 else (np.zeros(0, np.int64), np.zeros(0, np.int64))
    dir_, zone, trig, Li, Hi, Pl, T2, atr = 逐根(o, h, l, c, v, None, 套, Vt, Vj, 起等下限, 斜率天, 照字面)
    k = 可进.reindex(D.index).fillna(False).to_numpy(bool) if 可进 is not None else np.ones(len(c), bool)
    a = int(np.searchsorted(D.index.values, np.datetime64(起日))); b = int(np.searchsorted(D.index.values, np.datetime64(止日), side="right")) - 1
    if b <= a: return None
    out = 全部候选(o, h, l, c, dir_, zone, trig, Li, Hi, Pl, T2, atr, k, a, b, 缓冲, 平, 拿, FEE)
    ii = np.where(~np.isnan(out[:, 0]))[0]
    if not len(ii): return None
    X = pd.DataFrame(out[ii], columns=["R", "pct", "出", "区", "扳", "比", "段号", "期末没走完", "风险占价"]); X["进"] = ii
    X["进日"] = D.index[ii]; X["出日"] = D.index[X["出"].astype(int).to_numpy()]
    return X


def 挑(X, 步):
    """第 1~4 步：按条件筛出能进的根，再按「同一只同时一笔、同一段只进一次（第 2 步起）」从前往后挑。"""
    m = np.ones(len(X), bool)
    if 步 >= 2: m &= X["区"].to_numpy() > 0
    if 步 >= 3: m &= X["扳"].to_numpy() > 0
    if 步 >= 4: m &= X["比"].to_numpy() > 0
    Y = X[m]; keep = []; busy = -1; used = set()
    for r in Y.itertuples():
        if r.进 <= busy: continue
        if 步 >= 2 and r.段号 in used: continue
        keep.append(r.Index); busy = int(r.出); used.add(r.段号)
    return X.loc[keep]


def 加大盘(X, spy):
    a = spy.reindex(X["进日"]).to_numpy(); b = spy.reindex(X["出日"]).to_numpy()
    X = X.copy(); X["标普pct"] = b / a - 1; X["扣标普pct"] = X["pct"] - X["标普pct"]; return X


def 最深(X):
    """按平仓日排好，每笔都按同样的风险（1R）记，累计 R 从最高处往下最多掉过几 R。"""
    if not len(X): return np.nan
    r = X.sort_values("出日")["R"].to_numpy(); cum = np.concatenate([[0], np.cumsum(r)])
    return float((np.maximum.accumulate(cum) - cum).max())


def 概(X):
    if not len(X): return dict(笔数=0)
    d = dict(笔数=int(len(X)), 每笔R=round(float(X.R.mean()), 3), 每笔pct=round(float(X.pct.mean()) * 100, 2), 赚钱笔占比pct=round(float((X.R > 0).mean()) * 100, 1),
             最差一笔R=round(float(X.R.min()), 2), 最差一笔pct=round(float(X.pct.min()) * 100, 1), 累计最深亏R=round(最深(X), 1),
             扣标普每笔pct=round(float(X["扣标普pct"].mean()) * 100, 2) if "扣标普pct" in X and X["扣标普pct"].notna().any() else None,
             持仓天中位=int((X["出"] - X["进"]).median()), 期末没走完=int(X["期末没走完"].sum()))
    y = X.groupby(X["进日"].dt.year)["R"].agg(["mean", "size"]); y = y[y["size"] >= 5]
    if len(y): d["最差一年每笔R"] = round(float(y["mean"].min()), 3); d["最差一年"] = int(y["mean"].idxmin()); d["每笔R为正的年份"] = f"{int((y['mean'] > 0).sum())}/{len(y)}"
    if len(X) < 30: d["备注"] = "样本不够，下不了结论"
    return d


def 随机(池, N, 我们, reps=1000, seed=1128):
    if N == 0 or len(池) < N: return dict(池子根数=int(len(池)), 说明="池子不够抽")
    rng = np.random.default_rng(seed); R = 池.R.to_numpy(); P = 池.pct.to_numpy(); Ex = 池["扣标普pct"].to_numpy() if "扣标普pct" in 池 else None
    mr = np.empty(reps); mp = np.empty(reps); me = np.empty(reps)
    for k in range(reps):
        ix = rng.choice(len(池), N, replace=False); mr[k] = R[ix].mean(); mp[k] = P[ix].mean(); me[k] = np.nanmean(Ex[ix]) if Ex is not None else np.nan
    d = dict(池子根数=int(len(池)), 随机每笔R_中位=round(float(np.median(mr)), 3), 随机每笔R_95分位=round(float(np.quantile(mr, 0.95)), 3),
             我们每笔R排在第几分位=round(float((mr < 我们.R.mean()).mean()) * 100, 1),
             随机每笔pct_中位=round(float(np.median(mp)) * 100, 2), 我们每笔pct排在第几分位=round(float((mp < 我们.pct.mean()).mean()) * 100, 1))
    if Ex is not None and "扣标普pct" in 我们:
        d["随机扣标普每笔pct_中位"] = round(float(np.nanmedian(me)) * 100, 2); d["我们扣标普排在第几分位"] = round(float((me < 我们["扣标普pct"].mean()).mean()) * 100, 1)
    return d


def 报一组(X全, 名, 段们, 拿结果=None):
    """X全 = 一组品种的全部候选根（带「品种」「段」列）。四步逐个加；第 4 步配两种随机对照。"""
    res = []
    for 段名, m in 段们:
        X = X全[m(X全)]
        if not len(X): continue
        rows = {}
        for 步 in (1, 2, 3, 4):
            Y = pd.concat([挑(g, 步) for _, g in X.groupby("品种")]) if len(X) else X
            rows[步] = Y; res.append(dict(组=名, 段=段名, 步=步, **概(Y)))
        Y4 = rows[4]
        ra = 随机(X[X["区"] > 0], len(Y4), Y4); rb = 随机(X[(X["区"] > 0) & (X["比"] > 0)], len(Y4), Y4)
        res[-1]["随机A_大方向加等待区"] = ra; res[-1]["随机B_再加盈亏比够"] = rb
        if 拿结果 is not None: 拿结果[(名, 段名)] = rows
    return res
