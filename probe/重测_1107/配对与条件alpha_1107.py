# -*- coding: utf-8 -*-
"""★★★ 配对检验（规矩㊸v2 第①道）+ 条件 alpha 交互项回归（本批跑前登记的主判据）。

★★ 这一份只读 `日序列_1107/`（每日净值 · 每日敞口）和 `arms_1107/`，★ 不碰跑批、不改 engine。

★★★ 它为什么必须存在：规矩㊸v2 写死「任何『A 比 B 好』的比较，必须先做配对检验」，
  ★ 而配对要的是**同一天同一批信号逐日相减** —— 要日收益序列。
  ★★ 原来的跑批只存逐笔流水，日序列是 1107 夜补的覆盖层才存下来的。

★ 三件产出：
  ① **配对检验**：A原样 vs 每条 R随机，日超额逐日相减 → Newey-West t
  ② **条件 alpha**：策略日收益 ~ 指数日收益 + 环境×指数日收益，看**交互项**的 NW t
  ③ **随机对照的离散度**：★★★ 按规矩㊾ 报分位数 + **偏度**，★ 并诚实标明 N 够不够估分位数

★★ 口径（规矩㊼ 五字段，每份产出都带）：全收益 · 摩擦档跟原样臂 · 窗口 · 池 · 标签滞后 1 天。
"""
from __future__ import annotations
import glob, hashlib, io, json, os, sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DS = os.path.join(HERE, "日序列_1107")
ARMS = os.path.join(HERE, "arms_1107")
NW_LAG = 8          # ★ 《93》第六节第 7 条：Newey-West 滞后阶数按公式取 8（原来用 5）


def 臂hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:16]


