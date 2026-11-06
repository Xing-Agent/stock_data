# -*- coding: utf-8 -*-
"""
★★★ 环境卡 12 张(9 整 + 3 半)· 算法 + 分辨力实测（B 路 1106）

大白话:环境卡**不是策略**,不测「赚不赚钱」;测的是 ——
  **它把单子切成几档之后,各档的成绩是不是真的不一样。**
  切不开 = 这张卡对交易决策没用(展示可以,不能进决策)。

★ 每张卡的定义一律**照卡里的原文**(METHOD_LIBRARY/状-N.md「怎么判定 / 参数」两行),
  原文没给的数、或我们改了的地方,在 卡定义 里逐张写明档位:
  ①原著 / ②行业通行 / ③我们的 / ⑤外部模型说的·待核。
★★ 时点纪律:单子在 T 日开盘买 → 信号是 T−1 日收盘 → **环境一律取 T−1 日收盘能算出来的值**。
   摆动点用「确认时点」,不用「发生时点」(否则偷看未来)。

★ 判据(★★ 不用赢随机):大盘替身**修正口径 C**(不扔当天单、时点对齐 —— 见 probe/挂件_1106/替身口径复核_1106.py)。
  每张卡事先登记一组「主对比」(A 档 vs B 档),双侧检验:
  · 差值的标准误按**进场日聚类**(同一天的几笔不独立)
  · 另做**按月块重抽样**的 95% 区间
  · ★★★ 两种都过才算「分得开」;只过一种 = 不算数
  · 多重检验:N 张卡 × 4 个宿主 → 运气约给 0.05×N 个「显著」,报告里对账

宿主流水:probe/挂件_1106/arms_1106 里四个宿主的「不装」那条(同一引擎、新池研发池)。
engine 零改动;只读面板。
"""
from __future__ import annotations
import glob, gzip, io, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as T                                            # noqa: E402

OUT = os.path.join(HERE, "环境卡结果_1106.json")
ETF = os.path.join(ROOT, "market_etf_1106")
SECT = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]

卡定义 = {
    "状-1 道氏高低点排列": "ZigZag 阈值 3×ATR(14)①卡原文默认;摆动点用收盘③(卡说影线/收盘二选一未定);"
                     "最近两组高低点:都抬高=上涨,都降低=下跌,其余=震荡①",
    "状-2 温斯坦四阶段": "150 日线(=30 周)①;斜率=近 50 日(10 周)每周变化,|斜率|<0.5%/周=走平①;"
                    "持续≥20 日(4 周)①;阶段1/3 用前一个非走平阶段区分③;"
                    "「前序阶段符合循环顺序」这一条未实现(只用前一阶段)③",
    "状-3 冲量与修正(半)": "近 20 根:实体占比 0.6/0.4、重叠度 0.4/0.6 ①卡原文(卡注明是 XING 所设);"
                      "同色连续性阈值卡没给数 → 0.6/0.4 ③;微型通道≥4 根①。"
                      "★ 半张:Al Brooks 原著靠人眼读 K 线,这里只是卡上的可算近似",
    "状-4 威科夫区间结构(半)": "区间来自状-8;事件只做两类:下刺收回(Spring:最低破下界、收盘收回界内)、"
                         "上冲回落(Upthrust)①卡原文;★ 低点抬高/触及未破/缩量测试**没做**;"
                         "★ 吸筹/派发这种性质判断**不做**(卡自己也写「不输出区间性质结论」)",
    "状-5 相对强度": "SPY 从阶段高点回撤≥5% 的窗口①;回看 24 个月(504 日)①;该股同窗口:跌幅<SPY 的 1/3 或收涨=抗跌,"
                 ">1.5 倍=更弱,其余=同步①;按多数票定档、窗口<2 个=样本不足③;"
                 "★ 行业 ETF 那一路基准和「率先创新高」那一条没做",
    "状-7 跳空缺口": "Low[t]>High[t−1] 或 High[t]<Low[t−1],且|Open−前收|≥0.5×ATR(14)①;"
                 "只做信号日当天有没有缺口③(真空区注销与缺口分类没做)",
    "状-8 区间年龄与假突破": "摆动点折返≥0.5×ATR①;|P3−P1|≤1ATR 且|P4−P2|≤1ATR 成立①;"
                      "界外收盘超出 1ATR 连续 5 根=区间终结①;越界后≤3 根收回=假突破+1①;"
                      "年龄从 P1 起算①;边界扩增没做③",
    "状-9 相对成交量": "RVOL=量/20 日均量①;≥2.5 极值、≤0.5 干燥①(卡注明经验值待校准)",
    "状-10 可交易性": "20 日平均美元成交额<1000 万=不合格①;点差那一半没有数据",
    "状-11 板块趋势一致性": "★ 绕法③:每只票的行业 = 过去 252 日和它相关性最高的那只行业 ETF(每月重算,只用过去数据);"
                      "一致性 = 研发池里同一行业的票,处于温斯坦阶段二的比例(卡原文是该行业前 10 大权重股 —— 没有成分权重数据)",
    "状-12 空间位置": "★ 替代口径③(工单指定):在 52 周(252 日)高低点之间的相对位置 0~1;"
                  "中轴带 = 0.5±0.15①卡原文宽度;卡原文的上下界来自状-6 共振价位 —— 没用",
    "状-6 共振计数(半)": "支撑侧:收盘下方 3ATR 内的候选价位,数 ±0.5ATR 内有几类来源①:"
                     "前高前低(3ATR 摆动点)、均线 20/50/150/200、整数关口、最近一段摆动的斐波那契 0.382/0.5/0.618①;"
                     "★ 成交密集区(要分时数据)和背离来源**没做**,所以满分是 4 类不是 6 类",
}

