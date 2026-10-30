"""
★ 一条改动 = 一次复核。本文件只做**复核**,不改配置文件。

三秒版:每改一条,要看四个数 —— 笔数 · 总R · 最大一笔占总R · 邻近参数单调性。
        抖动的就不提交。

口径(★ 和上一轮 probe/weekly_daily_mapping_1030/impact.py 逐行一致,直接抄它的
      _load / _set_param / _summary,没另写一套):
  · 样本:300 只票 × 2018-01-01 ~ 2025-12-31
  · ★ R 的分母:技-4 / 技-8 两条链**都有初始止损** → 1R = 进场价 − 初始止损价,
    是真 R。只在同一条链同一份配置的不同参数值之间比,★ 不和无止损的链同列。
  · ★ 「最大一笔占总R」用 max(R) / 总R;总R 接近 0 时这个比值会炸 —— 炸了正是
    「这条链的总R就是那一笔」的信号,不要把它当异常值丢掉。

跑法:python3 probe/bar_conversion_fix_1030/verify.py [技-4|技-8]
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

from engine import cache, chain, data, pat6_ops  # noqa: E402

pat6_ops.install()          # ★ 同 pat6_run.py:271,不装钩子 matrices 会 raise

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CONFIG_DIR = os.path.join(ROOT, "engine", "configs")


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _set_param(cfg: dict, rule_type: str, key: str, value) -> bool:
    hit = False
    for r in cfg.get("entry", {}).get("rules", []) or []:
        if r.get("type") == rule_type:
            r.setdefault("params", {})[key] = value
            hit = True
    return hit


def _summary(res) -> dict:
    led = res.ledger
    if led is None or len(led) == 0:
        return {"笔数": 0, "★备注": "一笔都没有"}
    rcol = None
    for cand in ("r_multiple_net", "r_multiple", "R", "r"):
        if cand in led.columns:
            rcol = cand
            break
    out = {"笔数": int(len(led)), "★R列名": rcol}
    if rcol:
        r = led[rcol].to_numpy(float)
        r = r[np.isfinite(r)]
        tot = float(r.sum())
        mx = float(r.max()) if r.size else float("nan")
        out.update({
            "有效R笔数": int(r.size),
            "胜率": round(float((r > 0).mean()), 4),
            "总R": round(tot, 2),
            "平均R": round(float(r.mean()), 4),
            "中位R": round(float(np.median(r)), 4),
            "最大一笔R": round(mx, 2),
            # ★ 分母用总R的绝对值:总R 为负时「占比」才有可读的符号
            "★最大一笔占总R": (None if abs(tot) < 1e-9
                               else round(mx / abs(tot) * 100, 1)),
            "去掉最大一笔后总R": round(tot - mx, 2) if r.size else None,
            "前3笔占总R": (None if abs(tot) < 1e-9 else round(
                float(np.sort(r)[-3:].sum()) / abs(tot) * 100, 1)),
        })
    out["期末净值倍数"] = round(float(res.equity.iloc[-1] / res.initial_equity), 4)
    return out


# (组名, 算子类型, 参数名, 现行值, 原著值, 扫描的邻近值, 配置清单)
GROUPS = {
    "技-4": (
        "pat6_cup_with_handle", "handle_min_bars", 3, 5, (3, 4, 5, 6, 7, 8),
        ["技-4-原著.yaml", "技-4-原著-中值.yaml",
         "技-4-原著-宽松端.yaml", "技-4-行业.yaml"],
    ),
    "技-8": (
        "htf_flag_breakout", "flag_min_bars", 3, 15, (3, 13, 14, 15, 16, 17),
        ["技-8.yaml", "技-8-行业-时间止损20日.yaml"],
    ),
}


def main() -> None:
    which = sys.argv[1] if len(sys.argv) > 1 else "技-4"
    rtype, key, cur, book, grid, ymls = GROUPS[which]
    syms = cache.symbols()
    print(f"★ {which}:{len(syms)} 只票 · {data.PERF_START}~{data.PERF_END} · "
          f"{key} 扫 {grid} · {len(ymls)} 份配置")
    out: dict = {"组": which, "算子": rtype, "参数": key,
                 "现行值": cur, "原著值": book, "扫描网格": list(grid),
                 "样本": {"票数": len(syms),
                          "窗口": f"{data.PERF_START} ~ {data.PERF_END}"},
                 "逐配置": {}}
    for yml in ymls:
        base = _load(yml)
        per = {}
        for v in grid:
            cfg_d = copy.deepcopy(base)
            if not _set_param(cfg_d, rtype, key, v):
                raise RuntimeError(
                    f"★★ {yml} 里找不到 type={rtype} 的规则 → 改不到 {key}。"
                    f"★ 不许静默跳过(「同一样东西两种写法」那一类错)。")
            res = chain.run_chain(chain.ChainConfig.from_dict(cfg_d), syms)
            per[str(v)] = _summary(res)
            s = per[str(v)]
            print(f"  · {yml} {key}={v} → 笔数 {s.get('笔数')} "
                  f"总R {s.get('总R')} 最大一笔占总R {s.get('★最大一笔占总R')}% "
                  f"RSS {_rss_mb():.0f}MB")
        tot = [per[str(v)].get("总R") for v in grid]
        n = [per[str(v)].get("笔数") for v in grid]
        out["逐配置"][yml] = {
            "逐值": per,
            "★单调性": {
                "总R序列": tot, "笔数序列": n,
                "总R单调": _mono(tot), "笔数单调": _mono(n),
            },
        }
    p = os.path.join(HERE, f"verify_{which}_1030.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(f"\n→ {p}")


def _mono(seq) -> str:
    s = [x for x in seq if x is not None]
    if len(s) < 3:
        return "样本不足"
    d = np.diff(s)
    if (d >= 0).all():
        return "单调不减"
    if (d <= 0).all():
        return "单调不增"
    return f"★ 非单调({int((np.sign(d)[:-1] != np.sign(d)[1:]).sum())} 次换向)"


if __name__ == "__main__":
    main()