def 读日序列(label: str) -> pd.DataFrame | None:
    p = os.path.join(DS, f"d_{臂hash(label)}.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p, parse_dates=["日期"]).set_index("日期")
    return d


def 日收益(label: str) -> pd.Series | None:
    d = 读日序列(label)
    if d is None or len(d) < 30:
        return None
    r = d["净值"].astype(float).pct_change()
    return r.dropna()


# ────────────────────────────────────────────────────────────── Newey-West
def nw_t(x: pd.Series, lag: int = NW_LAG) -> dict:
    """★ 对「均值是否为 0」做 Newey-West(HAC) 修正的 t 检验。

    ★★ 用的是 statsmodels 的 HAC —— ★★★ 不自己手写核权重（规矩：不许凭记忆写公式）。
    ★ 同时报**标准差**（单次的离散度）和**标准误**（均值的精度）—— 规矩㊹：
      比单次用标准差、比均值用标准误，★★ 并且写明用的是哪一把。
    """
    import statsmodels.api as sm
    x = pd.Series(x).astype(float).dropna()
    n = len(x)
    if n < 30:
        return {"★样本不够": n}
    X = np.ones((n, 1))
    m = sm.OLS(x.to_numpy(), X).fit(cov_type="HAC", cov_kwds={"maxlags": lag})
    return {"n": int(n), "均值": float(m.params[0]),
            "★标准差(单次离散度)": float(x.std(ddof=1)),
            "★NW标准误(均值精度)": float(m.bse[0]),
            "★★★NW_t": float(m.tvalues[0]), "p": float(m.pvalues[0]),
            "★NW滞后阶": lag,
            "★用的哪把尺子": "检验的是**均值是否为 0**，所以用标准误（规矩㊹）"}


def 配对检验(a: str, b: str) -> dict:
    """★★★ 同一天逐日相减再检验 —— ★ 规矩㊸v2 第①道。

    ★★ 为什么必须配对：两条臂走的是**同一段行情**，市场起伏互相抵消，
      ★★★ 配对差的噪声远小于两条各跑各的再比均值。
    """
    ra, rb = 日收益(a), 日收益(b)
    if ra is None or rb is None:
        return {"★算不了": f"缺日序列（a={ra is not None} b={rb is not None}）"}
    共同 = ra.index.intersection(rb.index)
    if len(共同) < 30:
        return {"★算不了": f"共同交易日只有 {len(共同)} 天"}
    d = (ra.reindex(共同) - rb.reindex(共同))
    out = {"★A": a, "★B": b, "★共同交易日": int(len(共同)),
           "★★★配对差(A−B)的检验": nw_t(d)}
    t = out["★★★配对差(A−B)的检验"].get("★★★NW_t")
    out["★怎么写这一句"] = (
        "★★★ 配对已做 → 可以说方向" if t is not None else "★★★ 待配对检验")
    return out


# ────────────────────────────────────────────── 条件 alpha（交互项回归）
def 取指数与环境(start: str, end: str) -> pd.DataFrame:
    """★ 指数日收益（SPY **全收益**，和策略侧同口径）+ 环境标签（200 日线，**滞后 1 天**）。

    ★★★ 两件硬口径：
      ① SPY 必须用**全收益**（分红再投）—— 策略侧开了全收益，基准侧不开就是
         单方面给自己加分（规矩㊽ / #77）。
      ② 环境标签必须 `shift(1)`：★★★ 用当天的状态决定当天在不在场 = #68 那处错。
    """
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
    cwd = os.getcwd(); os.chdir(ROOT)
    try:
        import 接新基准_1107 as BM
        import 分红覆盖层_1107 as DV
        from engine import data as edata
        BM.install(); DV.install()
        px = BM._覆盖("SPY")
        close = px["close"].astype(float) if "close" in px.columns else px.iloc[:, 0].astype(float)
        div = edata.dividends("SPY")
        # ★★★ 全收益：把现金分红当天按收盘价再投（和 chain.py 的 cash += gain 同一意思）
        d = pd.Series(0.0, index=close.index)
        if div is not None and len(div):
            共同 = close.index.intersection(pd.DatetimeIndex(div.index))
            d.loc[共同] = pd.Series(div).astype(float).reindex(共同).fillna(0.0).to_numpy()
        指数日收益 = ((close + d) / close.shift(1) - 1.0)
        ma200 = close.rolling(200, min_periods=200).mean()
        线上 = (close > ma200)
        df = pd.DataFrame({"指数日收益": 指数日收益,
                           "环境_线上": 线上.shift(1)})      # ★★★ 滞后 1 天，不偷看
        df = df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
        return df.dropna()
    finally:
        os.chdir(cwd)


def 条件alpha(label: str, start: str, end: str, 指环: pd.DataFrame | None = None) -> dict:
    """★★★ 策略日收益 ~ 指数日收益 + 环境×指数日收益，看**交互项**的 NW t。

    ★ 门槛（《102》第六节，跑前写死）：**|t| > 3** —— ★★ 因为 3 族 × 3 个均线档 = 9 次检验（HLZ 2016）。
      ★★★ 这个数不许报的时候再放宽。
    """
    import statsmodels.api as sm
    r = 日收益(label)
    if r is None:
        return {"★算不了": "缺日序列"}
    ie = 取指数与环境(start, end) if 指环 is None else 指环
    共同 = r.index.intersection(ie.index)
    if len(共同) < 200:
        return {"★算不了": f"共同交易日只有 {len(共同)} 天"}
    y = r.reindex(共同).to_numpy(dtype=float)
    mkt = ie["指数日收益"].reindex(共同).to_numpy(dtype=float)
    on = ie["环境_线上"].reindex(共同).to_numpy().astype(float)
    X = np.column_stack([np.ones(len(共同)), mkt, on, on * mkt])
    m = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": NW_LAG})
    名 = ["截距(alpha)", "指数日收益(beta)", "环境", "★★★交互项 环境×指数"]
    return {"★臂": label, "n": int(len(共同)),
            "★关闸天数占比": float(1.0 - np.nanmean(on)),
            **{f"{名[i]}": {"系数": float(m.params[i]), "NW_t": float(m.tvalues[i])}
               for i in range(4)},
            "★★★交互项_NW_t": float(m.tvalues[3]),
            "★★★门槛": "|t| > 3（《102》第六节：9 次检验，HLZ 2016）—— ★ 跑前写死",
            "★★★过没过": ("过" if abs(float(m.tvalues[3])) > 3 else "没过"),
            "★NW滞后阶": NW_LAG}


# ──────────────────────────────────────── 随机对照的离散度（规矩㊾ + ㊹）
def 随机离散度(真值: float, 随机值: list[float]) -> dict:
    """★★★ 规矩㊾：报**分位数**，★ 偏度必须跟着一起报；★★ 不许用均值 ±2σ 单独下结论。

    ★★★ 并且诚实标明 **N 够不够估 2.5/97.5 分位数** ——
      ★ N=10 时「2.5 分位数」其实就是最小值，★★ 那不是一个能用的分位数估计。
    """
    v = np.asarray([x for x in 随机值 if x is not None and np.isfinite(x)], dtype=float)
    n = len(v)
    if n < 3:
        return {"★样本不够": n}
    from scipy import stats
    sd = float(v.std(ddof=1))
    out = {
        "★随机臂数N": int(n), "★随机均值": float(v.mean()),
        "★★★随机单次标准差(比单次用这把，规矩㊹)": sd,
        "★随机均值的标准误(只能用来比均值)": sd / np.sqrt(n),
        "★★★偏度": float(stats.skew(v, bias=False)),
        "★①均值±2sd": [float(v.mean() - 2 * sd), float(v.mean() + 2 * sd)],
        "★②分位数2.5_97.5": [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))],
        "★最小_最大": [float(v.min()), float(v.max())],
        "★真值": float(真值),
        "★真值距随机均值_以单次标准差计": float((真值 - v.mean()) / sd) if sd > 0 else None,
        "★真值在随机里的分位": float((v < 真值).mean()),
    }
    if n < 40:
        out["★★★分位数能不能用"] = (
            f"★★★ **不能当分位数用** —— N={n}，2.5/97.5 分位数实际就是最小/最大值附近，"
            f"★ 是极值不是分位数。★★ 规矩㊾ 要的三种区间这里只有「均值±2sd」是可算的，"
            f"★★★ 要真按㊾ 办需要 N ≥ 100（本批预先登记只给了 10 个种子）。")
    else:
        out["★★★分位数能不能用"] = f"N={n}，可以"
    out["★★★这一行只许怎么写"] = (
        "★ 只许写「真值落在随机 N 条臂的什么位置」+ 偏度；"
        "★★★ 「比随机好/差」这类话**必须先做配对检验**（规矩㊸v2）")
    return out