# ★★★ 事先登记的主对比(★ 跑之前写死;双侧检验,不预言方向)
主对比 = {
    "状-1 道氏高低点排列": ("上涨", "下跌"),
    "状-2 温斯坦四阶段": ("阶段2", "阶段4"),
    "状-3 冲量与修正(半)": ("趋势", "震荡"),
    "状-4 威科夫区间结构(半)": ("近10日有下刺收回", "区间内无事件"),
    "状-5 相对强度": ("抗跌", "更弱"),
    "状-7 跳空缺口": ("向上缺口", "无缺口"),
    "状-8 区间年龄与假突破": ("在区间内", "不在区间"),
    "状-9 相对成交量": ("极值放量", "正常"),
    "状-10 可交易性": ("不合格", "可交易"),
    "状-11 板块趋势一致性": ("高(≥0.5)", "低(<0.25)"),
    "状-12 空间位置": ("上三分之一", "下三分之一"),
    "状-6 共振计数(半)": ("强支撑(≥3类)", "弱支撑(≤1类)"),
}


# ═══════════════════════════ 基础零件 ═══════════════════════════
def atr(h, l, c, n=14):
    pc = np.r_[np.nan, c[:-1]]
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def zigzag(c, a, k):
    """★ 收盘价 ZigZag,阈值 k×ATR。返回 [(发生位, 价, 确认位, 'H'/'L')]。★ 确认位 = 反向走出阈值那一根。"""
    piv = []
    n = len(c)
    i0 = 0
    while i0 < n and not (np.isfinite(c[i0]) and np.isfinite(a[i0])):
        i0 += 1
    if i0 >= n:
        return piv
    dir_ = 0; ext_i = i0; ext = c[i0]
    for i in range(i0 + 1, n):
        x, th = c[i], k * a[i]
        if not (np.isfinite(x) and np.isfinite(th)):
            continue
        if dir_ >= 0:
            if x > ext:
                ext, ext_i = x, i
                if dir_ == 0:
                    dir_ = 1
            elif ext - x >= th:
                piv.append((ext_i, ext, i, "H")); dir_ = -1; ext, ext_i = x, i
        if dir_ < 0:
            if x < ext:
                ext, ext_i = x, i
            elif x - ext >= th:
                piv.append((ext_i, ext, i, "L")); dir_ = 1; ext, ext_i = x, i
    return piv


def 道氏(c, a, n):
    piv = zigzag(c, a, 3.0)
    out = np.array([None] * n, dtype=object)
    H, L = [], []
    pi = 0
    for t in range(n):
        while pi < len(piv) and piv[pi][2] <= t:
            (H if piv[pi][3] == "H" else L).append(piv[pi][1]); pi += 1
        if len(H) >= 2 and len(L) >= 2:
            if H[-1] > H[-2] and L[-1] > L[-2]:
                out[t] = "上涨"
            elif H[-1] < H[-2] and L[-1] < L[-2]:
                out[t] = "下跌"
            else:
                out[t] = "震荡"
    return out, piv


