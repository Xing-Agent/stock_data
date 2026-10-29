"""
专家 2026-10-29 第二轮裁决落地的新算子(全部新增,不改任何老算子)。

================================ 三秒版 ================================
这个文件只装四样新东西,每一样都是专家第二轮裁决明确要求的:

  ① ★ 流派三的「摆动波谷」改成 **Connors 滚动 20 日绝对低点**
     —— 不再借用流派二那个 5 根 Bar 的 2-1-2 分型。
     大白话:2-1-2 每三五天就造一个小波谷,那种地方没人挂止损;
     要猎杀的是全市场都看得见的那条 20 日防线。

  ② ★★ 4 天存活门禁(上一轮漏了,这一轮必须加回)
     Age_Gate:t − t_low ≥ 4 个交易日。
     大白话:如果前低就是昨天刚创的,价格正在瀑布式下跌,
     跌破再反弹只是顺势推动浪的一个喘气 —— 去抄底是接飞刀。
     只有那条低点挺过 4 天以上,散户和突破客才来得及把止损挂在它下面,
     这时候把它砸穿再收回来,才是真的「猎杀流动性」。
     ★ 出处已核实:Connors & Raschke《Street Smarts》(1995) Ch.4
       Turtle Soup, Rule 2 —— 原文 "The previous 20-day low must have
       occurred at least four trading sessions earlier. This is very
       important."(见本轮报告出处核查节)

  ③ ★ 流派一的「同一根 K 线既破底又站上 EMA20」拆成**双阶段状态机**
     大白话:原来那条要求一根巨阳线同时覆盖整个 20 日区间,深度价值股
     几乎做不到(实测砍掉 98.3% 样本)。现在拆成两步:
     先等它破底当天收回来(记下那根的最低价当止损锚),
     再等它在 10 个交易日内收盘站上 EMA20 才进场。

  ④ ★ Piotroski F-Score 的三层修补
     大白话:原来那道闸剔掉的票里 94.7% 是「算不出分」,不是「分低」——
     等于系统性剔掉了银行、保险、REIT 这些科目口径不一样的行业,
     产生极恶劣的选择性偏差。三层修补:
       第一层 行业豁免:SIC 6000–6999(金融 + 房地产)不适用 F-Score,由 Altman Z'' 兜底
       第二层 容差缩放:9 项里有效项 ≥ 7 时,按比例放大到 9 分制再判 ≥ 5
       第三层 严重缺失降级:回退到 Altman Z'' ≥ 阈值,★ 不许直接判死刑

★★ 阈值的来源警告(必须跟着数一起走,不许省略):
   专家给的 **Altman Z'' ≥ 1.80** 和 **「有效项 ≥ 7」** 这两个数
   ★ 他没有给出处。而 Altman 自己的分区是:困境 < 1.10 / 灰区 1.10~2.60 /
   安全 > 2.60 —— 1.80 落在灰区正中间,来路不明。
   ★ 所以这两个数一律标「来源存疑(专家自定)」,
   ★ 并且 Z'' 阈值同时跑 1.80 和 1.10 两版并列报,不许只跑 1.80 那一版。

★★ 出处核查结论(本轮两处,一处对一处错):
   · Connors 4 天规则 —— ★ 核实了,Ch.4 / Rule 2 / 英文原文一字不差
   · Piotroski 剔金融 —— ★★ **核不实**。论文(2000 年 4 月,JAR 38 Supplement)
     第 1 节是引言、不含任何样本筛选;样本选择在第 3.1 节,口径是
     「COMPUSTAT 上股价与账面价值数据齐备的票,按上一财年 BM 分五组取最高那组」,
     ★ 全文没有任何 SIC 码或行业剔除的句子。
     ★ 所以「剔除金融业」这件事本身是**行业惯例 / 我们自己的判断**,
       ★ 不是 Piotroski 原著 —— 严格说原著是**把金融股留在样本里的**。
     ★ 机制讲得通(金融企业的流动资产 / 应收 / 经营现金流和工商业不是一个概念,
       套通用公式必然 NaN),而且和我们实测的 94.7% 完全对得上 —— 但出处要改。

跑法:python -m engine.ops_1029        # 自验:覆盖率 + 三层修补的分流统计
=========================================================================
"""

from __future__ import annotations

import functools

import numpy as np
import pandas as pd

from . import cache, data

# ---------------------------------------------------------------- 死数(全部带出处)

