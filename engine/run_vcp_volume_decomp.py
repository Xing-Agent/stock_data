"""
成交量门禁的拆解核查(2026-10-29)—— ★ 专家两条推理,逐条拿数据对。

大白话(三秒):裁决版跑完只有 32 笔,离专家说的 140~220 还差 4 倍多。
  所以要回头查:专家做裁决时用的两条推理,在我们数据上成不成立。

★ 要核的两条:
  推理 A「条件1 和条件2 高度共线、冗余」
      → 测法:在门禁1 成立的那些单元里,条件2 自动成立的比例有多高?
        真·共线 = 比例接近 100%(那删掉条件2 几乎不该放回样本)。
  推理 B「只要突破日上了 50 日均量,而前 5 天又有 0.6x 的极度缩量日,
          它对前 5 日均量的放大倍数天然已经超过 1.2 倍」
      → 测法:在门禁1 AND 门禁2 成立的单元里,
        Vol[t] ≥ 1.20 × SMA5(t−1) 的比例有多高?

★ 顺带两件:
  · 门禁1 与门禁2 是不是**互相拉扯**(负相关)—— 用「实测 AND 率 ÷ 两者独立相乘」
    判:< 1 就是互相拉扯,> 1 就是同向。这决定「只剩两条」够不够松。
  · 1.80 倍上限删对了没有 —— 数一下成交的那几笔里有多少笔突破日量 > 1.80×SMA50,
    ★ 如果上限还在,这些笔会被精准击杀。

★ 本脚本只产出比例与计数,★ 不产出任何成绩,★ 不是在搜参数。

跑法:python -m engine.run_vcp_volume_decomp
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from . import cache, data

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_成交量门禁拆解.json")
LEDGER = os.path.join(HERE, "ledgers_1029_vcp简化后",
                      "流派二_VCP_裁决版_slots10.csv")


def main(argv=None) -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    v = cache.field("volume", syms)
    perf = np.asarray(v.index >= pd.Timestamp(data.PERF_START))

    sma50_1 = v.rolling(50, min_periods=50).mean().shift(1)
    sma5_1 = v.rolling(5, min_periods=5).mean().shift(1)
    vmin5 = v.rolling(5, min_periods=5).min().shift(1)

    def rate(mask) -> tuple[int, float]:
        a = np.asarray(mask.to_numpy(bool))[perf, :]
        return int(a.sum()), float(a.mean())

    # 只在三条序列都算得出来的单元上统计(否则分母里混着热机期的 NaN)
    ok = sma50_1.notna() & sma5_1.notna() & vmin5.notna() & v.notna()

    g1 = (vmin5 <= 0.60 * sma50_1) & ok          # 门禁1 单日地量
    g2 = (v >= 1.00 * sma50_1) & ok              # 门禁2 突破日点火
    c2 = (sma5_1 <= 0.85 * sma50_1) & ok         # ★ 已废除的条件2
    f12 = (v >= 1.20 * sma5_1) & ok              # ★ 已删除的 1.20×SMA5 连乘项
    cap = (v > 1.80 * sma50_1) & ok              # ★ 已删除的 1.80 上限会拦掉的

    n_ok, _ = rate(ok)
    out: dict = {"口径": f"全池 {len(syms)} 只 × 绩效窗口 "
                         f"{data.PERF_START}..{data.PERF_END};"
                         f"分母 = 三条均量序列都算得出来的「日×票」单元 {n_ok} 个",
                 "单条通过率": {}}

    for name, m in [("门禁1 单日地量 ≤0.60×SMA50", g1),
                    ("门禁2 突破日 ≥1.00×SMA50", g2),
                    ("★已废除 条件2 SMA5 ≤0.85×SMA50", c2),
                    ("★已删除 连乘项 ≥1.20×SMA5", f12),
                    ("★已删除 1.80 上限会拦掉的(量>1.80×SMA50)", cap)]:
        n, r = rate(m)
        out["单条通过率"][name] = {"单元数": n, "占比": round(r, 4)}

    # ---------------- 推理 A:条件1 与条件2 真的共线吗
    n_g1, _ = rate(g1)
    n_g1c2, _ = rate(g1 & c2)
    n_c2, r_c2 = rate(c2)
    out["★推理A_条件1与条件2是否共线"] = {
        "专家说法": "条件1 和条件2 高度共线、冗余 —— 所以条件2 可以直接废除",
        "门禁1 成立的单元里 条件2 也成立的比例": round(n_g1c2 / max(1, n_g1), 4),
        "条件2 在全体单元上的无条件通过率": round(r_c2, 4),
        "提升倍数(条件概率 ÷ 无条件概率)": round(
            (n_g1c2 / max(1, n_g1)) / max(1e-9, r_c2), 3),
        "怎么读": "★ 提升倍数 ≈ 1 → 两者其实互相独立,「共线」不成立;"
                  "★ 条件概率接近 1 → 真·共线、删掉条件2 几乎不放回样本",
    }

    # ---------------- 推理 B:1.20×SMA5 是不是天然满足
    n_both, _ = rate(g1 & g2)
    n_bothf, _ = rate(g1 & g2 & f12)
    out["★推理B_1.20×SMA5是否天然满足"] = {
        "专家说法": "突破日上了 50 日均量 + 前 5 天有 0.6x 地量日 → "
                    "对前 5 日均量的放大倍数天然已超 1.20 倍",
        "门禁1∧门禁2 的单元数": n_both,
        "其中 Vol[t] ≥ 1.20×SMA5(t−1) 的比例": round(n_bothf / max(1, n_both), 4),
        "怎么读": "★ 比例接近 1 → 专家这条推理成立,删掉连乘项不改变门禁;"
                  "★ 比例明显 < 1 → 删掉它确实放宽了门禁(放宽多少就是 1 − 比例)",
    }

    # ---------------- 门禁1 与门禁2 互相拉扯还是同向
    _, r_g1 = rate(g1)
    _, r_g2 = rate(g2)
    _, r_both = rate(g1 & g2)
    indep = r_g1 * r_g2
    out["★门禁1与门禁2_互相拉扯还是同向"] = {
        "门禁1 通过率": round(r_g1, 4),
        "门禁2 通过率": round(r_g2, 4),
        "实测 AND 通过率": round(r_both, 4),
        "两者独立相乘应为": round(indep, 4),
        "实测 ÷ 独立": round(r_both / max(1e-9, indep), 3),
        "怎么读": "★ < 1 = 互相拉扯(一个要「前几天极度缩量」、另一个要"
                  "「今天放量上均量」,本来就不容易同时出现)——"
                  "这种情况下「只剩两条」仍然会砍掉大量样本;"
                  "★ ≈ 1 = 互相独立;★ > 1 = 同向",
    }

    # ---------------- ★ 门禁内部的留一法:两道门禁各自砍掉多少信号
    #   ★ 只为定位是哪一道在砍,★ 去掉任一道的版本一律不作为结果上报。
    #   口径和主报告的信号漏斗对齐:③ 四关串完事件化、再 ∧ ① 选股范围。
    from . import chain, matrices
    from .run_batch import _vcp_base

    base, _ = _vcp_base()
    idx = v.index
    uni = None
    for r in base["universe"]["rules"]:
        m = matrices._universe_rule_mask(r, syms, idx)
        uni = m if uni is None else uni & m

    others = None
    for r in base["entry"]["rules"]:
        if r.get("type") == "vcp_volume_duo":
            continue
        m = matrices._entry_rule_raw(r, syms)
        others = m if others is None else others & m

    def events_with(volmask) -> int:
        cum = others if volmask is None else (others & volmask)
        ev = matrices._event_only(cum)
        a = np.asarray((ev & uni).to_numpy(bool))[perf, :]
        return int(a.sum())

    out["★门禁内部留一法_哪一道在砍"] = {
        "★口径": "★ 只为定位,去掉任一道门禁的版本一律不作为结果上报;"
                  "数的是「③ 事件化 ∧ ① 选股范围」的信号数,和主报告漏斗同口径",
        "两道都在(裁决版)": events_with(g1 & g2),
        "只留门禁1(去掉突破日点火)": events_with(g1),
        "只留门禁2(去掉单日地量)": events_with(g2),
        "两道都去掉(没有任何成交量门禁)": events_with(None),
    }

    # ---------------- 1.80 上限删对了没有:看实际成交的那几笔
    if os.path.exists(LEDGER):
        led = pd.read_csv(LEDGER)
        hit, miss = [], []
        for _, row in led.iterrows():
            s, d = str(row.get("symbol")), pd.Timestamp(row.get("entry_date"))
            # 进场是「信号日次日开盘」,所以信号日 = 进场日的前一个交易日
            try:
                pos = v.index.get_indexer([d], method="ffill")[0]
            except Exception:
                continue
            k = pos - 1
            if k < 50 or s not in v.columns:
                continue
            ratio = float(v.iloc[k][s]) / float(sma50_1.iloc[k][s])
            r_mult = float(row.get("r_multiple", np.nan))
            (hit if ratio > 1.80 else miss).append((s, round(ratio, 2), r_mult))
        out["★1.80上限删对了没有"] = {
            "口径": "对结论档(slots=10)实际成交的每一笔,算它信号日的 "
                    "Vol ÷ SMA50(t−1)",
            "成交笔数": int(len(led)),
            "★量比 > 1.80 的笔数(★ 上限还在就会被精准击杀)": len(hit),
            "这些笔的明细(代码/量比/R)": hit,
            "量比 ≤ 1.80 的笔数": len(miss),
            "★量比>1.80 那组的平均R": (round(float(np.nanmean([x[2] for x in hit])), 3)
                                     if hit else None),
            "量比≤1.80 那组的平均R": (round(float(np.nanmean([x[2] for x in miss])), 3)
                                    if miss else None),
            "★怎么读": "★ 样本极小(全链只有几十笔),这两个平均 R 只能当"
                        "「上限会不会碰到东西」的证据,★ 不能当成绩引用",
        }
    else:
        out["★1.80上限删对了没有"] = f"★ 拿不到 —— 流水文件不存在:{LEDGER}"

    print(json.dumps(out, ensure_ascii=False, indent=2))
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n原始数字已写:{OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