def 温斯坦(c):
    s = pd.Series(c)
    ma = s.rolling(150, min_periods=150).mean()
    slope = (ma / ma.shift(50) - 1.0) / 10.0 * 100      # %/周
    raw = np.array([None] * len(c), dtype=object)
    prev = None
    ma_, sl_ = ma.to_numpy(), slope.to_numpy()
    for t in range(len(c)):
        m, sl, x = ma_[t], sl_[t], c[t]
        if not (np.isfinite(m) and np.isfinite(sl) and np.isfinite(x)):
            continue
        if abs(sl) < 0.5:
            lab = "阶段3" if prev == "阶段2" else ("阶段1" if prev == "阶段4" else "走平未定")
        elif x > m and sl > 0:
            lab = "阶段2"
        elif x < m and sl < 0:
            lab = "阶段4"
        else:
            lab = "过渡"
        if lab in ("阶段2", "阶段4"):
            prev = lab
        raw[t] = lab
    # ★ 持续 ≥ 20 日才给编号
    out = np.array([None] * len(c), dtype=object)
    run = 0
    for t in range(len(c)):
        run = run + 1 if (t > 0 and raw[t] == raw[t - 1] and raw[t] is not None) else 1
        if raw[t] is None:
            continue
        out[t] = raw[t] if (run >= 20 and raw[t] in ("阶段1", "阶段2", "阶段3", "阶段4")) else "过渡/未满4周"
    return out


def 冲量(o, h, l, c):
    rng = np.where(h - l > 0, h - l, np.nan)
    body = pd.Series(np.abs(c - o) / rng).rolling(20, min_periods=15).mean().to_numpy()
    ph, pl = np.r_[np.nan, h[:-1]], np.r_[np.nan, l[:-1]]
    ov = np.maximum(0, np.minimum(h, ph) - np.maximum(l, pl)) / (np.maximum(h, ph) - np.minimum(l, pl))
    ovm = pd.Series(ov).rolling(20, min_periods=15).mean().to_numpy()
    col = np.sign(c - o); same = (col == np.r_[np.nan, col[:-1]]) & (col != 0)
    con = pd.Series(same.astype(float)).rolling(20, min_periods=15).mean().to_numpy()
    tr = (body > 0.6) & (ovm < 0.4) & (con > 0.6)
    rg = (body < 0.4) & (ovm > 0.6) & (con < 0.4)
    out = np.where(np.isnan(body) | np.isnan(ovm), None, np.where(tr, "趋势", np.where(rg, "震荡", "混合")))
    return out, body, ovm, con


def 区间(c, h, l, a):
    """★ 状-8 + 状-4(半)。返回每日:在不在区间、年龄、假突破计数、近10日下刺收回/上冲回落。"""
    n = len(c)
    piv = zigzag(c, a, 0.5)
    inr = np.zeros(n, bool); age = np.full(n, np.nan); fb = np.full(n, np.nan)
    spring = np.zeros(n, bool); upth = np.zeros(n, bool)
    cur = None    # dict(up, lo, start, fb, out_run, pending_out)
    pi = 0; P = []
    for t in range(n):
        while pi < len(piv) and piv[pi][2] <= t:
            P.append(piv[pi]); pi += 1
            if cur is None and len(P) >= 4 and np.isfinite(a[t]):
                p1, p2, p3, p4 = P[-4:]
                if abs(p3[1] - p1[1]) <= a[t] and abs(p4[1] - p2[1]) <= a[t]:
                    hs = [p[1] for p in (p1, p2, p3, p4) if p[3] == "H"]
                    ls = [p[1] for p in (p1, p2, p3, p4) if p[3] == "L"]
                    if hs and ls and max(hs) > min(ls):
                        cur = {"up": max(hs), "lo": min(ls), "start": p1[0], "fb": 0, "out": 0, "outside_since": None}
        if cur is None or not np.isfinite(c[t]) or not np.isfinite(a[t]):
            continue
        up, lo = cur["up"], cur["lo"]
        # 事件(状-4 半):当天刺破又收回
        if np.isfinite(l[t]) and l[t] < lo and c[t] >= lo:
            spring[t] = True
        if np.isfinite(h[t]) and h[t] > up and c[t] <= up:
            upth[t] = True
        outside = c[t] > up or c[t] < lo
        far = c[t] > up + a[t] or c[t] < lo - a[t]
        if outside:
            if cur["outside_since"] is None:
                cur["outside_since"] = t
        else:
            if cur["outside_since"] is not None and t - cur["outside_since"] <= 3:
                cur["fb"] += 1
            cur["outside_since"] = None
        cur["out"] = cur["out"] + 1 if far else 0
        if cur["out"] >= 5:
            cur = None; P = P[-1:]
            continue
        inr[t] = True; age[t] = t - cur["start"]; fb[t] = cur["fb"]
    sp10 = pd.Series(spring.astype(float)).rolling(10, min_periods=1).sum().to_numpy() > 0
    return inr, age, fb, sp10, upth, piv


