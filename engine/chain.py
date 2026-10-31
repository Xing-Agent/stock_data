"""
第二层:模拟层 —— 一个老老实实的逐日 for 循环。

★ 为什么自己写、不用向量化回测库:
  我们真正要跑的出场逻辑是「初始止损 + 吊灯跟踪 + 时间止损 + 浮盈后移保本」,
  这是强路径依赖的 —— 今天的止损价取决于进场以来每一天发生过什么。
  这种东西用张量广播表达,最后会退化成密集循环,而且极容易写错
  (吊灯那个 bug 两天内被三个人独立踩到)。所以第一层向量化,第二层手写。

七步里这一层负责 ③~⑦:
  ③ 进场扳机(查第一层的 entry 矩阵)
  ④ 初始止损  ⑤ 移动止损  ⑥ 离场  ⑦ 仓位

成交约定:
  · 信号在 t 日收盘后成立 → t+1 日开盘成交
  · ★★ 止损成交价 = min(止损价, 当日开盘价) —— 坑二(跳空风险)
    跳空穿透止损时按开盘价成交,不许按止损价成交。
    并单独统计「有多少笔是跳空穿透的、平均穿透多少」。
  · 止盈 / 时间止损按收盘判断 → 次日开盘成交
  · 退市:破产类在缓存层已埋 0 价 bar,这里照常走止损/结算,自然吃到 −100%

★★ 吊灯止损两条铁律(写死在代码里,配置改不动):
   一、止损价不能高于当根收盘价
   二、只能往上抬
   征兆:胜率 >60% 或每笔 >+0.5R。跑出这种数先停下来检查。

吐出来的是一份交易流水(ledger),第三层 analyze.py 吃它做全部统计。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import cache, data, matrices

TRADING_DAYS_PER_YEAR = 252

# ---------------------------------------------------------------- 摩擦成本分档
# ★ 坑四:统一扣固定摩擦会系统性美化高频、惩罚低频。按 ADV20 分位数分三档。
# ★ 具体数值定不下来,所以做成配置项,并默认同时报三档敏感度 ——
#   不许自己挑一个好看的。
# ★★★ 退化 R 的判据(2026-10-31 · 策略组拍板甲)
#   risk 占进场价的比例低于这个数,就认为「本来准备亏多少」说不清 → 这笔 R 剔掉。
#   ★ 1e-4 = 万分之一。$100 的票对应 1 分钱 —— 比任何真实止损距离都小几个量级。
DEGENERATE_R_MIN = 1e-4

FRICTION_TIERS_DEFAULT = {
    "high_liquidity_bps": 5.0,    # ADV20 排在全池前 1/3
    "mid_liquidity_bps": 15.0,    # 中间 1/3
    "low_liquidity_bps": 30.0,    # 后 1/3
}
FRICTION_SENSITIVITY_FLAT = (5.0, 15.0, 30.0)   # 一刀切敏感度:0.05% / 0.15% / 0.30%


# ================================================================ 配置

@dataclass
class ChainConfig:
    raw: dict[str, Any]
    adapt_report: Any = None

    @classmethod
    def load(cls, path: str) -> "ChainConfig":
        with open(path, encoding="utf-8") as fh:
            if path.endswith((".yaml", ".yml")):
                import yaml
                cfg = yaml.safe_load(fh)
            else:
                cfg = json.load(fh)
        return cls.from_dict(cfg)

    @classmethod
    def from_dict(cls, cfg: dict) -> "ChainConfig":
        # ★ 先过适配层:两套字段名都认,并把「还没实现的规则」明确报出来
        from .config_adapter import adapt
        norm, rep = adapt(cfg)
        obj = cls(norm).validate()
        obj.adapt_report = rep
        return obj

    def validate(self) -> "ChainConfig":
        need = ["universe", "regime", "entry", "initial_stop",
                "trailing_stop", "exit", "sizing"]
        missing = [k for k in need if k not in self.raw]
        if missing:
            raise ValueError(f"配置缺了这几步(七步一步都不能少):{missing}")
        for step in need:
            blk = self.raw[step] or {}
            if isinstance(blk, dict) and blk.get("params") and not blk.get("source"):
                raise ValueError(
                    f"★ 第 {step} 步有参数但没写 source。参数只能来自原著或行业惯例,"
                    f"并在配置里标明出处(硬纪律第 6 条,禁止网格搜索)。")
        return self

    def get(self, k: str, default=None):
        return self.raw.get(k, default)

    @property
    def name(self) -> str:
        return (self.raw.get("meta") or {}).get("name", "unnamed_chain")

    def copy_with(self, **overrides) -> "ChainConfig":
        import copy
        cfg = copy.deepcopy(self.raw)
        cfg.update(overrides)
        return ChainConfig(cfg)      # 内部变体不再强制 validate


# ================================================================ 交易流水

LEDGER_COLUMNS = [
    "symbol", "entry_date", "exit_date", "entry_price", "exit_price",
    "shares", "initial_stop", "stop_at_exit", "reason", "holding_days",
    "gross_return", "r_multiple", "r_multiple_net", "risk_per_share",
    "notional_in", "notional_out", "friction_bps", "friction_cost",
    "net_pnl", "gross_pnl", "capital_days",
    "gap_through", "gap_penetration_r", "adv20_at_entry", "liquidity_tier",
    # ★ 进场那天广度标尺给的风险乘数(1.0 = 正常 1.0R,0.5 = 减半)。
    #   ★ 位置标尺不会改变每笔的 R 倍数(R 是价格口径),只改变这一笔冒多少风险 ——
    #   所以比较「减不减仓」必须用 风险加权R = r_multiple × size_mult,
    #   直接比 r_multiple 的话两版一模一样,等于什么都没测。
    "size_mult",
]


@dataclass
class ChainResult:
    name: str
    equity: pd.Series             # 净值(已扣摩擦)
    equity_gross: pd.Series       # 毛净值(不扣摩擦)
    exposure: pd.Series           # 每日净敞口(持仓市值 / 权益)
    ledger: pd.DataFrame
    initial_equity: float
    notes: list[str] = field(default_factory=list)

    def save_ledger(self, path: str) -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.ledger.to_csv(path, index=False)
        return path


# ================================================================ 内部小工具

def _liquidity_tiers(adv20: np.ndarray) -> np.ndarray:
    """
    把每天每只票按 ADV20 分成三档(0=高流动性, 1=中, 2=低)。
    分位线用全池当日横截面的 1/3、2/3 —— 规则固定,不是调出来的。
    """
    out = np.full(adv20.shape, 1, dtype=np.int8)
    for t in range(adv20.shape[0]):
        row = adv20[t]
        ok = np.isfinite(row)
        if ok.sum() < 10:
            continue
        q1, q2 = np.nanquantile(row[ok], [1 / 3, 2 / 3])
        out[t] = np.where(row >= q2, 0, np.where(row >= q1, 1, 2))
    return out


def _friction_bps(tier: int, tiers_cfg: dict, flat: float | None) -> float:
    if flat is not None:
        return float(flat)
    keys = ("high_liquidity_bps", "mid_liquidity_bps", "low_liquidity_bps")
    return float(tiers_cfg.get(keys[tier], FRICTION_TIERS_DEFAULT[keys[tier]]))


#: ★ t0_anchor_stop 回退到「进场根最低价」的次数。
#   ★ 用途:证明**正式链一次都没走到回退路径**(只有基准一/归因中间行会走)。
#   跑完用 t0_fallback_count() 读,报告里打出来。
_T0_FALLBACK = {"n": 0}


def t0_fallback_count() -> int:
    return int(_T0_FALLBACK["n"])


def reset_t0_fallback_count() -> None:
    _T0_FALLBACK["n"] = 0


def _stage_hits(when: dict, r_now: float, held: int,
                extra: dict | None = None) -> bool:
    """
    多级移动止损:判断当前是不是落在这一级的条件里。
    认得的条件:unrealized_r_gt / unrealized_r_lt / unrealized_r_between /
                days_held_gte / days_held_lte / close_above_ma(不支持,见下)
    ★ 认不出来的条件一律返回 False(这一级不生效),并不会悄悄放宽别的级 ——
      配置里真用到了没实现的条件,config_adapter 会在加载时就报出来。
    """
    if not when:
        return True
    for k, v in when.items():
        if k == "unrealized_r_gt":
            if not (np.isfinite(r_now) and r_now > float(v)):
                return False
        elif k == "unrealized_r_lt":
            if not (np.isfinite(r_now) and r_now < float(v)):
                return False
        elif k == "unrealized_r_between":
            lo, hi = float(v[0]), float(v[1])
            if not (np.isfinite(r_now) and lo <= r_now <= hi):
                return False
        elif k == "days_held_gte":
            if not held >= int(v):
                return False
        elif k == "days_held_lte":
            if not held <= int(v):
                return False
        # ------------------------------------------------------------------
        # ★★ 1029 第二轮新增两个条件 —— 为了让流派三的 ⑤ 能跑。
        #   两条都是 A 类(口径本来就讲得清楚,只是引擎没写),★ 不是我们在填参数:
        #   · close_above_ma: N   收盘价站上 N 日简单均线
        #   · after_stage: 名字   前面那一级已经触发过了(分级有先后顺序)
        # ★ 需要的数由主循环通过 extra 传进来;extra 没给 → 这一级不生效(返回
        #   False),★ 不会悄悄放宽成 True。
        # ------------------------------------------------------------------
        elif k == "close_above_ma":
            if extra is None or not extra.get("close_above_ma", False):
                return False
        elif k == "after_stage":
            if extra is None or str(v) not in (extra.get("stages_done") or set()):
                return False
        else:
            return False       # 不认识的条件 → 这一级不生效
    return True


def _chandelier_at(m: matrices.Matrices, j: int, i: int, sp: dict) -> float:
    """
    按这一级自己的参数算吊灯原始值。
    参数和预算好的矩阵一致时直接查表;不一致就现算(只算一只票一根,很便宜)。
    """
    lb = int(sp.get("lookback", 22))
    mult = float(sp.get("multiple", 3.0))
    lo = max(0, i - lb + 1)
    hh = m.high[lo:i + 1, j]
    hh = hh[np.isfinite(hh)]
    a = m.atr[i, j]
    if not hh.size or not np.isfinite(a):
        return float("nan")
    return float(hh.max()) - mult * float(a)


def _one_stop(m: matrices.Matrices, j: int, i: int, entry_px: float,
              spec: dict) -> float:
    """算一个止损价。i 是成交那一行,一律用 i-1 行的指标(不偷看当天)。"""
    kind = spec.get("type")
    p = spec.get("params", {}) or {}
    k = max(0, i - 1)

    if kind == "atr_multiple":
        a = m.atr[k, j]
        mult = float(p.get("multiple", 2.0))
        if not np.isfinite(a):
            return float("nan")
        # ★ anchor:止损挂在哪条线下面。★ 认不出来的 anchor 直接报错 ——
        #   悄悄按进场价处理会让配置里写的「挂在突破位下方」没被执行。
        anchor = str(p.get("anchor", "entry_price"))
        if anchor == "entry_price":
            base = entry_px
        elif anchor == "breakout_level_of_20d_high":
            # 突破位 = 信号那根之前 20 日的最高收盘(和 ③ 的扳机口径一致)
            n = 20
            win = m.close[max(0, k - n):k, j]
            win = win[np.isfinite(win)]
            base = float(win.max()) if win.size else entry_px
        elif anchor == "signal_bar_low":
            lo = m.low[k, j]
            base = float(lo) if np.isfinite(lo) else entry_px
        else:
            raise NotImplementedError(
                f"④ 初始止损的 anchor={anchor!r} 还没实现 —— ★ 没有悄悄按进场价处理。")
        return base - mult * float(a)
    if kind == "pct":
        return entry_px * (1.0 - float(p.get("pct", 0.10)))
    if kind == "chandelier":
        raw = m.chandelier[k, j]
        return float(min(raw, entry_px * 0.999)) if np.isfinite(raw) else float("nan")
    if kind == "none":
        # ★★ A0:「原著不设止损」的显式表达方式(技-2 法伯 / 技-12 康纳斯)。
        #   止损价写 0.0 —— 只有价格归零(破产退市那根 0 价 bar)才会触发,
        #   也就是说普通行情下永远不止损,★ 这正是原著的行为。
        #   ★ 为什么不用「pct: 0.99」那种远止损顶替:那会让 1R = 99% 的进场价,
        #     R 乘数(模-5)全部被稀释成假数字。写 0 的话 risk = 进场价,
        #     R 退化成「收益率」,口径清楚、可解释。
        #   ★ 代价必须写明:这条链的 R 不是「风险归一化」后的 R,
        #     不能和有止损的链比每笔 R。
        return 0.0
    if kind == "lowest_low":
        n = int(p.get("lookback", 20))
        lo = m.low[max(0, k - n + 1):k + 1, j]
        lo = lo[np.isfinite(lo)]
        return float(lo.min()) if lo.size else float("nan")
    if kind in ("structure_low_minus_atr", "day_low_minus_atr"):
        n = int(p.get("structure_lookback", 1))
        lo = m.low[max(0, k - n + 1):k + 1, j]
        lo = lo[np.isfinite(lo)]
        a = m.atr[k, j]
        if not lo.size or not np.isfinite(a):
            return float("nan")
        # ★ 两套字段名都认(atr_multiple / multiple);★ 都没写才用默认 0.3,
        #   并且这种情况下配置必然没标 source,validate 那一关已经拦住了。
        mult = p.get("atr_multiple", p.get("multiple", 0.3))
        return float(lo.min()) - float(mult) * float(a)
    if kind == "t0_anchor_stop":
        # ★★ 1029:流派一双阶段状态机的「绝对初始止损锚点」
        #   Stop = Low[T0] − 0.5 × ATR14[T0],T0 = 第一阶段触底排毒那一根。
        #   ★ 值已在第一层算好存进 m.t0_stop(进场日那一格),这里只取出来。
        #   ★ 为什么不能用 day_low_minus_atr 顶替:进场发生在第二阶段
        #     (T0+1 .. T0+10),用进场那根的最低价算会得到完全不同的止损 ——
        #     专家裁决写的是「记录当日最低价 Low[T0] 作为绝对初始止损锚点」。
        v = m.t0_stop[k, j]
        if np.isfinite(v):
            return float(v)
        # ==============================================================
        # ★★ 取不到 T0 锚点怎么办 —— 这一段必须讲清楚,它关系到基准一公不公平。
        #
        # 什么时候会取不到:**只有当进场扳机被换掉的时候**。
        #   · 「基准一 同环境随机进场」把 ③ 换成随机进场 → 随机那天没有 T0
        #   · 分步归因的中间行(买入持有 / +环境 / +选股)同理
        #   ★ 正式链的每一个进场日都必然有 T0 锚点(状态机吐信号的同时就写了锚点),
        #     ★ 所以正式链**永远不会**走到这里 —— 下面的计数器可以证明这一点。
        #
        # 怎么处理:★ 回退到「同一个公式、锚在进场那根」= Low[进场根] − mult×ATR14。
        #   ★ 为什么这是对的:基准一问的是「**扳机**挑得准不准」,
        #     所以除了扳机以外的六步要尽量一样。而 T0 锚点本身是**扳机状态机的一部分**
        #     (它来自第一阶段那根),随机进场根本没有「第一阶段」——
        #     ★ 最接近的同类止损就是「同样的 0.5×ATR14,锚在它自己的信号根上」。
        #   ★★ 但必须如实标明:基准一和正式链的止损锚点**不是同一根 K 线**,
        #     所以两者的 R 定义有细微差别。方向上:正式链的锚点(T0 的低点)通常
        #     比进场根的低点更低、更远 → 正式链的止损更宽、每笔 R 的分母更大。
        #   ★ 必须显式开启(fallback_to_signal_bar_low: true),★ 不是默认行为 ——
        #     默认仍然报错,免得哪天真链出问题被这条路径悄悄盖过去。
        # ==============================================================
        if p.get("fallback_to_signal_bar_low"):
            lo = m.low[k, j]
            a = m.atr[k, j]
            if np.isfinite(lo) and np.isfinite(a):
                mult = p.get("atr_multiple", p.get("multiple", 0.5))
                _T0_FALLBACK["n"] += 1
                return float(lo) - float(mult) * float(a)
            return float("nan")
        raise ValueError(
            "④ t0_anchor_stop 在进场日取不到 T0 止损锚点 —— ★ 没有悄悄回退到"
            "进场那根的最低价(那会算出完全不同的止损)。\n"
            "★ 如果你是在跑「基准一 随机进场」或分步归因的中间行,这是预期的:"
            "那些变体把 ③ 换掉了,没有第一阶段、也就没有 T0 锚点 —— "
            "请在 stop_init.params 里显式写 fallback_to_signal_bar_low: true,"
            "并在报告里写明基准一的止损锚点和正式链不是同一根 K 线。\n"
            "★ 如果这是正式链报的,那是真 bug:检查 ③ 是否写了 "
            "deep_value_two_stage,以及 matrices.build 是否把 t0_stop 填上了。")
    raise ValueError(f"不认识的初始止损 type={kind}")


def _initial_stop_spec(m: matrices.Matrices, j: int, i: int, entry_px: float,
                       spec: dict) -> float:
    """
    ④ 初始止损。支持 tightest_of:几种算法各算一个,取离进场价最近的那个
    (做多就是取最高的那个止损价 —— 止损最紧)。
    还支持 hard_gate:止损距离超过上限就直接拒掉这个信号(返回 nan)。
    """
    kind = spec.get("type")
    if kind == "tightest_of":
        vals = [_one_stop(m, j, i, entry_px, c)
                for c in (spec.get("components") or [])]
        vals = [v for v in vals if np.isfinite(v) and v < entry_px]
        if not vals:
            return float("nan")
        stop = max(vals) if spec.get("select", "nearest_to_price") == "nearest_to_price" \
            else min(vals)
    else:
        stop = _one_stop(m, j, i, entry_px, spec)
    if not np.isfinite(stop):
        return float("nan")
    hg = spec.get("hard_gate")
    if hg and hg.get("type") == "max_stop_distance_pct":
        max_pct = float((hg.get("params", {}) or {}).get("max_pct", 100.0)) / 100.0
        if (entry_px - stop) / entry_px > max_pct:
            return float("nan")      # ★ 止损太远 → 拒掉这个信号,不是放大止损
    # ★ 1029:顶层写法 max_stop_distance_pct + on_exceed 也认一下。
    #   ★★ 诚实交代:我一开始以为这是一个「配置写了、引擎没执行」的失真 bug,
    #     ★ 核下来**不是** —— config_adapter 第 320 行已经把顶层写法翻成
    #     hard_gate 了,所以走正常加载路径的配置一直都在执行这道硬闸,
    #     ★ 流派一历史结果**没有**受影响,不需要重跑校正。
    #   ★ 这里留着只是兜底:直接把原始 dict 喂给执行器、不过适配层的时候
    #     (测试、留一法里手搓的 dict)也不会漏掉这道闸。
    #   ★ 两条路径阈值相同 → 重复判一次是幂等的,不改变任何结果。
    flat = spec.get("max_stop_distance_pct")
    if flat is not None:
        oe = str(spec.get("on_exceed", "reject_entry"))
        if oe != "reject_entry":
            raise NotImplementedError(
                f"④ max_stop_distance_pct 的 on_exceed={oe!r} 还没实现 —— "
                f"★ 没有悄悄当成 reject_entry 处理。")
        if (entry_px - stop) / entry_px > float(flat) / 100.0:
            return float("nan")
    return stop


# ================================================================ 主循环

def run_chain(cfg: ChainConfig,
              symbols: list[str] | None = None,
              start: str = data.PERF_START,
              end: str = data.PERF_END,
              initial_equity: float = 1_000_000.0,
              m: matrices.Matrices | None = None,
              flat_friction_bps: float | None = None,
              total_return: bool | None = None) -> ChainResult:
    """
    跑一条链。
    flat_friction_bps 不为 None 时改用一刀切成本(做摩擦敏感度用)。

    ★★ total_return —— 分红口径开关(2026-10-29 新增):
      None(默认)→ 取 data.TOTAL_RETURN_DEFAULT
      False → 纯价格收益(历史口径)
      True  → ★ 总收益:持仓跨过除息日时,把 每股分红 × 持股数 记为现金收入

    ★ 为什么是"记现金"而不是"把历史价格按分红往回折算":
      折算历史价格会改变**信号**(均线、突破、ATR 全在价格上),
      那样 A/B 两版成交的就不是同一批交易,分不清变化是分红带来的还是信号漂移带来的。
      ★ 记现金则**完全不动信号** —— 成交哪几笔一模一样,只是每笔多收一笔股息,
      而且这笔钱会跟着净值一起复利(这正是上一轮"加法测算"做不到的那一部分)。

    ★ 时点口径(PIT):分红在**每日循环的最开头**入账,即只有
      "昨天收盘就已经持有"的仓位才拿得到 —— 和除息日规则一致:
        · 今天开盘卖出的仓位 → ★ 拿得到(昨收时还持有)
        · 今天开盘买入的仓位 → ★ 拿不到(除息日当天买不享有)
    """
    if total_return is None:
        total_return = bool(data.TOTAL_RETURN_DEFAULT)
    m = m or matrices.build(cfg.raw, symbols)
    idx = m.index
    perf = data.perf_window(idx, start, end)
    if len(perf) == 0:
        raise ValueError(f"绩效窗口 {start}..{end} 里没有交易日")
    i0, i1 = int(idx.get_loc(perf[0])), int(idx.get_loc(perf[-1]))

    tiers = _liquidity_tiers(m.adv20)
    costs_cfg = cfg.get("costs") or {}
    fric_cfg = costs_cfg.get("friction_tiers", FRICTION_TIERS_DEFAULT)
    # 配置里写了 one_way_bps 就当一刀切成本用(基线链/对数用);
    # 正式跑链一律留空,走 ADV20 分三档(坑四)
    if flat_friction_bps is None and costs_cfg.get("one_way_bps") is not None \
            and "friction_tiers" not in costs_cfg:
        flat_friction_bps = float(costs_cfg["one_way_bps"])

    sz = cfg.get("sizing") or {}
    sz_type = sz.get("type", "risk_fraction")
    szp = sz.get("params", {}) or {}
    risk_frac = float(szp.get("risk_per_trade", 0.01))
    max_slots = int(szp.get("max_positions", 10))          # ★ 槽位数是配置项
    max_w = float(szp.get("max_weight", 1.0 / max(1, max_slots)))
    equal_all = sz_type == "equal_weight_all"

    istop_spec = dict(cfg.get("initial_stop") or {})
    istop_spec.setdefault("type", "atr_multiple")

    trail = cfg.get("trailing_stop") or {}
    trail_type = trail.get("type", "none")
    be_trigger = (trail.get("params", {}) or {}).get("breakeven_after_r")
    be_trigger = float(be_trigger) if be_trigger is not None else None
    # ★★ 1029 修一处「反向的悄悄忽略」:执行器以前不看分级上的 enabled: false,
    #   config_adapter 看(_off),于是会出现「适配层说这一级已显式关掉、
    #   执行器照样在跑」的不一致 —— 方向上比漏执行更坏:报告里写着关掉了,
    #   实际它还在干活。★ 现在两边口径一致。
    stages = [s for s in (trail.get("stages") or [])
              if not (isinstance(s, dict) and s.get("enabled") is False)]
    _stages_off = [s.get("name") for s in (trail.get("stages") or [])
                   if isinstance(s, dict) and s.get("enabled") is False]

    exp_ = (cfg.get("exit") or {}).get("params", {}) or {}
    target_r = exp_.get("profit_target_r")
    time_stop = exp_.get("time_stop_days")
    target_r = float(target_r) if target_r is not None else None
    time_stop = int(time_stop) if time_stop is not None else None

    rank_by = (cfg.get("sizing") or {}).get("rank_by", "rs_rank")

    cash = cash_gross = initial_equity
    # ★★ 分红矩阵 [日 × 票]:只在 total_return=True 时才建(默认完全不碰)。
    #   ★ 用 data.dividends() —— 它已经按源头 split_coefficient 把每股分红折算过,
    #     所以"每股分红"和"每股价格"在同一个口径上。
    div_mat: np.ndarray | None = None
    div_received = 0.0
    n_div_credits = 0
    if total_return:
        div_mat = np.zeros((len(idx), len(m.symbols)), dtype=float)
        for j, sym in enumerate(m.symbols):
            try:
                s = data.dividends(sym)
            except Exception:
                continue
            if len(s) == 0:
                continue
            s = s[(s.index >= idx[0]) & (s.index <= idx[-1])]
            if len(s) == 0:
                continue
            locs = idx.get_indexer(s.index)
            for k, v in zip(locs, s.to_numpy(float)):
                if k >= 0:
                    div_mat[k, j] += float(v)
    # ★ 广度标尺的落地诊断:有多少笔真的被减仓、其中多少笔被 max_weight 顶住
    n_scaled = n_cap_bind = 0
    pos: dict[int, dict] = {}
    rows: list[dict] = []
    eq, eqg, expo = [], [], []
    pending_exit: dict[int, str] = {}
    pending_entry: list[int] = []

    def _price(j: int, i: int, which: np.ndarray) -> float:
        v = which[i, j]
        if np.isfinite(v):
            return float(v)
        k = min(i, int(m.last_bar[j]))
        while k >= 0 and not np.isfinite(m.close[k, j]):
            k -= 1
        return float(m.close[k, j]) if k >= 0 else 0.0

    def _close(j: int, i: int, px: float, reason: str,
               gap: bool = False, pen_r: float = 0.0) -> None:
        nonlocal cash, cash_gross
        p = pos.pop(j)
        tier = int(tiers[min(p["entry_i"], len(tiers) - 1), j])
        bps = _friction_bps(tier, fric_cfg, flat_friction_bps)
        rate = bps / 10_000.0
        nin, nout = p["shares"] * p["entry"], p["shares"] * px
        fric = (nin + nout) * rate
        cash += nout * (1 - rate)
        cash_gross += nout
        risk = abs(p["entry"] - p["init_stop"])
        # ★★★ 退化 R(2026-10-31 定,策略组拍板「甲:剔掉这一笔」)
        #   止损价落在进场价上 → 这笔「本来准备亏」= 0 → R = 盈亏 ÷ 0。
        #   ★ 原来只挡 `risk > 0`,挡不住 risk 是**极小正数**(浮点残差)的情况 ——
        #     实测算出 1.75e14,一笔就把技-10 的基准一毁成 −31 亿。
        #   ★★ 判据用相对值(risk 占进场价的比例),不用绝对值 ——
        #     因为 $5 的票和 $500 的票,同样的绝对 risk 含义完全不同。
        #   ★★★ 剔掉 = 承认「这一笔算不出来」,★ 其余所有 R 一个不动
        #     (另一种补法「用进场价当分母」会改全库每一个 R,已否决)。
        #   ★ 实测:真链流水 0 笔退化,全部出在随机对照组那边。
        r_ok = risk > 0 and p["entry"] > 0 and (risk / p["entry"]) >= DEGENERATE_R_MIN
        hd = i - p["entry_i"]
        rows.append({
            "symbol": m.symbols[j],
            "entry_date": idx[p["entry_i"]], "exit_date": idx[i],
            "entry_price": p["entry"], "exit_price": px, "shares": p["shares"],
            "initial_stop": p["init_stop"], "stop_at_exit": p["stop"],
            "reason": reason, "holding_days": hd,
            "gross_return": px / p["entry"] - 1.0 if p["entry"] > 0 else np.nan,
            "r_multiple": (px - p["entry"]) / risk if r_ok else np.nan,
            # ★ 扣掉摩擦之后的 R —— 比较高频/低频策略必须看这个,
            #   价格口径的 R 不受摩擦影响,会系统性美化高频
            "r_multiple_net": ((nout - nin - fric) / (risk * p["shares"])
                               if r_ok and p["shares"] > 0 else np.nan),
            # ★ 留痕:这一笔是不是因为退化 R 被剔掉的(便于事后对账,不许静默丢弃)
            "r_degenerate": bool(not r_ok),
            "risk_per_share": risk,
            "notional_in": nin, "notional_out": nout,
            "friction_bps": bps, "friction_cost": fric,
            "gross_pnl": nout - nin, "net_pnl": nout - nin - fric,
            "capital_days": nin * max(1, hd),      # 坑一:资金占用用它算
            "gap_through": bool(gap), "gap_penetration_r": float(pen_r),
            "adv20_at_entry": float(m.adv20[p["entry_i"], j]),
            "liquidity_tier": ("高流动性", "中流动性", "低流动性")[tier],
            "size_mult": float(m.size_mult[p["entry_i"]]),
        })

    for i in range(i0, i1 + 1):
        # ---- ⓞ ★★ 分红入账(总收益口径)。★ 放在最前面 = 只有"昨收已持有"的
        #        仓位拿得到:今天卖的拿得到、今天买的拿不到 —— 与除息日规则一致。
        if div_mat is not None and pos:
            for j, p in pos.items():
                dv = div_mat[i, j]
                if dv:
                    gain = p["shares"] * dv
                    cash += gain
                    cash_gross += gain
                    div_received += gain
                    n_div_credits += 1

        # ---- ① 昨天收盘决定的离场,今天开盘成交
        for j in list(pending_exit):
            if j in pos:
                _close(j, i, _price(j, i, m.open), pending_exit[j])
            pending_exit.pop(j, None)

        # ---- ② 昨天收盘的信号,今天开盘买入
        queue = [j for j in pending_entry
                 if j not in pos and np.isfinite(m.open[i, j]) and m.open[i, j] > 0]
        remaining = len(queue)
        for j in queue:
            if not equal_all and len(pos) >= max_slots:
                break
            entry_px = float(m.open[i, j])
            stop0 = _initial_stop_spec(m, j, i, entry_px, istop_spec)
            if not np.isfinite(stop0) or stop0 >= entry_px:
                remaining -= 1
                continue
            equity_now = cash + sum(p["shares"] * _price(k, i, m.open)
                                    for k, p in pos.items())
            if equal_all:
                notional = cash / max(1, remaining)
            elif sz_type == "risk_fraction":
                # ★★ 改动二:广度当「风险预算标尺」—— 当天的单笔风险 = risk_frac × 乘数。
                #   广度好 → ×1.0(1.0R 正常);广度差 → ×low_risk_mult(例如 0.5R),
                #   ★ 但照常允许开仓(不是开关)。乘数由第一层按广度算好,已 shift(1)。
                rf = risk_frac * float(m.size_mult[i])
                by_risk = (equity_now * rf) / (entry_px - stop0) * entry_px
                by_cap = equity_now * max_w
                if rf != risk_frac:
                    n_scaled += 1
                    if by_cap < by_risk:
                        n_cap_bind += 1      # ★ 这笔被 max_weight 顶住了,减仓没生效多少
                notional = min(by_risk, by_cap)
            elif sz_type == "fixed_fraction":
                notional = equity_now * max_w
            else:
                raise ValueError(f"不认识的仓位 type={sz_type}")
            tier = int(tiers[i, j])
            rate = _friction_bps(tier, fric_cfg, flat_friction_bps) / 10_000.0
            notional = min(notional, cash / (1 + rate))
            remaining -= 1
            if notional <= 0:
                continue
            shares = notional / entry_px
            cash -= notional * (1 + rate)
            cash_gross -= notional
            pos[j] = {"shares": shares, "entry": entry_px, "stop": stop0,
                      "init_stop": stop0, "entry_i": i, "be_done": False}
        pending_entry = []

        # ---- ③ 持仓当日:先查止损 / 退市
        for j in list(pos):
            p = pos[j]
            lo, op_, cl = m.low[i, j], m.open[i, j], m.close[i, j]
            if i >= int(m.last_bar[j]):
                # 末根:破产类这一根已经是 0 价 bar → 自动 −100%
                _close(j, i, _price(j, i, m.close), "退市结算")
                continue
            if np.isfinite(lo) and lo <= p["stop"]:
                # ★★ 坑二:跳空穿透止损时按开盘价成交,不许按止损价
                if np.isfinite(op_) and op_ < p["stop"]:
                    fill, gap = float(op_), True
                    risk = abs(p["entry"] - p["init_stop"])
                    pen = (p["stop"] - op_) / risk if risk > 0 else 0.0
                else:
                    fill, gap, pen = float(p["stop"]), False, 0.0
                _close(j, i, fill, "止损", gap=gap, pen_r=pen)

        # ---- ④ 还活着的持仓:抬止损 + 收盘判离场
        for j, p in pos.items():
            cl = m.close[i, j]
            if not np.isfinite(cl):
                continue
            risk = abs(p["entry"] - p["init_stop"])
            r_now = (cl - p["entry"]) / risk if risk > 0 else np.nan

            if trail_type == "chandelier":
                raw = m.chandelier[i, j]
                if np.isfinite(raw):
                    # ★★ 两条铁律:不能高于当根收盘;只能往上抬
                    p["stop"] = max(p["stop"], min(raw, cl))
                    assert p["stop"] <= cl + 1e-9, (
                        f"吊灯止损高于当根收盘:{m.symbols[j]} {idx[i].date()} "
                        f"stop={p['stop']} close={cl}")
            elif trail_type == "staged":
                # 多级移动止损:按条件挑出当前该用哪一级
                # ★★ 取「最后一个条件满足的那一级」,不是第一个。
                #   以前取第一个是个真 bug:流派二的 ⑤ 是 保护期 → 保本(>2R)
                #   → EMA10 跟踪(>3R),取第一个的话浮盈 5R 时会停在「保本」那级,
                #   EMA10 跟踪永远不会启动 —— 配置里写了的东西没被执行。
                held = i - p["entry_i"]
                # ★★ 1029:给 _stage_hits 补两个它自己算不出来的条件
                #   (close_above_ma 要价格和均线,after_stage 要持仓的历史状态)
                ma_ok = False
                if np.isfinite(m.stage_ma[i, j]):
                    ma_ok = bool(cl > m.stage_ma[i, j])
                extra = {"close_above_ma": ma_ok,
                         "stages_done": p.setdefault("stages_done", set())}
                st = None
                for cand in stages:
                    if _stage_hits(cand.get("when") or {}, r_now, held, extra):
                        st = cand
                        # ★ 记下「这一级触发过」,给 after_stage 用。
                        #   ★ 注意顺序:先记录再执行,所以同一天后面那一级
                        #     就能看到前一级已经触发 —— 这正是「保本 → 前低跟踪」
                        #     要的语义(站上 MA20 的那天起就可以开始跟踪)。
                        nm = cand.get("name")
                        if nm:
                            extra["stages_done"].add(str(nm))
                if st is not None:
                    act = st.get("action")
                    if act == "hold_initial_stop":
                        pass                        # 锁死期:不动
                    elif act in ("move_to_breakeven", "breakeven",
                                 "move_stop_to_breakeven"):
                        p["stop"] = max(p["stop"], min(p["entry"], cl))
                    elif act == "exit_unconditional":
                        pending_exit[j] = st.get("name") or "分级离场"
                    elif st.get("type") == "chandelier" or act == "chandelier":
                        sp = st.get("params", {}) or {}
                        raw = _chandelier_at(m, j, i, sp)
                        if np.isfinite(raw):
                            # ★★ 同样两条铁律
                            p["stop"] = max(p["stop"], min(raw, cl))
                    elif st.get("type") == "lowest_low_trail" or act == "lowest_low_trail":
                        # Stop_t = max(Stop_{t−1}, LowestLow_N)
                        sp = st.get("params", {}) or {}
                        n = int(sp.get("lookback", 20))
                        lo = m.low[max(0, i - n + 1):i + 1, j]
                        lo = lo[np.isfinite(lo)]
                        if lo.size:
                            # ★★ 同样两条铁律:不能高于当根收盘、只能往上抬
                            p["stop"] = max(p["stop"], min(float(lo.min()), cl))
                    elif st.get("type") == "ema_trail":
                        raw = m.ema_trail[i, j]
                        if np.isfinite(raw):
                            # ★★ 同样两条铁律:不能高于当根收盘、只能往上抬
                            p["stop"] = max(p["stop"], min(raw, cl))
                    elif act == "rotate_out":
                        # ★ 「滞涨换血」—— 换血条件(备选池有新高动量信号)没定义,
                        #   这一阶段显式关掉。走到这里说明配置没按约定剔除该级。
                        raise NotImplementedError(
                            "⑤「滞涨换血」rotate_out 的触发条件"
                            "(candidate_pool_has_new_high_signal)没有定义 —— "
                            "不能猜。要跑必须显式把这一级从配置里去掉,"
                            "并在报告里写明「这一版关掉了换血」。见审计报告 §2-C。")
                    else:
                        raise NotImplementedError(
                            f"⑤ 移动止损这一级还没实现:name={st.get('name')} "
                            f"action={act} type={st.get('type')} —— ★ 没有悄悄忽略它。")
            # ⑤ 浮盈后移保本:赚到 be_trigger 个 R 就把止损抬到成本
            if be_trigger is not None and not p["be_done"] \
                    and np.isfinite(r_now) and r_now >= be_trigger:
                p["stop"] = max(p["stop"], min(p["entry"], cl))
                p["be_done"] = True
            assert p["stop"] <= cl + 1e-9, (
                f"止损高于当根收盘:{m.symbols[j]} {idx[i].date()}")

            if target_r is not None and np.isfinite(r_now) and r_now >= target_r:
                pending_exit[j] = "止盈"
            elif m.exit_fund[i, j]:
                # ★ ⑥ 基本面季度否决(PIT 生效日触发)—— 排在时间止损之前,
                #   因为它是这一派明写的主动离场,优先于「持满 N 天就走」
                pending_exit[j] = "基本面季度否决"
            elif time_stop is not None and (i - p["entry_i"]) >= time_stop:
                pending_exit[j] = "时间止损"
            elif m.exit_sig[i, j]:
                # ★ ⑥ 离场规则(收盘跌破 MA50 / EMA10)—— 以前这一条没被执行
                pending_exit[j] = "离场规则"

        # ---- ⑤ 今天收盘产生明天的候选
        regime_next = bool(m.regime[i + 1]) if i + 1 < len(idx) else False
        if regime_next:
            cands = [j for j in range(len(m.symbols))
                     if j not in pos and m.entry[i, j] and m.universe[i, j]
                     and i < int(m.last_bar[j])]
            slots = max(0, max_slots - len(pos))
            if not equal_all and len(cands) > slots:
                # ★ 名额不够时按配置里的 ranking 排序打分取前几只。
                #   分数已在第一层按配置的公式算好(rank_score,越大越优先);
                #   并列时按 ADV20 大的优先(专家给的 tiebreak),再按代码字母序定死。
                def _k(j):
                    s = m.rank_score[i, j]
                    a = m.adv20[i, j]
                    return (-(s if np.isfinite(s) else -np.inf),
                            -(a if np.isfinite(a) else -np.inf),
                            m.symbols[j])
                cands.sort(key=_k)
                cands = cands[:slots]
            pending_entry = cands
        else:
            if (cfg.get("regime") or {}).get("flatten_when_off", True):
                for j in pos:
                    pending_exit.setdefault(j, "环境关闸")

        # ---- ⑥ 记净值与敞口
        mv = sum(p["shares"] * _price(j, i, m.close) for j, p in pos.items())
        e = cash + mv
        eq.append(e)
        eqg.append(cash_gross + mv)
        expo.append(mv / e if e > 0 else 0.0)

    for j in list(pos):
        _close(j, i1, _price(j, i1, m.close), "期末平仓")

    ledger = pd.DataFrame(rows, columns=LEDGER_COLUMNS) if rows \
        else pd.DataFrame(columns=LEDGER_COLUMNS)
    notes: list[str] = []
    if total_return:
        notes.append(
            f"★ 分红口径 = 总收益:收到股息 {div_received:,.2f}"
            f"(占初始资金 {div_received / max(1.0, initial_equity):.4%}),"
            f"共 {n_div_credits} 次入账。"
            f"★ 信号未受影响(分红只记现金、不改价格)")
    else:
        notes.append("★ 分红口径 = 纯价格收益(未计分红)")
    if m.breadth_diag:
        notes.append("广度标尺:" + ";".join(f"{k}={v}" for k, v in m.breadth_diag.items()))
        notes.append(
            f"★ 实际被减仓的笔数 {n_scaled} / {len(ledger)};"
            f"其中 {n_cap_bind} 笔被 max_weight 名义上限顶住 "
            f"(这几笔减仓没完全生效 —— 风险预算降了但名义占用本来就被上限压着)")
    return ChainResult(
        name=cfg.name,
        equity=pd.Series(eq, index=perf, dtype=float),
        equity_gross=pd.Series(eqg, index=perf, dtype=float),
        exposure=pd.Series(expo, index=perf, dtype=float),
        ledger=ledger,
        initial_equity=initial_equity,
        notes=notes,
    )


# ================================================================ CLI

def main(argv: list[str] | None = None) -> int:
    import argparse
    from . import analyze
    ap = argparse.ArgumentParser(
        description="链执行器:吃一份七步配置,吐完整结果(含两条基准线与五行归因)")
    ap.add_argument("config", help="配置文件路径(.yaml / .json)")
    ap.add_argument("--start", default=data.PERF_START)
    ap.add_argument("--end", default=data.PERF_END)
    ap.add_argument("--pool", default="ALL", choices=["ALL", "A", "B"])
    ap.add_argument("--equity", type=float, default=1_000_000.0)
    ap.add_argument("--ledger", default=None, help="把交易流水存成 CSV")
    ap.add_argument("--no-attribution", action="store_true")
    ap.add_argument("--no-sensitivity", action="store_true")
    a = ap.parse_args(argv)

    cfg = ChainConfig.load(a.config)
    syms = data.full_universe().pool(a.pool)
    print(data.cohort_report())
    print()
    res = run_chain(cfg, syms, a.start, a.end, a.equity)
    if a.ledger:
        print(f"交易流水已存:{res.save_ledger(a.ledger)}")
    out = analyze.evaluate(cfg, res, syms, a.start, a.end,
                           with_attribution=not a.no_attribution,
                           with_sensitivity=not a.no_sensitivity)
    print(analyze.format_report(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
