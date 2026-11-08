# -*- coding: utf-8 -*-
"""★★★ 出数 —— ★ 只读。把跑完的臂变成《102》要求的那几个数。

★★ 三秒版：这个脚本**不跑回测**，只读已经落盘的臂 / 流水 / 日净值，
   ★★★ 算四样东西：赢没赢随机 · 比不比得过标普全收益 · 买的是大票还是小票 · 最长连亏。

★★★ 它刻意做不到的事（规矩）：
  · ★ 不会把还在跑的跑批的任何计数写进结论句 —— ★★ 臂数不齐就在表头写「★进行中」。
  · ★★ 两条臂的差别，没做配对检验之前一律写「**待配对检验**」（规矩㊸v2），
    ★★★ 不许写「更好」，也不许写「分不出」。
  · ★ 不写「建议挂 / 不挂」。★★★ 结论由 Lin 定。
"""
from __future__ import annotations
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
# ★★★ 1108 主路：这三个目录原来写死 —— ★ 跑批侧早就能用 XING_ARMS_DIR / XING_DS_DIR
#   换目录，★★ 出数侧换不了 → 只能靠改名字去凑，★★★ 而改名字就是 #96 那一类
#   「同一个目录里新旧混着」。所以也给环境变量（默认值不变）。
ARMS = os.path.join(HERE, os.environ.get("XING_ARMS_DIR", "arms_1107"))
LEDG = os.path.join(HERE, os.environ.get("XING_LEDG_DIR", "ledgers_1107"))
CURV = os.path.join(HERE, os.environ.get("XING_NAV_DIR", "日净值_1107"))
池表 = os.path.join(ROOT, "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv")

# ★★★ 预先登记的门槛（《102》第六节）—— ★ 出数的时候不许改
门槛_第四档 = 3.0        # ★ 3 族 × 3 个均线档 = 9 次检验 → HLZ(2016) |t| > 3
门槛_配对 = 2.5          # ★★ 单独一次配对检验（不属于那 9 次）用 2.5


# ============================================================ 读
def 读臂(窗口名: str | None = None) -> pd.DataFrame:
    """★★★ 1108 修（错号 #95）：**必须按窗口过滤**。

    ★ 原来这里把 `arms_1107/` 里的臂**全读进来**，main 里只按「族」分组 ——
      ★★ 而 A 段（2004~2014）和 B 段（2015~2025）的臂**同在一个目录**，
      ★★★ 于是 `g["链"].iloc[0]` 很可能抓到**另一个窗口**那条 A原样：
        · 出 B 段报告时，大波段 / 震荡 抓到的是 A 段那条 →
          尺子②「重叠交易日只有 0 天」（2004~2014 的曲线对 2015~2025 的日期）、
          持仓画像里出现 YHOO / COP、最大回撤 −72.45%（那是 2008 年那一段）。
        · 尺子③ 的「随机臂条数 20」也是两段混在一起（每段 10 条）。
    ★★★ 为什么必须喊出来：它**不报错**，只是悄悄换了一段数据 ——
      而「0 天重叠」那行看起来像缺数据，不像拿错窗口（#80 的同一类）。
    """
    rs = []
    for f in sorted(glob.glob(os.path.join(ARMS, "*.json"))):
        try:
            rs.append(json.load(open(f, encoding="utf-8")))
        except Exception:
            continue
    df = pd.DataFrame(rs)
    if 窗口名 and not df.empty:
        前 = len(df)
        df = df[df["链"].astype(str).str.startswith(f"{窗口名}·")].reset_index(drop=True)
        print(f"★★★ 按窗口过滤臂：{前} 条 → {len(df)} 条（窗口 {窗口名}）", flush=True)
        assert not df.empty, f"★★★ 这个窗口一条臂都没有：{窗口名}"
        坏 = [c for c in df["链"].astype(str) if not c.startswith(f"{窗口名}·")]
        assert not 坏, f"★★★ 过滤没干净：{坏[:3]}"
    return df