def 共振支撑(c, a, piv3, t, ma_vals):
    """★ 状-6 半:收盘下方 3ATR 内,数 ±0.5ATR 内有几类来源。"""
    x, at = c[t], a[t]
    if not (np.isfinite(x) and np.isfinite(at)) or at <= 0:
        return np.nan
    cands = {"前高前低": [p[1] for p in piv3 if p[2] <= t][-10:],
             "均线": [v for v in ma_vals if np.isfinite(v)]}
    step = 10 ** np.floor(np.log10(x)) / 2 if x > 0 else 1
    cands["整数关口"] = [np.floor(x / step) * step, np.floor(x / step) * step - step]
    pp = [p for p in piv3 if p[2] <= t][-2:]
    if len(pp) == 2:
        hi, lo_ = max(pp[0][1], pp[1][1]), min(pp[0][1], pp[1][1])
        cands["斐波那契"] = [hi - r * (hi - lo_) for r in (0.382, 0.5, 0.618)]
    lv = [v for vs in cands.values() for v in vs if x - 3 * at <= v <= x]
    best = 0
    for v in lv:
        k = sum(1 for vs in cands.values() if any(abs(u - v) <= 0.5 * at for u in vs))
        best = max(best, k)
    return best


def 相对强度档(c, eps, t):
    done = [e for e in eps if e[2] <= t and e[0] >= t - 504]
    k = {"抗跌": 0, "同步": 0, "更弱": 0}
    for p0, p1, _, D in done:
        if not (np.isfinite(c[p0]) and np.isfinite(c[p1]) and c[p0] > 0):
            continue
        r = c[p1] / c[p0] - 1
        k["抗跌" if (r > 0 or r > D / 3) else ("更弱" if r < 1.5 * D else "同步")] += 1
    return max(k, key=k.get) if sum(k.values()) >= 2 else "样本不足"


def etf收盘(sym):
    raw = json.load(gzip.open(os.path.join(ETF, sym, "daily.json.gz"), "rt"))
    df = pd.DataFrame(raw["data"]); df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    c = df["close"].astype(float)
    sc = df["split_coefficient"].astype(float).replace(0, 1).fillna(1)
    adj = sc[::-1].cumprod()[::-1].shift(-1).fillna(1)        # ★ 之后发生的拆股累计
    return c / adj


# ═══════════════════════════ 主流程 ═══════════════════════════
def 宿主流水():
    """★ 读挂件跑批里四个宿主的「不装」流水(按 label 找臂文件)。"""
    out = {}
    for 名 in ("技-1·唐奇安突破", "技-8·高紧旗形", "技-14-XING·布林触下轨", "技-12·康纳斯RSI2"):
        p = T.臂文件(os.path.join(ROOT, "probe", "挂件_1106", "arms_1106"), f"{名}|不装")
        if os.path.exists(p):
            out[名] = pd.read_csv(p)
    return out


