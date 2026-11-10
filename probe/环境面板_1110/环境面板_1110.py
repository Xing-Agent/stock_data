# -*- coding: utf-8 -*-
"""★★★★★ 「哪几套打法的环境前提成立」面板 —— ★ Lin 1110 10:56「这周做一个」。

★★ 三秒版：A 组一直报「宏观指标取数失败，所以给不出第二层」——
   ★★★★★ **那个取数本来就不该发生。** 6 套打法的环境前提全是这些：
      index_above_ma{SPY,200} · index_ma_slope · sector_diffusion_above{行业ETF}
      · no_large_down_day{SPY,3天,2%} · breadth_above · credit_ratio
   ★★★ **全部能用我们手上的日线算出来，一个宏观指标都不需要。**

★★ 所以这张面板绕开两条红线：
   · ★★★★★ **不是宏观预测**（是查当下状态，不给方向）
   · ★★★★★ **不是 Gemini 的 ⑤ 档数**（是我们自己的日线）

★★★ 它用**引擎自己的 `regime_mask`** 来判，★★★★★ **不自己重写一套判定** ——
   ★ 自己重写就等于发明了第二套环境闸，和回测里那套不一致，直接撞红线。

★ 口径写死在输出里：**数据止于本机日线最后一天，不是「现在这会儿」。**
"""
from __future__ import annotations
import io
import json
import os
import sys

import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)

from engine import matrices as M          # noqa: E402
from engine import data as D            # noqa: E402

六套 = ["trend_following", "vcp_momentum", "quality_compounder",
       "deep_value", "cashflow_discipline", "liquidity_sweep"]
中文 = {"trend_following": "趋势跟随（唐奇安/海龟那一路）",
       "vcp_momentum": "VCP 动量（欧奈尔那一路）",
       "quality_compounder": "质量复利（巴菲特/芒格那一路）",
       "deep_value": "深度价值（格雷厄姆那一路）",
       "cashflow_discipline": "现金流纪律",
       "liquidity_sweep": "流动性扫荡"}
规则白话 = {
    "index_above_ma": "大盘在 {ma} 日均线**上方**",
    "index_above_ma_scaled": "大盘在 {ma} 日均线的 {factor} 倍上方",
    "index_ma_slope": "{ma} 日均线**在往上走**",
    "sector_diffusion_above": "够多的**行业**也在往上（行业扩散）",
    "breadth_above": "够多的**个股**在均线上方（市场宽度）",
    "breadth_above_chain": "本策略池内够多的票在均线上方",
    "no_large_down_day": "近 {window} 天**没有**单日跌超 {single_day_drop_pct}%",
    "no_distribution_day": "近期**没有**派发日",
    "credit_ratio_above": "信用环境没恶化",
    # ★★★★★ 1110 补：这两条我第一次漏了，★ 结果面板上打出「未登记的规则类型」——
    #   ★★★ 我当时怀疑是**引擎默默放行**，查完发现 `regime_mask` 遇到不认识的类型
    #   **会抛 ValueError**，★★ 所以是**我这张白话表少了两条**，不是引擎的问题。
    "vix_below": "恐慌指数（VIX）没有高过 {level}" ,
    "credit_ratio_gate": "信用环境这道闸成立（高收益债 vs 国债的相对强弱）",
}


def 白话(rule: dict) -> str:
    t = rule.get("type", "?")
    p = rule.get("params") or {}
    tpl = 规则白话.get(t)
    if not tpl:
        return f"（未登记的规则类型：{t}）"
    try:
        return tpl.format(**p)
    except KeyError:
        return tpl.split("{")[0] + f"（参数：{p}）"