#: Connors 的 20 日回看窗口 —— 原著写死
CONNORS_LOOKBACK = 20
#: ★★ Connors 的 4 天存活门禁 —— 原著写死,★ 本轮已核实原文
CONNORS_MIN_AGE = 4
#: ★ 金融 + 房地产的 SIC 区间(SEC Division H:Finance, Insurance, And Real Estate)
#   ★ 一个区间同时盖住「金融」和「房地产」—— REIT 是 6798、房地产是 65xx,都在里面
SIC_FINANCE_LO, SIC_FINANCE_HI = 6000, 6999
#: Altman 1983 基准版 Z''(四变量,★ 无常数项)—— 与 deep_value.yaml 锁定的版本一致
ALTMAN_Z2_COEF = {"X1": 6.56, "X2": 3.26, "X3": 6.72, "X4": 1.05}
ALTMAN_Z2_CONST = 0.0
#: ★★ 两个「来源存疑(专家自定)」的数
F_MIN_VALID_ITEMS = 7          # ★ 来源存疑(专家自定)
Z2_FALLBACK_EXPERT = 1.80      # ★ 来源存疑(专家自定),落在 Altman 灰区正中
Z2_FALLBACK_ALTMAN = 1.10      # ★ Altman 自己的困境线(灰区下沿)—— 并列跑的另一版

#: ★ 本文件所有「显式做了选择但专家没给口径」的地方都往这里记一条
_NOTES: list[str] = []


def notes() -> list[str]:
    return list(dict.fromkeys(_NOTES))


def _note(s: str) -> None:
    _NOTES.append(s)


def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


# ================================================================
# ① + ② Connors 滚动 20 日绝对低点 + 4 天存活门禁
# ================================================================