def 读日净值(label: str) -> pd.Series | None:
    """★ 返回该臂的**日收益率**序列（已扣摩擦）。"""
    p = os.path.join(CURV, f"{安全名(label)}.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p, parse_dates=["date"]).set_index("date")
    eq = d["equity"].astype(float).dropna()
    if len(eq) < 30:
        return None
    return eq.pct_change().dropna()


def 安全名(label: str) -> str:
    return label.replace("/", "_").replace(" ", "")


def 读流水(label: str) -> pd.DataFrame | None:
    p = os.path.join(LEDG, f"REAL__{安全名(label)}.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, parse_dates=["entry_date", "exit_date"])


# ============================================================ 尺子③：赢没赢随机
def 尺子三(df: pd.DataFrame, 族: str) -> dict:
    """★★★ 同池随机挑股对照。★ 风格暴露两边一样（同池、同十年、同样那些科技股），
    ★★ **唯一的差别是挑法** —— 所以这把尺子不受 Lin 1107 19:38 那个反对意见影响。"""
    g = df[df["族"] == 族]
    真 = g[g["臂"] == "A原样"]
    随 = g[g["臂"].astype(str).str.startswith("R随机")]
    if 真.empty or len(随) < 2:
        return {"★算不出来": f"真臂 {len(真)} 条 · 随机臂 {len(随)} 条（不够）"}
    a = float(真["每笔净R"].iloc[0])
    xs = 随["每笔净R"].astype(float).to_numpy()
    # ★★★ 规矩㊹：用**随机单次的标准差**，不是均值的标准误（★ #73 在这里错过一次）
    sd = float(xs.std(ddof=1))
    z = (a - xs.mean()) / sd if sd > 0 else float("nan")
    return {"真臂每笔净R": round(a, 4),
            "随机臂条数": int(len(随)),
            "随机均值": round(float(xs.mean()), 4),
            "★★★随机单次标准差": round(sd, 4),
            "★★★差几个标准差(z)": None if sd <= 0 else round(z, 2),
            "★随机臂最好那条": round(float(xs.max()), 4),
            "★真臂排第几": int((xs >= a).sum() + 1),
            "★★口径": "z 用随机单次 SD（不是 SE）· 11 条臂里真臂排名",
            "★★★怎么读": ("★ z 只是「差几个标准差」，**不是 p 值**；"
                       "★★ 11 个种子估出来的 SD 本身很糙（Gemini 建议 ≥100 个）。")}


# ============================================================ 尺子②：比标普全收益
def 尺子二(label: str, 窗口起: str, 窗口止: str) -> dict:
    """★★★ 满仓标普五百**全收益**（分红再投，《104》拍板的甲案）。"""
    r = 读日净值(label)
    if r is None:
        return {"★算不出来": "这条臂没有日净值（★ 23:1x 之前跑的臂没存）"}
    try:
        sys.path.insert(0, os.path.join(ROOT, "probe/并池_1107"))
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "DV", os.path.join(ROOT, "probe/并池_1107/分红覆盖层_1107.py"))
        DV = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(DV)
        DV.install()
        nav = DV.全收益基准("SPY")
    except Exception as e:
        return {"★算不出来": f"取不到标普全收益：{type(e).__name__}: {e}"}
    nav = nav[(nav.index >= pd.Timestamp(窗口起)) & (nav.index <= pd.Timestamp(窗口止))]
    b = nav.pct_change().dropna()
    共 = r.index.intersection(b.index)
    if len(共) < 100:
        return {"★算不出来": f"重叠交易日只有 {len(共)} 天"}
    r, b = r.reindex(共), b.reindex(共)
    年 = 252.0

    def 年化(x):
        return float((1.0 + x).prod() ** (年 / len(x)) - 1.0)
    差 = r - b
    t = 配对t(差)
    return {"★策略年化": f"{年化(r)*100:+.2f}%",
            "★★★标普全收益年化": f"{年化(b)*100:+.2f}%",
            "★差": f"{(年化(r)-年化(b))*100:+.2f}pp/年",
            "★★重叠交易日": int(len(共)),
            "★★★配对检验": t,
            "★★口径": "甲案 = 全收益（分红再投）· 满仓标普 · 两边同口径"}


# ============================================================ 配对检验（规矩㊸v2）
def 配对t(差: pd.Series, lag: int | None = None, 门槛: float | None = None) -> dict:
    """★★★ 逐日差值的 Newey-West 修正 t 检验。★ 滞后期按持仓期定，默认 8。"""
    x = pd.Series(差).dropna().astype(float).to_numpy()
    n = len(x)
    if n < 60:
        return {"★算不出来": f"只有 {n} 天，不够"}
    L = int(lag if lag is not None else 8)
    # ★★★ 1108 修（错号 #96）：门槛要能传进来。★ 原来**写死** 门槛_配对=2.5，
    #   ★★ 于是第四档那 9 次检验（《102》第六节门槛 |t|>3）印出来的是「门槛 |t|>2.5」——
    #   ★★★ 口径行写 3.0、判决行写 2.5，两行自相矛盾。本轮三族 9 个 t 最大 1.47，
    #     两个门槛下都是「没过」，★ 所以**结论没被改**；但 t 落在 2.5~3.0 之间时会判反。
    门 = float(门槛 if 门槛 is not None else 门槛_配对)
    说 = "9 次检验，HLZ 2016" if 门 == 门槛_第四档 else "单次配对"
    m = x.mean()
    e = x - m
    g0 = float((e * e).sum() / n)
    s = g0
    for k in range(1, L + 1):
        gk = float((e[k:] * e[:-k]).sum() / n)
        s += 2.0 * (1.0 - k / (L + 1.0)) * gk      # ★ Bartlett 权
    if s <= 0:
        return {"★算不出来": "Newey-West 方差 ≤ 0"}
    t = m / np.sqrt(s / n)
    return {"逐日差均值": f"{m*1e4:+.3f} 个基点/天",
            "★★★NW修正t": round(float(t), 2),
            "★滞后期": L, "★天数": n,
            "★★★过没过门槛": (f"门槛 |t|>{门}（{说}）→ "
                         + ("**过了**" if abs(t) > 门 else "**没过**")),
            "★★注意": "★ 这是跑前写死的门槛（《102》第六节），★★★ 出数时不许放宽"}


# ============================================================ 第四档：A/B 配对
def 第四档(族标签前缀: str, 窗口起: str, 窗口止: str) -> dict:
    """★★★ 《102》第四档：A原样 vs B挂开关，**逐日相减** + Newey-West。

    ★★ 这是 Lin 一整天在讲的那条判断的**真正判据** ——
      ★ 条件 alpha 只说明「现象存在」，这一档说明「我们能不能吃到」。
    """
    出 = {"★★★口径": "逐日相减 · Newey-West 滞后 8 · 门槛 |t|>3（跑前写死，9 次检验）"}
    a = 读日净值(f"{族标签前缀}·A原样")
    if a is None:
        return {"★算不出来": "A原样 还没有日净值"}
    # ★★★ 红线②：三点都要报，★ 不许只报 200
    哈希 = {}
    for ma in (100, 200, 300):
        名 = f"B挂开关MA{ma}"
        b = 读日净值(f"{族标签前缀}·{名}")
        哈希[名] = 流水哈希(f"{族标签前缀}·{名}")
        if b is None:
            出[f"MA{ma}"] = "★★★ **待配对检验** —— 这条臂还没跑完"
            continue
        共 = a.index.intersection(b.index)
        if len(共) < 250:
            出[f"MA{ma}"] = {"★算不出来": f"重叠只有 {len(共)} 天"}
            continue
        关 = 关闸占比(ma, 窗口起, 窗口止)
        块 = {"★关闸天数占比": f"{关*100:.1f}%",
             **配对t(b.reindex(共) - a.reindex(共), 门槛=门槛_第四档)}
        # ★★★ 《102》情形三：闸太松等于没挂，太紧等于换了另一个策略 —— 两头都不是在测这件事
        if 关 < 0.05 or 关 > 0.50:
            块 = {"★★★这一档作废": f"关闸占比 {关*100:.1f}% 落在作废区间"
                            f"（<5% 或 >50%，《102》情形三）—— **不报 t 值**",
                 "★关闸天数占比": f"{关*100:.1f}%"}
        出[f"MA{ma}"] = 块
    # ★★★ 1106 的坑：params 写在 rule 顶层会**静默退回默认 200** → 逐字节比流水哈希
    有 = {k: v for k, v in 哈希.items() if v}
    出["★★★三条臂流水哈希"] = 哈希
    出["★★★三条真的不一样吗"] = (
        "★ 还不够三条，等跑完" if len(有) < 2 else
        ("**是**，三条流水逐字节不同" if len(set(有.values())) == len(有)
         else f"★★★ **不是！有重复** → 参数静默退回了，这一档作废：{有}"))
    return 出


def 流水哈希(label: str) -> str | None:
    import hashlib
    p = os.path.join(LEDG, f"REAL__{安全名(label)}.csv")
    if not os.path.exists(p):
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:16]


