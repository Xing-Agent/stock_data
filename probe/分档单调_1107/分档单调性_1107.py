# -*- coding: utf-8 -*-
"""
★★★★★ 《83》第二步：**把信号从强到弱切十档，看是不是排成阶梯** ——
   ★ 这是五步里**唯一一次都没做过**的一步（《83》第二步末尾原话：「❌ 没做」）。

★★★ 它在问什么（★ 一句话）：**「信号强一点，是不是就该赚多一点？」**
   ★★ 为什么它比「有信号 / 没信号」强：★ 两个点之间永远能连一条线，很容易被运气骗；
   ★★★ 而**十个点要排成阶梯**，运气很难做到（《83》第二步那个吃药的类比）。

★★★ 口径（★ 每一条都写死在这里，★★ 跑完只能照它读）：
  · 池子：**研发池 2,224 只**（`probe/新策略_1106/holdout_newpool_1106.json`）—— ★★★ 留出池和考卷不碰
  · 流动性闸：ADV20（60 日均成交额）**≥ 100 万美元/天** —— ★ 和《99》留出池复验同一道闸
  · ★★★★★ **脏日**：和《93》**完全同一个并集**（四份清单，906 只）—— ★ 跨过脏日的只×日**整格剔掉**
  · 调仓：**每月第一个交易日**（★ 逐日会把同一个信号数上千遍，没有额外信息）
  · ★★★★★ **滞后（规矩㉙）**：信号只用到**第 t 天收盘**；
      ★★ 前瞻收益从**第 t+1 天收盘**量到**第 t+1+N 天收盘** ——
      ★★★ 信号用到的最后一根 K 线和收益窗口**不重叠一天**。
  · 基准：同窗口 SPY 收益（★ 逐档减掉它）
  · ★★ 判「是不是阶梯」：① 十档均值对档位序号的 **Spearman 秩相关**
      ② 最强档减最弱档的**月度时序**做 t 检验（★ 按月聚类，不是按只×日）
      ★★★ ③ 并且**逐年报一遍**（规矩㉗：不许只报一个混合平均 —— #66 就是这么出来的）

★★★ 这一轮只做**算得出的技术面信号**（★ 基本面信号要接财报库，下一轮）。
★ 产出：`分档单调性_报告_1107.json`
"""
from __future__ import annotations
import glob, gzip, io, json, os, re, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe/假跳变_1107"))
import 扫假跳变_1107 as 扫            # noqa: E402  ★ 只借门槛常数
import 并两份脏日重量_1107 as U       # noqa: E402  ★ 只借 源头脏日()
sys.path.insert(0, os.path.join(ROOT, "probe/剔脏日重出_1107"))
import 剔脏日后重量33条_1107 as C     # noqa: E402  ★ 借第三、四类（源头改名日）

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
OUT = os.path.join(HERE, "分档单调性_报告_1107.json")

档数 = 10
ADV闸 = 1_000_000.0
容差日 = 15
前瞻 = [5, 20]        # ★ 交易日；★★ 两个窗口 —— 1106 查出的规律是「持有越短越容易赢大盘」
源跳门槛 = 50.0
每档最少 = 20         # ★ 一档不足这么多只，这一期整期不用（★★ 并报丢了几期）


