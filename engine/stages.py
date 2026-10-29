"""
状态引擎(阶段判定)—— 参考实现 / 对照答案。

================================================================================
三秒版
================================================================================
这个文件回答一个问题:**这只票今天是在底部、在上涨、还是在下跌。**
它吐出五个状态之一:上涨段 / 上涨段回踩 / 下跌段 / 下跌段反弹 / 震荡。

这是**生产口径**,不是实验版。参数不许改。
它存在的唯一目的是:运营那边的脚本和我们这边算出来的,要能逐日对上。

★ 为什么单独一个文件、而且只用 numpy/pandas:
  运营要能直接 `python -m engine.stages --demo AAPL` 跑起来,
  不用装我们整套引擎(cache / data / matrices 一个都不依赖)。
  所以这里**故意**重新实现了一个最小的 json 读取器 —— 冗余是有意的。

跑法:
    python -m engine.stages --symbol AAPL                  # 看单只票
    python -m engine.stages --selftest                     # 自检(含两个坑的回归测试)
    python -m engine.stages --table SYM1,SYM2 --out x.csv  # 出逐日对照表

================================================================================
口径(★ 生产定义,参数不许动)
================================================================================
    MA_N      = 150   日均线 —— 牛熊分界线
    ER_WIN    = 30    效率比率窗口
    ER_IN     = 0.35  进入趋势态门槛
    ER_OUT    = 0.25  退出趋势态门槛(滞回 1.4 : 1)
    MA_FAST   = 20    日均线 —— 判「有没有像样的反弹/回踩」
    CHOP_BARS = 3     连续几根低效率才算真的转成震荡

================================================================================
★★ 两个已经踩过的坑(重建时必须避开,文件末尾有回归测试守着)
================================================================================
坑 ①  BEAR_RALLY 一次都不出现。
      原因:中间量(到快线的距离)当初只在「价格低于慢线」时才算,
      价格一站上慢线就置 NaN —— 于是「跌势里反弹到快线上方」这个
      组合在数据上永远不存在,状态永远判不出来。
      ★ 本实现的做法:**所有中间量一律在全样本上无条件计算**,
        不做任何条件遮罩(见 _intermediates),只在最后一步用布尔组合挑状态。
      守门测试:selftest 第 ① 项,BEAR_RALLY 计数必须 > 0。

坑 ②  用 numpy 的布尔值做身份比较会静默失败:
          np.True_ is True   →  False
      所以本文件里**一律**用 bool(x) 转换或直接取真值,
      绝不写 `x is True` / `x is False`。
      守门测试:selftest 第 ② 项,扫本文件源码确认没有这种写法。
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

# ============================================================================
# 参数 —— 每一个旁边注明出处
# ============================================================================

MA_N = 150
# 出处:原著。Stan Weinstein《Secrets for Profiting in Bull and Bear Markets》(1988)
# 用的是 30 周线;日线换算 30 × 5 = 150。
# ★ 不是 50 日线。50 日线只在开发期的注释里当过草稿,从没进过生产。

ER_WIN = 30
# 出处:原著。Perry Kaufman《Smarter Trading》(1995) 的 Efficiency Ratio
# (又名 Fractal Efficiency),Kaufman 自己在 AMA 里用的就是 n ≈ 20~30 这一档。

ER_IN = 0.35
# 出处:我们定的。在 pilot_300 上扫出来的分界 —— 再高趋势态几乎不触发,
# 再低则大量横盘被误判成趋势。

ER_OUT = 0.25
# 出处:我们定的。ER_IN / ER_OUT = 1.4,施密特触发器式滞回。
# ★ 为什么要滞回:单门槛会在门槛上下来回抖,一天一个状态,
#   产品端看到的就是状态乱跳。进门高、出门低,状态才稳。

MA_FAST = 20
# 出处:行业惯例。20 日线(≈ 一个月)是判「像样的反弹/回踩」的通用快线。

CHOP_BARS = 3
# 出处:我们定的。低效率要连续 3 根才认定转震荡 —— 挡掉单日噪声。
# ★ 配合滞回一起用:门槛管「幅度」,这个管「持续性」。

# 五个状态(代码里的名字;给用户看的说法在 STAGE_PLAIN)
STAGE_2 = "STAGE_2"                # 上涨段
BULL_PULLBACK = "BULL_PULLBACK"    # 上涨段里的回踩
STAGE_4 = "STAGE_4"                # 下跌段(主跌)
BEAR_RALLY = "BEAR_RALLY"          # 下跌段里的反弹
CHOP = "CHOP"                      # 震荡

ALL_STAGES = (STAGE_2, BULL_PULLBACK, STAGE_4, BEAR_RALLY, CHOP)

STAGE_PLAIN = {
    STAGE_2:       "上涨中",
    BULL_PULLBACK: "上涨中的回调",
    STAGE_4:       "下跌中",
    BEAR_RALLY:    "下跌中的反弹",
    CHOP:          "方向不明(震荡)",
}

# 预热不够(慢线还没算出来)时给的值。★ 不是 CHOP —— 「没数据」和「震荡」
# 是两件事,混在一起运营就没法定位分叉。
STAGE_WARMUP = "WARMUP"


# ============================================================================
# 第一步:中间量 —— ★ 全部无条件计算(坑 ① 的修法)
# ============================================================================

def _intermediates(close: pd.Series,
                   ma_n: int = MA_N,
                   ma_fast: int = MA_FAST,
                   er_win: int = ER_WIN) -> pd.DataFrame:
    """
    算出判状态要用到的每一个中间量。

    ★ 本函数内**没有任何 if / where / mask**。每一列都在全样本上算满。
      这是坑 ① 的修法:当初就是因为「只在均线下方算」才让 BEAR_RALLY 消失。
    """
    c = close.astype(float)

    # 慢线 / 快线。min_periods = 窗口长度 —— 不足就给 NaN,★ 不用部分窗口凑数,
    # 否则前 150 天的慢线是用 3 天、5 天算的,状态全是假的。
    ma_slow = c.rolling(ma_n, min_periods=ma_n).mean()
    ma20 = c.rolling(ma_fast, min_periods=ma_fast).mean()

    # ---- Kaufman 效率比率 ----
    # 分子 = 这 30 天**净**走了多远(首尾直线距离)
    # 分母 = 这 30 天**总共**走了多远(逐日路程累加)
    # 比值 = 走得有多「直」。1 = 一条直线;接近 0 = 来回折返、原地踏步。
    # ★ 为什么用它而不用均线斜率:斜率只看首尾,区分不了
    #   「慢慢稳稳涨 10%」和「暴涨 30% 再暴跌 20% 净剩 10%」——
    #   这两件事对交易的意义完全不同,但斜率给出同一个数。
    er_num = (c - c.shift(er_win)).abs()
    er_den = c.diff().abs().rolling(er_win, min_periods=er_win).sum()
    # 分母为 0(连续 30 天一个价,停牌/极度低流动性)→ 无意义,给 NaN 不给 0。
    er = er_num / er_den.replace(0.0, np.nan)

    # 净方向:这 30 天净着是往上还是往下。★ 只做诊断用,不参与状态判定
    #（方向由慢线决定,见下一步)—— 但必须列出来,运营对不上时要看它。
    net = c - c.shift(er_win)
    er_dir = np.sign(net)

    out = pd.DataFrame({
        "close": c,
        "ma150": ma_slow,
        "ma20": ma20,
        "er_num": er_num,
        "er_den": er_den,
        "er30": er,
        "net_chg_30": net,
        "er_dir": er_dir,
    }, index=c.index)

    # 到两条线的距离(%)—— 判状态用的是符号,但百分比是运营定位
    # 「差一点点」那种边界日的唯一办法。
    out["dist_ma150_pct"] = (c / ma_slow - 1.0) * 100.0
    out["dist_ma20_pct"] = (c / ma20 - 1.0) * 100.0

    # 结构确认的两个布尔量。★ 无条件算,两边都算。
    out["above_ma150"] = c > ma_slow
    out["above_ma20"] = c > ma20

    return out


# ============================================================================
# 第二步:趋势态开关 —— 滞回 + 连续确认(逐日状态机,必须用循环)
# ============================================================================

def _trend_switch(er: pd.Series,
                  er_in: float = ER_IN,
                  er_out: float = ER_OUT,
                  chop_bars: int = CHOP_BARS) -> pd.DataFrame:
    """
    「现在算趋势态还是震荡态」这一个开关。

    规则:
        震荡态 → 趋势态:ER ≥ 0.35,当天就翻(进门要果断,不然错过起涨段)
        趋势态 → 震荡态:ER < 0.25 **连续 3 根**才翻
                         (出门要迟疑,不然一个回踩日就被踢出趋势)
        夹在 0.25 ~ 0.35 之间:★ 维持原状 —— 这就是滞回带。

    ★ 为什么必须写循环、不能向量化:今天的状态取决于昨天的状态,
      而昨天的状态又取决于前天 —— 强路径依赖,没有闭式解。
      3000 根 bar 的 for 循环是毫秒级的事,不值得为它写错。

    返回三列:trend_on(开关) / low_eff(当天是否低效率) / low_streak(连续低效率根数)
    """
    e = er.to_numpy(dtype=float)
    n = len(e)
    trend_on = np.zeros(n, dtype=bool)
    streak = np.zeros(n, dtype=np.int64)

    state = False      # ★ 初值:震荡态。没有证据之前不许认定趋势
    run = 0
    for i in range(n):
        x = e[i]
        if np.isnan(x):
            # ER 还没算出来(预热期)或分母为 0 —— 不改状态、不累计连击。
            # ★ 不把 NaN 当低效率,否则预热期结束时会凭空攒出一串连击。
            trend_on[i] = state
            streak[i] = run
            continue
        if not state:
            if x >= er_in:
                state = True
                run = 0
        else:
            if x < er_out:
                run += 1
                if run >= chop_bars:
                    state = False
                    run = 0
            else:
                run = 0
        trend_on[i] = state
        streak[i] = run

    low_eff = er < er_out          # 注意:NaN < x 得 False,正合要求
    return pd.DataFrame({
        "low_eff": low_eff.to_numpy(),
        "low_streak": streak,
        "trend_on": trend_on,
    }, index=er.index)


# ============================================================================
# 第三步:五个状态 —— 纯布尔组合
# ============================================================================

def _classify(x: pd.DataFrame) -> pd.Series:
    """
    两个轴交叉出五个格子:

                      │ 趋势态 (trend_on=True)    │ 震荡态
        ──────────────┼───────────────────────────┼─────────
        慢线上方       │ 站上快线 → STAGE_2        │  CHOP
        (above_ma150) │ 跌破快线 → BULL_PULLBACK  │
        ──────────────┼───────────────────────────┼─────────
        慢线下方       │ 跌破快线 → STAGE_4        │  CHOP
                      │ 站上快线 → BEAR_RALLY     │

    ★ 慢线(150 日)决定**方向**,效率比率决定**是不是趋势**,
      快线(20 日)决定**是主推进还是逆向的小波**。
      三件事各管一件,不互相顶替 —— 这是「效率比率 + 结构确认」。

    ★ 坑 ② 的纪律:下面全部用 pandas/numpy 的布尔运算和 .to_numpy(),
      绝不对 np.bool_ 做 `is True` 这类身份比较。
    """
    ready = x["ma150"].notna() & x["ma20"].notna()

    up = x["above_ma150"].fillna(False).to_numpy(dtype=bool)
    fast = x["above_ma20"].fillna(False).to_numpy(dtype=bool)
    trend = x["trend_on"].to_numpy(dtype=bool)
    ok = ready.to_numpy(dtype=bool)

    stage = np.full(len(x), STAGE_WARMUP, dtype=object)
    stage = np.where(ok & trend & up & fast, STAGE_2, stage)
    stage = np.where(ok & trend & up & ~fast, BULL_PULLBACK, stage)
    stage = np.where(ok & trend & ~up & ~fast, STAGE_4, stage)
    stage = np.where(ok & trend & ~up & fast, BEAR_RALLY, stage)
    stage = np.where(ok & ~trend, CHOP, stage)
    return pd.Series(stage, index=x.index, name="stage")


# ============================================================================
# 入口函数
# ============================================================================

def compute_stages(df: pd.DataFrame,
                   *,
                   price_col: str = "close",
                   ma_n: int = MA_N,
                   ma_fast: int = MA_FAST,
                   er_win: int = ER_WIN,
                   er_in: float = ER_IN,
                   er_out: float = ER_OUT,
                   chop_bars: int = CHOP_BARS) -> pd.DataFrame:
    """
    ★ 这是唯一的入口。

    吃什么
    ------
    df : pandas.DataFrame
        · 索引  = 交易日,必须是 DatetimeIndex,必须升序,必须唯一
        · 必需列 = `close`(收盘价,float)。★ 只需要这一列,
                   不需要 open/high/low/volume。
        · 其他列一律忽略,不会影响结果。
        · 复权口径 = **只拆股、不做分红复权**(1029 已和运营定死)。
          ★ 口径不一样,数就一定对不上 —— 这是第一个要核对的东西。
        · 行数建议 ≥ ma_n + er_win + chop_bars( = 183 根)才会有第一个有效状态。

    吐什么
    ------
    pandas.DataFrame,索引和入参完全一致(逐行对齐),列如下:

        close           收盘价(原样带出,方便逐行核对)
        ma150           150 日均线(慢线 / 牛熊分界)
        ma20            20 日均线(快线)
        er_num          效率比率分子 = |close - close[-30]|
        er_den          效率比率分母 = Σ|日涨跌| 过去 30 根
        er30            效率比率 = er_num / er_den
        net_chg_30      30 日净涨跌(诊断用,不参与判定)
        er_dir          30 日净方向 +1/-1/0(诊断用,不参与判定)
        dist_ma150_pct  收盘相对慢线的距离 %
        dist_ma20_pct   收盘相对快线的距离 %
        above_ma150     收盘 > 慢线
        above_ma20      收盘 > 快线
        low_eff         当天 er30 < ER_OUT
        low_streak      连续低效率根数(到 CHOP_BARS 就转震荡)
        trend_on        趋势态开关(已含滞回 + 连续确认)
        stage           ★ 最终状态:五个之一,或 WARMUP(预热不够)

    ★ 中间量全部吐出来,不是为了好看 —— 是为了对不上的时候能定位到
      **哪一步开始分叉**,而不是只知道「最后结果不一样」。
    """
    if price_col not in df.columns:
        raise ValueError(f"入参缺列:{price_col}。compute_stages 只要一列 close。")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError("入参索引必须是 DatetimeIndex。")
    if not df.index.is_monotonic_increasing:
        raise ValueError("入参索引必须按日期升序。")
    if df.index.has_duplicates:
        raise ValueError("入参索引有重复日期。")

    x = _intermediates(df[price_col], ma_n=ma_n, ma_fast=ma_fast, er_win=er_win)
    sw = _trend_switch(x["er30"], er_in=er_in, er_out=er_out, chop_bars=chop_bars)
    x = x.join(sw)
    x["stage"] = _classify(x)
    cols = ["close", "ma150", "ma20", "er_num", "er_den", "er30",
            "net_chg_30", "er_dir", "dist_ma150_pct", "dist_ma20_pct",
            "above_ma150", "above_ma20", "low_eff", "low_streak",
            "trend_on", "stage"]
    return x[cols]


def stage_series(df: pd.DataFrame, **kw) -> pd.Series:
    """只要最终状态一列的简便写法。"""
    return compute_stages(df, **kw)["stage"]


# ============================================================================
# 运营脚本那套「均线斜率三分」的等价复刻 —— ★ 只用于标注「该重点看哪几天」
# ============================================================================

OPS_SLOPE_WIN = 20          # 斜率回看窗口(我们猜的,运营可改)
OPS_FLAT_BAND_PCT = 1.25
# 走平带:慢线 20 日变化率的绝对值 ≤ 1.25% 算走平。
# ★ 这个 1.25 是我们**反推**出来的,不是运营给的:在 pilot 池上实测
#   |变化率| 的 33% 分位正好是 1.26% —— 既然叫「三分」,就按三格大致均等来定。
#   ★ 运营只要改这一个数,就能把这份复刻调成和自己脚本一样。


def ops_slope_proxy(df: pd.DataFrame,
                    price_col: str = "close",
                    ma_n: int = MA_N,
                    slope_win: int = OPS_SLOPE_WIN,
                    flat_band_pct: float = OPS_FLAT_BAND_PCT) -> pd.DataFrame:
    """
    ★ 重要声明:这**不是**运营的脚本,我们没有他们的代码。
      这是按「均线斜率三分」这句定义做的一个等价复刻,只有一个用途 ——
      在对照表里把「两套方法最可能吵架的日子」标出来,好让运营知道
      对答案时该重点看哪几天。**它的结果不是答案,答案是 stage 列。**

    斜率三分:慢线 20 日变化率 > +1% → 上涨;< −1% → 下跌;中间 → 走平。
    """
    c = df[price_col].astype(float)
    ma = c.rolling(ma_n, min_periods=ma_n).mean()
    slope = (ma / ma.shift(slope_win) - 1.0) * 100.0
    s = np.full(len(c), STAGE_WARMUP, dtype=object)
    ok = slope.notna().to_numpy(dtype=bool)
    v = slope.to_numpy(dtype=float)
    s = np.where(ok & (v > flat_band_pct), "OPS_UP", s)
    s = np.where(ok & (v < -flat_band_pct), "OPS_DOWN", s)
    s = np.where(ok & (np.abs(v) <= flat_band_pct), "OPS_FLAT", s)
    return pd.DataFrame({"ops_ma150_slope_pct": slope,
                         "ops_proxy_stage": s}, index=c.index)


def mark_divergence(x: pd.DataFrame, ops: pd.DataFrame) -> pd.DataFrame:
    """
    标出「两套方法最可能分歧」的三类日子。标签写进 watch_tag 列,
    可以同时命中多个,用 `|` 连接。

    A. watch_counter_move —— 回踩 / 反弹日。
       斜率三分只有三个格子,**没有「趋势内的逆向小波」这个概念**。
       我们判 BULL_PULLBACK / BEAR_RALLY 的那些天,他们必然给别的答案。
       ★ 这是分歧的第一来源,也是最大来源。

    B. watch_hysteresis —— ER 落在 0.25 ~ 0.35 滞回带里的日子。
       我们这天的状态取决于**前面几天怎么走过来的**(记忆);
       斜率三分只看当天那一个数(无记忆)。
       同一天同样的数据,两边可以给出不同答案,而且都"对"。

    C. watch_slope_vs_er —— 「走得远」和「走得直」**严重**打架的日子。
       慢线斜率很陡(> 2 倍走平带)但我们判震荡 → 暴涨暴跌来回折返,净位移大但路径不直;
       慢线几乎不动(< 半个走平带)但我们判趋势 → 慢牛爬升,净位移小但极其平滑。
       ★ 只标「严重」的那一档:轻微不一致每天都有,全标出来等于没标。

    另外还给一列 disagree_vs_ops —— 粗口径直接对不上的日子
    (我们的五态按 上涨/下跌/震荡 折成三态,和 ops_proxy_stage 比)。
    ★ 运营对答案时先按这一列筛,就是该重点看的那些天。
    """
    tags = []
    cm = x["stage"].isin([BULL_PULLBACK, BEAR_RALLY]).to_numpy(dtype=bool)
    hy = ((x["er30"] >= ER_OUT) & (x["er30"] < ER_IN)).fillna(False).to_numpy(dtype=bool)
    absl = ops["ops_ma150_slope_pct"].abs()
    very_steep = (absl > 2.0 * OPS_FLAT_BAND_PCT).fillna(False).to_numpy(dtype=bool)
    very_flat = (absl < 0.5 * OPS_FLAT_BAND_PCT).fillna(False).to_numpy(dtype=bool)
    trend = x["trend_on"].to_numpy(dtype=bool)
    sv = (very_steep & ~trend) | (very_flat & trend)
    for a, b, c in zip(cm, hy, sv):
        t = []
        if bool(a):
            t.append("watch_counter_move")
        if bool(b):
            t.append("watch_hysteresis")
        if bool(c):
            t.append("watch_slope_vs_er")
        tags.append("|".join(t))
    out = ops.copy()
    out["watch_tag"] = tags

    coarse = x["stage"].map({STAGE_2: "OPS_UP", BULL_PULLBACK: "OPS_UP",
                             STAGE_4: "OPS_DOWN", BEAR_RALLY: "OPS_DOWN",
                             CHOP: "OPS_FLAT"})
    out["xing_coarse"] = coarse
    ready = coarse.notna() & (out["ops_proxy_stage"] != STAGE_WARMUP)
    out["disagree_vs_ops"] = (ready & (coarse != out["ops_proxy_stage"])).to_numpy(dtype=bool)
    return out


# ============================================================================
# 最小 json 读取器 —— ★ 故意不依赖 engine 里任何别的模块
# ============================================================================

DEFAULT_DATA_ROOT = "/home/claude/xing-agent-stock_data/pilot_300"


def load_daily_json(symbol: str, data_root: str = DEFAULT_DATA_ROOT) -> pd.DataFrame:
    """
    读 <data_root>/<SYM>/daily.json 的 data 数组,吐一张以日期为索引的表。

    ★ 用的是 `close` 字段 = 未复权收盘价(adjustment: "raw")。
      和运营脚本同口径:只拆股、不做分红复权。
    """
    path = os.path.join(data_root, symbol, "daily.json")
    with open(path, "r", encoding="utf-8") as f:
        blob = json.load(f)
    rows = blob.get("data") or []
    if not rows:
        raise ValueError(f"{symbol}: daily.json 里没有 data")
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df[["close"]].astype(float).dropna()


# ============================================================================
# 对照表
# ============================================================================

def build_table(symbols: list[str],
                start: str = "2018-01-01",
                data_root: str = DEFAULT_DATA_ROOT,
                with_ops_proxy: bool = True) -> pd.DataFrame:
    """出逐日对照表。★ 慢线预热用的是 start 之前的数据,不是从 start 才开始算。"""
    frames = []
    for sym in symbols:
        raw = load_daily_json(sym, data_root)
        x = compute_stages(raw)                       # ★ 全样本算,再切
        if with_ops_proxy:
            ops = ops_slope_proxy(raw)
            ops = mark_divergence(x, ops)
            x = x.join(ops)
        x = x.loc[x.index >= pd.Timestamp(start)]
        x.insert(0, "symbol", sym)
        x = x.reset_index().rename(columns={"date": "date", "index": "date"})
        frames.append(x)
    out = pd.concat(frames, ignore_index=True)
    cols = ["symbol", "date", "close", "ma150", "er30", "stage"]
    rest = [c for c in out.columns if c not in cols]
    return out[cols + rest]


def stage_mix(table: pd.DataFrame) -> pd.Series:
    """五个状态各占多少(只统计非 WARMUP 的行)。"""
    s = table["stage"]
    s = s[s != STAGE_WARMUP]
    return (s.value_counts(normalize=True) * 100.0).reindex(ALL_STAGES).fillna(0.0)


# ============================================================================
# 自检 —— ★ 两个坑的回归测试在第 ①② 项
# ============================================================================

def selftest(data_root: str = DEFAULT_DATA_ROOT, verbose: bool = True) -> bool:
    rep: list[tuple[str, bool, str]] = []

    # ---------- ① 坑一:BEAR_RALLY 必须出现 ----------
    # 造一段「下跌趋势 + 中途两次像样反弹」的价格,BEAR_RALLY 必须被判出来。
    n = 900
    t = np.arange(n)
    px = 100.0 * np.exp(-0.0022 * t)                        # 稳稳下跌
    px = px * (1 + 0.10 * np.sin(t / (55.0 / (2 * np.pi))))  # 叠上 55 根一轮的反弹波
    idx = pd.bdate_range("2016-01-04", periods=n)
    syn = pd.DataFrame({"close": px}, index=idx)
    r = compute_stages(syn)
    nbr = int((r["stage"] == BEAR_RALLY).sum())
    rep.append(("① BEAR_RALLY 不为零(坑一回归)", nbr > 0,
                f"合成下跌+反弹序列上判出 {nbr} 天 BEAR_RALLY"))

    # 对称性:同一段序列翻过来(上涨+回踩),BULL_PULLBACK 也必须出现
    syn2 = pd.DataFrame({"close": px[::-1]}, index=idx)
    r2 = compute_stages(syn2)
    nbp = int((r2["stage"] == BULL_PULLBACK).sum())
    rep.append(("① 对称:BULL_PULLBACK 不为零", nbp > 0,
                f"翻转序列上判出 {nbp} 天 BULL_PULLBACK"))

    # 中间量不许被遮罩:所有行(预热之后)的 dist_ma20_pct 都必须有值
    post = r.iloc[MA_N + ER_WIN:]
    nomask = bool(post["dist_ma20_pct"].notna().all() and post["dist_ma150_pct"].notna().all())
    rep.append(("① 中间量无条件计算、未被遮罩", nomask,
                f"预热后 {len(post)} 行里 NaN 中间量 "
                f"{int(post['dist_ma20_pct'].isna().sum())} 个"))

    # ---------- ② 坑二:不许用 numpy 布尔做身份比较 ----------
    # ★ 用 tokenize 扫**真实代码**,注释和字符串天然被排除 ——
    #   否则这个文件自己的说明文字就会把测试打红。
    import io
    import tokenize
    src = open(os.path.abspath(__file__), "r", encoding="utf-8").read()
    names: list[tuple[int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.NAME:
            names.append((tok.start[0], tok.string))
    bad = []
    for i, (ln, w) in enumerate(names):
        if w != "is":
            continue
        nxt = [n for _, n in names[i + 1:i + 3]]
        if nxt[:1] == ["not"]:
            nxt = nxt[1:2]
        else:
            nxt = nxt[:1]
        if nxt and nxt[0] in ("True", "False"):
            bad.append(ln)
    rep.append(("② 源码里没有 `is True/False` 身份比较(坑二回归)", not bad,
                f"命中行号 {bad}" if bad else "tokenize 全文扫过,干净"))
    # 并且实测一次:np.True_ is True 确实是 False,所以这条纪律不是多余的
    # 实测一次:np.True_ 和 True 不是同一个对象 —— 所以上面那条纪律不是多余的。
    # ★ 这里用 operator.is_ 而不是写出身份比较,否则会被自己的扫描抓到。
    import operator
    rep.append(("② numpy 布尔与 True 不同一(所以才要这条纪律)",
                not operator.is_(np.True_, True),
                "operator.is_(np.True_, True) = False,已确认"))

    # ---------- ③ 参数必须是生产值 ----------
    ok = (MA_N == 150 and ER_WIN == 30 and ER_IN == 0.35
          and ER_OUT == 0.25 and MA_FAST == 20 and CHOP_BARS == 3)
    rep.append(("③ 参数为生产值(150/30/0.35/0.25/20/3)", ok,
                f"MA_N={MA_N} ER_WIN={ER_WIN} ER_IN={ER_IN} "
                f"ER_OUT={ER_OUT} MA_FAST={MA_FAST} CHOP_BARS={CHOP_BARS}"))

    # ---------- ④ 滞回必须真的起作用 ----------
    # 手搓一条 ER 序列:0.40(进)→ 0.30 ×10(在滞回带里,应维持趋势)
    #                 → 0.10 ×2(连续 2 根,还不够)→ 0.30(清零)→ 0.10 ×3(够了,转震荡)
    e = pd.Series([np.nan] * 3 + [0.40] + [0.30] * 10 + [0.10] * 2 + [0.30] + [0.10] * 3,
                  index=pd.bdate_range("2020-01-01", periods=20))
    sw = _trend_switch(e)
    ok4 = (bool(sw["trend_on"].iloc[3]) and bool(sw["trend_on"].iloc[13])
           and bool(sw["trend_on"].iloc[15]) and not bool(sw["trend_on"].iloc[19]))
    rep.append(("④ 滞回带内维持原状 + 连续 3 根才转震荡", ok4,
                "0.30 十根仍为趋势;0.10 两根不转;被 0.30 清零后再三根才转"))

    # ---------- ⑤ 因果性:截断重算,截断前结果必须一字不差 ----------
    cut = 700
    full = compute_stages(syn)
    part = compute_stages(syn.iloc[:cut])
    same = bool((full["stage"].iloc[:cut].to_numpy() == part["stage"].to_numpy()).all())
    rep.append(("⑤ 因果性:截断到第 700 根重算,前 700 天状态完全一致", same,
                "无未来函数"))

    # ---------- ⑥ 五个状态在真实数据上都要出现 ----------
    try:
        probe = [s for s in ("AAPL", "ABT", "AAL", "KO", "AIG")
                 if os.path.exists(os.path.join(data_root, s, "daily.json"))]
        seen: set[str] = set()
        for s in probe:
            seen |= set(compute_stages(load_daily_json(s, data_root))["stage"].unique())
        miss = [s for s in ALL_STAGES if s not in seen]
        rep.append(("⑥ 真实数据上五个状态都出现过", not miss,
                    f"缺 {miss}" if miss else f"探测 {probe} 全部命中"))
    except Exception as exc:                            # noqa: BLE001
        rep.append(("⑥ 真实数据探测", False, f"拿不到数据:{exc}"))

    # ---------- ⑦ 空表 / 全 NaN / 数据不足:不许崩,也不许凭空出状态 ----------
    try:
        e0 = compute_stages(pd.DataFrame({"close": []},
                                         index=pd.DatetimeIndex([], name="date")))
        short = compute_stages(pd.DataFrame(
            {"close": np.linspace(10, 20, 50)},
            index=pd.bdate_range("2020-01-01", periods=50)))
        ok7 = len(e0) == 0 and bool((short["stage"] == STAGE_WARMUP).all())
        rep.append(("⑦ 空表不崩、数据不足一律 WARMUP(不凭空出状态)", ok7,
                    f"空表 {len(e0)} 行;50 根全部 WARMUP={bool((short['stage']==STAGE_WARMUP).all())}"))
    except Exception as exc:                            # noqa: BLE001
        rep.append(("⑦ 边界输入", False, f"抛异常:{exc}"))

    allok = all(bool(b) for _, b, _ in rep)
    if verbose:
        print("=" * 78)
        print("engine/stages.py 自检")
        print("=" * 78)
        for name, b, note in rep:
            print(f"  [{'通过' if b else '不通过'}] {name}\n           {note}")
        print("-" * 78)
        print("结论:" + ("全绿" if allok else "★ 有不通过项,不要往下用"))
    return allok


# ============================================================================
# 命令行
# ============================================================================

def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="状态引擎参考实现")
    ap.add_argument("--symbol", help="看单只票的最后 30 天")
    ap.add_argument("--table", help="出对照表,逗号分隔的代码")
    ap.add_argument("--out", default="stages_table.csv", help="对照表输出路径")
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)

    if a.selftest:
        return 0 if selftest(a.data_root) else 1
    if a.symbol:
        x = compute_stages(load_daily_json(a.symbol, a.data_root))
        print(x.tail(30).to_string())
        print()
        print("全样本状态占比(%):")
        print(stage_mix(x.reset_index().assign(symbol=a.symbol)).round(2).to_string())
        return 0
    if a.table:
        syms = [s.strip().upper() for s in a.table.split(",") if s.strip()]
        t = build_table(syms, start=a.start, data_root=a.data_root)
        t.to_csv(a.out, index=False, encoding="utf-8-sig")
        print(f"写好 {a.out}:{len(t)} 行 × {len(t.columns)} 列,{len(syms)} 只票")
        print(stage_mix(t).round(2).to_string())
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
