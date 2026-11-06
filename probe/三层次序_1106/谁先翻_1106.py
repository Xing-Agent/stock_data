# -*- coding: utf-8 -*-
"""
★★★ 个股先翻,还是大盘先翻? —— 第 40 轮「要干啥」第 5 件。

★ 为什么这件最便宜又最要紧:
  ★★ 它同时验两样 ——
     · Lin 的框架:「大盘是**原因**,但变化最终落在个股自己的阶段上」
     · Gemini 的推断:「中位数股票跌破自己的 200 日线,比标普早 **30–90 个交易日**」
       ★★★ 它自己标了这是**推断**,而我们的数据能直接测。

★★ 做法(只用现成数据,不重跑回测):
  ① 找出 SPY 每一次「跌破 200 日线」和「站回 200 日线」的日期
  ② 对研发池每只票,算它自己跌破/站回**自己的** 200 日线的日期
  ③ 对每一次大盘事件,算「池子里中位数股票的翻转日」比大盘早/晚几个交易日
★★★ 只用研发池,考卷不碰。
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.abspath("."))
from engine import data as edata                               # noqa: E402

OUT = "probe/三层次序_1106"
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
MA = 200


def 翻转日(px: pd.Series, ma: int = MA) -> tuple[list, list]:
    """★ 返回 (跌破日列表, 站回日列表)。★★ 只用当天及以前的数据。"""
    m = px.rolling(ma, min_periods=ma).mean()
    above = (px > m).where(m.notna())
    a = above.dropna()
    if a.empty:
        return [], []
    chg = a.astype(int).diff()
    down = list(a.index[chg == -1])      # True→False = 跌破
    up = list(a.index[chg == 1])         # False→True = 站回
    return down, up


def main() -> int:
    spy = edata.load_benchmark("SPY")["close"].astype(float)
    s_down, s_up = 翻转日(spy)
    print(f"★ SPY 跌破 200 日线 {len(s_down)} 次 · 站回 {len(s_up)} 次", flush=True)

    wide = pd.read_parquet(PANEL)
    cl = wide["close"]
    dev = set(json.load(io.open(HOLD, encoding="utf-8"))["研发池名单"])
    cols = [c for c in cl.columns if c in dev]
    cl = cl[cols]
    cal = cl.index
    pos = {d: i for i, d in enumerate(cal)}

    # ★ 每只票自己的翻转日
    个股down, 个股up = {}, {}
    for s in cols:
        d, u = 翻转日(cl[s].dropna())
        个股down[s] = [x for x in d if x in pos]
        个股up[s] = [x for x in u if x in pos]
    print(f"★ 研发池 {len(cols)} 只 · 个股跌破事件合计 "
          f"{sum(len(v) for v in 个股down.values())} 次", flush=True)

    def 最近一次(事件表: dict, 基准日, 窗口=250) -> list:
        """★ 对每只票,找它在基准日前后 ±窗口 个交易日内**最接近**的那次翻转,
        ★★ 返回「相对基准日的交易日差」(负=个股更早)。"""
        b = pos.get(基准日)
        if b is None:
            return []
        out = []
        for s, ds in 事件表.items():
            diffs = [pos[d] - b for d in ds if abs(pos[d] - b) <= 窗口]
            if diffs:
                out.append(min(diffs, key=abs))
        return out

    结果 = {"★口径": {
        "大盘": "SPY 收盘 vs 200 日均线(min_periods=200)",
        "个股": "各自收盘 vs 自己的 200 日均线,同口径",
        "池": f"新池研发池 {len(cols)} 只(⚠ 考卷不碰)",
        "匹配办法": "对每次大盘事件,取每只票在 ±250 个交易日内**最接近**的一次翻转,"
                    "报「相对大盘的交易日差」,负=个股更早",
        "★★★ 要验的推断": "Gemini:中位数股票跌破自己 200 日线比标普早 30–90 个交易日"
                           "(★ 它自己标为推断)",
    }, "大盘跌破": [], "大盘站回": []}

    for 名, 大盘事件, 个股表 in (("大盘跌破", s_down, 个股down),
                                 ("大盘站回", s_up, 个股up)):
        for d in 大盘事件:
            diffs = 最近一次(个股表, d)
            if len(diffs) < 50:
                结果[名].append({"大盘日": str(d.date()), "可比只数": len(diffs),
                                "★状态": "可比只数<50,算不出"})
                continue
            arr = np.array(diffs, float)
            结果[名].append({
                "大盘日": str(d.date()), "可比只数": len(arr),
                "★中位数差(交易日)": float(np.median(arr)),
                "25分位": float(np.percentile(arr, 25)),
                "75分位": float(np.percentile(arr, 75)),
                "个股更早的比例": float((arr < 0).mean()),
            })
    os.makedirs(OUT, exist_ok=True)
    io.open(os.path.join(OUT, "谁先翻_1106.json"), "w", encoding="utf-8").write(
        json.dumps(结果, ensure_ascii=False, indent=1))

    for 名 in ("大盘跌破", "大盘站回"):
        rows = [r for r in 结果[名] if "★中位数差(交易日)" in r]
        print(f"\n=== {名}（{len(rows)} 次可算）===")
        print(f"{'大盘日':12s} {'可比只数':>7s} {'中位差':>8s} {'个股更早占比':>11s}")
        for r in rows:
            print(f"{r['大盘日']:12s} {r['可比只数']:7d} "
                  f"{r['★中位数差(交易日)']:+8.0f} {r['个股更早的比例']:11.1%}")
        if rows:
            med = np.median([r["★中位数差(交易日)"] for r in rows])
            print(f"   ★★★ 全部事件的中位差: {med:+.0f} 个交易日"
                  f"（负=个股更早）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ══════════════════════════════════════════════════════════════════════════
# ★★★ 补一个**无偏**的量法(1106 追加)
#   ★ 上面那个「取 ±250 天内最接近的一次翻转」**天生偏向 0** ——
#     一只票翻转次数多的话,总能在大盘事件附近找到一次,
#     ★★★ 所以那个中位差 +0 可能是量法造出来的,不是事实。本函数不受这个影响。
#   ★★ 新量法:**大盘跌破那天,已经有多少比例的股票早就在自己 200 日线下方了。**
#     · 如果 Lin / Gemini 对(个股先翻)→ 这个比例应该**明显高于 50%**
#     · 如果大盘先翻 → 应该**明显低于 50%**
#     · 50% 附近 = 同步
# ══════════════════════════════════════════════════════════════════════════
def 无偏量法() -> int:
    spy = edata.load_benchmark("SPY")["close"].astype(float)
    s_down, s_up = 翻转日(spy)
    wide = pd.read_parquet(PANEL)
    cl = wide["close"]
    dev = set(json.load(io.open(HOLD, encoding="utf-8"))["研发池名单"])
    cl = cl[[c for c in cl.columns if c in dev]]
    ma = cl.rolling(MA, min_periods=MA).mean()
    below = (cl < ma).where(ma.notna() & cl.notna())      # ★ NaN 的不算分母

    out = {"★口径": {
        "★这是什么": "大盘跌破/站回自己 200 日线那天,已经在自己 200 日线下方的股票比例",
        "★为什么用它": "不受「取最接近一次」那个偏差影响 —— 它只看当天的横截面状态",
        "怎么读": "跌破日的比例**明显 >50%** = 个股先翻;**<50%** = 大盘先翻;≈50% = 同步",
        "分母": "当天有有效 200 日均线的股票数(NaN 不计)",
    }, "大盘跌破日": [], "大盘站回日": []}
    for 名, 事件 in (("大盘跌破日", s_down), ("大盘站回日", s_up)):
        for d in 事件:
            if d not in below.index:
                continue
            row = below.loc[d].dropna()
            if len(row) < 50:
                out[名].append({"日": str(d.date()), "★状态": f"分母只有 {len(row)},算不出"})
                continue
            out[名].append({"日": str(d.date()), "分母": int(len(row)),
                            "★已在自己200日线下方的比例": round(float(row.mean()), 4)})
    io.open(os.path.join(OUT, "谁先翻_无偏量法_1106.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1))
    for 名 in ("大盘跌破日", "大盘站回日"):
        rows = [r for r in out[名] if "★已在自己200日线下方的比例" in r]
        print(f"\n=== {名}（{len(rows)} 次）===")
        for r in rows[:40]:
            print(f"   {r['日']}  分母 {r['分母']:5d}  已在线下 {r['★已在自己200日线下方的比例']:6.1%}")
        if rows:
            v = [r["★已在自己200日线下方的比例"] for r in rows]
            print(f"   ★★★ 中位数 {np.median(v):.1%}  （>50% = 个股先翻）")
    return 0


if __name__ == "__main__" and "--unbiased" in sys.argv:
    raise SystemExit(无偏量法())
