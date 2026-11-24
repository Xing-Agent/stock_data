# -*- coding: utf-8 -*-
"""《396》第二件 · 四种行情的挂件配法（照《369》拍板第 2 条 + Gemini 原文「最后一问：挂件怎么配」的配置矩阵），两个十年。
engine/ 一个字节没动：配置只在内存里改副本；大盘闸在内存里换 m.regime；引擎外把几条子策略按仓位合成一条净值。

大白话：每天先判大盘处在哪种行情（在涨 / 震荡 / 刚转弱 / 跌了很久），再按 Gemini 那张表决定：
  在涨 → 主策略（趋势跟随，唐奇安原著离场版）满仓开新仓；
  震荡 → 换成回踩买（技-14 RSI2 均值回归），打开「推保本」，仓位减半；
  刚转弱 → 不开任何新仓，手里的按各自止损走（不强卖）；
  跌了很久 → 只做极度超卖的反弹（RSI2 去掉「在 200 日线上」那道闸），仓位四分之一。
  大盘开关「慢关快开」：往弱的方向换行情要连续 N 天确认（N 基准 3，邻点 1 / 5）；往强的方向当天换；
  出现宽度脉冲（10 日平均上涨股占比 10 天内从 < 40% 到 > 61.5%）→ 30 天内按「在涨」放行。
对照：不挂挂件的主策略（手册原样）/ 主策略只加四种行情开关（在涨、震荡放行，刚转弱、跌了很久关）/ 同样仓位的标普 / 标普买入不动。

══ 我补的定义（拍板没写死的）══
 G1 宽度 = 当天流动性池（中档）里收盘站上自己 50 日线的股票占比（Gemini 原文用标普 500 或罗素 3000 成分股，我们没有历史成分，用流动性池代替）。
 G2 四种行情没盖住的格子：SPY 在 200 日线上、但既不满足「在涨」也不满足「震荡」（比如 50 日线在 200 日线下、价格又在 50 日线上）→ 算震荡；
    SPY 在 200 日线下、离一年高点 < 12%、但宽度 ≥ 30% → 算刚转弱（邻点：改算震荡）。「跌了很久」里 Gemini 写的「可选：VIX>30 或连续 40 天在 200 日线下」没用。
 G3 慢关：往弱的方向连续 3 天（邻点 1 / 5）都判成更弱才换；快开：往强的方向当天换。宽度脉冲 = 每天上涨股占比的 10 日均线，10 天内从 < 0.40 升到 > 0.615；之后 30 天按在涨放行。
 G4 主策略 = 手册的「趋势跟随-唐奇安反向通道离场」（《401》两段里最稳的一条）；它配置里自带的大盘闸（SPY 在 200 日线上且 20 日斜率向上）在「只加开关」「整套」两臂里被我们的行情闸换掉，在「不挂挂件」那一臂原样保留。
 G5 震荡臂 = 手册的「技-14-行业-RSI2」，加「浮盈 1R 推保本」。Gemini 写的「赚 1~1.5R 卖一半」引擎做不到分批卖，只做了推保本。
 G6 跌了很久臂 = 同一条 RSI2 去掉「在 200 日线上且 200 日线向上」那道闸；Gemini 写的「按波动定大小」「反弹到下降的 20 日线全平」没做，用 RSI2 原来的「回到布林中轨就走」。
 G7 刚转弱：Gemini 写的「把持仓止损收紧到 1.5 倍 ATR」引擎外做不到，只做了不开新仓、不强卖。在涨臂的「只做强度前三的行业」也没做。
 G8 合成：几条子策略各自用一份全额资金跑，合成那天的收益 = 在涨臂 ×1.0 + 震荡臂 ×0.5 + 跌了很久臂 ×0.25（Gemini 的仓位：在涨满仓、震荡 40~50%、深熊 20~30%）。
    行情切换的那几天几条臂的老仓位会叠在一起，合成后的仓位可能超过 100%（报告里报了超过的天数和最高值）。
 G9 研究库：2015–2025 用研发池名单（同《401》段一），2005–2014 用 环境2004 的 dev（同《401》段二，并套数据组 11-23 的坏点修正，同《401》页头更正）；流动性池中档；含分红；留出池一只没碰（断言）。
"""
import copy, io, json, os, sys, time, traceback
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
W2 = os.path.join(ROOT, "probe/两段时间_1120")
主 = "trend_following-原著-唐奇安反向通道离场"; 回踩 = "技-14-行业-RSI2"
段们 = {"一": ("2015-01-02", "2025-12-31"), "二": ("2005-01-03", "2014-12-31")}


def mod(name, path):
    import importlib.util
    sp = importlib.util.spec_from_file_location(name, path); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m