def 关闸占比(ma: int, 窗口起: str, 窗口止: str) -> float:
    """★ 这十年里有几成的天被闸掉了（闸 = 标普在均线下方）。"""
    from engine import data
    px = data.load_benchmark("SPY")["close"].dropna()
    上 = (px > px.rolling(ma).mean()).shift(1)
    上 = 上[(上.index >= pd.Timestamp(窗口起)) & (上.index <= pd.Timestamp(窗口止))].dropna()
    return float(1.0 - 上.mean()) if len(上) else float("nan")


# ============================================================ 条件 alpha 交互项
def 条件alpha(label: str, 窗口起: str, 窗口止: str, ma: int = 200) -> dict:
    """★★★ Lin 的核心判断能不能测出来，就看这个交互项。

    ★ 回归：策略日收益 = a + b·指数日收益 + c·(环境×指数日收益) + d·环境
    ★★ 环境 = 昨天标普在 200 日均线上方（1）还是下方（0）—— ★★★ 用 shift(1)，不偷看。
    ★ c 显著为正 = 「线上的时候，策略对指数的敏感度更高」→ **环境确实在起作用**。
    """
    r = 读日净值(label)
    if r is None:
        return {"★算不出来": "这条臂没有日净值"}
    try:
        from engine import data
        px = data.load_benchmark("SPY")["close"].dropna()
    except Exception as e:
        return {"★算不出来": f"取不到 SPY：{type(e).__name__}: {e}"}
    上方 = (px > px.rolling(ma).mean()).shift(1)        # ★★★ 滞后 1 天
    b = px.pct_change()
    共 = r.index.intersection(b.dropna().index).intersection(上方.dropna().index)
    共 = [d for d in 共 if pd.Timestamp(窗口起) <= d <= pd.Timestamp(窗口止)]
    if len(共) < 250:
        return {"★算不出来": f"重叠只有 {len(共)} 天"}
    y = r.reindex(共).to_numpy(float)
    m = b.reindex(共).to_numpy(float)
    e = 上方.reindex(共).to_numpy(float)
    X = np.column_stack([np.ones(len(y)), m, e * m, e])
    β, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ β
    # ★★ HAC(Newey-West) 稳健标准误，滞后 8
    n, k = X.shape
    L = 8
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for l in range(1, L + 1):
        A = (X[l:] * resid[l:, None]).T @ (X[:-l] * resid[:-l, None])
        S += (1.0 - l / (L + 1.0)) * (A + A.T)
    XtXi = np.linalg.pinv(X.T @ X)
    V = XtXi @ S @ XtXi
    se = np.sqrt(np.maximum(np.diag(V), 0.0))
    名 = ["截距(alpha)", "指数收益(beta)", "★★★环境×指数(交互项)", "环境(单独)"]
    出 = {名[i]: {"系数": round(float(β[i]), 5),
                 "t": (round(float(β[i] / se[i]), 2) if se[i] > 0 else None)}
         for i in range(k)}
    tc = float(β[2] / se[2]) if se[2] > 0 else float("nan")
    出["★★★主判据"] = (f"交互项 t = {tc:+.2f} · 门槛 |t|>{门槛_第四档}（9 次检验，HLZ 2016）→ "
                   + ("**过了**" if abs(tc) > 门槛_第四档 else "**没过**"))
    出["★环境口径"] = f"SPY 收盘 > {ma} 日均线（昨天的状态，shift(1)）"
    出["★线上天数占比"] = f"{float(np.nanmean(e))*100:.1f}%"
    出["★★★怎么读"] = ("★ 交互项为正 = 线上的时候策略跟涨得更多；"
                  "★★ 但这**只说明现象存在**，不等于「挂上开关就能吃到」——"
                  "★★★ 后者要《102》第四档的 A/B 配对。")
    return 出


