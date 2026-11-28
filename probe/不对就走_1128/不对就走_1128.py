# -*- coding: utf-8 -*-
"""《516》空单「不对就走」：在四批做空单上加两条出场，重算。引擎外。
四批单子都由原脚本原样产出（不改原文件：把源码读进来、在内存里只加一行「记下这笔单子的进场根、进场价、止损、颈线」，然后照原样跑），
再用同一套 K 线逐根重放出场：
  原来：打止损（盘中最高碰到，跳空按开盘）/ 到目标 / 拿满上限，照各批原来的写法。
  甲 · 收回颈线就走：某根收盘 > 颈线 + 缓冲×ATR（缓冲 0 / 0.2 / 0.5），在那根收盘平。只用收盘，不用同一根的高低挑价。
  乙 · 走不快就走：进场后第 N 根收盘时，进场以来最大浮盈 < 门槛×风险（门槛 1.0 / 0.5），在那根收盘平。4 小时线 N = 6/12/18，日线 N = 3/5/8。
  甲乙都加：两条都挂上，谁先到算谁。同一根里的先后：止损（盘中）→ 目标（盘中）→ 甲（收盘）→ 乙（收盘）。
颈线（每批用自己的）：
  急拉后高位派发区 右侧 = 跌破前那段横盘的最低（被跌破的下沿）；左侧 = 触发进场的那个顶的最高（左侧进场时还没有跌破任何线，用「反上来过这个顶就平」，写明）。
  派发楔形 右侧·追 = 跌破那根时的下轨；右侧·反抽 = 那天的 20 日线；左侧 = 触发那根的最高。
  反抽 20 日线没过再空 = 信号那天的 20 日线（日线）。
  箱顶假突破 = 箱顶。
「本来会赚」= 被甲 / 乙提前平掉的单子，照原来的出场最后是赚的。"""
import os, sys, json, re, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
FEE = 0.0005; 封 = pd.Timestamp("2021-12-31 23:59")
PW = os.path.join(ROOT, "probe/派发楔形_1125")
REC = []


def 载入改过的(path, 改法, name):
    src = open(path, encoding="utf-8").read().split('if __name__ == "__main__":')[0]
    for a, b in 改法:
        assert a in src, (name, a[:60]); src = src.replace(a, b)
    g = {"__file__": path, "__name__": name, "REC": REC}; sys.path.insert(0, os.path.dirname(path)); exec(compile(src, name, "exec"), g); return g


# ---------- 一、二：两批 4 小时线（派发区、楔形）——在 出() 被调用前记下颈线 ----------
记 = '        REC.append(dict(批=批名, sym=sym, i=i, e=e, stop=stop, neck=颈[0], 类=颈[1], arr=(o, h, l, c, atr), t=t))\n'
改派发区 = [("    def 出(i, e, stop, 平位=None):\n        r = stop - e\n", "    颈 = [None, None]\n    def 出(i, e, stop, 平位=None):\n        r = stop - e\n" + 记.replace("        REC", "        if 平位 is None: REC", 1)),
         ("j, tk = lefts[0]; e = o[j + 1]; stop = h[f:j + 1].max() + 0.3 * A; rl = 出(j + 1, e, stop)", "j, tk = lefts[0]; e = o[j + 1]; stop = h[f:j + 1].max() + 0.3 * A; 颈[:] = [h[tk], \"左侧\"]; rl = 出(j + 1, e, stop)"),
         ("            rr = 出(brk + 1, o[brk + 1], h[tops[-1]] + 0.3 * A)", "            颈[:] = [l[f + 1:brk].min(), \"右侧\"]; rr = 出(brk + 1, o[brk + 1], h[tops[-1]] + 0.3 * A)")]
