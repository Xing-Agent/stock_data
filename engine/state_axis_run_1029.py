"""
状态轴三版并跑 —— 跑动入口。

大白话:把状-1 / 状-2 / 状-3 / 状-5 各跑三版,出分布对照,
再单独做一件事:实测「强制 1→2→3→4 循环」是不是在误杀真实的阶段二。

跑法:python -m engine.state_axis_run_1029 --out engine/results_1029_状态轴三版.json
"""

from __future__ import annotations

import json
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data, state_axis_tri_1029 as tri


def _strip(obj):
    """去掉 _panel 这种大对象,只留能进 json 的。"""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items()
                if not k.startswith("_panel") and k != "_sel"}
    if isinstance(obj, (list, tuple)):
        return [_strip(x) for x in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def agreement(res: dict, keys: list[str]) -> dict:
    """逐日逐票比:两版给出同一个状态的比例(只比两边都不是 WARMUP 的格子)。"""
    out = {}
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = res[keys[i]].get("_panel"), res[keys[j]].get("_panel")
            if not a or not b:
                continue
            same = tot = 0
            for s in a:
                x, y = a[s], b[s]
                m = (x != tri.WARMUP) & (y != tri.WARMUP)
                tot += int(m.sum())
                same += int((x[m] == y[m]).sum())
            out[f"{keys[i]} vs {keys[j]}"] = {
                "可比格子": tot,
                "同一状态比例": round(same / max(1, tot), 4)}
    return out


def _fwd_stats(evs: list[dict], key: str = "fwd60") -> dict:
    v = np.array([e[key] for e in evs if e.get(key) is not None], dtype=float)
    if len(v) == 0:
        return {"n": 0}
    return {
        "n": int(len(v)),
        "n_truncated": int(sum(1 for e in evs if e.get(key) is None)),
        "mean": round(float(v.mean()), 4),
        "median": round(float(np.median(v)), 4),
        "p25": round(float(np.percentile(v, 25)), 4),
        "p75": round(float(np.percentile(v, 75)), 4),
        "hit_rate_gt0": round(float((v > 0).mean()), 4),
    }


def cycle_experiment(events: list[dict]) -> dict:
    """
    ★★ 本次最重要的一节:强制循环到底挡掉了什么。
    只看落在计分窗口(2018-01-01 起)里的阶段二。
    """
    s2 = [e for e in events if e["stage"] == "2" and e.get("in_window")]
    forced = [e for e in s2 if e["forced_ok"]]
    three = [e for e in s2 if e["three_ok"]]
    four = [e for e in s2 if e["four_ok"]]
    blocked = [e for e in s2 if e["four_ok"] and not e["forced_ok"]]
    both_rej = [e for e in s2 if not e["four_ok"]]

    by_path: dict[str, dict] = {}
    for e in blocked:
        d = by_path.setdefault(e["path"], {"n": 0, "evs": []})
        d["n"] += 1
        d["evs"].append(e)
    for k in by_path:
        by_path[k]["fwd60"] = _fwd_stats(by_path[k]["evs"])
        by_path[k]["fwd60_excess"] = _fwd_stats(by_path[k]["evs"], "fwd60_excess")
        by_path[k]["episode_bars_median"] = float(np.median(
            [x["episode_bars"] for x in by_path[k]["evs"]]))
        by_path[k].pop("evs")

    post = pd.Timestamp("2020-03-01")
    sc2_post = [e for e in blocked
                if e["path"] == "4→2" and pd.Timestamp(e["date"]) >= post]
    sc2_2020 = [e for e in sc2_post
                if pd.Timestamp(e["date"]) <= pd.Timestamp("2020-12-31")]

    return {
        "阶段二候选总数(原始确认,未加拓扑)": len(s2),
        "强制循环放行": len(forced),
        "Gemini三条路径放行": len(three),
        "三条路径+3→2 放行": len(four),
        "被强制循环挡掉(三路径+3→2 放行)": len(blocked),
        "Gemini三条路径也挡掉的(=3→2 中继基底)": len(four) - len(three),
        "三版全挡掉": len(both_rej),
        "三版全挡掉的路径分布": dict(pd.Series(
            [e["path"] for e in both_rej]).value_counts()) if both_rej else {},
        "被挡掉的归类": by_path,
        "放行组的后续60日": {
            "强制循环放行": _fwd_stats(forced),
            "强制循环放行_超额": _fwd_stats(forced, "fwd60_excess"),
            "被挡掉": _fwd_stats(blocked),
            "被挡掉_超额": _fwd_stats(blocked, "fwd60_excess"),
            "三版全挡掉": _fwd_stats(both_rej),
            "三版全挡掉_超额": _fwd_stats(both_rej, "fwd60_excess"),
        },
        "场景二(4→2)专项": {
            "全窗口次数": by_path.get("4→2", {}).get("n", 0),
            "2020-03 之后次数": len(sc2_post),
            "2020-03 至 2020-12 次数": len(sc2_2020),
            "2020-03 之后后续60日": _fwd_stats(sc2_post),
            "2020-03 之后后续60日_超额": _fwd_stats(sc2_post, "fwd60_excess"),
            "2020 年内样本": sorted(
                [(e["symbol"], e["date"], e["fwd60"]) for e in sc2_2020],
                key=lambda x: x[1])[:40],
        },
        "样本(被挡掉的前 30 条)": sorted(
            [(e["symbol"], e["date"], e["path"], e["fwd60"], e["episode_bars"])
             for e in blocked], key=lambda x: x[1])[:30],
    }


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="状态轴三版并跑")
    ap.add_argument("--out", default="engine/results_1029_状态轴三版.json")
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 只(调试用)")
    a = ap.parse_args(argv)

    t0 = time.time()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    if a.limit:
        syms = syms[:a.limit]
    idx = cache.load()["close"].index
    win = idx[idx >= pd.Timestamp(tri.START)]
    print(f"池子 {len(syms)} 只 × 计分窗口 {len(win)} 个交易日 "
          f"({win[0].date()} ~ {win[-1].date()}),预热用 {idx[0].date()} 起")

    res: dict = {
        "meta": {
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd="/home/claude/xing-agent-stock_data").stdout.strip(),
            "symbols": len(syms),
            "scoring_days": len(win),
            "scoring_start": str(win[0].date()),
            "scoring_end": str(win[-1].date()),
            "warmup_start": str(idx[0].date()),
            "no_backtest": "状-1/2/3/5 不产生交易信号 → 不跑回测、不出 Z 值。"
                           "产出只有分布统计。",
        }
    }

    print("跑 状-1 道氏 …")
    res["状-1"] = tri.run_dow(syms)
    res["状-1"]["_agreement"] = agreement(res["状-1"], list(tri.DOW_VERSIONS))
    print("跑 状-2 温斯坦 …")
    st = tri.run_stage(syms)
    res["状-2"] = st
    print("做 状-2 强制循环实测 …")
    res["状-2_强制循环实测"] = {
        v: cycle_experiment(evs) for v, evs in st["_cycle_events"].items()}
    print("跑 状-3 Brooks …")
    res["状-3"] = tri.run_brooks(syms)
    res["状-3"]["_agreement"] = agreement(res["状-3"], list(tri.BROOKS_VERSIONS))
    print("跑 状-5 相对强度 …")
    res["状-5"] = tri.run_rs(syms)
    res["impl_notes"] = tri.IMPL_NOTES

    out = _strip(res)
    out.get("状-2", {}).pop("_cycle_events", None)
    for k in list(out.get("状-5", {})):
        if isinstance(out["状-5"].get(k), dict):
            out["状-5"][k].pop("_sel", None)
    with open(a.out, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=str)
    print(f"写好 {a.out},用了 {time.time()-t0:.1f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
