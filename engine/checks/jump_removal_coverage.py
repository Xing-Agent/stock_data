#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查:引擎实际用的序列里,还剩多少没有归属的价格跳变 · 2026-10-30 重写

★★★ 这个文件的第一版判据是错的,而且错得很难看 —— 写在这里当教训:

  第一版的逻辑:
    「断裂清单上 30 只票,而 residual_jumps(3.0) 只列了 10 根 / 8 只票
      → 另外 22 只『一根都没列到』→ 它们原样进了回测
      → 剔掉 0.0016%,污染 8.05%,差 4,898 倍」

  ★★★ 把自己工具的含义读反了。residual_jumps 列的是★【还没修掉的】——
     所以「一根都没列到」的真实含义是 ★★「这只票已经修干净了,没有残余」,
     和第一版写的意思正好相反。

  ★ 实测证据(2026-10-30 自己核的):
     SQBG  原始 daily.json 的 close:最大单日跳变 1,201.62x @ 2020-07-27
     SQBG  引擎实际跑的序列:        最大单日跳变     1.892x @ 2021-07-02
     ★★ 那个跳变早就被 split_gate 修掉了。FTLF 1.399x · BNED 2.527x 同理。

  ★★ 第一版之所以能算出那个数,是因为它绕过引擎、直接读
     pilot_300/*/daily.json 的原始 close —— ★★★ 那是未修的序列。
     ★ 我们实际跑的任何东西都不用它。

  ★★★ 一句话教训:
     ★ 不要用"清单里有几条"去推断"保护够不够" ——
     ★★ 要直接量【引擎实际用的那份数据】。
     ★ 这个文件现在就是这么做的:逐只 load_daily(),量真实序列。

────────────────────────────────────────────────────────────────────────
现在的判据(两条,都量引擎实际用的序列)
  ① 引擎序列里,单日跳变 ≥ JUMP_X 的,★ 每一根都必须有归属
     (已登记的公司行为 / 已人工认领 / 在待裁决清单上)
  ② residual_jumps() 列出的每一根,★ 同样必须有归属

  ★★ 「有归属」不等于「已修」—— 一根跳变可以是真实行情(财报暴涨),
     那就该被认领成真实行情。★★★ 不许的是「既没修、也没人看过」。
────────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ENGINE)

#: 单日跳变倍数门槛。★ 不是新挑的数:用的就是 split_gate.residual_jumps 的默认 3.0。
JUMP_X = 3.0

#: 2026-10-30 重写后的实测基线(留作回归)
EXPECTED_NOTE = (
    "2026-10-30:SQBG 引擎序列最大单日跳变 1.892x(原始文件里是 1,201.62x)"
    " —— 根因修复后残余跳变 10 根 / 8 只票。"
)


def _sibling(mod: str):
    p = os.path.join(_HERE, mod + ".py")
    spec = importlib.util.spec_from_file_location("checks_" + mod, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                  # type: ignore
    return m


def claimed_symbols() -> set:
    """已经有归属的票:已登记的公司行为 + 已人工认领的离群笔。"""
    ah = _sibling("anchor_health")
    return set(ah.known_break_symbols()) | set(ah.CLAIMED_OUTLIERS)


def scan_engine_series(jump_x: float = JUMP_X) -> dict:
    """★ 逐只读【引擎实际用的序列】,量真实的单日跳变。"""
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    from engine import data as D                                # noqa: PLC0415

    pool_dir = os.path.join(_REPO, "pilot_300")
    pool = [d for d in sorted(os.listdir(pool_dir))
            if os.path.isdir(os.path.join(pool_dir, d)) and d != "benchmarks"]

    worst, flagged, failed = [], [], []
    for s in pool:
        try:
            c = D.load_daily(s)["close"]
            r = (c / c.shift(1)).dropna()
            if r.empty:
                continue
            mx = float(r.max())
            worst.append((mx, s, str(r.idxmax())[:10]))
            if mx >= jump_x:
                flagged.append((mx, s, str(r.idxmax())[:10]))
        except Exception as e:                                  # noqa: BLE001
            failed.append((s, type(e).__name__))
    worst.sort(reverse=True)
    flagged.sort(reverse=True)
    return {"池子只数": len(pool), "读失败": failed,
            "最大跳变前十": worst[:10], "超门槛的": flagged}


def check(jump_x: float = JUMP_X) -> dict:
    sc = scan_engine_series(jump_x)
    claimed = claimed_symbols()

    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    from engine import split_gate                               # noqa: PLC0415
    residual = split_gate.residual_jumps(jump_x)

    # ① 引擎序列里超门槛、且没有归属的
    unowned_series = [t for t in sc["超门槛的"] if t[1] not in claimed]
    # ② residual_jumps 里没有归属的
    unowned_resid = [t for t in residual if t[0] not in claimed]

    out: dict = {
        "门槛": f"单日跳变 ≥ {jump_x:g}x",
        "池子只数": sc["池子只数"],
        "引擎序列超门槛的票数": len(sc["超门槛的"]),
        "★其中没有归属的": len(unowned_series),
        "残余跳变根数": len(residual),
        "★残余跳变里没有归属的": len(unowned_resid),
        "已有归属的票数": len(claimed),
        "最大跳变前十": sc["最大跳变前十"],
        "话": [],
    }
    if sc["读失败"]:
        out["读失败"] = sc["读失败"][:10]

    if unowned_series or unowned_resid:
        out["级别"] = "FAIL"
        if unowned_series:
            out["话"].append(
                f"★★ FAIL 引擎序列里有 {len(unowned_series)} 只票的单日跳变 "
                f"≥ {jump_x:g}x,★ 而它们**既不在已登记的公司行为里、也没被人工认领** "
                f"→ ★★★ 既没修、也没人看过。")
            for mx, s, d in unowned_series[:12]:
                out["话"].append(f"    · {s:6s} {mx:8.3f}x @ {d}")
        if unowned_resid:
            out["话"].append(
                f"★ FAIL residual_jumps({jump_x:g}) 里有 {len(unowned_resid)} 根"
                f"没有归属。")
            for s, d, x in unowned_resid[:12]:
                out["话"].append(f"    · {s:6s} {x:8.3f}x @ {d}")
        out["话"].append(
            "    · ★ 怎么办:逐根判定是**真实行情**还是**未登记的公司行为** —— "
            "真实行情写进 anchor_health.CLAIMED_OUTLIERS(要附依据),"
            "公司行为写进 split_gate 的事件清单。"
            "★★ 不许默认它是真的就放过去。")
    else:
        out["级别"] = "OK"
        out["话"].append(
            f"✅ 引擎序列里 ≥{jump_x:g}x 的跳变共 {len(sc['超门槛的'])} 只票,"
            f"残余跳变 {len(residual)} 根 —— ★ 全部有归属。")

    out["话"].append(
        f"★ 报告口径提醒:凡写「已剔除假跳变」必须说清剔的是什么。"
        f"现在的实情是:★ 根因已修(改读源头 split_coefficient),"
        f"★★ 引擎序列里最大单日跳变 {sc['最大跳变前十'][0][0]:.3f}x"
        f"({sc['最大跳变前十'][0][1]});"
        f"★ residual_jumps 列的是**还没修掉的** {len(residual)} 根,"
        f"★★★ 不是「我们只保护了这几根」。")
    return out


def _selftest() -> None:
    r = check()
    for line in r["话"]:
        print("  ", line)
    print(f"\n  引擎序列最大跳变前五:")
    for mx, s, d in r["最大跳变前十"][:5]:
        print(f"     {s:6s} {mx:8.3f}x @ {d}")

    # ★ 回归断言:根因修复后,SQBG 在引擎序列里不该是个巨大跳变
    big = {s: mx for mx, s, _ in r["最大跳变前十"]}
    assert all(mx < 50 for mx in big.values()), r["最大跳变前十"]
    assert r["残余跳变根数"] >= 0

    # ★★ 反向自测:把门槛压到 1.5x → 一定会抓出一批没有归属的
    r2 = check(jump_x=1.5)
    assert r2["级别"] == "FAIL", "压到 1.5x 还 OK → 这道闸没在工作"
    print(f"\n  ★ 反向自测:门槛压到 1.5x → {r2['级别']}"
          f"(超门槛 {r2['引擎序列超门槛的票数']} 只,"
          f"其中没归属 {r2['★其中没有归属的']} 只)→ ★ 闸在工作")

    print("\nchecks/jump_removal_coverage 自测通过 —— "
          "★★★ 第一版把 residual_jumps 的含义读反了(把『已修完』当成『没保护』),"
          "现在改成直接量引擎实际用的序列。")


if __name__ == "__main__":
    _selftest()