def main() -> int:
    # ★★ 基准日线：环境闸全部挂在指数/行业 ETF 上
    bench = D.load_benchmark("SPY")
    idx = bench.index
    print(f"★ 日线覆盖：{idx.min().date()} ~ {idx.max().date()}（{len(idx)} 个交易日）")
    print(f"★★★★★ 口径：**这是截至 {idx.max().date()} 的状态，不是「现在这会儿」** "
          f"—— 本机日线就到这一天。\n")

    报 = {"★口径": f"截至 {idx.max().date()}，本机日线最后一天；不是实时",
         "★★这张面板不做什么": [
             "★★★★★ 不做宏观预测 —— 不给降息概率、不给通胀数值、不给方向",
             "★★★ 不用外部模型的数 —— 全部来自我们自己的日线",
             "★★ 不给买卖建议 —— 只报「这套打法的环境前提今天成立几条」",
         ],
         "打法": {}}
    成立, 不成立, 算不出 = [], [], []

    for 名 in 六套:
        f = os.path.join(ROOT, "engine", "configs", f"{名}.yaml")
        if not os.path.exists(f):
            算不出.append({"打法": 名, "因": "配置文件不存在"})
            continue
        cfg = yaml.safe_load(io.open(f, encoding="utf-8"))
        spec = cfg.get("regime") or {}
        规则们 = spec.get("rules") or []
        逐条 = []
        整体 = None
        # ★★★ 逐条单独跑一遍，★ 这样能说清「卡在哪一条」而不只是「不成立」
        for r in 规则们:
            try:
                m = M.regime_mask({"rules": [r]}, idx)
                今 = bool(m.iloc[-1])
                逐条.append({"条": 白话(r), "类型": r.get("type"),
                           "今天": "✅ 成立" if 今 else "❌ 不成立",
                           "近 20 日成立天数": int(m.tail(20).sum())})
            except Exception as e:
                逐条.append({"条": 白话(r), "类型": r.get("type"),
                           "今天": f"★★★ 算不出：{type(e).__name__}", "近 20 日成立天数": None})
        try:
            全 = M.regime_mask(spec, idx)
            整体 = bool(全.iloc[-1])
            近 = int(全.tail(20).sum())
        except Exception as e:
            整体, 近 = None, None
            算不出.append({"打法": 名, "因": f"{type(e).__name__}: {e}"})

        报["打法"][名] = {"中文": 中文.get(名, 名), "整体": 整体,
                       "近 20 日成立天数": 近, "逐条": 逐条}
        (成立 if 整体 else 不成立 if 整体 is False else 算不出).append(名)

        状 = "✅ **环境前提成立**" if 整体 else ("❌ 环境前提不成立" if 整体 is False else "★★★ 算不出")
        print(f"★★★ {中文.get(名, 名)}　{状}" + (f"（★ 近 20 日成立 {近} 天）" if 近 is not None else ""))
        for x in 逐条:
            print(f"     {x['今天']:<12} {x['条']}"
                  + (f"　★ 近 20 日 {x['近 20 日成立天数']}/20" if x["近 20 日成立天数"] is not None else ""))
        print()

    报["★★★三秒版"] = (f"6 套打法里，**{len(成立)} 套环境前提成立**、"
                   f"{len([x for x in 不成立])} 套不成立"
                   + (f"、{len(算不出)} 套算不出" if 算不出 else "")
                   + f"（截至 {idx.max().date()}）")
    报["★★算不出的"] = 算不出
    print("=" * 60)
    print(f"★★★★★ {报['★★★三秒版']}")
    if 算不出:
        print(f"★★★ 算不出的 {len(算不出)} 套：{算不出}")
        print("★★ 按规矩：「算不出来」和「不成立」**分开记，不许混成一个数**。")
    # ---- ★★★★★ 自证：拿历史压力日试。★ 如果熊市那几天也报「全成立」，这张面板就是坏的。
    import pandas as pd
    print("\n★★★ 自证（★ 历史压力日）")
    压力 = ["2020-03-20", "2022-06-16", "2022-10-14", "2018-12-24", "2025-04-07"]
    全masks = {}
    for 名 in 六套:
        f = os.path.join(ROOT, "engine", "configs", f"{名}.yaml")
        if os.path.exists(f):
            全masks[名] = M.regime_mask(
                (yaml.safe_load(io.open(f, encoding="utf-8")).get("regime") or {}), idx)
    自证 = {}
    for d in 压力:
        ts = pd.Timestamp(d, tz=idx.tz) if idx.tz else pd.Timestamp(d)
        近 = idx[idx <= ts]
        if not len(近):
            continue
        n = sum(bool(m.loc[近[-1]]) for m in 全masks.values())
        自证[str(近[-1].date())] = f"{n}/6"
        print(f"   {近[-1].date()}  成立 {n}/6  {'✓ 合理（压力期本该少）' if n <= 2 else '✗ ★★★★★ 压力期还全成立，面板有问题'}")
    占比 = {名: round(float(m.mean()) * 100, 1) for 名, m in 全masks.items()}
    print(f"   ★★ 全历史成立占比：{占比}")
    退化 = [名 for 名, v in 占比.items() if v >= 99]
    print(f"   {'✓' if not 退化 else '✗'} 没有哪一套接近 100%"
          + (f" —— ★★★★★ 但 {退化} 接近 100%，那道闸形同不存在" if 退化 else ""))
    报["★★★自证_历史压力日"] = 自证
    报["★★全历史成立占比"] = 占比

    out = os.path.join(ROOT, "手册", "环境面板_1110.json")
    io.open(out, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1))
    print(f"★ 写到 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