def 算所有卡(syms, panel, idx):
    """★ 返回 {卡: DataFrame[日×票] 档位}。只算流水里出现的票。"""
    res = {k: {} for k in 卡定义}
    extra = {"状-8 年龄": {}, "状-8 假突破": {}, "状-12 位置": {}, "状-9 RVOL": {}}
    spy = T.data.load_benchmark("SPY")["close"].reindex(idx).ffill().to_numpy()
    # 状-5:SPY 回撤 ≥5% 的窗口(高点→低点),完成时点 = 回到新高那天
    eps = []
    pk_i, pk = 0, spy[0]; tr_i, tr = 0, spy[0]; inep = False
    for t in range(len(spy)):
        x = spy[t]
        if not np.isfinite(x):
            continue
        if x >= pk:
            if inep:
                eps.append((pk_i, tr_i, t, tr / pk - 1)); inep = False
            pk, pk_i, tr, tr_i = x, t, x, t
        else:
            if x < tr:
                tr, tr_i = x, t
            if tr / pk - 1 <= -0.05:
                inep = True
    ws = {}
    for s in syms:
        o, h, l, c, v = (panel[f][s].to_numpy(float) for f in ("open", "high", "low", "close", "volume"))
        a = atr(h, l, c)
        res["状-1 道氏高低点排列"][s], piv3 = 道氏(c, a, len(c))
        ws[s] = 温斯坦(c); res["状-2 温斯坦四阶段"][s] = ws[s]
        res["状-3 冲量与修正(半)"][s] = 冲量(o, h, l, c)[0]
        inr, age, fb, sp10, upth, _ = 区间(c, h, l, a)
        res["状-8 区间年龄与假突破"][s] = np.where(np.isfinite(c), np.where(inr, "在区间内", "不在区间"), None)
        extra["状-8 年龄"][s] = age; extra["状-8 假突破"][s] = fb
        res["状-4 威科夫区间结构(半)"][s] = np.where(~inr, "不在区间", np.where(sp10, "近10日有下刺收回", "区间内无事件"))
        # 状-5:★ 按需算(只在信号日算),先存零件
        res["状-5 相对强度"][s] = (c, eps)
        pc = np.r_[np.nan, c[:-1]]; ph = np.r_[np.nan, h[:-1]]; pl = np.r_[np.nan, l[:-1]]
        big = np.abs(o - pc) >= 0.5 * a
        res["状-7 跳空缺口"][s] = np.where(~np.isfinite(a), None,
                                     np.where((l > ph) & big, "向上缺口", np.where((h < pl) & big, "向下缺口", "无缺口")))
        rv = v / pd.Series(v).rolling(20, min_periods=20).mean().to_numpy()
        extra["状-9 RVOL"][s] = rv
        res["状-9 相对成交量"][s] = np.where(~np.isfinite(rv), None,
                                      np.where(rv >= 2.5, "极值放量", np.where(rv <= 0.5, "干燥", "正常")))
        adv = pd.Series(c * v).rolling(20, min_periods=20).mean().to_numpy()
        res["状-10 可交易性"][s] = np.where(~np.isfinite(adv), None, np.where(adv < 1e7, "不合格", "可交易"))
        hi = pd.Series(c).rolling(252, min_periods=252).max().to_numpy()
        lo = pd.Series(c).rolling(252, min_periods=252).min().to_numpy()
        pos = (c - lo) / np.where(hi - lo > 0, hi - lo, np.nan)
        extra["状-12 位置"][s] = pos
        res["状-12 空间位置"][s] = np.where(~np.isfinite(pos), None,
                                      np.where(pos > 2 / 3, "上三分之一", np.where(pos < 1 / 3, "下三分之一", "中间")))
        # 状-6 半:只在流水用到的日子才算(省时间)—— 先存零件
        mas = {n: pd.Series(c).rolling(n, min_periods=n).mean().to_numpy() for n in (20, 50, 150, 200)}
        res["状-6 共振计数(半)"][s] = (c, a, piv3, mas)
    # 状-11:每只票映射到相关性最高的行业 ETF(每月重算,只用过去 252 日)
    E = pd.DataFrame({e: etf收盘(e) for e in SECT}).reindex(idx).ffill()
    er = np.log(E).diff()
    C = panel["close"][syms]
    sr = np.log(C).diff()
    month_ends = pd.Series(idx).groupby(pd.Series(idx).dt.to_period("M")).last()
    映射 = pd.DataFrame(index=idx, columns=syms, dtype=object)
    for me in month_ends:
        t = idx.get_loc(me)
        if t < 252:
            continue
        S = sr.iloc[t - 251:t + 1]; X = er.iloc[t - 251:t + 1]
        ok = X.notna().sum() >= 200
        Xs = (X - X.mean()) / X.std(); Ss = (S - S.mean()) / S.std()
        cor = Ss.fillna(0).T.to_numpy() @ Xs.fillna(0).to_numpy() / 251.0
        cor[:, ~ok.to_numpy()] = -9
        good = S.notna().sum().to_numpy() >= 200
        best = np.array(SECT, dtype=object)[cor.argmax(1)]
        best[~good] = None
        映射.iloc[t + 1:t + 23] = np.tile(best, (min(22, len(idx) - t - 1), 1))
    W = pd.DataFrame(ws, index=idx)
    st2 = (W == "阶段2").astype(float).where(W.notna())
    一致a = np.full((len(idx), len(syms)), np.nan)
    M = 映射.to_numpy(); S2 = st2.to_numpy()
    for t in range(len(idx)):
        row = M[t]
        for e in SECT:
            sel = row == e
            if sel.sum() < 5:
                continue
            vals = S2[t, sel]
            fin = np.isfinite(vals)
            if fin.sum() < 5:
                continue
            tot, k = np.nansum(vals), fin.sum()
            # ★ 排除自己
            own = np.where(np.isfinite(vals), vals, 0)
            一致a[t, sel] = (tot - own) / np.maximum(1, k - fin.astype(int))
    res["状-11 板块趋势一致性"] = pd.DataFrame(一致a, index=idx, columns=syms)
    return res, extra, 映射