改楔形 = [("    def 出(i, e, stop):\n        r = stop - e\n", "    颈 = [None, None]\n    def 出(i, e, stop):\n        r = stop - e\n" + 记),
         ("            e = o[j + 1]; r = 出(j + 1, e, hi_all", "            颈[:] = [h[j], \"左侧\"]; e = o[j + 1]; r = 出(j + 1, e, hi_all"),
         ("            e = o[brk + 1]; r = 出(brk + 1, e, h[tops[-1]] + 0.3 * A)", "            颈[:] = [line, \"右侧·追\"]; e = o[brk + 1]; r = 出(brk + 1, e, h[tops[-1]] + 0.3 * A)"),
         ("                    e = o[q]; hi = h[max(0, q - 30):q].max(); r = 出(q, e, hi + 0.3 * A)", "                    颈[:] = [r_.ma, \"右侧·反抽\"]; e = o[q]; hi = h[max(0, q - 30):q].max(); r = 出(q, e, hi + 0.3 * A)")]


def 重放(arr, i, e, stop, neck, 目标, 上限, 甲=None, 乙=None, 份=None):
    """返回 (R, 走法, 平仓根)。目标 = 几倍风险（单一目标）；份 = [(比例, 价)] 分批目标（箱顶假突破用）。甲 = 缓冲倍数或 None；乙 = (N, 门槛) 或 None。"""
    o, h, l, c, atr = arr; n = len(c); r = stop - e
    if r <= 0: return None
    end = min(n - 1, i + 上限); pnl = 0.0; 剩 = 1.0; parts = [list(p) for p in 份] if 份 else None; 最低 = np.inf
    for j in range(i, end + 1):
        if h[j] >= stop:
            px = max(o[j], stop) if j > i else stop; return (pnl + 剩 * (e - px)) / r - 2 * FEE * e / r, "止损", j
        最低 = min(最低, l[j])
        if parts is None:
            if l[j] <= e - 目标 * r: return 目标 - 2 * FEE * e / r, "目标", j
        else:
            for p in parts:
                if p[0] > 0 and l[j] <= p[1]: pnl += p[0] * (e - p[1]); 剩 -= p[0]; p[0] = 0
            if 剩 <= 1e-9: return pnl / r - 2 * FEE * e / r, "目标", j
        if 甲 is not None and c[j] > neck + 甲 * atr[j]: return (pnl + 剩 * (e - c[j])) / r - 2 * FEE * e / r, "甲", j
        if 乙 is not None and j == i + 乙[0] - 1 and (e - 最低) < 乙[1] * r: return (pnl + 剩 * (e - c[j])) / r - 2 * FEE * e / r, "乙", j
    return (pnl + 剩 * (e - c[end])) / r - 2 * FEE * e / r, "到期", end


def 批_4小时():
    out = []
    for 名, f, 改 in (("急拉后高位派发区", "急拉后高位派发区_1125.py", 改派发区), ("派发楔形", "识别和扫历史_1125.py", 改楔形)):
        g = 载入改过的(os.path.join(PW, f), 改, 名); g["批名"] = 名; k0 = len(REC)
        for s in ("BTC", "ETH"): g["扫"](s)
        for x in REC[k0:]:
            x["日"] = x["t"][x["i"]]; x["目标"] = 3.0; x["上限"] = 59 if 名 == "急拉后高位派发区" else 59; x["周期"] = "4小时"; out.append(x)
    return out


