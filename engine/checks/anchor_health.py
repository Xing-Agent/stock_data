"""
★ 七(上)· 锚点自身体检 —— 凡被用作锚点 / 基线的链,★ 每次跑完必须先过它自己的
   「单笔异常收益 + 集中度」体检。不过就不许当锚点。

三秒版:我们用 buy_and_hold 这把尺子去校准别的尺子。
        ★ 如果这把尺子自己被一笔污染数据顶歪了,后面所有校准都是歪的。

为什么要有这个文件(2026-10-29 真实案例):
    buy_and_hold 是新基准线那道自检的锚点,而当时有 67 笔交易骑在数据断裂日上,
    最严重的 FTLF ★ +499.62 倍(net_pnl +167 万)。

  ★★★ 注意:上面那个 +499.62 倍 **已经不是现状了**(2026-10-30 核实)。
     ★ 根因修复之后(改读源头 split_coefficient,提交 1b6b28e),
       FTLF 在引擎序列里最大单日跳变是 **1.399x**;
       ★ 全池最大单日跳变是 3.141x(EXPR,2021-01-27,疑似 meme 逼空的真实行情)。
     ★★ 两版锚点体检现在**都是 OK**。
     ★ 保留上面那段是因为它是这个文件存在的理由,★★ 不是现状描述 ——
       ★★★ 读的时候别当成现在还有一笔 +499 倍在锚点里。
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

#: ★★ 已人工认领为「真实行情」的离群笔 —— symbol → 认领依据。
#:
#: 为什么要有这张表(2026-10-29 晚的真实误报):
#:   这道闸第一版在 buy_and_hold 上把 TSLA +20.01x 判成 FAIL,理由是
#:   「不在已知断裂清单上 → 需人工认领」。★ 人工核了,它是真的。
#:   ★★ 而「累计倍数」本身区分不了真假 —— 八年持有拿到 20 倍是正常的,
#:      污染的特征是**单根 bar 的跳变**(FTLF 那笔 +499.62 倍是一根假跳变
#:      复利出来的),不是累计倍数。
#:   ★ 所以累计倍数这把尺子只能用来「提请人工认领」,不能用来判 FAIL ——
#:     否则它会在每一个真实大赢家上喊狼,喊几次就没人看了。
#:
#: 认领一笔的要求:写清依据,不许只写「已核」。
CLAIMED_OUTLIERS: dict[str, str] = {
    "TSLA": (
        "真实行情。2018-01-03 的 21.40 是拆股调整后价(TSLA 在 2020-08 做过 "
        "5:1、2022-08 做过 3:1,累计 15:1;当时未调整价约 320,320/15≈21.3,"
        "与流水里的 21.40 一致)。2025-12-31 的 449.72 量级也对得上。"
        "★ 认领人:本会话,2026-10-29 晚,逐笔核过入场价与拆股系数的一致性。"
    ),
}

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

    # ★★ 三分:① 在已知断裂清单上 → FAIL  ② 已人工认领 → 过  ③ 其余 → WARN
    on_break = [t for t in bad if t[0] in known]
    claimed = [t for t in bad if t[0] not in known and t[0] in CLAIMED_OUTLIERS]
    unclaimed = [t for t in bad if t[0] not in known
                 and t[0] not in CLAIMED_OUTLIERS]
    out["★在已知断裂清单上的笔数"] = len(on_break)
    out["★已人工认领的笔数"] = len(claimed)
    out["★待人工认领的笔数"] = len(unclaimed)

    level = "OK"

    # ① 骑在已知断裂上的 —— 这个才是 FAIL
    if on_break:
        level = "FAIL"
        out["话"].append(
            f"[{name}] ★★ FAIL 锚点有 {len(on_break)} 笔骑在**已知数据断裂票**上 "
            f"—— ★ 锚点的绝对数字在这几笔裁决完之前不可用。"
            f"(我们是拿这把尺子去校准别的尺子的。)")
        for sym, x, pnl, d0, d1 in on_break:
            out["话"].append(
                f"    · {sym:6s} {x:+.2f}x  net_pnl={pnl:+,.0f}  "
                f"{d0}..{d1}  ★★ 在已知断裂清单上 → 高度疑似污染,先裁决。")

    # ② 已认领的 —— 列出来,但不影响级别(依据写在 CLAIMED_OUTLIERS 里)
    for sym, x, pnl, d0, d1 in claimed:
        out["话"].append(
            f"    · {sym:6s} {x:+.2f}x  net_pnl={pnl:+,.0f}  {d0}..{d1}  "
            f"✅ 已人工认领为真实行情 —— {CLAIMED_OUTLIERS[sym]}")

    # ③ 既不在断裂清单、也没认领的 —— WARN,不是 FAIL
    #    ★ 理由见 CLAIMED_OUTLIERS 的注释:累计倍数区分不了真假,
    #      八年持有拿到 10 倍是正常的。它只能用来提请人工认领。
    if unclaimed:
        if level == "OK":
            level = "WARN"
        out["话"].append(
            f"[{name}] ★ WARN 有 {len(unclaimed)} 笔单笔收益超过 {outlier_x:g} 倍、"
            f"既不在已知断裂清单上、也还没被认领 → **需人工认领**:"
            f"真实行情 还是 未登记的数据断裂?"
            f"★ 不许默认它是真的就放过去;认领完写进 CLAIMED_OUTLIERS 并附依据。")
        for sym, x, pnl, d0, d1 in unclaimed:
            out["话"].append(
                f"    · {sym:6s} {x:+.2f}x  net_pnl={pnl:+,.0f}  {d0}..{d1}")

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
        if claimed:
            out["话"].append(
                f"[{name}] ✅ 锚点体检通过:{len(claimed)} 笔 ≥{outlier_x:g}x "
                f"已人工认领为真实行情,无待认领、无骑在已知断裂上的笔,"
                f"集中度 {share:.1%}。")
        else:
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
    #    ★★ 三分口径的三条路都在这条真实流水上验一遍。
    p = os.path.join(_ENGINE, "ledgers_1029_新基准线", "buy_and_hold.csv")

    # ②-a 已认领 → 过。TSLA +20.01x 的依据写在 CLAIMED_OUTLIERS 里。
    r = check_anchor_ledger(p)
    assert r["级别"] == "OK", r
    assert r["★已人工认领的笔数"] == 1 and r["★待人工认领的笔数"] == 0, r
    print(f"  ② 真实锚点 buy_and_hold({r['笔数']} 笔)→ ✅ 通过:"
          f"TSLA +20.01x 已认领为真实行情")

    # ②-b ★ 把认领撤掉 → 立刻变 WARN(不是 FAIL)。
    #     为什么是 WARN:累计倍数区分不了真假,八年持有拿到 20 倍是正常的。
    #     ★ 这道闸第一版在这里判了 FAIL —— 那是误报,修的就是这个。
    _saved = CLAIMED_OUTLIERS.pop("TSLA")
    try:
        rw = check_anchor_ledger(p)
        assert rw["级别"] == "WARN", rw
        assert rw["★待人工认领的笔数"] == 1, rw
        print(f"  ③ 撤掉 TSLA 的认领 → ★ WARN「需人工认领」,**不是 FAIL** "
              f"→ ★ 累计倍数只能提请认领,不能判污染")
    finally:
        CLAIMED_OUTLIERS["TSLA"] = _saved

    # ②-c ★ 同一笔,如果它在已知断裂清单上 → FAIL。
    #     这才是真污染的形状(FTLF 那笔 +499.62x 是一根假跳变复利出来的)。
    _orig = globals()["known_break_symbols"]
    globals()["known_break_symbols"] = lambda: _orig() | {"TSLA"}
    try:
        rf = check_anchor_ledger(p)
        assert rf["级别"] == "FAIL", rf
        assert rf["★在已知断裂清单上的笔数"] == 1, rf
        print(f"  ④ 同一笔,假设 TSLA 在已知断裂清单上 → ★★ FAIL "
              f"→ ★ 「在断裂清单上」才是判 FAIL 的依据")
    finally:
        globals()["known_break_symbols"] = _orig

    # ── 退化的链不许当锚点:技-13(223 笔 / 盈利 9 笔)─────────────────
    r3 = check_anchor_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                          "技-13_TD序列.csv"))
    assert r3["级别"] == "FAIL", r3
    assert any("集中度体检退化" in x for x in r3["话"]), r3["话"]
    print(f"  ⑤ 技-13_TD序列 若被当锚点 → ★ FAIL(集中度体检退化)")

    # ── 该通过的:技-12(2631 笔、集中度 7.4%、无 10x 单笔)──────────────
    r4 = check_anchor_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                          "技-12_康纳斯均值回归.csv"))
    assert r4["级别"] == "OK", r4
    print(f"  ⑥ 不误伤:技-12_康纳斯 → ✅ 通过({r4['话'][-1][-30:]})")

    print("checks/anchor_health 自测通过 —— ★★ 三分口径:"
          "在已知断裂清单上 → FAIL;已人工认领 → 过;其余 → WARN 需认领。"
          "★ 修的是第一版把 TSLA +20.01x(真实行情)判成 FAIL 的误报 —— "
          "累计倍数区分不了真假,污染的特征是单根 bar 的跳变。")


if __name__ == "__main__":
    _selftest()
