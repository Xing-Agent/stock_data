"""
★ R 的分母锁死首仓初始风险 —— 口径 + 一道会 FAIL 的闸。

三秒版:R 的分母只能是**第一笔进场**时的风险,一辈子不变。
        加仓不许改它,止损抬高不许改它。

口径(策略组已拍板):

    1R = |Entry₁ − InitialStop₁| × Shares₁

    Final R-Multiple = [ Σ(Exit_i − Entry_i) × Shares_i − 总费用 ] / 1R_initial

★ 严禁随加仓动态改变分母。两条理由,第二条是**纯数学**:

  ① **稀释**:一笔顺风暴赚的交易,后期分母大 3 倍 → +12R 被稀释成 +4R。
     也就是说「分母随仓位走」这个写法会系统性地**低估最赚钱的那几笔** ——
     而趋势跟随的全部利润就来自那几笔。量错的正好是唯一重要的那部分。

  ② ★★ **除以 0**:如果止损抬到保本以上,账面名义风险 = 0
     → 分母 = 0 → 公式崩溃。
     ★ 这一条不是「可能不准」,是**没有定义**。而且它一定会发生:
       我们几乎每条链的 trailing_stop 里都有「保本」那一级
       (move_to_breakeven / move_stop_to_breakeven)—— 也就是说
       「分母随当前止损走」这个写法在本仓库是**必然**崩的,不是偶然。

────────────────────────────────────────────────────────────────────────
★ 现状(已核实,不是推测):
  engine/chain.py 的 `_close()` 用的是
      risk = abs(p["entry"] - p["init_stop"])
  —— 分母取的是 **init_stop**(首仓初始止损),不是 p["stop"](当前止损)。
  ★ 所以引擎现在的口径已经是对的。本文件做两件事:
    一、把口径落成可调用的函数(`one_r` / `final_r_multiple`),加仓落地时直接用;
    二、★ 做一道闸,盯住它以后不被改回去 —— 并且在真实流水上证明闸在工作。

★ 同时保留已有的**双侧判定**(上一轮已改好,本文件确认它还在):
      risk_per_share / entry_price > 0.9  或  < 0.01
  → 这条链不用 R,改用每笔收益率 %。
  定义在 engine/run_declean_1030.py(RATIO_HI / RATIO_LO)。
"""

from __future__ import annotations

import glob
import os
import sys
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: ★ 双侧判定的两个门槛 —— 和 run_declean_1030 必须一致,本文件的自测会核对
RATIO_HI_EXPECTED = 0.9
RATIO_LO_EXPECTED = 0.01


# ────────────────────────────────────────────────────────────────────────
# 一 · 口径本身
# ────────────────────────────────────────────────────────────────────────

#: 一份仓位(首仓或加仓的一份)。
#  ★ 这里故意用 collections.namedtuple,**不用 @dataclass** ——
#    engine/checks/run_all.py 的 _load() 是用 module_from_spec 加载的,
#    不往 sys.modules 注册;而 @dataclass 在求值时要回查 sys.modules[cls.__module__],
#    于是在 run_all 里会炸成 "'NoneType' object has no attribute '__dict__'"。
#    ★ 单跑这个文件时不会炸 —— 又是一个「两种跑法只测了一种」的坑,记在这里。
Leg = namedtuple("Leg", "entry shares exit")


class RDenominatorError(ValueError):
    """R 的分母被动过了,或者分母退化到不能用。"""


def one_r(entry1: float, initial_stop1: float, shares1: float) -> float:
    """
    1R = |Entry₁ − InitialStop₁| × Shares₁。

    ★ 三个参数**全部**来自第一笔进场那一刻,之后一个都不许变。
    ★ 分母 ≤ 0 直接抛 —— 不许静默返回 nan 然后让后面的均值变成天文数字。
      (上一轮真的出现过 R ≈ 1.2e+11,就是分母贴着 0 造出来的。)
    """
    r = abs(float(entry1) - float(initial_stop1)) * float(shares1)
    if not (r > 0):
        raise RDenominatorError(
            f"1R = |{entry1} − {initial_stop1}| × {shares1} = {r} —— 分母不是正数。\n  "
            f"★ 最常见的成因:把『当前止损』当成了分母,而止损已经抬到保本"
            f"(名义风险 = 0)→ 除以 0。★ 分母必须锁死**首仓初始**止损。")
    return r


def final_r_multiple(legs: list[Leg], total_cost: float, one_r_initial: float) -> float:
    """
    Final R-Multiple = [ Σ(Exit_i − Entry_i) × Shares_i − 总费用 ] / 1R_initial。

    ★ 分母由调用方传进来,本函数**不会**根据 legs 重算分母 ——
      这正是「严禁随加仓动态改变分母」在代码上的落点。
    """
    if not (one_r_initial > 0):
        raise RDenominatorError(f"1R_initial = {one_r_initial},不是正数")
    pnl = sum((lg.exit - lg.entry) * lg.shares for lg in legs)
    return (pnl - float(total_cost)) / float(one_r_initial)