# ============================================================ 持仓画像
def 持仓画像(label: str) -> dict:
    """★★ Lin 1107 19:38 问的那件事：突破信号到底有没有自己走到巨头上去。

    ★★★ 注意：池表的 `rank` 是**60 日成交额排名**，★ 不是市值排名 —— 不许写成市值。
    """
    led = 读流水(label)
    if led is None or led.empty:
        return {"★算不出来": "没有这条臂的流水"}
    try:
        p = pd.read_csv(池表, usecols=["year", "rank", "symbol"])
    except Exception as e:
        return {"★算不出来": f"读不到池表：{type(e).__name__}: {e}"}
    p = p.groupby(["year", "symbol"], as_index=False)["rank"].min()
    led = led.copy()
    led["year"] = led["entry_date"].dt.year
    j = led.merge(p, on=["year", "symbol"], how="left")

    def 档(r):
        if not np.isfinite(r):
            return "查不到排名"
        return "前500" if r <= 500 else ("501~1500" if r <= 1500 else "1500名以后")
    j["档"] = j["rank"].map(档)
    笔 = j["档"].value_counts()
    金 = j.groupby("档")["notional_in"].sum()
    总笔, 总金 = max(1, int(笔.sum())), max(1.0, float(金.sum()))
    出 = {"★按笔数": {k: f"{int(v)} 笔 = {v/总笔*100:.1f}%" for k, v in 笔.items()},
         "★★按买入金额": {k: f"{v/总金*100:.1f}%" for k, v in 金.items()},
         "★★★口径": "排名 = 池表 60 日成交额排名（★ 不是市值）· 按**进场那一年**的排名归档",
         "★查不到排名的笔数": int((j["rank"].isna()).sum())}
    前十 = (j.groupby("symbol")["notional_in"].sum().sort_values(ascending=False)
           .head(10) / 总金 * 100).round(1)
    出["★买得最多的十只(占买入金额%)"] = {k: float(v) for k, v in 前十.items()}
    return 出


