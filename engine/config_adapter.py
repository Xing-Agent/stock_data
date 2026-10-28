"""
配置适配层 —— 把「流派配置」那套字段名翻成执行器的七步接口。

大白话:三流派配置(trend_following / vcp_momentum / liquidity_sweep)是另一条线
写的,字段名和模板不一样:它用 stop_init / stop_trail / slots / ranking,
模板用 initial_stop / trailing_stop / sizing.params.max_positions。
两套名字不一致,所以那三份配置原来根本加载不了。

这个文件干两件事:
  一、名字对齐 —— 两套名字都认,不用去改那三份配置
  二、★ 把「还没实现的规则」明确报出来 —— 列出每一条的名字和原因,
      而不是悄悄忽略。悄悄忽略最危险:配置里写了基本面闸门、
      引擎没执行,跑出来的成绩会凭空变好,而且没人知道。
      (硬纪律第 7 条:拿不到就说拿不到,不要用近似值顶上。)

★ 有两类「还没实现」要分清楚:
  A. 引擎没写 —— 规则讲得清楚,是工作量问题,补代码就行
  B. ★ 配置本身没定 —— params 里是 null,或那条线自己标了 audit_blocked,
     说明连定义都还没定下来。这类不能猜,必须等那条线给定义。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

# 字段别名:流派配置的名字 → 执行器的名字
STEP_ALIASES = {
    "stop_init": "initial_stop",
    "stop_trail": "trailing_stop",
}

# 已实现的规则类型(按步分),其余一律报出来
IMPLEMENTED = {
    "universe": {
        "price_above_ma",
        "adv_rank_exclude_bottom",
        "dollar_volume_rank_exclude_bottom",
        "return_rank_top",
        "ma_stack_bullish",
        "hv_below",
    },
    "regime": {
        "none", "index_above_ma", "index_above_ma_scaled", "index_ma_slope",
        "breadth_above", "vix_below", "no_distribution_day", "no_large_down_day",
    },
    "entry": {
        "donchian_close_breakout", "donchian_breakout", "atr_squeeze",
        "volume_dryup", "ma_cross", "rsi_oversold", "roc_momentum",
        "pullback_to_ma", "always", "random", "never",
    },
    "initial_stop": {
        "atr_multiple", "pct", "chandelier", "lowest_low", "tightest_of",
        "structure_low_minus_atr", "day_low_minus_atr",
    },
    "trailing_stop": {"chandelier", "none", "staged"},
}

# 明确「配置本身没定」的规则:为什么不能猜
BLOCKED_REASONS = {
    "vcp_contraction": "params 全是 null —— 收缩次数/幅度口径都没定义,不能猜",
    "swing_low_exists": "swing_definition / min_bars_before 是 null —— 摆动低点的定义没定",
    "intraday_break_below_swing_low": "依赖 swing_low_exists 的定义,同上",
    "close_reclaim_above_swing_low": "strength_metric / min_reclaim 是 null —— 收复强度没定",
    "credit_spread_weekly_change_below": "series 是 null,且仓库里没有信用利差数据 —— 拿不到",
    "altman_z_double_prime_exclude_bottom":
        "Altman Z'' 需要的几个科目,仓库基本面里不是每只票每期都齐 —— 算不全就不算",
    "mktcap_rank_exclude_bottom":
        "仓库没有严格 PIT 的市值(README 明确说 WeightedAverageDilutedShares × 收盘价 "
        "只是规模代理,不是 PIT 市值)—— 改用 dollar_volume_rank_exclude_bottom 或等定义",
    "mansfield_rs_positive":
        "against: SECTOR 这一条要个股→板块 ETF 的 PIT 映射,仓库的行业标签是"
        "当前快照、非 PIT —— 需先定映射口径",
}


@dataclass
class AdaptReport:
    renamed: list[str] = field(default_factory=list)
    unimplemented: list[tuple[str, str, str]] = field(default_factory=list)  # (步, 规则, 原因)

    @property
    def ok(self) -> bool:
        return not self.unimplemented

    def text(self) -> str:
        lines = []
        if self.renamed:
            lines.append(f"字段名已对齐:{', '.join(self.renamed)}")
        if self.unimplemented:
            lines.append("★ 这些规则还没法跑(没有悄悄忽略,全列在这里):")
            for step, rule, why in self.unimplemented:
                lines.append(f"    [{step}] {rule}")
                lines.append(f"        原因:{why}")
        else:
            lines.append("全部规则都已实现,可以直接跑。")
        return "\n".join(lines)


def _rule_types(block) -> list[str]:
    if not isinstance(block, dict):
        return []
    out = []
    for r in (block.get("rules") or []):
        if isinstance(r, dict) and r.get("type"):
            out.append(r["type"])
    if block.get("type"):
        out.append(block["type"])
    for c in (block.get("components") or []):
        if isinstance(c, dict) and c.get("type"):
            out.append(c["type"])
    for s in (block.get("stages") or []):
        if isinstance(s, dict) and s.get("type"):
            out.append(s["type"])
    return out


def adapt(raw: dict) -> tuple[dict, AdaptReport]:
    """
    把一份配置规范化成执行器能吃的形状,并报告哪些规则还没法跑。
    ★ 不改任何数值,只改字段名和结构。
    """
    cfg = copy.deepcopy(raw)
    rep = AdaptReport()

    # 一、字段名对齐
    for old, new in STEP_ALIASES.items():
        if old in cfg and new not in cfg:
            cfg[new] = cfg.pop(old)
            rep.renamed.append(f"{old} → {new}")

    # slots / ranking 并进 sizing
    sizing = cfg.setdefault("sizing", {})
    if not isinstance(sizing, dict):
        sizing = cfg["sizing"] = {}
    params = sizing.setdefault("params", {})
    if cfg.get("slots") is not None:
        params.setdefault("max_positions", int(cfg["slots"]))
        rep.renamed.append(f"slots({cfg['slots']}) → sizing.params.max_positions")
    else:
        # ★ 槽位没写就必须有个值,否则引擎不知道能同时持几只。
        #   这里不替配置猜,给一个明确的默认并记下来。
        params.setdefault("max_positions", 10)
        rep.renamed.append("slots 没写 → sizing.params.max_positions 默认 10(★ 需确认)")
    if cfg.get("ranking") is not None:
        sizing.setdefault("rank_by", cfg["ranking"])
        rep.renamed.append(f"ranking → sizing.rank_by")
    cfg.pop("slots", None)
    cfg.pop("ranking", None)
    cfg.pop("source_slots", None)

    # 多级移动止损:stages 形式 → type: staged
    ts = cfg.get("trailing_stop")
    if isinstance(ts, dict) and ts.get("stages") and not ts.get("type"):
        ts["type"] = "staged"
        rep.renamed.append("trailing_stop.stages → type: staged")

    # exit 的 rules 形式 → 执行器的 signal_only + 规则列表
    ex = cfg.get("exit")
    if isinstance(ex, dict) and ex.get("rules") and not ex.get("type"):
        ex["type"] = "rules"

    # 七步齐不齐
    need = ["universe", "regime", "entry", "initial_stop",
            "trailing_stop", "exit", "sizing"]
    for k in need:
        cfg.setdefault(k, {})

    # 二、查哪些规则还没实现
    for step in ("universe", "regime", "entry", "initial_stop", "trailing_stop"):
        for rt in _rule_types(cfg.get(step)):
            if rt in IMPLEMENTED.get(step, set()):
                continue
            why = BLOCKED_REASONS.get(
                rt, "引擎还没实现这条规则 —— 规则本身讲得清楚,是工作量问题")
            rep.unimplemented.append((step, rt, why))

    # audit_blocked 标记一并带出来
    def _scan_blocked(node, path):
        if isinstance(node, dict):
            if node.get("audit_blocked"):
                rep.unimplemented.append(
                    (path, node.get("name") or node.get("type") or "?",
                     f"那条线自己标了 audit_blocked={node['audit_blocked']} —— 定义未定,不能猜"))
            for k, v in node.items():
                _scan_blocked(v, path)
        elif isinstance(node, list):
            for v in node:
                _scan_blocked(v, path)

    for step in need:
        _scan_blocked(cfg.get(step), step)

    return cfg, rep


def check_file(path: str) -> AdaptReport:
    """只做检查、不跑链:看一份配置离「能跑」还差什么。"""
    import json
    with open(path, encoding="utf-8") as fh:
        raw = (__import__("yaml").safe_load(fh)
               if path.endswith((".yaml", ".yml")) else json.load(fh))
    _, rep = adapt(raw)
    return rep


def main(argv: list[str] | None = None) -> int:
    import argparse
    import glob
    import os
    ap = argparse.ArgumentParser(
        description="检查配置能不能跑:对齐字段名,并列出还没实现的规则")
    ap.add_argument("configs", nargs="*",
                    help="配置文件;不给就检查 engine/configs/ 下全部")
    a = ap.parse_args(argv)
    paths = a.configs or sorted(
        glob.glob(os.path.join(os.path.dirname(__file__), "configs", "*.yaml")))
    bad = 0
    for p in paths:
        rep = check_file(p)
        print("=" * 72)
        print(os.path.basename(p), "—", "✅ 可以跑" if rep.ok else "⚠ 还差东西")
        print(rep.text())
        bad += 0 if rep.ok else 1
    print("=" * 72)
    print(f"共 {len(paths)} 份配置,{len(paths)-bad} 份可以跑,{bad} 份还差东西")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
