"""
流派一 深度价值 —— ★ Z'' 兜底阈值 1.80 vs 1.10 两版并列 + slots 三档敏感度。

================================ 三秒版 ================================
★ 任务书硬要求:Altman Z'' 兜底阈值 1.80 是专家自定、★ 没有出处,
  而 Altman 自己的困境线是 1.10 —— ★ 所以两版必须并列跑,★ 不许只跑 1.80 那一版。

★ 这个脚本只补主结论链已经跑完之后**还缺的那几档**,★ 口径刻意收窄:
  · 主档(slots12)两版:★ 全套输出(两条基准线 / 判据 / 四格硬关 / 代价 /
    执行负荷 / 摩擦三档 / 分步归因 / 跳空穿透)
  · 敏感度档(slots15 / 24):★ 只出【笔数 / 每笔 R / 胜率 / 四格硬关】——
    ★ 按新硬纪律 9,两版比较要看的就是这三个数,不是总收益;
    ★ 分步归因和摩擦敏感度对「换个 slots」没有新信息,省掉它们是为了
      把算力留给两版对比本身。★ 这是**刻意的口径收窄,不是漏跑**。

跑法:python -m engine.run_dv_compare_1029
=========================================================================
"""

from __future__ import annotations

import copy
import json
import os
import time

from . import analyze, cache, chain, data, matrices, ops_1029, stats_gate
from .run_batch import _num, window_pool_gate
from .run_second_round_1029 import (PLACEHOLDER_RANKING, _load, LEDGER_DIR)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_流派一_Z两版对比.json")


def build(z2_thr: float, slots: int) -> dict:
    raw = _load("deep_value.yaml")
    for r in raw["universe"]["rules"]:
        if r.get("type") == "piotroski_f_score_three_layer":
            r["params"]["z2_fallback_threshold"] = float(z2_thr)
    raw["ranking"] = copy.deepcopy(PLACEHOLDER_RANKING)
    raw["slots"] = slots
    return raw


def run(z2_thr: float, slots: int, full: bool, syms: list[str]) -> dict:
    name = f"流派一_深度价值_Z{z2_thr:g}_slots{slots}"
    print("=" * 78)
    print(f"跑链:{name}" + ("   ★ 全套输出" if full else "   (只出三个数 + 四格)"))
    t0 = time.time()
    chain.reset_t0_fallback_count()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(build(z2_thr, slots)))
    if not cfg.adapt_report.ok:
        raise RuntimeError(cfg.adapt_report.text())
    res = chain.run_chain(cfg, syms)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name}.csv"))
    t0_fb_main = chain.t0_fallback_count()
    n = len(res.ledger)
    led = res.ledger
    rec = {
        "链名": name, "slots": slots, "Z''兜底阈值": z2_thr, "笔数": n,
        "★过没过纪律8的150底线": ("过了" if n >= stats_gate.SYSTEM_MIN_TRADES
                                  else f"★★ 没过(n={n} < "
                                       f"{stats_gate.SYSTEM_MIN_TRADES})"),
        "★样本不足警示": analyze.sample_size_banner(n),
        # ★★ 新硬纪律 9 要的三个数 —— 两版比较只看这三个,不看总收益
        "★纪律9_三个必看的数": ({
            "笔数": n,
            "每笔R(毛)": round(float(led["r_multiple"].mean()), 4),
            "胜率": round(float((led["net_pnl"] > 0).mean()), 4),
        } if n else None),
        "★T0止损锚点回退次数_正式链": t0_fb_main,
    }
    out = analyze.evaluate(cfg, res, syms, with_attribution=full,
                           with_sensitivity=full, with_gate=True)
    gate4 = window_pool_gate(cfg, syms)
    rec["★两窗口两池子硬关"] = _num(gate4)
    rec["判据_三套对照组"] = _num(out["判据"])
    rec["绝对表现"] = _num(out["绝对表现"])
    if full:
        for k in ("坑一_现金拖累", "坑二_跳空穿透止损", "代价", "执行负荷",
                  "摩擦成本", "基准一_同环境随机进场", "基准二_同等仓位大盘",
                  "分步归因", "坑四_摩擦敏感度"):
            rec[k] = _num(out.get(k))
    rec["出场原因分布"] = ({str(k): int(v) for k, v in
                            led["reason"].value_counts().items()} if n else {})
    rec["★T0止损锚点回退次数_含基准与归因"] = chain.t0_fallback_count()
    rec["耗时秒"] = round(time.time() - t0, 1)
    print(f"  笔数 {n}  每笔R {rec['★纪律9_三个必看的数']}")
    print("  " + gate4.report().replace("\n", "\n  "))
    print(f"  (用了 {rec['耗时秒']} 秒)")
    return rec


def main(argv=None) -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★这个脚本补的是什么": (
            "★ 主结论链(Z''=1.80 · slots12)已在 run_second_round_1029 跑完。"
            "★ 这里补 Z''=1.10 那一版,以及两版各自的 slots 敏感度档 —— "
            "★ 任务书明写「不许只跑 1.80 那一版」。"),
        "★为什么两版并列": (
            "★★ Z''=1.80 与「有效项≥7」是专家自定、**没有出处**的两个数。"
            "★ 而 Altman 自己的分区是 困境<1.10 / 灰区 1.10~2.60 / 安全>2.60 —— "
            "★ 1.80 落在灰区正中间,来路不明。"
            "★ 1.10 是 Altman 真正的困境线,所以拿它当并列的另一版。"),
        "★比较口径(新硬纪律9)": (
            "★★ 两版比较**不许只看总收益** —— 要看 笔数 / 每笔 R / 胜率 三个数。"
            "★ 总收益受 slots 与单票上限影响很大,单看它会把"
            "「门槛松了多买几笔」误读成「挑得更准」。"),
        "链": [],
    }
    for thr in (1.80, 1.10):
        for slots in (12, 15, 24):
            full = (slots == 12)
            # ★ 1.80×slots12 主结论链已经在 run_second_round_1029 跑过,这里不重跑
            if abs(thr - 1.80) < 1e-9 and slots == 12:
                out["链"].append({
                    "链名": "流派一_深度价值_Z1.8_slots12",
                    "★说明": "★ 已在 run_second_round_1029 跑完(全套输出),"
                              "数字见 results_1029_三流派第二轮.json,这里不重跑。",
                })
                continue
            try:
                out["链"].append(run(thr, slots, full, syms))
            except Exception as e:
                import traceback
                traceback.print_exc()
                out["链"].append({"链名": f"流派一_Z{thr:g}_slots{slots}",
                                  "★跑挂了": f"{type(e).__name__}: {e}"})
            with open(OUT_JSON, "w", encoding="utf-8") as fh:
                json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n原始数字已写:{OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
