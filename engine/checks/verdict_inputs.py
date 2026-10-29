"""
★ 六 · 判据不许混线 —— 判定函数的输入必须显式分成「策略量」和「对照量」两组,
   混用 → ★ 直接 FAIL。

三秒版:「这条策略有没有边际」只能用**收益口径**的对照组来判。
        「它是不是在挑波动大的票」是另一个问题,用的是另一个口径(|R|)。
        把后者折进前者的判定里 → 低波动类形态会被整批误判成「负边际」。

为什么要有这个文件(2026-10-29 真实踩的坑):
    pat6_table._verdict 把**波动率选择检验**的 Z 折进了「负边际」判定,
    ★ 结果技-6 三个版本全被误判:
      技-6 原著版:条件分层随机 −0.92 / 块重排 −0.71 / ★ 波动率选择 −2.98
      技-6 行业版:条件分层随机 −1.53 / 块重排 −1.23 / ★ 波动率选择 −3.42
      技-6 XING版:条件分层随机 −0.81 / 块重排 −0.61 / ★ 波动率选择 −2.44
    ★ 混线时 min(三个) ≤ −1.65 → 三版全判「负边际」。
    ★ 分线后 min(收益两关) = −1.53 > −1.65 → 正确结论是「测出来没有边际」。
    两个结论的行动完全不同:「负边际」是「这条有害,砍掉」,
    「没有边际」是「这条白跑,但不害人」。
    已修(commit 728da32),★ 但当时没有任何检查防止它再发生 —— 这就是本文件。

★ 本文件只读,不改任何跑批逻辑。
"""

from __future__ import annotations

import json
import os
from typing import Iterable, Sequence

# ────────────────────────────────────────────────────────────────────────
# 一 · 两组量的登记 —— ★ 按本代码库实际在用的键名写
# ────────────────────────────────────────────────────────────────────────

#: 收益口径的对照组 —— ★ 只有这一组可以进「有没有边际」的判定。
STRATEGY_MARGIN_KEYS: frozenset[str] = frozenset({
    "条件分层随机",
    "块重排(Politis&Romano)",
    "块重排",
})

#: 对照量 —— 测的是「信号在挑什么样的票」,★ 不是「收益好不好」。
#  ★ 这一组一旦进了策略边际的判定,就是混线。
CONTROL_ONLY_KEYS: dict[str, str] = {
    "波动率选择(|R|)": (
        "测的是 mean(|R|) 信号 vs 随机 = 「是不是在挑波动大的票」。"
        "它为负只说明信号挑到的票振幅**比随机更小**(低波动结构)—— "
        "★ 这不是「收益差于随机」。把它混进负边际判定会把低波动类形态"
        "(箱体突破这一类)全部误判。"),
    "波动率选择": "同上",
    "极性反转·做多": (
        "★ 严格镜像、零信息量:analyze 把信号和对照同时取负,"
        "Z_做空 ≡ −Z_做多。它连独立结果都不是,更不能进判定。"),
    "极性反转·做空": "同上",
    "极性反转": "同上",
}


class CrossLine(ValueError):
    """判据混线 —— ★ 不许只警告。"""


# ────────────────────────────────────────────────────────────────────────
# 二 · 闸
# ────────────────────────────────────────────────────────────────────────

def classify(keys: Iterable[str]) -> dict[str, list[str]]:
    """把一组键名分成 策略量 / 对照量 / 没登记 三堆。"""
    out: dict[str, list[str]] = {"策略量": [], "对照量": [], "没登记": []}
    for k in keys:
        s = str(k)
        if s in STRATEGY_MARGIN_KEYS:
            out["策略量"].append(s)
        elif s in CONTROL_ONLY_KEYS or any(
                s.startswith(p) for p in ("波动率选择", "极性反转")):
            out["对照量"].append(s)
        else:
            out["没登记"].append(s)
    return out


def check_margin_inputs(name: str, used_keys: Sequence[str]) -> list[str]:
    """
    ★ 核心闸:给出一个「策略有没有边际」判定**实际读了哪些键**,
      里面出现对照量 → FAIL;出现没登记的键 → 也 FAIL(不许偷偷加输入)。
    """
    g = classify(used_keys)
    problems: list[str] = []
    for k in g["对照量"]:
        why = CONTROL_ONLY_KEYS.get(k, "这是对照量,不是策略量")
        problems.append(
            f"[{name}] ★★ FAIL 判据混线:「有没有边际」的判定里读进了"
            f"**对照量** `{k}` —— {why}")
    for k in g["没登记"]:
        problems.append(
            f"[{name}] ★★ FAIL 判定读了一个**没登记**的输入 `{k}` —— "
            f"判定函数必须把输入显式分成「策略量」和「对照量」两组;"
            f"没登记的键不许进判定(★ 今天那个 bug 就是这样悄悄进来的)。")
    if not g["策略量"]:
        problems.append(
            f"[{name}] ★★ FAIL 判定里一个策略量都没有 —— "
            f"收益口径两关({sorted(STRATEGY_MARGIN_KEYS)})至少要有一关。")
    return problems


