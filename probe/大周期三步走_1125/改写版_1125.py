# -*- coding: utf-8 -*-
"""《455》· 大周期认顶「三步走」改写版（照 手册/拍板和要干啥-大周期认顶三步走改写-周线判破位-慢熊急跌两条路-Lin两条都同意-1125.md）· 引擎外
大白话：这一版不再去筛原来状态机的报警，而是自己从头认顶：
  主版本（周线）：先要「两年内从低点涨超 35%」→ 创 52 周新高后高位震荡 4~12 周，取震荡里最低的周收盘当箱底
                → 周收盘跌破箱底 2.5% 以上、两周累计跌 4.5% 以上、收在 30 周线下 = 破位
                → 破位后最多看 4 周：任一周收盘低于箱底 6.5% 以上（急跌）直接切跌势；或连续 2 周收在「箱底 + 1%」下方、且反抽量 < 破位段 85%（慢熊）也切。
                → 连续 2 周站上箱底和 30 周线、30 周线拐头向上 = 解除。
  对照版本（日线）：65 天摆动低点的中位数当箱底；前提 = 200 日线 20 天斜率 ≤ 0 且连续 10 天收在 200 日线下；日收盘跌破箱底 1.5% = 破位；
                15 天内反弹收不回箱底、再跌破破位以来最低收盘 = 慢熊确认；在箱底和 200 日线下方、10 天累计跌 > 10% = 急跌确认。
原来的状态机（《429》三层第一版：严版 = 17 次 / 12 次那版；现默认版 = 11-24 放宽后）用同一把尺子重新评，前后好比。

══ 我补的定义（拍板没写死的）══
 R1 「前提」在创 52 周新高那一周判：这周收盘 ÷ 之前 104 周最低收盘 ≥ 1.35。「离 52 周高点 10% 以内」在新高那周天然满足，不再单独判。
 R2 箱底：最近一次 52 周收盘新高那周记为 H。离 H ≥ 4 周时，箱底 = H 之后到「H 后 12 周 / 上一周」为止的最低周收盘；
    离 H 不到 4 周就破位的，箱底 = H 之前最近一个周线摆动低点（比左右各 3 周的收盘都低）。
 R3 两周累计跌 = 本周收盘 ÷ 两周前收盘 − 1 < −4.5%。全历史只用收盘价判；「1962 年后改用 1.5 倍 ATR」那条没用；量只在慢熊那条用（1950 年前不看量）。
 R4 观察 4 周 = 破位那周之后的 4 周；急跌在破位那周本身也算。破位后 4 周内没确认 = 这次破位作废，同一个箱子以后可以再破、再确认（箱底在 H 后 12 周就定住）。
    第一稿写成「作废后要等下一次 52 周新高才重新认」，2000 年这种第一次破位没确认、后面慢慢跌的顶就再也认不出来；两种都报（「第一稿·作废等新高」）。
 R5 跌势中不再报新的顶；解除后也要等新的 52 周新高才重新认。
 R6 对照版：日线摆动低点 = 比左右各 3 天的收盘都低；箱底取过去 65 天里摆动低点的中位数；破位那天要满足前提；
    解除 = 连续 10 天站上箱底和 200 日线、200 日线比 20 天前高（拍板没给日线的解除，我照周线那条翻成日线）。宽度背离那条前提没数据，没用。
 R7 BTC 主版本用日线判：52 周 = 365 天，震荡 28~84 天，30 周线换成 120 日线，「两周累计」换成「两天累计」仍是 4.5%，观察 12 天（拍板写 5~12 天，取上限），破位 5%、急跌 12%。
    BTC 对照：45 天箱底、破位 4%、急跌 20%（10 天累计），200 日线。
 R8 SOXX 主版本：破位 4%、急跌 9%；对照：45 天箱底、破位 3%、急跌 15%。
 R9 评分：真大顶 = 《429》同一个认法（两年新高后回落 ≥ 20%）。认出 = 确认日落在「顶 → 收盘重新站上顶之前的最低点」之间（整轮熊市）。
    虚惊 = 不属于任何真顶的报警里，报警后一年内最低收盘比报警时跌不到 10%。原来的状态机也用这把尺子重评（所以和《429》的 12 次不完全一样）。
 R11 BTC 数据 2017-01-01 才开始，「52 周新高」要攒满 365 天，2017 年底那个顶按主版本判不了；另报一版「新高按已有数据、至少 180 天就算」。
 R10 封存：2022-01-01 以后不进统计；BTC 2023–2025 那几次只回答报不报、晚几天。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
P3 = os.path.join(ROOT, "probe/美股三层状态机_1123")
L = mod("L", os.path.join(P3, "长历史_1124.py")); V1 = L.M
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
封存 = pd.Timestamp("2022-01-01")


def 周线(D):
    return D.resample("W-FRI").agg({"close": "last", "volume": "sum"}).dropna(subset=["close"])


def 摆动低(c, k=3):
    n = len(c); out = np.zeros(n, bool)
    for j in range(k, n - k):
        if c[j] < c[j - k:j].min() and c[j] < c[j + 1:j + k + 1].min(): out[j] = True
    return out          # 第 j 根是摆动低点，要到 j + k 根收盘才看得出来


def 主版(B, 破=0.025, 急=0.065, 观=4, 两根跌=0.045, 均线=30, 用均线=True, 用急跌=True, 年=52, 盒小=4, 盒大=12, 涨=0.35, 两年=104, 缩=0.85, 量起=None, 作废等新高=False, 看量=True, 年最少=None):
    """B: 周线（BTC 时是日线）DataFrame[close, volume]。返回报警列表。"""
    c = B.close.to_numpy(float); v = B.volume.to_numpy(float); idx = B.index; n = len(c)
    ma = pd.Series(c).rolling(均线, min_periods=均线).mean().to_numpy()
    hi = pd.Series(c).rolling(年, min_periods=年最少 or 年).max().shift(1).to_numpy()
    lo2 = pd.Series(c).rolling(两年, min_periods=年).min().to_numpy()
    sw = 摆动低(c)
    有量 = lambda j: (量起 is None or idx[j] >= 量起) and v[j] > 0
    ev = []; H = None; st = 0; t = 0
    while t < n:
        if st == 0:
            if not np.isnan(hi[t]) and c[t] > hi[t]:
                H = t if (lo2[t] > 0 and c[t] / lo2[t] - 1 >= 涨) else None
                t += 1; continue
            if H is None or t - H < 1 or t < 2: t += 1; continue
            if t - H >= 盒小:
                底 = c[H + 1:min(t, H + 盒大 + 1)].min()
            else:
                cand = [j for j in range(H) if sw[j] and j + 3 <= t]
                if not cand: t += 1; continue
                底 = c[cand[-1]]
            破了 = c[t] < 底 * (1 - 破) and c[t] / c[t - 2] - 1 < -两根跌 and (not 用均线 or (not np.isnan(ma[t]) and c[t] < ma[t]))
            if not 破了: t += 1; continue
            bt = t; segv = np.mean(v[t - 1:t + 1]); 确 = None; 路 = None
            for j in range(bt, min(bt + 观 + 1, n)):
                if 用急跌 and c[j] < 底 * (1 - 急): 确 = j; 路 = "急跌"; break
                if j >= bt + 2 and c[j] < 底 * 1.01 and c[j - 1] < 底 * 1.01:
                    if not 看量 or not (有量(j) and 有量(j - 1) and segv > 0) or np.mean(v[j - 1:j + 1]) < 缩 * segv:
                        确 = j; 路 = "慢熊"; break
            if 确 is None:
                if 作废等新高: H = None
                t = bt + 观 + 1; continue          # 破位作废：默认同一个箱子允许再破（R4 修正）；作废等新高 = 第一稿的写法
            # 跌势，找解除
            r = None
            for j in range(确 + 1, n):
                if j >= 1 and c[j] > 底 and c[j - 1] > 底 and not np.isnan(ma[j]) and c[j] > ma[j] and c[j - 1] > ma[j - 1] and ma[j] > ma[j - 1]: r = j; break
            ev.append({"高点周": idx[H], "破位": idx[bt], "确认": idx[确], "路": 路, "箱底": float(底), "解除": idx[r] if r is not None else None})
            H = None; t = (r + 1) if r is not None else n
        else:
            t += 1
    return ev


def 日线版(D, 箱=65, 破=0.015, 急=0.10, 急天=10, 慢天=15, ma_n=200):
    c = D.close.to_numpy(float); idx = D.index; n = len(c)
    ma = pd.Series(c).rolling(ma_n, min_periods=ma_n).mean().to_numpy(); sw = 摆动低(c)
    ev = []; t = ma_n + 30
    while t < n:
        lows = [c[j] for j in range(max(0, t - 箱), t - 3) if sw[j]]
        if not lows: t += 1; continue
        底 = float(np.median(lows))
        前提 = ma[t] - ma[t - 20] <= 0 and all(c[t - k] < ma[t - k] for k in range(10))
        确 = None; 路 = None
        if c[t] < 底 and c[t] < ma[t] and t >= 急天 and c[t] / c[t - 急天] - 1 < -急: 确 = t; 路 = "急跌"
        elif 前提 and c[t] < 底 * (1 - 破):
            bt = t; mn = c[t]; 弹 = False
            for j in range(bt + 1, min(bt + 慢天 + 1, n)):
                if c[j] >= 底: break
                if c[j] > c[j - 1]: 弹 = True
                if 弹 and c[j] < mn: 确 = j; 路 = "慢熊"; break
                mn = min(mn, c[j])
                if c[j] < 底 and c[j] < ma[j] and c[j] / c[j - 急天] - 1 < -急: 确 = j; 路 = "急跌"; break
            if 确 is None: t = bt + 1; continue
        if 确 is None: t += 1; continue
        r = None
        for j in range(确 + 10, n):
            if all(c[j - k] > 底 and c[j - k] > ma[j - k] for k in range(10)) and ma[j] > ma[j - 20]: r = j; break
        ev.append({"破位": idx[t], "确认": idx[确], "路": 路, "箱底": 底, "解除": idx[r] if r is not None else None})
        t = (r + 1) if r is not None else n
    return ev


def 原来(D, **kw):
    R, EV = V1.跑(D, **kw)
    return [{"确认": pd.Timestamp(e["日期"]), "路": e["事"]} for e in EV if e["事"].startswith(("转空", "复跌"))]


def 熊底(c, a):
    top = c.iloc[a]; after = c.iloc[a:]; back = after[after > top].index[:1]
    seg = after.loc[:back[0]] if len(back) else after
    return seg.idxmin()


def 评(D, ev, 止=封存, 起=None, 原=None):
    c = D.close; idx = D.index; tops = [(a, b) for a, b in L.真顶(c) if idx[a] < 止 and (起 is None or idx[a] >= 起)]
    ev = [e for e in ev if e["确认"] < 止 and (起 is None or e["确认"] >= 起)]
    用 = set(); rows = []
    for a, b in tops:
        ta = idx[a]; tb = 熊底(c, a); x = [e for e in ev if ta <= e["确认"] <= tb]
        row = {"顶": str(ta.date()), "熊底": str(tb.date()), "整轮跌幅pct": round((c.loc[tb] / c.iloc[a] - 1) * 100, 1)}
        if x:
            e = x[0]; 用 |= {id(y) for y in x}; px = float(c.loc[:e["确认"]].iloc[-1])
            row.update({"认出": str(e["确认"].date()), "路": e["路"], "离顶天": int((e["确认"] - ta).days), "确认时离顶pct": round((px / c.iloc[a] - 1) * 100, 1),
                        "确认后还要跌pct": round((c.loc[tb] / px - 1) * 100, 1)})
            if 原 is not None:
                o = [y for y in 原 if ta <= y["确认"] <= tb]
                row["比原来晚天"] = int((e["确认"] - o[0]["确认"]).days) if o else None
        else: row["认出"] = "没认出"
        rows.append(row)
    别 = []
    for e in ev:
        if id(e) in 用: continue
        t = e["确认"]; px = float(c.loc[:t].iloc[-1]); fut = c.loc[t:t + pd.Timedelta(days=365)]
        别.append({"报警": str(t.date()), "路": e["路"], "一年内最多再跌pct": round((fut.min() / px - 1) * 100, 1)})
    T = pd.DataFrame(rows); F = pd.DataFrame(别)
    y = T[T["认出"] != "没认出"] if len(T) else T
    S = {"真大顶": int(len(T)), "认出": int(len(y)), "离顶天中位": float(y["离顶天"].median()) if len(y) else None,
         "确认时离顶pct中位": float(y["确认时离顶pct"].median()) if len(y) else None,
         "比原来晚天中位": float(y["比原来晚天"].dropna().median()) if len(y) and "比原来晚天" in y and y["比原来晚天"].notna().any() else None,
         "别的报警": int(len(F)), "其中虚惊": int((F["一年内最多再跌pct"] > -10).sum()) if len(F) else 0}
    return S, T, F


def 跑指数(nm, D, 起=None):
    W = 周线(D); 量起 = pd.Timestamp("1950-01-01")
    原严 = 原来(D, 要ST或UT=True, BC严=True); 原默 = 原来(D)
    out = {}
    def 记(k, ev, 原=原严):
        S, T, F = 评(D, ev, 起=起, 原=原); out[k] = {"概要": S, "每个真顶": T.to_dict("records"), "别的报警": F.to_dict("records")}
    记("原来·严版(429那版)", 原严); 记("原来·现默认版", 原默)
    记("主版本(周线)", 主版(W, 量起=量起))
    记("主版本·不要30周线过滤", 主版(W, 用均线=False, 量起=量起)); 记("主版本·不要急跌直通", 主版(W, 用急跌=False, 量起=量起))
    for 破 in (0.02, 0.03): 记(f"主版本·破位{破:.1%}", 主版(W, 破=破, 量起=量起))
    for 急 in (0.05, 0.08): 记(f"主版本·急跌{急:.1%}", 主版(W, 急=急, 量起=量起))
    for 观 in (3, 5): 记(f"主版本·观察{观}周", 主版(W, 观=观, 量起=量起))
    记("主版本·第一稿(破位作废等新高)", 主版(W, 量起=量起, 作废等新高=True))
    记("主版本·不要35%前提", 主版(W, 涨=0.0, 量起=量起))
    记("主版本·慢熊不看量", 主版(W, 量起=量起, 看量=False))
    记("主版本·不要35%前提·慢熊不看量", 主版(W, 涨=0.0, 量起=量起, 看量=False))
    记("对照版本(日线)", 日线版(D))
    return out


if __name__ == "__main__":
    R = {}
    for nm, 起 in (("标普500指数", None), ("道琼斯工业指数", None), ("纳斯达克综合指数", None)):
        D = L.读(nm); R[nm] = 跑指数(nm, D, 起)
        print("==", nm, {k: v["概要"] for k, v in R[nm].items()}, flush=True)
    # SOXX
    D = SC.soxx(); W = 周线(D); o = {}
    原严 = 原来(D, 要ST或UT=True, BC严=True)
    for k, ev in (("原来·严版", 原严), ("原来·现默认版", 原来(D)), ("主版本(周线)", 主版(W, 破=0.04, 急=0.09)),
                  ("主版本·不要30周线过滤", 主版(W, 破=0.04, 急=0.09, 用均线=False)), ("主版本·不要急跌直通", 主版(W, 破=0.04, 急=0.09, 用急跌=False)),
                  ("对照版本(日线)", 日线版(D, 箱=45, 破=0.03, 急=0.15))):
        S, T, F = 评(D, ev, 原=原严); o[k] = {"概要": S, "每个真顶": T.to_dict("records"), "别的报警": F.to_dict("records")}
    R["SOXX"] = o; print("== SOXX", {k: v["概要"] for k, v in o.items()}, flush=True)
    # BTC（2017 起；2022 后只答报不报）
    D = M4.币日线("BTC"); D = D[D.index >= "2016-01-01"]; o = {}
    B = D[["close", "volume"]]
    for k, ev in (("主版本(日线判,120日线)", 主版(B, 破=0.05, 急=0.12, 观=12, 两根跌=0.045, 均线=120, 年=365, 盒小=28, 盒大=84, 两年=730)),
                  ("主版本·不要120日线过滤", 主版(B, 破=0.05, 急=0.12, 观=12, 均线=120, 年=365, 盒小=28, 盒大=84, 两年=730, 用均线=False)),
                  ("主版本·不要急跌直通", 主版(B, 破=0.05, 急=0.12, 观=12, 均线=120, 年=365, 盒小=28, 盒大=84, 两年=730, 用急跌=False)),
                  ("主版本·新高至少180天就算(补2017年底)", 主版(B, 破=0.05, 急=0.12, 观=12, 两根跌=0.045, 均线=120, 年=365, 盒小=28, 盒大=84, 两年=730, 年最少=180)),
                  ("对照版本(日线)", 日线版(D, 箱=45, 破=0.04, 急=0.20))):
        o[k] = [{"破位": str(e["破位"].date()), "确认": str(e["确认"].date()), "路": e["路"], "解除": str(e["解除"].date()) if e["解除"] is not None else ""} for e in ev if e["确认"] >= pd.Timestamp("2017-01-01")]
    R["BTC"] = o; print("== BTC", json.dumps(o, ensure_ascii=False), flush=True)
    json.dump(R, open(os.path.join(OUT, "改写版_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE")