def 档位(res, extra, d, idx, 映射):
    """★ 每笔单子取信号日(进场日前一个交易日)的档位。"""
    ei = idx.searchsorted(pd.to_datetime(d["entry_date"]).values)
    si = ei - 1
    out = {}
    for 卡, tab in res.items():
        labs = []
        for s, t in zip(d["symbol"].astype(str), si):
            if t < 0:
                labs.append(None); continue
            if 卡 == "状-11 板块趋势一致性":
                v = tab.at[idx[t], s] if s in tab.columns else np.nan
                labs.append(None if not np.isfinite(v) else ("高(≥0.5)" if v >= 0.5 else ("低(<0.25)" if v < 0.25 else "中")))
            elif 卡 == "状-5 相对强度":
                labs.append(相对强度档(*tab[s], t) if s in tab else None)
            elif 卡 == "状-6 共振计数(半)":
                if s not in tab:
                    labs.append(None); continue
                c, a, piv3, mas = tab[s]
                k = 共振支撑(c, a, piv3, t, [mas[n][t] for n in mas])
                labs.append(None if not np.isfinite(k) else ("强支撑(≥3类)" if k >= 3 else ("弱支撑(≤1类)" if k <= 1 else "中(2类)")))
            else:
                arr = tab.get(s)
                labs.append(None if arr is None else arr[t])
        out[卡] = labs
    return pd.DataFrame(out, index=d.index)


def 对比(y, g, 日, A, B):
    """★ A 档均值 − B 档均值;标准误按进场日聚类(影响函数法);另做按月块重抽样。"""
    m = g.isin([A, B]) & y.notna()
    y, g, 日 = y[m], g[m], 日[m]
    nA, nB = int((g == A).sum()), int((g == B).sum())
    if nA < 30 or nB < 30:
        return {"A笔数": nA, "B笔数": nB, "★判定": "★算不出(某一档<30笔)"}
    mA, mB = y[g == A].mean(), y[g == B].mean()
    e = np.where(g == A, (y - mA) / nA, -(y - mB) / nB)
    S = pd.Series(e, index=y.index).groupby(日.values).sum()
    G = len(S)
    se = float(np.sqrt((S ** 2).sum() * G / (G - 1)))
    diff = mA - mB; t = diff / se if se > 0 else np.nan
    # 月块重抽样
    月 = pd.to_datetime(日.values).to_period("M")
    df = pd.DataFrame({"y": y.values, "a": (g == A).values, "m": 月})
    agg = df.groupby(["m", "a"])["y"].agg(["sum", "count"]).unstack(fill_value=0)
    sa, ca = agg[("sum", True)].to_numpy(), agg[("count", True)].to_numpy()
    sb, cb = agg[("sum", False)].to_numpy(), agg[("count", False)].to_numpy()
    rng = np.random.default_rng(11); nb = len(sa)
    pk = rng.integers(0, nb, size=(2000, nb))
    with np.errstate(invalid="ignore", divide="ignore"):
        bs = sa[pk].sum(1) / ca[pk].sum(1) - sb[pk].sum(1) / cb[pk].sum(1)
    bs = bs[np.isfinite(bs)]
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"A笔数": nA, "B笔数": nB, "A均值pct": round(mA * 100, 4), "B均值pct": round(mB * 100, 4),
            "★差pct(A−B)": round(diff * 100, 4), "聚类标准误pct": round(se * 100, 4), "聚类数": G,
            "t": round(t, 2), "月块95%区间pct": [round(lo * 100, 4), round(hi * 100, 4)],
            "★判定": T.判(t, bool(lo > 0 or hi < 0)).replace("正且显著", "分得开(A 好)").replace(
                "负且显著", "分得开(B 好)").replace("测不出（在噪声里）", "分不开（在噪声里）")}


