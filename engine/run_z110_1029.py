"""
流派一 深度价值 —— ★ Altman Z'' 兜底阈值 = **1.10** 那一版(slots12 主档,全套输出)。

★ 为什么必须单独跑这一版:任务书明写 ——
  「★ 那个 1.80 和「≥7 项」他**没有给出处**。而我们之前确认过:Altman 的困境线
    是 1.10、安全线 2.60 —— 1.80 落在灰色区中间,来路不明。
    ★ 处理:这两个数标「来源存疑(专家自定)」,并且**同时跑一版用 1.10 的**,
    两版并列报。★ 不许只跑 1.80 那一版。」

★ 1.80 那一版已在 engine.run_second_round_1029 跑完(全套输出)。
★ 比较口径按新硬纪律 9:★ 不许只看总收益,要看 笔数 / 每笔 R / 胜率。

跑法:python -m engine.run_z110_1029
"""

from __future__ import annotations

import copy
import json
import os
import time

from . import analyze, cache, chain, data, stats_gate
from .run_batch import _num, window_pool_gate
from .run_second_round_1029 import PLACEHOLDER_RANKING, _load, LEDGER_DIR

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "results_1029_流派一_Z110.json")


def main(argv=None) -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    raw = _load("deep_value.yaml")
    for r in raw["universe"]["rules"]:
        if r.get("type") == "piotroski_f_score_three_layer":
            r["params"]["z2_fallback_threshold"] = 1.10
    raw["ranking"] = copy.deepcopy(PLACEHOLDER_RANKING)
    raw["slots"] = 12

    chain.reset_t0_fallback_count()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    if not cfg.adapt_report.ok:
        raise RuntimeError(cfg.adapt_report.text())

    t0 = time.time()
    res = chain.run_chain(cfg, syms)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, "流派一_深度价值_Z1.1_slots12.csv"))
    fb_main = chain.t0_fallback_count()
    led, n = res.ledger, len(res.ledger)
    print(f"笔数 {n}", flush=True)

    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)
    g4 = window_pool_gate(cfg, syms)

    rec = {
        "链名": "流派一_深度价值_Z1.1_slots12",
        "Z''兜底阈值": 1.10,
        "slots": 12,
        "★这一版是什么": "★ Altman 自己的困境线 1.10(灰区下沿)—— "
                          "和专家自定的 1.80 那一版并列报。"
                          "★ 1.80 落在 Altman 灰区(1.10~2.60)正中间,来路不明。",
        "笔数": n,
        "★过没过纪律8的150底线": ("过了" if n >= stats_gate.SYSTEM_MIN_TRADES
                                  else f"★★ 没过(n={n} < "
                                       f"{stats_gate.SYSTEM_MIN_TRADES})"),
        "★样本不足警示": analyze.sample_size_banner(n),
        "★纪律9_三个必看的数": {
            "笔数": n,
            "每笔R(毛)": round(float(led["r_multiple"].mean()), 4),
            "胜率": round(float((led["net_pnl"] > 0).mean()), 4),
        },
        "★T0止损锚点回退次数_正式链": fb_main,
        "绝对表现": _num(out["绝对表现"]),
        "判据_三套对照组": _num(out["判据"]),
        "★两窗口两池子硬关": _num(g4),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "代价": _num(out["代价"]),
        "执行负荷": _num(out["执行负荷"]),
        "坑一_现金拖累": _num(out["坑一_现金拖累"]),
        "坑二_跳空穿透止损": _num(out["坑二_跳空穿透止损"]),
        "分步归因": _num(out.get("分步归因")),
        "坑四_摩擦敏感度": _num(out.get("坑四_摩擦敏感度")),
        "出场原因分布": {str(k): int(v) for k, v in
                          led["reason"].value_counts().items()},
        "★T0止损锚点回退次数_含基准与归因": chain.t0_fallback_count(),
        "耗时秒": round(time.time() - t0, 1),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(rec, fh, ensure_ascii=False, indent=2, default=str)
    print(g4.report())
    print(f"原始数字已写:{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