# ============================================================ 最长连亏
def 最长连亏(label: str) -> dict:
    """★★ 产品说明书要的那个数 —— ★★★ 比年化更决定用户能不能拿得住。"""
    出 = {}
    led = 读流水(label)
    if led is not None and not led.empty and "net_pnl" in led:
        s = led.sort_values("exit_date")["net_pnl"].astype(float).to_numpy()
        best = cur = 0
        for v in s:
            cur = cur + 1 if v < 0 else 0
            best = max(best, cur)
        出["★最长连续亏损笔数"] = int(best)
        出["★总笔数"] = int(len(s))
        出["★亏损笔占比"] = f"{(s < 0).mean()*100:.1f}%"
        出["★★注意"] = "★★★ 亏损笔过半很正常 —— 每笔净R 是**赔率**，不是胜率"
    r = 读日净值(label)
    if r is not None:
        eq = (1.0 + r).cumprod()
        峰 = eq.cummax()
        水下 = eq < 峰 * (1 - 1e-12)
        best = cur = 0
        for v in 水下.to_numpy():
            cur = cur + 1 if v else 0
            best = max(best, cur)
        出["★★★最长多少个交易日没创新高"] = int(best)
        出["★★折合约几个月"] = round(best / 21.0, 1)
        出["★最大回撤"] = f"{float((eq/峰 - 1.0).min())*100:.2f}%"
    return 出 or {"★算不出来": "既没流水也没日净值"}


