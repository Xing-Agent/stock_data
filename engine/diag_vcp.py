"""
流派二的两个诊断(★ 都不是在搜参数)。

诊断一 松紧三个数各自贡献多少
  链跑出来松端只有 1 笔、紧端 0 笔,成绩层面没法比。
  但「信号量」这一层有数据:把松端当底,★ 一次只换一个数换成紧端,
  看信号少掉多少。这是在把已经定死的「松端↔紧端」这段差异拆开看是谁造成的,
  ★ 不是在三个数里挑好看的。

诊断二 哪一关把样本吃光了(留一法)
  松端整条链 8 年只出 57 个进场事件、过了选股范围只剩 2 个。
  ★ 一次只去掉一关,看样本能不能回来 —— 这是在定位瓶颈,好拿去追问专家,
  ★ 不是在放宽规则跑成绩。去掉任何一关的版本都★ 不作为结果上报。

跑法:python -m engine.diag_vcp
"""

from __future__ import annotations

import copy
import json
import os

import numpy as np
import pandas as pd

from . import cache, chain, data, matrices, run_batch

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_1028_流派二诊断.json")


def _syms() -> list[str]:
    return [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]


def _entry_events(raw: dict, syms: list[str], skip: str | None = None
                  ) -> pd.DataFrame:
    cum = None
    for r in (raw["entry"]["rules"]):
        if skip is not None and r.get("type") == skip:
            continue
        m = matrices._entry_rule_raw(r, syms)
        cum = m if cum is None else cum & m
    return matrices._event_only(cum)


def _universe(raw: dict, syms: list[str], idx, skip_idx: int | None = None
              ) -> pd.DataFrame:
    cum = None
    for k, r in enumerate(raw["universe"]["rules"]):
        if skip_idx is not None and k == skip_idx:
            continue
        m = matrices._universe_rule_mask(r, syms, idx)
        cum = m if cum is None else cum & m
    return cum


def _count(df, perf) -> int:
    return int(np.asarray(df.to_numpy(bool))[perf, :].sum())


def _set(raw: dict, decay=None, dryup=None, stop_pct=None) -> dict:
    raw = copy.deepcopy(raw)
    if stop_pct is not None:
        raw["stop_init"]["hard_gate"]["params"]["max_pct"] = stop_pct
    for r in raw["entry"]["rules"]:
        if decay is not None and r.get("type") == "vcp_contraction":
            r["params"]["decay_coefficient"] = decay
        if dryup is not None and r.get("type") == "volume_dryup":
            r["params"]["max_ratio"] = dryup
    return raw


def main(argv=None) -> int:
    syms = _syms()
    idx = cache.field("close", syms).index
    perf = np.asarray(idx >= pd.Timestamp(data.PERF_START))
    base, _ = run_batch._vcp_base()        # 已关掉行业 RS + 滞涨换血
    L = run_batch.LOOSE_TIGHT["松端(专家给的)"]
    T = run_batch.LOOSE_TIGHT["紧端(原著另一端)"]

    def trades(raw):
        cfg = chain.ChainConfig.from_dict(raw)
        return len(chain.run_chain(cfg, syms).ledger)

    # ---------------- 诊断一:一次只换一个数
    print("=" * 78)
    print("诊断一:松紧三个数,一次只换一个(★ 不是在三个数里挑好看的)")
    cases = [
        ("松端(专家给的):8.0% / 0.65 / 0.60",
         _set(base, L["decay"], L["dryup"], L["max_stop_pct"])),
        ("只把 递减 0.65→0.50(其余留松端)",
         _set(base, T["decay"], L["dryup"], L["max_stop_pct"])),
        ("只把 缩量 0.60→0.50(其余留松端)",
         _set(base, L["decay"], T["dryup"], L["max_stop_pct"])),
        ("只把 止损硬闸 8.0%→7.0%(其余留松端)",
         _set(base, L["decay"], L["dryup"], T["max_stop_pct"])),
        ("紧端(原著另一端):7.0% / 0.50 / 0.50",
         _set(base, T["decay"], T["dryup"], T["max_stop_pct"])),
    ]
    one_at_a_time = []
    for label, raw in cases:
        ev = _entry_events(raw, syms)
        uni = _universe(raw, syms, idx)
        row = {"版本": label,
               "③进场事件数": _count(ev, perf),
               "③×①过选股范围": _count(ev & uni, perf),
               "实际成交笔数": trades(raw)}
        one_at_a_time.append(row)
        print(f"  {label:44s} 事件={row['③进场事件数']:5d} "
              f"过选股={row['③×①过选股范围']:4d} 成交={row['实际成交笔数']:4d}")

    # ---------------- 诊断二:留一法,哪一关吃掉样本
    print()
    print("=" * 78)
    print("诊断二:松端版留一法 —— 一次只去掉一关(★ 只为定位瓶颈,不作为结果上报)")
    loose = _set(base, L["decay"], L["dryup"], L["max_stop_pct"])
    full_ev = _entry_events(loose, syms)
    full_uni = _universe(loose, syms, idx)
    leave_one = [{"去掉哪一关": "(不去掉,完整松端版)",
                  "③进场事件数": _count(full_ev, perf),
                  "③×①过选股范围": _count(full_ev & full_uni, perf)}]
    print(f"  {'(不去掉,完整松端版)':46s} 事件={leave_one[0]['③进场事件数']:6d} "
          f"过选股={leave_one[0]['③×①过选股范围']:5d}")
    for r in loose["entry"]["rules"]:
        t = r.get("type")
        ev = _entry_events(loose, syms, skip=t)
        row = {"去掉哪一关": "③ " + str(t),
               "③进场事件数": _count(ev, perf),
               "③×①过选股范围": _count(ev & full_uni, perf)}
        leave_one.append(row)
        print(f"  {'③ '+str(t):46s} 事件={row['③进场事件数']:6d} "
              f"过选股={row['③×①过选股范围']:5d}")
    for k, r in enumerate(loose["universe"]["rules"]):
        uni = _universe(loose, syms, idx, skip_idx=k)
        row = {"去掉哪一关": f"① {r.get('type')}(第{k+1}条)",
               "③进场事件数": _count(full_ev, perf),
               "③×①过选股范围": _count(full_ev & uni, perf)}
        leave_one.append(row)
        print(f"  {'① '+str(r.get('type'))+f'(第{k+1}条)':46s} "
              f"事件={row['③进场事件数']:6d} 过选股={row['③×①过选股范围']:5d}")

    out = {
        "★这两个诊断都不是网格搜索": [
            "诊断一:把已经定死的「松端↔紧端」这段差异拆开,看三个数各自贡献多少;"
            "不是在三个数里挑好看的。",
            "诊断二:留一法只为定位「哪一关把样本吃光了」,好拿去追问专家;"
            "★ 去掉任何一关的版本都不作为结果上报。",
        ],
        "诊断一_松紧一次只换一个": one_at_a_time,
        "诊断二_松端版留一法": leave_one,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print()
    print(f"原始数字已写:{OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