def 脏格(cl: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """★★★★★ 和《93》同一个四份并集 —— ★ 现算，不手抄。
       ★★ 返回一张和 cl 同形的 bool 表：True = 这一只×这一天在脏日 ±15 日内。"""
    def 前(x): return x.shift(1).rolling(扫.窗, min_periods=扫.窗).median()
    def 后(x): return x.iloc[::-1].rolling(扫.窗, min_periods=扫.窗).median().iloc[::-1]
    pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
    疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
          | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
    并: dict[str, set] = {}
    ii, jj = np.where(疑.to_numpy())
    for i, j in zip(ii, jj):
        并.setdefault(str(cl.columns[j]), set()).add(cl.index[i].normalize())
    断层, 改名 = C.源头改名日()
    for 份 in (U.源头脏日(源跳门槛), 断层, 改名):
        for k, v in 份.items():
            并.setdefault(k, set()).update(pd.Timestamp(x).normalize() for x in v)
    # ★★ 用 searchsorted 把 ±15 日窗口直接切成下标区间（★ 逐日做布尔比较太慢）
    idx = cl.index
    M = np.zeros((len(idx), len(cl.columns)), dtype=bool)
    pos = {str(c): j for j, c in enumerate(cl.columns)}
    for sym, ds in 并.items():
        j = pos.get(str(sym))
        if j is None:
            continue
        for t in ds:
            a0 = int(np.searchsorted(idx.values, np.datetime64(t - pd.Timedelta(days=容差日)), "left"))
            b0 = int(np.searchsorted(idx.values, np.datetime64(t + pd.Timedelta(days=容差日)), "right"))
            if b0 > a0:
                M[a0:b0, j] = True
    return pd.DataFrame(M, index=idx, columns=cl.columns)


def 建信号(cl, hi, lo, dv) -> dict[str, pd.DataFrame]:
    """★★★ 只用**到当天收盘为止**的数据 —— ★ 每一条都在 docstring 里写明它看多少根 K 线。"""
    out = {}
    # ① 动量：过去 60 个交易日涨幅（★ 技-1/技-5/基-20 都用它）
    out["①动量60日"] = cl / cl.shift(60) - 1.0
    # ② 康纳斯 RSI(2) 的替身：过去 2 日涨幅（★ 技-12；★★ 越低越「超卖」→ 取负号让「强 = 第1档」
    out["②短期超卖(2日跌幅)"] = -(cl / cl.shift(2) - 1.0)
    # ③ 离 52 周高点多远（★ 状-12；★★ 越接近高点 = 信号越强）
    out["③贴52周高点"] = cl / hi.rolling(252, min_periods=200).max() - 1.0
    # ④ 布林带位置 %B（★ 技-14；★★ 越低越「触下轨」→ 取负号）
    ma, sd = cl.rolling(20, min_periods=20).mean(), cl.rolling(20, min_periods=20).std()
    out["④布林带触下轨(-%B)"] = -((cl - (ma - 2 * sd)) / (4 * sd))
    # ⑤ 波动率（★ 低波那一头是业内公认的异象，★★ 拿它当「这把尺子分不分得开」的对照）
    r = cl.pct_change()
    out["⑤低波动(负60日波动)"] = -r.rolling(60, min_periods=50).std()
    # ⑥ 成交额（★ 已知效应：《98》第三节「流动性闸越严 alpha 越小」→ ★★ 这条是**阳性对照**）
    out["⑥成交额(负·小票在前)"] = -np.log(dv.rolling(60, min_periods=40).mean().clip(lower=1))
    return out


def 一个信号(名, sig, cl, 可用, spy, 调仓日, N) -> dict:
    档均 = {k: [] for k in range(1, 档数 + 1)}
    价差 = []           # ★ 第1档 − 第10档，逐期
    日期 = []
    丢期 = 0
    idx = cl.index
    pos = {d: i for i, d in enumerate(idx)}
    for d in 调仓日:
        i = pos[d]
        if i + 1 + N >= len(idx):
            continue
        s = sig.loc[d]
        ok = 可用.loc[d] & s.notna()
        s = s[ok]
        if len(s) < 档数 * 每档最少:
            丢期 += 1
            continue
        # ★★★ 规矩㉙：信号到第 i 天收盘；收益从第 i+1 天收盘量到第 i+1+N 天收盘
        c0 = cl.iloc[i + 1][s.index]
        c1 = cl.iloc[i + 1 + N][s.index]
        ret = (c1 / c0 - 1.0)
        b = (spy.iloc[i + 1 + N] / spy.iloc[i + 1] - 1.0)
        q = pd.qcut(s.rank(method="first", ascending=False), 档数, labels=False) + 1
        g = (ret - b).groupby(q).mean()
        if g.isna().any() or len(g) != 档数:
            丢期 += 1
            continue
        for k in range(1, 档数 + 1):
            档均[k].append(float(g.loc[k]))
        价差.append(float(g.loc[1] - g.loc[档数]))
        日期.append(d)
    if len(价差) < 24:
        return {"★跑失败": f"只有 {len(价差)} 期 —— **少于 24 期不出数**", "丢期": 丢期}
    梯 = {f"第{k}档": round(float(np.mean(档均[k])) * 100, 3) for k in range(1, 档数 + 1)}
    xs = np.arange(1, 档数 + 1)
    ys = np.array([np.mean(档均[k]) for k in range(1, 档数 + 1)])
    # ★★ Spearman 秩相关（★ 不用 scipy，自己算 —— 档位本来就是 1..10）
    rx, ry = pd.Series(xs).rank().to_numpy(), pd.Series(ys).rank().to_numpy()
    sp = float(np.corrcoef(rx, ry)[0, 1])
    a = np.array(价差)
    t = float(a.mean() / (a.std(ddof=1) / np.sqrt(len(a)))) if a.std(ddof=1) > 0 else float("nan")
    # ★★★ 规矩㉗：逐年再报一遍（★ 不许只给一个混合平均）
    逐年 = {}
    ser = pd.Series(a, index=pd.DatetimeIndex(日期))
    for y, grp in ser.groupby(ser.index.year):
        逐年[str(y)] = {"期数": int(len(grp)), "第1档减第10档pct": round(float(grp.mean()) * 100, 3)}
    单调步数 = int(sum(1 for k in range(档数 - 1) if ys[k] > ys[k + 1]))
    # ★★★★★ 《83》第二步真正要分的是**情况 A（真阶梯）vs 情况 B（只有头上那一撮）** ——
    #   ★★ 而 Spearman **分不出来**：★ 只要第 1 档特别高、2~10 档略微下倾，Spearman 也能到 −0.7。
    #   → ★★★ 所以再加两个量：① 去掉头尾两档，看中段 2~9 档还有没有斜率
    #                        ② 第 1 档贡献了「1 档减 10 档」的百分之多少
    mid = ys[1:档数 - 1]
    rmx, rmy = pd.Series(np.arange(len(mid))).rank().to_numpy(), pd.Series(mid).rank().to_numpy()
    sp中 = float(np.corrcoef(rmx, rmy)[0, 1]) if len(mid) > 2 else float("nan")
    总差 = ys[0] - ys[档数 - 1]
    头贡献 = (float((ys[0] - np.mean(ys[1:])) / 总差 * 100) if 总差 else float("nan"))
    # ★★★ 三档，不是两档 —— ★ 第一版我按「头贡献 ≥ 60%」一刀切，★★ 但**完全线性的阶梯
    #   本身就会给出 ≈55%**，所以 60% 这条线会把真阶梯也误判成情况 B（★★★ 已改）。
    #   ★ 现在：中段有没有斜率（看符号和强度）和 第 1 档有没有明显超出趋势线，**分开报**。
    中段同向 = (np.isfinite(sp中) and abs(sp中) >= 0.5 and (sp中 * sp > 0 if sp else False))
    头独大 = (np.isfinite(头贡献) and 头贡献 >= 80)
    情况 = ("★★★ 判不了（总差≈0）" if not 总差 else
            ("★ **情况 A：真阶梯**（★★ 中段 2~9 档也同向，★★★ 不是靠头上那一撮）"
             if (中段同向 and not 头独大) else
             (f"🟡 **A/B 混合**：★ 中段确实有斜率（中段 Spearman {sp中:+.2f}），"
              f"★★★ **但第 1 档明显超出趋势线**（它一个人就占了总差的 {头贡献:.0f}%，"
              f"★ 完全线性的阶梯只该占 ≈55%）"
              if 中段同向 else
              f"★★★★★ **情况 B：只有头上那一撮**（★ 中段 2~9 档 Spearman 只有 "
              f"{sp中:+.2f}，★★ 第 1 档占总差 {头贡献:.0f}%）—— ★★★ 《83》说的「挖出来的」那一种")))
    return {
        "★★★★★情况A还是情况B(《83》第二步)": 情况,
        "★中段2~9档的Spearman": (round(sp中, 3) if np.isfinite(sp中) else None),
        "★第1档超额pct": round(float(ys[0]) * 100, 3),
        "★第10档超额pct": round(float(ys[档数 - 1]) * 100, 3),
        "★★第1档贡献占总差pct": (round(头贡献, 1) if np.isfinite(头贡献) else None),
        "期数": len(价差), "丢期(某档不足20只)": 丢期,
        "★★★十档阶梯(减同期SPY, pct)": 梯,
        # ★★★★★ 符号约定（★ 第一版我自己写反了，★★ 这一行就是防下次再反）：
        #   ★ 第 1 档 = **信号最强**那一档 → ★★ 真信号应当**档位越大、均值越小**
        #   → ★★★ 所以「阶梯对」是 Spearman **负**；Spearman **正** = **倒阶梯（信号方向反了）**
        "★★★Spearman(档位 vs 均值)": round(sp, 3),
        "★★★★★Spearman怎么读": ("★ **负 = 阶梯对**（信号越强赚越多）；★★ **正 = 倒阶梯**"
                        "（信号越强赚越少 → 方向反了）"),
        "★单调递减的相邻步数(阶梯对的方向)": f"{单调步数}/{档数 - 1}",
        "★单调递增的相邻步数(倒阶梯的方向)": f"{档数 - 1 - 单调步数}/{档数 - 1}",
        "★★★第1档减第10档pct(均值)": round(float(a.mean()) * 100, 3),
        "★★★t值(按月, 不是按只×日)": (round(t, 2) if np.isfinite(t) else None),
        "★★★判定": (
            ("✅ **阶梯成立**（Spearman ≤ −0.7 且 t ≥ 2）"
             + ("　★★★★★ ⚠ **但它是情况 B** —— 只有第 1 档，不是阶梯"
                if 情况.startswith("★★★★★") else ""))
            if (sp <= -0.7 and np.isfinite(t) and t >= 2)
            else ("❌ **倒阶梯**（Spearman ≥ +0.7 且 t ≤ −2）—— ★★★ 信号方向**反了**"
                  if (sp >= 0.7 and np.isfinite(t) and t <= -2)
                  else (f"🟡 只是方向（{'阶梯对' if sp < 0 else '倒阶梯'}那一侧 Spearman 够，"
                        f"但 t 只有 {t:+.2f}）"
                        if abs(sp) >= 0.7 else "🟡 **不是阶梯**（Spearman 不够，十档是乱的）"))),
        "★★逐年(规矩㉗)": 逐年,
    }


def main() -> int:
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev = set(hold["研发池名单"])
    w = pd.read_parquet(PANEL)
    cl, hi, lo, vol, dv = w["close"], w["high"], w["low"], w["volume"], w["dollar_volume"]
    del w
    cols = [c for c in cl.columns if str(c) in dev]
    cl, hi, lo, vol, dv = (x[cols] for x in (cl, hi, lo, vol, dv))
    print(f"★ 研发池命中面板 {len(cols)} 只（名单 {len(dev)} 只）", flush=True)

    脏 = 脏格(cl, vol)
    adv = dv.rolling(60, min_periods=40).mean()
    可用 = (cl > 0) & cl.notna() & (adv >= ADV闸) & (~脏)
    print(f"★★★ 可用只×日 {int(可用.to_numpy().sum()):,}；"
          f"★ 其中被脏日剔掉 {int((脏 & (cl > 0)).to_numpy().sum()):,} 格", flush=True)

    from engine import data
    spy = data.load_benchmark("SPY")["close"].reindex(cl.index).ffill()
    sigs = 建信号(cl, hi, lo, dv)
    调仓日 = [g.index[0] for _, g in cl.groupby([cl.index.year, cl.index.month])]
    调仓日 = [d for d in 调仓日 if d >= pd.Timestamp("2016-01-01")]
    print(f"★ 调仓期数 {len(调仓日)}（{调仓日[0].date()} → {调仓日[-1].date()}）", flush=True)

    out = {"★★★这一份是什么": "《83》第二步 · 分档组合单调性 —— ★ 五步里唯一一次都没做过的那一步",
           "★口径": {
               "池子": f"研发池 {len(cols)} 只（名单 2,224；留出池 583 和考卷 1,042 不碰）",
               "流动性闸": f"60 日均成交额 ≥ {ADV闸:,.0f} 美元/天",
               "脏日": "★★★ 和《93》完全同一个四份并集（906 只）→ 跨脏日的只×日整格剔掉",
               "调仓": f"每月第一个交易日，共 {len(调仓日)} 期",
               "★★★★★滞后(规矩㉙)": "信号只用到第 t 天收盘；收益从第 t+1 天收盘量到第 t+1+N 天收盘"
                              " —— ★ 信号和收益窗口**不重叠一天**",
               "基准": "同窗口 SPY（逐档减掉）",
               "档": f"{档数} 档，每档不足 {每档最少} 只则整期不用（并报丢期数）",
               "★★★判据": "① Spearman(档位 vs 档均) ② 第1档减第10档的**月度时序** t（按月聚类）"
                      " ③ 逐年再报一遍（规矩㉗）",
               "★★⑥成交额那一条是阳性对照": "《98》第三节已实测「流动性闸越严 alpha 越小」"
                                " → ★★★ 如果这把尺子有分辨力，⑥ 应当看得出阶梯",
           }, "逐信号": {}}

    for N in 前瞻:
        for 名, sig in sigs.items():
            r = 一个信号(名, sig, cl, 可用, spy, 调仓日, N)
            out["逐信号"].setdefault(f"前瞻{N}个交易日", {})[名] = r
            if "★跑失败" in r:
                print(f"✗ N={N:2d} {名[:22]:22s} {r['★跑失败']}", flush=True)
            else:
                print(f"✓ N={N:2d} {名[:22]:22s} Spearman {r['★★★Spearman(档位 vs 均值)']:+.2f} "
                      f"| 1档−10档 {r['★★★第1档减第10档pct(均值)']:+.3f}% "
                      f"t={r['★★★t值(按月, 不是按只×日)']} | {r['★★★判定']}", flush=True)

    # ★★★ 多重检验的账（★ 规矩：《83》第五步 —— 这一轮跑了 N 个检验）
    检 = [v for g in out["逐信号"].values() for v in g.values() if "★跑失败" not in v]
    正 = [k for g in out["逐信号"].values() for k, v in g.items()
          if "★跑失败" not in v and (v["★★★t值(按月, 不是按只×日)"] or 0) >= 2]
    负 = [k for g in out["逐信号"].values() for k, v in g.items()
          if "★跑失败" not in v and (v["★★★t值(按月, 不是按只×日)"] or 0) <= -2]
    out["★★★多重检验的账"] = {"检验数": len(检), "运气约给": round(len(检) * 0.05, 2),
                       "正显著": 正, "负显著": 负,
                       "★★★读法": "★ 正显著个数要**多于**运气该给的个数，否则「我们找到有用信号」不算数"}
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print("\n★★★ 多重检验:", json.dumps(out["★★★多重检验的账"], ensure_ascii=False))
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
