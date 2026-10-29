"""
★ 七(上)· 锚点自身体检 —— 凡被用作锚点 / 基线的链,★ 每次跑完必须先过它自己的
   「单笔异常收益 + 集中度」体检。不过就不许当锚点。

三秒版:我们用 buy_and_hold 这把尺子去校准别的尺子。
        ★ 如果这把尺子自己被一笔污染数据顶歪了,后面所有校准都是歪的。

为什么要有这个文件(2026-10-29 真实案例):
    buy_and_hold 是新基准线那道自检的锚点,而当时有 67 笔交易骑在数据断裂日上,
    最严重的 FTLF ★ +499.62 倍(net_pnl +167 万)。
  ★ 自检的**逻辑**是对的(择时贡献严格输出 0.0),
    ★ 但锚点的**绝对数字**不可用 —— 等于拿一把自己带病的尺子去校准别的尺子。
  ★ 现行代码里有「择时贡献必须为 0」这一个检查点,★ 但没有任何东西体检
    锚点自己的单笔分布。这就是本文件。

★ 规则(策略组拍的):锚点链每次跑完必须体检,
  ★ 单笔收益超过某个倍数(建议 10 倍)直接报警,并逐笔给出归属:
    · 这只票在已知的数据断裂清单上 → ★ 高度疑似污染,锚点数字不可用
    · 不在清单上                    → ★ 需人工认领(可能是真实行情,如 TSLA)
  ★ 另外锚点还要过集中度体检(见 concentration_degenerate.py)。

★ 本文件只读流水,不改任何跑批逻辑;★ 不 import engine 的跑批模块
  (另一个 agent 在跑回测,2 核 / 7GB),已知断裂清单从**仓库里现成的产物**读。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)

#: 单笔毛收益超过这个倍数 → 报警。出处:策略组 2026-10-29「建议 10 倍」。
OUTLIER_X = 10.0

#: 锚点的集中度上限。出处:pat6_table._verdict 现行口径「过半 → 数字不可用」。
ANCHOR_MAX_CONCENTRATION = 0.50


def _load_sibling(mod: str) -> Any:
    """按文件路径加载同目录的检查模块(engine/checks 不是包)。"""
    path = os.path.join(_HERE, mod + ".py")
    spec = importlib.util.spec_from_file_location("checks_" + mod, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                 # type: ignore
    return m


# ────────────────────────────────────────────────────────────────────────
# 一 · 已知的数据断裂票 —— 从仓库里现成的产物读,不 import 跑批模块
# ────────────────────────────────────────────────────────────────────────

def known_break_symbols() -> set[str]:
    syms: set[str] = set()

    # ① 真实产物:新基准线的假跳变审计
    p = os.path.join(_ENGINE, "results_1029_新基准线_假跳变审计.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as fh:
            syms |= set((json.load(fh).get("逐票跳变日") or {}).keys())

    # ② split_gate.py 里登记的 EVENTS / UNRESOLVED_BREAKS / 技术方核实清单
    #    ★ 文本解析,不 import —— 避免拉起 pandas / 读 cache
    #      (另一个 agent 正在跑回测,2 核 / 7GB)。
    #    ★ 取法:凡「"代码", "YYYY-MM-DD"」这个形状的,都算登记过的断裂票。
    #      这是 EVENTS / UNRESOLVED_BREAKS / TECH_VERIFIED_COEFFICIENTS
    #      三份清单共用的写法。
    g = os.path.join(_ENGINE, "split_gate.py")
    if os.path.exists(g):
        with open(g, encoding="utf-8") as fh:
            src = fh.read()
        syms |= set(re.findall(
            r'"([A-Z][A-Z0-9.\-]{0,5})",\s*"\d{4}-\d{2}-\d{2}"', src))
        # 换股并购盲区是一份裸代码清单,单独取
        i = src.find("MERGER_BLIND_SPOT_SYMBOLS")
        if i >= 0:
            j = src.find(")", i)
            syms |= set(re.findall(r'"([A-Z][A-Z0-9.\-]{0,5})"', src[i:j]))
    return {s for s in syms if 1 <= len(s) <= 6}


# ────────────────────────────────────────────────────────────────────────
# 二 · 体检
# ────────────────────────────────────────────────────────────────────────

def check_anchor_ledger(path: str, *, outlier_x: float = OUTLIER_X,
                        ret_col: str = "gross_return",
                        pnl_col: str = "net_pnl") -> dict:
    """
    体检一条**被当作锚点**的流水。返回 dict,级别 ∈ {FAIL, OK}。
    """
    name = os.path.basename(path)[:-4]
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    known = known_break_symbols()

    out: dict = {"锚点": name, "笔数": len(rows), "话": []}
    bad = []
    for r in rows:
        try:
            x = float(r[ret_col])
        except (KeyError, TypeError, ValueError):
            continue
        if abs(x) >= outlier_x:
            bad.append((r.get("symbol", "?"), x, float(r.get(pnl_col) or 0),
                        r.get("entry_date"), r.get("exit_date")))
    bad.sort(key=lambda t: -abs(t[1]))
    out["★单笔超%gx的笔数" % outlier_x] = len(bad)

    level = "OK"
    if bad:
        level = "FAIL"
        out["话"].append(
            f"[{name}] ★★ FAIL 锚点自己有 {len(bad)} 笔单笔收益超过 "
            f"{outlier_x:g} 倍 —— ★ 锚点的**绝对数字**在逐笔认领完之前不可用。"
            f"(我们是拿这把尺子去校准别的尺子的。)")
        for sym, x, pnl, d0, d1 in bad:
            if sym in known:
                out["话"].append(
                    f"    · {sym:6s} {x:+.2f}x  net_pnl={pnl:+,.0f}  "
                    f"{d0}..{d1}  ★★ 这只票在**已知数据断裂清单**上 → "
                    f"高度疑似污染,★ 这笔必须先裁决再谈锚点数字。")
            else:
                out["话"].append(
                    f"    · {sym:6s} {x:+.2f}x  net_pnl={pnl:+,.0f}  "
                    f"{d0}..{d1}  ★ 不在已知断裂清单上 → **需人工认领**:"
                    f"真实行情 还是 未登记的数据断裂?"
                    f"★ 不许默认它是真的就放过去。")

    # 集中度体检(锚点也要过)
    conc_mod = _load_sibling("concentration_degenerate")
    pnls = [float(r[pnl_col]) for r in rows if r.get(pnl_col) not in (None, "")]
    c = conc_mod.concentration(pnls, name=name)
    out["集中度体检"] = c
    share = c.get("集中度_前10笔占总盈利")
    if c.get("★退化") or c.get("★半退化"):
        level = "FAIL"
        out["话"].append(f"[{name}] ★★ FAIL 锚点的集中度体检退化 —— {c['★读法']}")
    elif isinstance(share, (int, float)) and share > ANCHOR_MAX_CONCENTRATION:
        level = "FAIL"
        out["话"].append(
            f"[{name}] ★★ FAIL 锚点集中度 {share:.1%} > "
            f"{ANCHOR_MAX_CONCENTRATION:.0%} —— 锚点自己的曲线是几笔扛起来的,"
            f"★ 不许当锚点。")

    out["级别"] = level
    if level == "OK":
        out["话"].append(f"[{name}] ✅ 锚点体检通过:无单笔 ≥{outlier_x:g}x,"
                         f"集中度 {share:.1%}。")
    return out


def assert_anchor(path: str, **kw) -> None:
    r = check_anchor_ledger(path, **kw)
    if r["级别"] != "OK":
        raise ValueError("锚点自身体检未通过:\n" + "\n".join(r["话"]))


# ────────────────────────────────────────────────────────────────────────
# 三 · 自测 —— ★ 跑在仓库里现成的真实锚点流水上
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    known = known_break_symbols()
    assert {"FTLF", "AMRS", "KDP", "OVV", "GNCA"} <= known, sorted(known)[:40]
    print(f"  ① 已知数据断裂票 {len(known)} 只(从真实产物"
          f" results_1029_新基准线_假跳变审计.json + split_gate.py 读出来的),"
          f"含 FTLF / AMRS / KDP / OVV / GNCA")

    # ── 真实锚点流水:ledgers_1029_新基准线/buy_and_hold.csv ────────────
    p = os.path.join(_ENGINE, "ledgers_1029_新基准线", "buy_and_hold.csv")
    r = check_anchor_ledger(p)
    assert r["级别"] == "FAIL", r
    assert r["★单笔超10x的笔数"] >= 1, r
    print(f"  ② 真实锚点 buy_and_hold({r['笔数']} 笔)→ ★ FAIL:")
    for line in r["话"][:4]:
        print("     ", line[:140])

    # ★ 把 10 倍线放到 25 倍 → 同一条锚点就过了。
    #   这正说明阈值是一个**要拍的数**,而不是一个自然常数 —— 所以写在顶上。
    r2 = check_anchor_ledger(p, outlier_x=25.0)
    assert r2["级别"] == "OK", r2
    print(f"  ③ 同一条锚点把门槛放到 25x → 通过({r2['话'][-1][:72]} …)"
          f" → ★ 说明 10x 这个数是拍的,必须显式写在文件顶上,不能埋在代码里")

    # ── 退化的链不许当锚点:技-13(223 笔 / 盈利 9 笔)─────────────────
    r3 = check_anchor_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                          "技-13_TD序列.csv"))
    assert r3["级别"] == "FAIL", r3
    assert any("集中度体检退化" in x for x in r3["话"]), r3["话"]
    print(f"  ④ 技-13_TD序列 若被当锚点 → ★ FAIL(集中度体检退化)")

    # ── 该通过的:技-12(2631 笔、集中度 7.4%、无 10x 单笔)──────────────
    r4 = check_anchor_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                          "技-12_康纳斯均值回归.csv"))
    assert r4["级别"] == "OK", r4
    print(f"  ⑤ 不误伤:技-12_康纳斯 → ✅ 通过({r4['话'][-1][-30:]})")

    print("checks/anchor_health 自测通过 —— "
          "★ 真实锚点 buy_and_hold 在 10x 线上 FAIL,"
          "TSLA +20.01x 被要求人工认领(真实行情 or 未登记的数据断裂)")


if __name__ == "__main__":
    _selftest()
