"""
★ 影响评估:甲类里影响最大的两条链,换成原著口径后笔数 / R 变多少。

挑的两条(理由:这两条是本轮唯一「原著原文给了周数、手册还给了显式日线换算、
而代码用的数字等于周数本身」的 —— 偏差有唯一正确值,不需要我们挑):
  · 技-4 欧奈尔杯柄   handle_min_bars 3 → 5   (手册六附 6.1 ① 明写「日线至少 5 个交易日」)
  · 技-8 高紧旗形 HTF flag_min_bars  3 → 15  (原著「整理 3 至 5 周」;上界 25 已按 ×5 换算)

★★ R 的分母纪律(engine/checks/r_denominator_lock.py):
   两条链都**有初始止损**,所以 1R = 进场价 − 初始止损价,R 是真 R。
   ★ 不和无止损的链放一列。本文件只在**同一条链的 A/B 两版之间**比,分母一致。

★ 本文件不改任何配置文件、不改 engine/ —— 变体在内存里改 dict。
跑法:python3 probe/weekly_daily_mapping_1030/impact.py
"""

from __future__ import annotations

import copy
import json
import os
import resource
import sys

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine import cache, chain, data, matrices, pat6_ops  # noqa: E402

# ★ 技-4 的杯柄算子挂在 pat6_ops 上,不在 matrices 原生注册表里 ——
#   不装这个钩子,matrices 会直接 raise「pat6_cup_with_handle 还没法跑」。
#   ★ 这就是 pat6_run.py:271 做的同一件事,照抄,不另写一套。
pat6_ops.install()

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "engine", "configs")
OUT = os.path.join(HERE, "impact_1030.json")


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _set_param(cfg: dict, rule_type: str, key: str, value) -> bool:
    """在 entry.rules 里找到 rule_type,改它 params 的 key。返回改没改到。"""
    hit = False
    for r in cfg.get("entry", {}).get("rules", []) or []:
        if r.get("type") == rule_type:
            r.setdefault("params", {})[key] = value
            hit = True
    return hit


def _summary(res) -> dict:
    """
    ★ 只报能从流水直接数出来的东西:笔数 / 胜率 / R 的分布 / 总 R / 净值。
    ★ 不报夏普、不报任何用户面禁止字段(engine/checks/user_facing_ban.py)。
    """
    led = res.ledger
    if led is None or len(led) == 0:
        return {"笔数": 0, "★备注": "一笔都没有"}
    # ★ R 列名两种写法都认(chain.py 原生用 r_multiple / r_multiple_net)
    rcol = None
    for cand in ("r_multiple_net", "r_multiple", "R", "r"):
        if cand in led.columns:
            rcol = cand
            break
    out = {"笔数": int(len(led)), "★R列名": rcol}
    if rcol:
        r = led[rcol].to_numpy(float)
        r = r[np.isfinite(r)]
        out.update({
            "有效R笔数": int(r.size),
            "胜率": round(float((r > 0).mean()), 4),
            "总R": round(float(r.sum()), 2),
            "平均R": round(float(r.mean()), 4),
            "中位R": round(float(np.median(r)), 4),
            "R_p25": round(float(np.percentile(r, 25)), 4),
            "R_p75": round(float(np.percentile(r, 75)), 4),
        })
    eq = res.equity
    out["期末净值倍数"] = round(float(eq.iloc[-1] / res.initial_equity), 4)
    return out


CASES = [
    # (标签, yaml, 算子类型, 参数名, 现行值, 原著值, 出处)
    ("技-4 欧奈尔杯柄 · 原著版(严格端)", "技-4-原著.yaml",
     "pat6_cup_with_handle", "handle_min_bars", 3, 5,
     "手册六附 6.1 ①:柄部持续时间「至少 1–2 周(★ 日线至少 5 个交易日)」"),
    ("技-8 高紧旗形 HTF", "技-8.yaml",
     "htf_flag_breakout", "flag_min_bars", 3, 15,
     "原著(欧奈尔 4th ed. Ch.2 High, Tight Flag)「横向整理 3 至 5 周」;"
     "★ 上界 flag_max_bars=25 已按 5 周 × 5 换算,下界没换算"),
]


def main() -> None:
    syms = cache.symbols()
    print(f"★ {len(syms)} 只票;窗口 {data.PERF_START} ~ {data.PERF_END};"
          f"RSS {_rss_mb():.0f}MB")
    results = {}
    for label, yml, rtype, key, cur, book, src in CASES:
        base = _load(yml)
        pair = {}
        for tag, val in (("现行(日线当周用)", cur), ("★原著口径", book)):
            cfg_d = copy.deepcopy(base)
            if not _set_param(cfg_d, rtype, key, val):
                raise RuntimeError(
                    f"★★ {yml} 里找不到 entry.rules 里 type={rtype} 的规则 —— "
                    f"改不到 {key}。★ 不许静默跳过:这正是「两种写法只认了一种」"
                    f"那一类错(见 engine/checks/four_slot_complete.py 顶部那张表)。")
            cfg = chain.ChainConfig.from_dict(cfg_d)
            res = chain.run_chain(cfg, syms)
            pair[tag] = _summary(res)
            print(f"  · {label} / {tag} {key}={val} → "
                  f"笔数 {pair[tag].get('笔数')} 总R {pair[tag].get('总R')} "
                  f"RSS {_rss_mb():.0f}MB")
        a, b = pair["现行(日线当周用)"], pair["★原著口径"]
        delta = {
            "笔数_现行": a.get("笔数"), "笔数_原著口径": b.get("笔数"),
            "★笔数变化": (b.get("笔数", 0) - a.get("笔数", 0)),
            "★笔数变化百分比": (round((b.get("笔数", 0) / max(1, a.get("笔数", 0)) - 1) * 100, 2)),
            "总R_现行": a.get("总R"), "总R_原著口径": b.get("总R"),
            "★总R变化": (None if a.get("总R") is None or b.get("总R") is None
                         else round(b["总R"] - a["总R"], 2)),
            "平均R_现行": a.get("平均R"), "平均R_原著口径": b.get("平均R"),
            "胜率_现行": a.get("胜率"), "胜率_原著口径": b.get("胜率"),
            "期末净值倍数_现行": a.get("期末净值倍数"),
            "期末净值倍数_原著口径": b.get("期末净值倍数"),
        }
        results[label] = {
            "配置": yml, "算子": rtype, "参数": key,
            "现行值": cur, "原著值": book, "出处": src,
            "★两版对比": delta, "逐版明细": pair,
            "★R的分母": ("本链有初始止损 → 1R = 进场价 − 初始止损价,是真 R;"
                         "★ 只在本链 A/B 之间比,不和无止损的链同列"),
        }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"样本": {"票数": len(syms),
                            "窗口": f"{data.PERF_START} ~ {data.PERF_END}"},
                   "逐条": results}, fh, ensure_ascii=False, indent=1)
    print(f"\n→ {OUT}")
    print(json.dumps(results, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