def margin_inputs(all_z: dict) -> dict[str, float]:
    """
    ★ 正确的取法:从「三套对照组Z」里**只**取收益口径那两关。
      凡是判定「有没有边际」,都该走这个函数,而不是自己 for 一遍。
    """
    return {k: float(v) for k, v in all_z.items()
            if k in STRATEGY_MARGIN_KEYS
            and isinstance(v, (int, float)) and not isinstance(v, bool)}


def assert_no_crossline(name: str, used_keys: Sequence[str]) -> None:
    problems = check_margin_inputs(name, used_keys)
    if problems:
        raise CrossLine("判据混线检查未通过(共 %d 项):\n  %s"
                        % (len(problems), "\n  ".join(problems)))


def negative_margin(all_z: dict, *, z_basic: float = 1.65,
                    name: str = "<未命名>") -> tuple[bool, str]:
    """
    ★ 「是不是负边际」的唯一正确读法,★ 自带混线闸。
      返回 (是不是负边际, 话)。
    """
    zs = margin_inputs(all_z)
    assert_no_crossline(name, list(zs))
    if not zs:
        return False, f"[{name}] 收益口径两关都算不出来 → 判不了"
    lo = min(zs.values())
    if lo <= -z_basic:
        return True, (f"[{name}] ★ 测出来是**负边际**:收益口径两关里"
                      f"最低 Z = {lo:+.2f} ≤ {-z_basic:+.2f}"
                      f"({', '.join(f'{k} {v:+.2f}' for k, v in zs.items())})")
    hi = max(zs.values())
    if hi >= z_basic:
        return False, (f"[{name}] 收益口径有单关达基础显著(最高 Z = {hi:+.2f}),"
                       f"不足以推翻硬关")
    return False, (f"[{name}] 收益口径两关都不显著 = **测出来没有边际**"
                   f"(最低 {lo:+.2f} / 最高 {hi:+.2f})"
                   f" —— ★ 这不等于「负边际」")


# ────────────────────────────────────────────────────────────────────────
# 三 · 自测 —— ★ 跑在仓库里现成的真实产物上(技-6 三版)
# ────────────────────────────────────────────────────────────────────────

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _selftest() -> None:
    with open(os.path.join(_ENGINE, "results_1029_技术派六条三版.json"),
              encoding="utf-8") as fh:
        d = json.load(fh)
    pat6 = [r for r in d["各版结果"] if "技-6" in r["报表名"]]
    assert len(pat6) == 3, [r["报表名"] for r in pat6]

    n_crossline = 0
    for r in pat6:
        allz = r["★三套对照组Z"]
        name = r["报表名"]

        # ── ① 复现当天的 bug:★ 把三个键**全部**折进负边际判定 ─────────
        buggy_keys = list(allz)
        got = check_margin_inputs(name + "(当天的 bug 写法)", buggy_keys)
        assert any("判据混线" in g and "波动率选择" in g for g in got), got
        n_crossline += 1
        lo_buggy = min(v for v in allz.values() if isinstance(v, (int, float)))

        # ── ② 正确写法:只取收益口径两关,闸通过 ─────────────────────────
        assert check_margin_inputs(name, list(margin_inputs(allz))) == [], name
        neg, words = negative_margin(allz, name=name)

        # ── ③ 两种写法的结论**不同** —— 这才是这道闸值钱的地方 ───────────
        assert lo_buggy <= -1.65, allz          # 混线 → 判「负边际」
        assert neg is False, (name, words)      # 分线 → 「没有边际」
        print(f"  · {name}")
        print(f"      混线(含波动率选择 {allz['波动率选择(|R|)']:+.2f}):"
              f"min Z = {lo_buggy:+.2f} ≤ −1.65 → ★ 误判为「负边际」")
        print(f"      分线:{words[len(name) + 3:]}")

    assert n_crossline == 3
    print(f"  ① 真实产物 results_1029_技术派六条三版.json:"
          f"技-6 三版**全部**在混线写法下被 FAIL 拦住(3/3)")

    # ── 不该误伤 ────────────────────────────────────────────────────────
    ok = {"条件分层随机": -0.9, "块重排(Politis&Romano)": -0.7}
    assert check_margin_inputs("ok", list(ok)) == []
    #   偷偷加一个没登记的输入 → 也要 FAIL
    sneaky = check_margin_inputs("sneaky", ["条件分层随机", "每笔R净"])
    assert any("没登记" in g for g in sneaky), sneaky
    #   一个策略量都没有 → FAIL
    assert any("一个策略量都没有" in g
               for g in check_margin_inputs("empty", ["波动率选择(|R|)"]))
    print("  ② 不误伤正确写法;偷偷加没登记的输入、以及「只有对照量」都 FAIL")

    # ── 真判负边际的情况也要能判出来(不许只会说「没有边际」)─────────────
    neg, words = negative_margin(
        {"条件分层随机": -2.10, "块重排(Politis&Romano)": -1.80}, name="假例")
    assert neg is True, words
    print("  ③ 收益口径两关真的显著为负时,照样判出「负边际」")

    print("checks/verdict_inputs 自测通过 —— "
          "★ 技-6 三版在真实数据上证明:混线 → 负边际(错);分线 → 没有边际(对)")


if __name__ == "__main__":
    _selftest()