def 环境(段):
    sys.path.insert(0, W2); sys.path.insert(0, ROOT)
    import 环境2004_1120 as ENV
    ENV.START, ENV.END = 段们[段]
    env = ENV.install(只留测试期=(段 == "二"))
    from engine import cache
    if 段 == "一":       # 省内存：2013 年以前的行情不要（留两年给 200 日线、一年高点热身）
        cache._PANEL = {f: df.loc["2013-01-01":] for f, df in cache._PANEL.items()}
        hold = json.load(io.open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
        dev = [s for s in hold["研发池名单"] if s in cache._PANEL["close"].columns and s not in set(env["拿掉"])]
        fn = os.path.join(HERE, "cache", "流动性池掩膜_中_2015起.parquet")
        if not os.path.exists(fn):
            os.makedirs(os.path.dirname(fn), exist_ok=True); mk, _ = ENV.流动性池(dev); mk.to_parquet(fn)
        mk = pd.read_parquet(fn)
    else:
        sys.path.insert(0, os.path.join(ROOT, "probe/成绩单_1122"))
        import 跑手册全套_修坏点_1123 as FX; env["坏点修正"] = len(FX.修面板())     # 同《401》更正：套数据组 11-23 的修正
        has = cache._PANEL["close"].loc[:ENV.END].notna().any(); dev = [x for x in env["dev"] if bool(has.get(x, False))]
        mk = pd.read_parquet(os.path.join(W2, "流动性池掩膜2004_中.parquet"))
    assert not (set(dev) & env["留出池"])
    return ENV, env, dev, mk


def 行情(idx, mk, 慢=3, 缺格算=3):
    """返回 [日] 的行情代码（1 在涨 2 震荡 3 刚转弱 4 跌了很久，已做慢关快开和宽度脉冲）和诊断表。都只用当天及以前的收盘。"""
    from engine import cache, data
    spy = data.load_benchmark("SPY")["close"].astype(float).dropna()
    s50, s200 = spy.rolling(50).mean(), spy.rolling(200).mean(); dd = spy / spy.rolling(252, min_periods=200).max() - 1
    cols = [c for c in mk.columns if c in cache._PANEL["close"].columns]
    C = cache._PANEL["close"][cols].astype(float).reindex(idx)
    M = mk.reindex(index=idx, columns=cols).fillna(False)
    above = (C > C.rolling(50, min_periods=50).mean()).where(M)
    br = above.sum(axis=1) / above.notna().sum(axis=1).replace(0, np.nan)
    up = (C > C.shift(1)).where(M); adv = (up.sum(axis=1) / up.notna().sum(axis=1).replace(0, np.nan)).ewm(span=10, adjust=False).mean()
    spy, s50, s200, dd = (x.reindex(idx).ffill() for x in (spy, s50, s200, dd))
    raw = pd.Series(2, index=idx)
    raw[(spy > s50) & (s50 > s200) & (br > 0.5)] = 1
    below = spy < s200
    raw[below & (dd <= -0.12)] = 4
    raw[below & (dd > -0.12) & (br < 0.30)] = 3
    raw[below & (dd > -0.12) & (br >= 0.30)] = 缺格算
    raw[s200.isna()] = 2
    # 宽度脉冲
    lo10 = adv.rolling(10, min_periods=10).min()
    thrust = (adv > 0.615) & (lo10.shift(1) < 0.40)
    lock = thrust.astype(int).rolling(30, min_periods=1).max().astype(bool)
    st = []; cur = 2; streak = 0
    for d, r in raw.items():
        if r < cur: cur = int(r); streak = 0           # 快开：往强的方向当天换
        elif r > cur:
            streak += 1
            if streak >= 慢: cur = int(r); streak = 0   # 慢关：连续 N 天更弱才换
        else: streak = 0
        st.append(cur)
    st = pd.Series(st, index=idx)
    st[lock] = 1
    diag = pd.DataFrame({"原始": raw, "最终": st, "宽度": br, "上涨占比10日": adv, "脉冲": thrust})
    return st, diag


def 配置(名, 改=None):
    import yaml
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    if 改: 改(raw)
    return raw


def 推保本(raw):
    raw["trailing_stop"] = {"type": "none", "params": {"breakeven_after_r": 1.0}, "source": "《396》第二件·震荡臂：浮盈 1R 推保本（Gemini 配置矩阵状态二）"}


def 去趋势闸(raw):
    rs = raw["entry"]["rules"]; raw["entry"]["rules"] = [r for r in rs if r.get("type") != "pat6_bb_trend_gate"]
    assert len(raw["entry"]["rules"]) == len(rs) - 1


def 跑(raw, dev, mk, s, e, gate, hs):
    from engine import matrices
    from engine_v2 import chain
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    if gate is not None:
        g = gate.reindex(m.index).fillna(False).astype(bool).shift(1).fillna(False)   # 今天收盘判的行情，明天才用
        m.regime = g.to_numpy(dtype=bool)
        raw = copy.deepcopy(raw); raw.setdefault("regime", {})["flatten_when_off"] = False
    r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, s, e, m=m, total_return=True, pyramid=None)
    L = r.ledger
    if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
    perf = mk.index
    return r.equity.reindex(perf).ffill(), r.exposure.reindex(perf).fillna(0), L