# ───────────────────────────────────────────────────── 逐笔流水的两件
def 最长连亏(ledger_csv: str) -> dict:
    """★★ 最长连亏几笔 —— ★★★ 这是用户真正会放弃的地方（本工单第 4 条）。

    ★ 按**离场日**排序数连亏（★ 不是按进场日：用户体验到的是账面上一笔笔平掉的顺序）。
    """
    d = pd.read_csv(ledger_csv)
    if not len(d):
        return {"★笔数": 0}
    d = d.sort_values("exit_date")
    r = d["r_multiple_net"].astype(float).to_numpy()
    亏 = r < 0
    最长 = cur = 0
    for b in 亏:
        cur = cur + 1 if b else 0
        最长 = max(最长, cur)
    # ★ 连亏那一串最多亏掉多少 R（累计）
    最差累计 = cur = 0.0
    for x in r:
        cur = min(0.0, cur + x)
        最差累计 = min(最差累计, cur)
    return {"★笔数": int(len(d)), "★亏的笔数": int(亏.sum()),
            "★胜率": float(1 - 亏.mean()),
            "★★★最长连亏笔数": int(最长),
            "★★★逐笔累计最差(R)": float(最差累计),
            "★口径": "按 exit_date 排序；r_multiple_net（净 R，已扣摩擦）"}


def 没新高多少天(label: str) -> dict:
    """★★★ 历史上最多多少天没创新高 —— ★ 要净值曲线（这就是为什么必须存日序列）。"""
    d = 读日序列(label)
    if d is None:
        return {"★算不了": "缺日序列"}
    eq = d["净值"].astype(float)
    峰 = eq.cummax()
    在水下 = eq < 峰
    最长 = cur = 0
    for b in 在水下.to_numpy():
        cur = cur + 1 if b else 0
        最长 = max(最长, cur)
    回撤 = (eq / 峰 - 1.0)
    return {"★交易日数": int(len(eq)),
            "★★★最多连续多少个交易日没新高": int(最长),
            "★约等于几个月": round(最长 / 21.0, 1),
            "★最大回撤": float(回撤.min()),
            "★期末净值倍数": float(eq.iloc[-1] / eq.iloc[0])}