@functools.lru_cache(maxsize=16)
def swing_low_20(symbols: tuple[str, ...], lookback: int = CONNORS_LOOKBACK
                 ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    返回 (SwingLow, Age)。

      SwingLow[t] = min(Low[t−lookback] … Low[t−1])      ★ 不含当天,不偷看
      Age[t]      = t − t_low,t_low = 窗口里**最近一次**创出该最低价的那天

    ★ 为什么 t_low 取「最近一次」而不是「第一次」:
      Connors 原文 "The previous 20-day low must have occurred at least four
      trading sessions earlier" 问的是「那条低点有多老」。如果同一个价位
      两天前又被摸过一次,这条防线就是新鲜的、底下还没堆起止损盘 ——
      取最近一次 = 严的那一端,不放水。

    ★ 因果性:SwingLow 与 Age 都只用到 t−1 及以前,当天收盘后即可知,
      次日开盘进场不存在偷看。
    """
    low = cache.field("low", list(symbols))
    arr = low.to_numpy(dtype=float)
    T, N = arr.shape
    best = np.full((T, N), np.nan)
    age = np.zeros((T, N), dtype=float)
    for k in range(1, int(lookback) + 1):
        v = np.full((T, N), np.nan)
        if k < T:
            v[k:, :] = arr[:T - k, :]
        # 严格小于 → 并列时保留更小的 k(= 更近的那一天)
        better = np.isfinite(v) & (~np.isfinite(best) | (v < best))
        best = np.where(better, v, best)
        age = np.where(better, float(k), age)
    # 窗口内任何一天缺价 → 整扇窗口判不可用(不猜不补)
    valid = np.isfinite(arr)
    win_full = (pd.DataFrame(valid, index=low.index, columns=low.columns)
                .rolling(int(lookback), min_periods=int(lookback)).sum()
                .shift(1).to_numpy(dtype=float) == float(lookback))
    best = np.where(win_full, best, np.nan)
    age = np.where(win_full, age, np.nan)
    sl = pd.DataFrame(best, index=low.index, columns=low.columns)
    ag = pd.DataFrame(age, index=low.index, columns=low.columns)
    return sl, ag


def age_gate(symbols: list[str], lookback: int = CONNORS_LOOKBACK,
             min_age: int = CONNORS_MIN_AGE) -> pd.DataFrame:
    """★★ Age_Gate:t − t_low ≥ min_age 个交易日。出处 Connors Ch.4 Rule 2(已核实)。"""
    sl, ag = swing_low_20(tuple(symbols), lookback)
    return _as_bool(sl.notna() & ag.notna() & (ag >= float(min_age)))


def break_below_swing_low(symbols: list[str], lookback: int = CONNORS_LOOKBACK
                          ) -> pd.DataFrame:
    """当日盘中跌破那条 20 日低点(= 同时就是「创至少 20 日新低」,两句是同一件事)。"""
    sl, _ = swing_low_20(tuple(symbols), lookback)
    low = cache.field("low", symbols)
    return _as_bool(sl.notna() & (low < sl))


def close_reclaim(symbols: list[str], lookback: int = CONNORS_LOOKBACK,
                  atr_period: int = 14, atr_multiple: float = 0.15,
                  min_bcl: float = 0.65) -> pd.DataFrame:
    """
    「强力收复」两条同时成立(专家第二轮给齐,数值一个没动):
      ① 绝对收复缓冲垫  Close ≥ SwingLow + 0.15 × ATR14
      ② 收盘相对位置    BCL = (Close − Low)/(High − Low) ≥ 0.65
    ★ BCL 的 0.65 出处是「微观执行台形态收盘过滤参数」,★ 不是 Sperandeo —— 专家已书面承认。
    """
    from .matrices import atr_matrix
    sl, _ = swing_low_20(tuple(symbols), lookback)
    close = cache.field("close", symbols)
    high = cache.field("high", symbols)
    low = cache.field("low", symbols)
    atr = atr_matrix(int(atr_period), symbols)
    rng = (high - low).replace(0.0, np.nan)
    bcl = (close - low) / rng
    c1 = sl.notna() & atr.notna() & (close >= sl + float(atr_multiple) * atr)
    c2 = bcl.notna() & (bcl >= float(min_bcl))
    return _as_bool(c1 & c2)


def bullish_candle(symbols: list[str]) -> pd.DataFrame:
    """收阳线(收 > 开)。原著写死。"""
    return _as_bool(cache.field("close", symbols) > cache.field("open", symbols))


# ================================================================
# ③ 流派一 双阶段状态机
# ================================================================

def deep_value_two_stage(symbols: list[str], lookback: int = CONNORS_LOOKBACK,
                         min_age: int = CONNORS_MIN_AGE, ema_period: int = 20,
                         max_wait_days: int = 10, atr_period: int = 14,
                         atr_multiple: float = 0.5
                         ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    双阶段状态机。返回 (进场事件矩阵, T0 止损价矩阵, 诊断).

    第一阶段 T0 触底排毒(三条同时成立):
        ① Low[T0] < SwingLow20[T0]        盘中击穿 20 日低点
        ② Age[T0] ≥ 4                     ★ 4 天存活门禁(Connors Ch.4 Rule 2)
        ③ Close[T0] > SwingLow20[T0]      当日收盘收复到该低点上方(U&R)
      → 记下 Low[T0],算出**绝对初始止损锚点** Stop = Low[T0] − 0.5 × ATR14[T0]
      → 状态机进入「等待趋势确认」

    第二阶段 T0+1 … T0+10:
        某日 Close > EMA20  → ★ 该日为进场信号日,次日开盘市价进
      失效(任一成立就整个作废、清空状态):
        · 10 个交易日内从未站上 EMA20
        · 中途跌破了 Low[T0]

    ★★ 三处专家没给、代码必须有答案的口径(全部记进 notes(),报告里逐条列出):
      (a) 「跌破 Low[T0]」按**盘中最低价** Low[t] < Low[T0] 判,不是收盘价判。
          理由:止损就挂在 Low[T0] 下方 0.5×ATR,盘中跌破 Low[T0] 时这笔
          假设的持仓其实已经濒临止损 —— 用收盘判会系统性放水。★ 这是紧的那一端。
      (b) 等待期内又出现一次合格的第一阶段 → **重新锚定**(T0 与 Low[T0] 都换成
          新的那根,10 天的钟重新起算)。理由:新的一次破底收复是更近、更有效的
          结构底,拿一个更旧的锚去配一个更新的趋势确认不自洽。
      (c) max_wait_days = 10 **按交易日**算(不是日历日)。
          ★ 标注:行业惯例(机构价值反转两周均线修复窗口)—— 专家没给出处,
          但「两周 ≈ 10 个交易日」这个换算是他自己在裁决里写的。
    """
    from .matrices import atr_matrix, ema_matrix
    sl, ag = swing_low_20(tuple(symbols), lookback)
    close = cache.field("close", symbols)
    low = cache.field("low", symbols)
    ema = ema_matrix(int(ema_period), symbols)
    atr = atr_matrix(int(atr_period), symbols)

    _note("③-a 「中途跌破 Low[T0]」按**盘中最低价**判(Low[t] < Low[T0]),"
          "不是按收盘价 —— 止损就挂在 Low[T0] 下方,用收盘判会系统性放水。"
          "★ 这是我们选的紧端口径,专家没给。")
    _note("③-b 等待期内再出现一次合格的第一阶段 → **重新锚定**(T0 / Low[T0] / "
          "10 天的钟全部重置)。★ 我们的读法,专家没给。")
    _note(f"③-c 等待窗口 N = {max_wait_days} 按**交易日**算。"
          f"★ 标注:行业惯例(机构价值反转两周均线修复窗口),专家未给出处。")

    stage1 = (sl.notna() & ag.notna() & (ag >= float(min_age))
              & (low < sl) & (close > sl)).fillna(False).to_numpy(bool)
    lo = low.to_numpy(float)
    cl = close.to_numpy(float)
    em = ema.to_numpy(float)
    at = atr.to_numpy(float)

    T, N = cl.shape
    ev = np.zeros((T, N), dtype=bool)
    stop_m = np.full((T, N), np.nan)
    diag = {"第一阶段事件数": int(stage1.sum()), "进场事件数": 0,
            "失效_从未站上EMA20": 0, "失效_中途跌破LowT0": 0,
            "重新锚定次数": 0, "止损锚算不出(ATR14 为 NaN)": 0}

    # ★★ 一个必须做掉的细节:entry_trigger 会在所有进场规则之上再套一层
    #   _event_only(只在「由不成立变成成立」那天为 True)。如果本状态机可能
    #   在相邻两天各吐一个进场事件,第二个会被那一层**静默吃掉**。
    #   做法:进场当天不许立刻重新锚定(新的第一阶段必须严格晚于进场日)——
    #   于是两次进场之间至少隔 2 个交易日,_event_only 可证明是空操作。
    #   ★ 这不是放水:它只影响「进场当天同时又是一次破底收复」这种同日重叠,
    #     下一根仍然可以重新开始排毒。
    _note("③-d 进场当天不许立刻重新锚定第一阶段(新 T0 必须严格晚于进场日)。"
          "★ 这是为了让 entry_trigger 那层 _event_only 不会静默吃掉相邻两天的"
          "第二个进场事件 —— 不是策略条件,是防静默丢信号的工程约束。")
    for j in range(N):
        t0 = -1           # 当前锚定的 T0 行号;-1 = 没有在等
        l0 = np.nan
        s0 = np.nan
        fired_today = False
        for i in range(T):
            fired_today = False
            if t0 >= 0:
                # --- 先判失效:中途跌破 Low[T0](盘中口径)
                if np.isfinite(lo[i, j]) and lo[i, j] < l0:
                    diag["失效_中途跌破LowT0"] += 1
                    t0 = -1
                # --- 再判趋势确认
                elif np.isfinite(cl[i, j]) and np.isfinite(em[i, j]) \
                        and cl[i, j] > em[i, j]:
                    ev[i, j] = True
                    stop_m[i, j] = s0
                    diag["进场事件数"] += 1
                    t0 = -1
                    fired_today = True
                elif i - t0 >= int(max_wait_days):
                    diag["失效_从未站上EMA20"] += 1
                    t0 = -1
            # --- 第一阶段(可以在同一天把旧状态换掉 = 重新锚定);
            #     ★ 但进场当天不行,见上面 ③-d
            if stage1[i, j] and not fired_today:
                if t0 >= 0:
                    diag["重新锚定次数"] += 1
                if not np.isfinite(at[i, j]):
                    diag["止损锚算不出(ATR14 为 NaN)"] += 1
                    t0 = -1
                    continue
                t0 = i
                l0 = lo[i, j]
                s0 = lo[i, j] - float(atr_multiple) * at[i, j]
    return (pd.DataFrame(ev, index=close.index, columns=close.columns),
            pd.DataFrame(stop_m, index=close.index, columns=close.columns),
            diag)


# ================================================================
# ④ PIT SIC + Altman Z'' + F-Score 三层修补
# ================================================================

@functools.lru_cache(maxsize=8)
def sic_daily(symbols: tuple[str, ...]) -> pd.DataFrame:
    """
    ★★ 严格 PIT 的 SIC 码日频面板(本轮新发现:仓库里**本来就有**)。

    来源:每只票 fundamentals.json 的 `sic_versions`,字段自带
      pit_status: "strict" 与 accepted_at(SEC 受理时间)。
    生效口径与基本面一致:**accepted_at + 1 个交易日**才看得见,其后 ffill,
    第一次观测之前 NaN。

    ★ 为什么这件事重要:原来要分辨「是不是金融股」只有
      sector_classification_current_non_pit.csv —— 它自己的元数据写明是
      **当前快照**,用它跑 2016 年整段都在用未来信息。
      ★ 现在用 sic_versions,这道行业豁免是**真 PIT 的**。
      ★ 实测 250 只里有 15 只的 SIC 在样本期内变过
        (例:EQIX 4813→6798、SBAC 4899→6798,是真实的 REIT 转型)——
        用当前快照会把这 15 只的早期年份归错行业。
    """
    import json
    from . import fundamentals
    cal = data.trading_calendar()
    out = pd.DataFrame(np.nan, index=cal, columns=list(symbols))
    arr = cal.to_numpy()
    for s in symbols:
        meta = data.load_manifest().get(s)
        if meta is None or not meta.fundamentals_path:
            continue
        try:
            with open(meta.fundamentals_path, encoding="utf-8") as fh:
                sv = json.load(fh).get("sic_versions") or []
        except (OSError, ValueError):
            continue
        rows = []
        for v in sv:
            code, ts = v.get("sic_code"), v.get("accepted_at") or v.get("observed_from")
            if not code or not ts:
                continue
            eff = fundamentals.effective_date(pd.Timestamp(ts))
            if eff is not None:
                rows.append((eff, float(code)))
        if not rows:
            continue
        rows.sort()
        col = pd.Series(np.nan, index=cal, dtype=float)
        for eff, code in rows:
            pos = int(np.searchsorted(arr, np.datetime64(eff), side="left"))
            if pos < len(cal):
                col.iloc[pos] = code
        out[s] = col.ffill()
    return out


def sic_exempt(symbols: list[str]) -> pd.DataFrame:
    """
    ★ 第一层 行业豁免:SIC 6000–6999 → 不适用 F-Score,由 Altman Z'' 兜底。

    ★ 一个区间同时盖住专家说的「金融」和「房地产」—— SEC 的 Division H
      就叫 Finance, Insurance, And Real Estate,REIT 是 6798、房地产 65xx 都在内。
    ★ 必须讲清楚的一个副作用:这个区间也会把**健康险**扫进去
      (ELV / CNC 的 SIC 是 6324 Hospital & Medical Service Plans)。
      ★ 这是「剔 6000–6999」这个行业惯例自带的后果,不是我们额外加的,
        但它确实让两只医疗保险股拿不到 F-Score 考核、改走 Altman 兜底。
    ★ SIC 看不到(没有 sic_versions 或还没第一次申报)→ **不豁免**(照常考 F-Score)。
      这是紧端:豁免是放宽,拿不到证据就不给放宽。
    """
    _note("④-第一层 行业豁免用的是**严格 PIT 的 SIC 码**(fundamentals.json 的 "
          "sic_versions,pit_status: strict),★ 不是那张非 PIT 的行业快照 CSV。"
          "★ SIC 区间 6000–6999 同时覆盖金融与房地产;★ 副作用:健康险 "
          "(ELV/CNC,SIC 6324)也会被豁免。★ SIC 看不到的那天一律**不豁免**(紧端)。")
    s = sic_daily(tuple(symbols))
    return _as_bool(s.notna() & (s >= SIC_FINANCE_LO) & (s <= SIC_FINANCE_HI))


#: 新增的派生指标 —— 由 fundamentals.metric_quarterly 转发到这里
METRICS = ("altman_z2", "f_score_valid_n", "f_score_sum_valid",
           "f_score_scaled")


def metric_quarterly(symbol: str, name: str, vals: pd.DataFrame,
                     ef: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """新增派生指标的季度序列。★ 算不出一律 NaN —— 不猜、不补、不用近似值顶上。"""
    if name == "altman_z2":
        # ★ Altman 1983 基准版 Z''(四变量,无常数项)—— 与 deep_value.yaml 锁定一致
        #   X1 = (流动资产 − 流动负债)/ 总资产      营运资金占比
        #   X2 = 留存收益 / 总资产                  历史积累
        #   X3 = EBIT / 总资产                      赚钱能力
        #   X4 = 股东权益账面值 / 总负债            偿债缓冲
        # ★ 总负债:先用申报的 Liabilities;缺的用恒等式 总资产 − 股东权益 补
        #   (deep_value.yaml 明确允许,实测能把非 EBIT 那几项齐备率从 ~73% 提到 ~77%)
        ta = vals["ta"].where(vals["ta"] > 0)
        liab = vals["liab"].copy()
        fb = liab.isna() & vals["ta"].notna() & vals["eq"].notna()
        liab[fb] = vals["ta"][fb] - vals["eq"][fb]
        liab = liab.where(liab > 0)
        x1 = (vals["ca"] - vals["cl"]) / ta
        x2 = vals["re"] / ta
        x3 = vals["ebit"] / ta
        x4 = vals["eq"] / liab
        z = (ALTMAN_Z2_COEF["X1"] * x1 + ALTMAN_Z2_COEF["X2"] * x2
             + ALTMAN_Z2_COEF["X3"] * x3 + ALTMAN_Z2_COEF["X4"] * x4
             + ALTMAN_Z2_CONST)
        ok = x1.notna() & x2.notna() & x3.notna() & x4.notna()
        eff = ef[["ta", "ca", "cl", "re", "ebit", "eq", "liab"]].max(axis=1)
        return z.where(ok), eff

    if name in ("f_score_valid_n", "f_score_sum_valid", "f_score_scaled"):
        need = ["ni", "ocf", "ta", "ca", "cl", "ltd", "rev", "cor", "shares"]
        v = vals[need]
        ta0 = v["ta"].shift(4)
        roa = v["ni"] / ta0.where(ta0 > 0)
        cfo = v["ocf"] / ta0.where(ta0 > 0)
        lever = v["ltd"] / v["ta"].where(v["ta"] > 0)
        liquid = v["ca"] / v["cl"].where(v["cl"] > 0)
        margin = (v["rev"] - v["cor"]) / v["rev"].where(v["rev"] > 0)
        turn = v["rev"] / ta0.where(ta0 > 0)
        # ★ 9 项,每项自己带一个「算不算得出」—— 这是三层修补的全部基础:
        #   原来的实现是「任一项算不出 → 整个 NaN」,所以 94.7% 的剔除是
        #   「算不出分」而不是「分低」。现在逐项记有效性。
        items = [
            (roa > 0, roa.notna()),
            (cfo > 0, cfo.notna()),
            (roa > roa.shift(4), roa.notna() & roa.shift(4).notna()),
            (cfo > roa, cfo.notna() & roa.notna()),
            (lever < lever.shift(4), lever.notna() & lever.shift(4).notna()),
            (liquid > liquid.shift(4), liquid.notna() & liquid.shift(4).notna()),
            (v["shares"] <= v["shares"].shift(4),
             v["shares"].notna() & v["shares"].shift(4).notna()),
            (margin > margin.shift(4), margin.notna() & margin.shift(4).notna()),
            (turn > turn.shift(4), turn.notna() & turn.shift(4).notna()),
        ]
        n_valid = sum(a.astype(float) for _, a in items)
        s_valid = sum((p & a).astype(float) for p, a in items)
        eff = ef[need].max(axis=1)
        if name == "f_score_valid_n":
            return n_valid, eff
        if name == "f_score_sum_valid":
            return s_valid, eff
        # ★ 第二层 容差缩放:按有效项比例放大到 9 分制。有效项 < 7 时不给分(NaN)
        scaled = (s_valid * 9.0 / n_valid.where(n_valid > 0))
        return scaled.where(n_valid >= float(F_MIN_VALID_ITEMS)), eff

    raise KeyError(name)


def f_score_three_layer(symbols: list[str], min_score: float = 5.0,
                        min_valid_items: int = F_MIN_VALID_ITEMS,
                        z2_threshold: float = Z2_FALLBACK_EXPERT
                        ) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """
    ★★ F-Score 三层修补的闸门。返回 (通过矩阵, 有效分矩阵, 分流统计)。

    大白话(三秒):原来这道闸是「算不出分就判死刑」,等于系统性剔掉银行、
    保险、REIT 这些科目口径不一样的行业 —— 剔掉的票里 94.7% 是算不出分、
    只有 5.3% 是真分低。三层修补把「算不出」和「分低」分开处理:

      第一层 行业豁免  SIC 6000–6999 → 不考 F-Score,看 Altman Z'' ≥ 阈值
      第二层 容差缩放  有效项 ≥ 7 → 按比例放大到 9 分制,再判 ≥ 5
      第三层 降级      有效项 < 7 → 回退看 Altman Z'' ≥ 阈值,★ 不直接判死刑

    ★ Z'' 也算不出 → 判不通过。这是唯一还会「判死刑」的情形,
      而且它是真的「什么都看不到」,不是「行业口径不一样」。

    ★★ min_valid_items=7 与 z2_threshold=1.80 两个数**专家没给出处** ——
      标「来源存疑(专家自定)」。1.80 落在 Altman 灰区(1.10~2.60)正中间;
      ★ 调用方必须同时跑 z2_threshold=1.10 的那一版并列报。
    """
    from . import fundamentals
    scaled = fundamentals.get("f_score_scaled", symbols)
    n_valid = fundamentals.get("f_score_valid_n", symbols)
    z2 = fundamentals.get("altman_z2", symbols)
    exempt = sic_exempt(symbols)

    l1 = exempt & z2.notna() & (z2 >= float(z2_threshold))
    l2 = (~exempt) & (n_valid >= float(min_valid_items)) & scaled.notna() \
        & (scaled >= float(min_score))
    l3 = (~exempt) & (n_valid < float(min_valid_items)) & z2.notna() \
        & (z2 >= float(z2_threshold))
    # ★ 有效项数算不出(连季报都没有)也走第三层:Z'' 看得到就看 Z''
    l3 |= (~exempt) & n_valid.isna() & z2.notna() & (z2 >= float(z2_threshold))
    gate = _as_bool(l1 | l2 | l3)

    perf = pd.Timestamp(data.PERF_START)
    w = gate.index >= perf
    def cnt(df):
        return int(np.asarray(_as_bool(df).to_numpy())[w, :].sum())
    cells = int(w.sum() * len(gate.columns))
    stat = {
        "口径": f"F-Score ≥ {min_score:g}(9 分制)· 有效项 ≥ {min_valid_items} ·"
                f" Altman Z'' 兜底阈值 {z2_threshold:g}",
        "★阈值来源": (f"★ 有效项 ≥ {min_valid_items} 与 Z'' ≥ {z2_threshold:g} 都是"
                      f"「来源存疑(专家自定)」—— 专家没给出处;"
                      f"Altman 自己的分区是 困境<1.10 / 灰区 1.10~2.60 / 安全>2.60"),
        "绩效窗口内格子数(日×票)": cells,
        "第一层 行业豁免(SIC 6000–6999)格子": cnt(exempt),
        "  其中 Z'' 兜底通过": cnt(l1),
        "  其中 Z'' 算不出或不达标 → 不通过": cnt(exempt) - cnt(l1),
        "第二层 容差缩放(有效项≥7)通过": cnt(l2),
        "第二层 有效项≥7 但缩放分 < 门槛 → ★ 真·分低被剔": cnt(
            (~exempt) & (n_valid >= float(min_valid_items)) & scaled.notna()
            & (scaled < float(min_score))),
        "第三层 降级(有效项<7)Z'' 兜底通过": cnt(l3),
        "★ 彻底算不出(F 项不足且 Z'' 也 NaN)→ 不通过": cnt(
            (~exempt) & (n_valid < float(min_valid_items)) & z2.isna()),
        "闸门通过格子合计": cnt(gate),
        "闸门通过率": round(cnt(gate) / cells, 4) if cells else None,
    }
    return gate, scaled, stat


# ================================================================ 自验

def main() -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"全池 {len(syms)} 只")
    sic = sic_daily(tuple(syms))
    last = sic.ffill().iloc[-1]
    print(f"★ PIT SIC 覆盖:{int(last.notna().sum())} / {len(syms)} 只拿到 SIC 码")
    ex = sic_exempt(syms)
    names = sorted(ex.columns[ex.any(axis=0)])
    print(f"★ 第一层 行业豁免(SIC 6000–6999)命中 {len(names)} 只:{names}")
    for thr in (Z2_FALLBACK_EXPERT, Z2_FALLBACK_ALTMAN):
        _, _, st = f_score_three_layer(syms, z2_threshold=thr)
        print(f"\n===== Altman Z'' 兜底阈值 = {thr} =====")
        for k, v in st.items():
            print(f"  {k}: {v}")
    print("\n★ 显式做了选择、专家没给口径的地方:")
    for n in notes():
        print("  · " + n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