def 一段(段, 慢=3, 缺格算=3, 只要基准臂=False):
    cj = mod("cj", os.path.join(ROOT, "probe/成绩单_1122/成绩单_1122.py"))
    ENV, env, dev, mk = 环境(段); s, e = 段们[段]; hs = env["留出池"]; perf = mk.index
    from engine import cache
    st, diag = 行情(cache._PANEL["close"].index, mk, 慢, 缺格算)
    diag.reindex(perf).to_parquet(os.path.join(OUT, f"行情_{段}_慢{慢}_缺格{缺格算}.parquet"))
    rows = {}; 存 = {}
    def 记(k, eq, ex, L):
        rows[k] = {"策略": cj.成绩单(eq, L, ex), "同样仓位的标普": cj.成绩单(cj.等仓位标普(perf, ex))}
        存[k] = pd.DataFrame({"eq": eq, "expo": ex})
        print(段, k, {a: rows[k]["策略"].get(a) for a in ("每年赚pct", "最深亏损pct", "每年赚除以最深亏损", "溃疡绩效", "平均仓位pct", "笔数")}, flush=True)
    raw主 = 配置(主)
    if not 只要基准臂:
        eq, ex, L = 跑(raw主, dev, mk, s, e, None, hs); 记("A0_不挂挂件的主策略", eq, ex, L)
    eq, ex, L = 跑(raw主, dev, mk, s, e, st <= 2, hs); 记("A1_主策略只加四种行情开关", eq, ex, L)
    臂 = {}
    臂["涨"] = 跑(raw主, dev, mk, s, e, st == 1, hs)
    臂["震"] = 跑(配置(回踩, 推保本), dev, mk, s, e, st == 2, hs)
    臂["深熊"] = 跑(配置(回踩, 去趋势闸), dev, mk, s, e, st == 4, hs)
    w = {"涨": 1.0, "震": 0.5, "深熊": 0.25}
    ret = sum(w[k] * 臂[k][0].pct_change().fillna(0) for k in w); eq = 1e6 * (1 + ret).cumprod()
    ex = sum(w[k] * 臂[k][1] for k in w)
    L = pd.concat([臂[k][2].assign(臂=k) for k in w], ignore_index=True)
    记("A2_整套配法", eq, ex, L)
    for k in w:
        rows["A2_整套配法"][f"子臂_{k}"] = {**cj.成绩单(臂[k][0], 臂[k][2], 臂[k][1]), "合成时的权重": w[k]}
    rows["A2_整套配法"]["合成仓位超过100pct的天数"] = int((ex > 1.0).sum()); rows["A2_整套配法"]["合成仓位最高pct"] = round(float(ex.max() * 100), 1)
    rows["标普买入不动"] = {"策略": cj.成绩单(cj.标普净值(perf))}
    d = diag.reindex(perf)
    rows["行情天数占比pct"] = {nm: round(float((d["最终"] == c).mean() * 100), 1) for c, nm in ((1, "在涨"), (2, "震荡"), (3, "刚转弱"), (4, "跌了很久"))}
    rows["宽度脉冲次数"] = int(d["脉冲"].sum())
    rows["行情换了几次"] = int((d["最终"] != d["最终"].shift(1)).sum() - 1)
    return rows, 存


if __name__ == "__main__":
    # 用法：python3 四种行情_1124.py 段 慢 缺格算    （一个进程跑一种设定，断点续跑：做完的不重做）
    段, 慢, 缺 = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    fn = os.path.join(OUT, f"成绩_{段}_慢{慢}_缺格{缺}.json")
    if os.path.exists(fn): print("已有", fn); sys.exit(0)
    t = time.time()
    try:
        rows, 存 = 一段(段, 慢, 缺, 只要基准臂=not (慢 == 3 and 缺 == 3))
        for k, v in 存.items(): v.to_parquet(os.path.join(OUT, f"日线_{段}_慢{慢}_缺格{缺}_{k}.parquet"))
        rec = {"段": 段, "慢关天数": 慢, "缺格算": 缺, "结果": rows, "秒": round(time.time() - t)}
    except Exception as ex_:
        rec = {"跑失败": f"{type(ex_).__name__}: {ex_}", "traceback": traceback.format_exc()[-3000:]}
        fn = fn.replace(".json", "_失败.json")
    json.dump(rec, io.open(fn, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE", round(time.time() - t), flush=True)