def main() -> int:
    t0 = time.time()
    T.装覆盖层()
    panel = T.cache._PANEL
    idx = panel["close"].index
    L = 宿主流水()
    if len(L) < 4:
        print(f"⚠⚠⚠ 宿主流水只找到 {len(L)} 条:{list(L)} —— 挂件跑批还没跑完?", flush=True)
    if not L:
        raise SystemExit("★★★ 一条宿主流水都没有,停")
    syms = sorted(set().union(*[set(d["symbol"].astype(str)) for d in L.values()]) & set(panel["close"].columns))
    print(f"★ 要算的票 {len(syms)} 只", flush=True)
    res, extra, 映射 = 算所有卡(syms, panel, idx)
    print(f"★ 环境卡算完 {time.time()-t0:.0f}s", flush=True)
    报 = {"★口径": {"测什么": "分辨力:切出来的档,单子成绩是否真的分得开(不测赚不赚钱)",
                  "判据": "大盘替身修正口径 C(每笔净收益 − 同期 SPY);另报每笔净收益",
                  "检验": "主对比 A−B:进场日聚类 t + 按月块重抽样 95% 区间;两种都过才算分得开",
                  "时点": "环境取信号日(进场前一个交易日)收盘",
                  "engine改动": "零", "宿主": list(L)},
          "★卡定义(逐张标档)": 卡定义, "★事先登记的主对比": {k: f"{a} vs {b}" for k, (a, b) in 主对比.items()}}
    总检验 = 0; 显著 = []
    for 名, led in L.items():
        d = T._键(led).reset_index(drop=True)
        d["x"] = d["ret"] - T.替身收益(d).to_numpy()
        lab = 档位(res, extra, d, idx, 映射)
        日 = d["entry_date"].dt.strftime("%Y-%m-%d")
        h = {"笔数": len(d)}
        for 卡, (A, B) in 主对比.items():
            g = lab[卡]
            dist = g.value_counts(dropna=False).to_dict()
            每档 = d.groupby(g)["x"].agg(["count", "mean"])
            r = 对比(d["x"], g, 日, A, B)
            r2 = 对比(d["ret"], g, 日, A, B)
            h[卡] = {"各档笔数": {str(k): int(v) for k, v in dist.items()},
                    "各档_比大盘均值pct": {str(k): round(float(v) * 100, 4) for k, v in 每档["mean"].items()},
                    "★主对比_比大盘": r, "主对比_每笔净收益": {k: r2.get(k) for k in ("★差pct(A−B)", "t", "★判定")}}
            if "算不出" not in r["★判定"]:
                总检验 += 1
                if "分得开" in r["★判定"]:
                    显著.append(f"{名} · {卡}:{r['★判定']} 差 {r['★差pct(A−B)']}% t={r['t']}")
        报[名] = h
        print("✓", 名, flush=True)
    报["★★★多重检验对账"] = {"有效检验数": 总检验, "运气约给(5%)": round(总检验 * 0.05, 1),
                       "实际分得开": len(显著), "清单": 显著}
    报["耗时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("★ 写到", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