def 批_反抽():
    sp = importlib.util.spec_from_file_location("搬", os.path.join(ROOT, "probe/反抽搬家_1127/反抽搬家_1127.py")); B = importlib.util.module_from_spec(sp); sp.loader.exec_module(B)
    out = []
    src = open(os.path.join(ROOT, "probe/反抽搬家_1127/反抽搬家_1127.py"), encoding="utf-8").read()
    # 在 跑() 里记下每笔：进场根 i+1、进场价、止损、颈线 = 信号那天的 20 日线
    改 = [("        e = o[i + 1]; stop = h[max(0, i - 30):i + 1].max() + 0.3 * a4[i]; r = stop - e\n        if r <= 0 or r / e < 0.003: continue\n",
          "        e = o[i + 1]; stop = h[max(0, i - 30):i + 1].max() + 0.3 * a4[i]; r = stop - e\n        if r <= 0 or r / e < 0.003: continue\n        REC.append(dict(批=\"反抽20日线没过再空\", sym=sym, i=i + 1, e=e, stop=stop, neck=ma, 类=_类[0], arr=(o, h, l, c, a4), t=t, 日=t[i + 1], 目标=3.0, 上限=60, 周期=\"4小时\", 牛熊=_牛熊(D, p)))\n")]
    g = 载入改过的(os.path.join(ROOT, "probe/反抽搬家_1127/反抽搬家_1127.py"), 改, "反抽")
    g["_类"] = [""]
    def 牛熊(D, p):
        m = D.close.rolling(200).mean(); return "200日线向上" if m.iloc[p] > m.iloc[max(0, p - 20)] else "200日线向下"
    g["_牛熊"] = 牛熊; k0 = len(REC)
    # 币：照 反抽加过滤 的 18 笔口径（状态机开关 + 过滤 0.8）。4 小时线、日线用 看九月那段 的币数据。
    K = g.get("K") or None
    spK = importlib.util.spec_from_file_location("k", os.path.join(PW, "看九月那段_1125.py")); KK = importlib.util.module_from_spec(spK); spK.loader.exec_module(KK)
    spF = importlib.util.spec_from_file_location("fl", os.path.join(PW, "反抽加过滤_1125.py")); FL = importlib.util.module_from_spec(spF); spF.loader.exec_module(FL)
    for s in ("BTC", "ETH"):
        X = KK.指标(KK.四小时(s)); X.index = X.index.tz_localize(None) if X.index.tz is not None else X.index
        D = X.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
        可, _ = FL.状态可空(s); 可 = pd.Series(可) if not isinstance(可, pd.Series) else 可
        g["_类"][0] = "币"; g["跑"](s, X, D, "状态机", True, 0.8, 状态=可)
    # SOXX：状态机开关 + 过滤 0.8（《494》那 18 笔）
    fs = sorted(f for f in os.listdir(os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线")) if f.endswith(".parquet") and int(f[5:9]) <= 2021)
    H = pd.concat([g["读小时"](os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线", f)) for f in fs]); H = H[H.t <= 封]; X, D = g["拼"](H)
    g["_类"][0] = "SOXX"; g["跑"]("SOXX", X, D, "状态机", True, 0.8, 状态=g["SOXX可空"]())
    # 个股：均线开关 + 过滤 0.8（《494》416 笔那组）
    名单 = json.load(open(os.path.join(ROOT, "probe/反抽搬家_1127/out/个股_每年名单.json"))); 全 = sorted(set(sum(名单.values(), [])))
    fsH = [os.path.join(g["HR"], f) for f in sorted(os.listdir(g["HR"])) if f.endswith(".parquet") and int(f[:4]) <= 2021]
    g["_类"][0] = "个股"
    for b in range(0, len(全), 40):
        批 = 全[b:b + 40]; H = pd.concat([g["读小时"](f, 批) for f in fsH]); H = H[H.t <= 封]
        for s in 批:
            x = H[H.symbol == s]
            if len(x) < 2000: continue
            X, D = g["拼"](x.drop(columns="symbol"))
            for y in [int(y) for y, v in 名单.items() if s in v]: g["跑"](s, X, D, "均线", True, 0.8, 年=y)
        print("个股批", b // 40 + 1, flush=True)
    return REC[k0:]


def 批_箱顶():
    sp = importlib.util.spec_from_file_location("箱", os.path.join(ROOT, "probe/箱顶假突破_1127/箱顶假突破_1127.py")); X = importlib.util.module_from_spec(sp); sp.loader.exec_module(X)
    T = pd.read_csv(os.path.join(ROOT, "probe/箱顶假突破_1127/out/冲出逐次.csv")); T = T[(T.窗 == 20) & (T.参数 == "默认") & (T.规则判 == "假")]
    out = []
    for _, e in T.iterrows():
        s = e.品种; D = X.价(s); R = X.档(s); D = D.loc[D.index.isin(R.index)]
        o, h, l, c = (D[k].to_numpy(float) for k in ("open", "high", "low", "close")); pc = np.roll(c, 1); pc[0] = c[0]
        atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().bfill().to_numpy()
        i0 = D.index.get_loc(pd.Timestamp(e.判的日子)); 高 = e.箱顶 - e.箱底
        m200 = pd.Series(c).rolling(200).mean().to_numpy()
        out.append(dict(批="箱顶假突破", sym=s, i=i0 + 1, e=c[i0], stop=e.止损, neck=e.箱顶, 类=s, arr=(o, h, l, c, atr), t=D.index, 日=D.index[i0], 份=[(0.5, (e.箱顶 + e.箱底) / 2), (0.35, e.箱底), (0.15, e.箱底 - 高)],
                        上限=119, 周期="日线", 牛熊=("200日线向上" if m200[i0] > m200[i0 - 20] else "200日线向下") if s not in ("BTC", "ETH") else ""))
    return out


def 跑全部(trades):
    rows = []
    for k, x in enumerate(trades):
        N档 = (6, 12, 18) if x["周期"] == "4小时" else (3, 5, 8)
        base = dict(编号=k, 批=x["批"], 类=x["类"], sym=x["sym"], 日=str(x["日"]), 牛熊=x.get("牛熊", ""))
        kw = dict(目标=x.get("目标"), 上限=x["上限"], 份=x.get("份"))
        R0 = 重放(x["arr"], x["i"], x["e"], x["stop"], x["neck"], **kw)
        if R0 is None: continue
        o, h, l, c, a = x["arr"]; rk = x["stop"] - x["e"]; i = x["i"]
        早 = {f"第{q}根浮盈R": (x["e"] - c[min(len(c) - 1, i + q - 1)]) / rk for q in (1, 3, 5)}
        rows.append(dict(base, 出场="原来", 档="—", R=R0[0], 走法=R0[1], 原来R=R0[0], **早))
        for b in (0.0, 0.2, 0.5):
            r = 重放(x["arr"], x["i"], x["e"], x["stop"], x["neck"], 甲=b, **kw); rows.append(dict(base, 出场="只加甲", 档=f"缓冲{b}", R=r[0], 走法=r[1], 原来R=R0[0], **早))
        for N in N档:
            for th in (1.0, 0.5):
                r = 重放(x["arr"], x["i"], x["e"], x["stop"], x["neck"], 乙=(N, th), **kw); rows.append(dict(base, 出场="只加乙", 档=f"N{N}·{th}R", R=r[0], 走法=r[1], 原来R=R0[0], **早))
                for b in (0.0, 0.2, 0.5):
                    r = 重放(x["arr"], x["i"], x["e"], x["stop"], x["neck"], 甲=b, 乙=(N, th), **kw); rows.append(dict(base, 出场="甲乙都加", 档=f"缓冲{b}·N{N}·{th}R", R=r[0], 走法=r[1], 原来R=R0[0], **早))
    return pd.DataFrame(rows)


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "全部"
    tr = []
    if which in ("全部", "4小时"): tr += 批_4小时(); print("4小时两批", len(tr), flush=True)
    if which in ("全部", "箱顶"): tr += 批_箱顶(); print("箱顶", len(tr), flush=True)
    if which in ("全部", "反抽"): tr += 批_反抽(); print("反抽", len(tr), flush=True)
    T = 跑全部(tr); T.to_csv(os.path.join(OUT, f"逐笔_{which}.csv"), index=False); print("DONE", len(T))