# ============================================================ 主
def 装基准覆盖层() -> dict:
    """★★★ 1108 修（错号 #97）：出数脚本**没装基准覆盖层**，读到的是引擎自带那份 SPY。

    ★ 引擎的 `data.load_benchmark("SPY")` 只扫 `pilot_300/benchmarks` 等老目录，
      ★★ 那份 **2014 年才开始**（这是 1106 就记下来的已知边界）。
    ★★★ 跑批侧装了 `接新基准_1107`（SPY 2004-01-02 起，5747 根），出数侧**没装** →
      A 段（2004~2014）这三样全是错的，而且**错得像缺数据，不像拿错数据**：
        · 尺子②「重叠交易日 251 天」—— ★ 那是 2014 一年，却按「A 段年化」印出来
        · 条件 alpha「线上天数占比 19.5%」—— ★ 同样只覆盖 2014
        · 关闸占比 MA200 = 80.5% / MA300 = 100% —— ★★ 均线算不出来时整段被当成「闸上」
          → ★★★ 反过来把这两档推进了《102》情形三的作废区间（>50%），
            看起来像「闸太紧」，其实是**基准没数据**。
    ★ B 段（2015~2025）不受影响（2014 起的 SPY 够它用），★★ 但 MA300 需要 300 天预热，
      ★★★ 装了覆盖层之后 2015 年初那段才算得出来 —— 所以 B 段也要重出一遍。
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "BM出数", os.path.join(ROOT, "probe/并池_1107/接新基准_1107.py"))
    BM = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(BM)
    证 = BM.install()
    from engine import data as _d
    px = _d.load_benchmark("SPY")["close"].dropna()
    证["★★★装完SPY覆盖到"] = f"{px.index.min().date()} → {px.index.max().date()} · {len(px)} 根"
    assert 证["★真的换掉了"], "★★★ 基准覆盖层没装上，停"
    assert str(px.index.min().date()) <= "2004-12-31", \
        f"★★★ SPY 还没拉到 2004：{px.index.min().date()}"
    print(f"★★★ 基准覆盖层（出数侧）: {json.dumps(证, ensure_ascii=False)}", flush=True)
    return 证


def main() -> int:
    窗口起 = os.environ.get("XING_WIN_START", "2015-01-01")
    窗口止 = os.environ.get("XING_WIN_END", "2025-12-31")
    窗口名 = os.environ.get("XING_WIN_NAME", "B_2015到2025")
    证_基准 = 装基准覆盖层()          # ★★★ 规矩 62：自证要落盘，只打印不算做过
    df = 读臂(窗口名)
    if df.empty:
        print("★ 还没有任何臂落盘。")
        return 0
    齐 = {族: int((df["族"] == 族).sum()) for 族 in sorted(df["族"].unique())}
    报 = {
        # ★★★ 规矩㊼：五个字段的「本次口径」表头，少一个这份报告作废
        "【本次口径】": (f"全收益（分红再投，两侧同口径）· 摩擦档 三档friction_tiers · "
                   f"窗口 {窗口起}~{窗口止} · 池 并池2004(3858,一档) · 标签滞后 1 天"),
        "★★★臂数": 齐,
        "★★★基准覆盖层自证(出数侧)": 证_基准,
        "★★★跑批跑完了吗": ("**没跑完**（★ 规矩：还在跑的跑批，任何计数不许进结论句）"
                      if min(齐.values()) < 11 else "★ 本段这些族已齐（11 条/族）"),
        "逐族": {},
    }
    for 族 in 齐:
        label = None
        g = df[(df["族"] == 族) & (df["臂"] == "A原样")]
        if not g.empty:
            label = str(g["链"].iloc[0])
        块 = {"★★★尺子③_赢没赢随机": 尺子三(df, 族)}
        if label:
            块["★★★尺子②_比标普全收益"] = 尺子二(label, 窗口起, 窗口止)
            块["★★★条件alpha_交互项"] = 条件alpha(label, 窗口起, 窗口止)
            块["★★持仓画像"] = 持仓画像(label)
            块["★★最长连亏"] = 最长连亏(label)
            前缀 = label.rsplit("·", 1)[0]      # ★ 去掉臂名，留到 技-1 那一层
            块["★★★第四档_挂开关"] = 第四档(前缀, 窗口起, 窗口止)
        报["逐族"][族] = 块
    # ★ 1108：加个后缀，免得两批同名互相盖（默认值不变）
    out = os.path.join(HERE, f"出数_{窗口名}{os.environ.get('XING_OUT_TAG', '_1107')}.json")
    open(out, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