def one_r_from_legs_WRONG(legs: list[Leg], initial_stop1: float) -> float:
    """
    ★★ 反面教材 —— 本函数故意写的是**错的**那个口径(分母跟着总股数放大)。
    只给自测用:用它跑一遍,把「稀释」和「除以 0」两种后果量出来。
    ★ 任何正式代码都不许调用它;名字里带 WRONG 就是为了 grep 得到。
    """
    tot = sum(lg.shares for lg in legs)
    return abs(legs[0].entry - initial_stop1) * tot


# ────────────────────────────────────────────────────────────────────────
# 二 · 闸
# ────────────────────────────────────────────────────────────────────────

def _source(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def check() -> dict:
    """
    三件事:
      ① engine/chain.py 的 R 分母必须取 init_stop,不许取当前 stop
      ② 双侧判定(0.9 / 0.01)必须还在
      ③ 真实流水上:分母逐笔等于 |entry − initial_stop|,且恒为正(或被双侧判定接管)
    """
    out: dict = {"级别": "OK", "话": [], "问题": []}

    # ① 分母取谁 —— 直接读源码,这是最不会被绕过去的检查方式
    src = _source(os.path.join(_ENGINE, "chain.py"))
    good = 'risk = abs(p["entry"] - p["init_stop"])'
    bad_patterns = ['abs(p["entry"] - p["stop"])', "abs(p['entry'] - p['stop'])"]
    if good not in src:
        out["问题"].append(
            f"★★ engine/chain.py 里找不到 `{good}` —— R 的分母可能被改了。"
            f"★ 口径要求:分母锁死**首仓初始**止损(init_stop),不是当前止损(stop)。")
    for bp in bad_patterns:
        if bp in src:
            out["问题"].append(
                f"★★ engine/chain.py 里出现了 `{bp}` —— 分母取了**当前**止损。"
                f"★ 止损一抬到保本,名义风险 = 0 → 分母除以 0 → 公式崩溃。")
    if not out["问题"]:
        out["话"].append(
            "✅ ① engine/chain.py 的 R 分母取 init_stop(首仓初始止损),不是当前止损。")

    # ② 双侧判定还在不在
    dc = os.path.join(_ENGINE, "run_declean_1030.py")
    hi = lo = None
    if os.path.exists(dc):
        import re
        s = _source(dc)
        m = re.search(r"RATIO_HI\s*,\s*RATIO_LO\s*=\s*([0-9.]+)\s*,\s*([0-9.]+)", s)
        if not m:
            m2 = re.search(r"RATIO_HI\s*=\s*([0-9.]+)", s)
            m3 = re.search(r"RATIO_LO\s*=\s*([0-9.]+)", s)
            if m2 and m3:
                hi, lo = float(m2.group(1)), float(m3.group(1))
        else:
            hi, lo = float(m.group(1)), float(m.group(2))
    if hi is None or lo is None:
        out["问题"].append(
            "★★ 找不到双侧判定的两个门槛(run_declean_1030.RATIO_HI / RATIO_LO)—— "
            "上一轮改好的那条「R 不可用就改用每笔收益率 %」可能被删了。")
    elif abs(hi - RATIO_HI_EXPECTED) > 1e-9 or abs(lo - RATIO_LO_EXPECTED) > 1e-9:
        out["问题"].append(
            f"★★ 双侧门槛被改了:现在是 {hi} / {lo},口径是 "
            f"{RATIO_HI_EXPECTED} / {RATIO_LO_EXPECTED}。")
    else:
        out["话"].append(
            f"✅ ② 双侧判定还在:risk/entry > {hi} 或 < {lo} → 这条链不用 R,"
            f"改用每笔收益率 %(engine/run_declean_1030.py)。")

    # ③ 真实流水:分母逐笔自洽
    led_rows, bad_rows, deg_chains = 0, 0, []
    import csv
    pats = sorted(glob.glob(os.path.join(_ENGINE, "ledgers_*", "*.csv")))
    out["流水文件数"] = len(pats)
    for p in pats:
        with open(p, encoding="utf-8") as fh:
            rd = list(csv.DictReader(fh))
        if not rd or "risk_per_share" not in (rd[0] or {}):
            continue
        hi_n = lo_n = 0
        for row in rd:
            try:
                e = float(row["entry_price"]); st = float(row["initial_stop"])
                rps = float(row["risk_per_share"])
            except (TypeError, ValueError, KeyError):
                continue
            led_rows += 1
            if abs(abs(e - st) - rps) > max(1e-6, 1e-6 * abs(e)):
                bad_rows += 1
            if e > 0:
                ratio = rps / e
                hi_n += ratio > RATIO_HI_EXPECTED
                lo_n += ratio < RATIO_LO_EXPECTED
        if hi_n or lo_n:
            deg_chains.append((os.path.basename(p), len(rd), hi_n, lo_n))
    if bad_rows:
        out["问题"].append(
            f"★★ 真实流水里有 {bad_rows}/{led_rows} 笔的 risk_per_share "
            f"≠ |entry_price − initial_stop| —— 分母不是首仓初始风险。")
    else:
        out["话"].append(
            f"✅ ③ 真实流水 {len(pats)} 个文件 / {led_rows} 笔:risk_per_share "
            f"逐笔等于 |entry_price − initial_stop| —— 分母就是首仓初始风险。")
    out["★双侧判定接管的链"] = deg_chains
    out["话"].append(
        f"★ 其中 {len(deg_chains)} 条链有笔子落在两头(>{RATIO_HI_EXPECTED} 或 "
        f"<{RATIO_LO_EXPECTED})→ 这些链按口径**不用 R**,改用每笔收益率 %。"
        f"★ 这不是 bug:技-12 / 技-2 的原著就是明确不设止损的。")

    if out["问题"]:
        out["级别"] = "FAIL"
    return out


# ────────────────────────────────────────────────────────────────────────
# 三 · 自测
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    global _ENGINE
    r = check()
    for line in r["话"]:
        print("  ", line)
    for q in r["问题"]:
        print("  ", q)
    assert r["级别"] == "OK", r["问题"]
    assert r["流水文件数"] > 0, "一个真实流水都没扫到 —— 这道闸是个壳子"

    # ── ① 稀释:一笔顺风加仓三次的交易,两种口径差多少 ───────────────
    # 首仓 100 股 @ 10,初始止损 9 → 1R = 1 × 100 = 100
    legs = [Leg(10.0, 100, 22.0), Leg(13.0, 100, 22.0), Leg(16.0, 100, 22.0)]
    r1 = one_r(entry1=10.0, initial_stop1=9.0, shares1=100)
    assert r1 == 100.0
    right = final_r_multiple(legs, total_cost=0.0, one_r_initial=r1)
    wrong = final_r_multiple(legs, total_cost=0.0,
                             one_r_initial=one_r_from_legs_WRONG(legs, 9.0))
    print(f"\n   ★ 稀释实测:同一笔交易 —— 锁死首仓分母 = {right:+.2f}R,"
          f"分母跟着加仓放大 = {wrong:+.2f}R(被稀释成 {wrong / right:.0%})")
    assert right > 3 * wrong - 1e-9, (right, wrong)   # 三份 → 稀释到约 1/3

    # ── ② ★★ 除以 0:止损抬到保本之后,「分母随当前止损走」必然崩 ──────
    try:
        one_r(entry1=10.0, initial_stop1=10.0, shares1=100)   # 止损 = 进场价(保本)
    except RDenominatorError as exc:
        assert "除以 0" in str(exc) or "不是正数" in str(exc)
        print("   ★ 保本止损实测:分母取当前止损 → 名义风险 0 → 抛 "
              "RDenominatorError(符合预期,不是静默 nan)")
    else:
        raise AssertionError("保本止损居然没抛 —— 这道闸没在工作")

    # 抬到保本**以上**(止损 10.5 > 进场 10)照样是 0 风险以下 → 也必须抛不了?
    # ★ 注意:|10 − 10.5| = 0.5 > 0,数学上算得出,但那是**负**风险 ——
    #   所以口径上必须用首仓初始止损,而不是靠这个函数挡。这里显式记一笔:
    assert one_r(10.0, 10.5, 100) == 50.0, \
        "★ 提醒:止损抬到进场价之上时 |entry−stop| 仍为正,但那是负风险 —— " \
        "这正是为什么分母必须**锁死首仓初始止损**,而不是『挡一下非正数』就够了"

    # ── ③ 反向自测:把 chain.py 的那行改成错的版本,闸必须 FAIL ──────
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        fake = os.path.join(td, "chain.py")
        shutil.copy(os.path.join(_ENGINE, "chain.py"), fake)
        s = _source(fake).replace('risk = abs(p["entry"] - p["init_stop"])',
                                  'risk = abs(p["entry"] - p["stop"])')
        with open(fake, "w", encoding="utf-8") as fh:
            fh.write(s)
        keep, _ENGINE = _ENGINE, td
        try:
            # 只测 ① 那一段:临时把 _ENGINE 指到副本目录
            r2 = check()
        finally:
            _ENGINE = keep
        assert r2["级别"] == "FAIL", r2
        assert any("当前" in q for q in r2["问题"]), r2["问题"]
        print(f"   ★ 反向自测:把 chain.py 的分母改成当前止损 → {r2['级别']}"
              f"(抓到 {len(r2['问题'])} 条)→ ★ 闸在工作")

    print("\nchecks/r_denominator_lock 自测通过 —— "
          "★ 1R = |Entry₁ − InitialStop₁| × Shares₁,加仓不许动分母;"
          "★★ 止损抬到保本 → 名义风险 0 → 分母除以 0,所以这不是口味问题,是数学问题。")


if __name__ == "__main__":
    _selftest()
