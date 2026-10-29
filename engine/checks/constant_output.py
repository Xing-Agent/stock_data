"""
★ 一 · 恒定输出检测 —— 一道闸抓三类「不报错的错」。

三秒版:一条判据,如果它 95% 以上的时间都输出同一个答案,那它等于没在判断;
        如果一半以上的时间算不出来,那它等于大部分时间不存在;
        如果一个分支永远不可能成立,那它是死代码。★ 这三件事都不会报错。

为什么要有这个文件(2026-10-29 当天真实踩的三个坑):
  ① 状-3 XING 版:mixed 占 99.57% —— ★ 这条判据从来没判出过任何东西,
     但它每天正常运行、不报错、报告里的数也「看起来正常」。
  ② 状-5 XING 版:73.47% 的票日落在 insufficient_sample —— ★ 指标大部分时间是空的。
  ③ 极性反转:analyze 里信号和对照**同时取负** → 数学上 Z_做空 ≡ −Z_做多,
     于是 polarity_check 里那条「多空两边都 ≥1.65」的分支 ★ 永远不可能成立 ——
     死代码,而「三套对照组缺一不可」的第三套实际上一直是空的。
     (stats_gate.polarity_check 的注释里已经留痕,但★ 没有任何检查会 FAIL。)

★ 所以这个文件的职责只有一件:把上面三件事做成**会 FAIL 的检查**。
★ 本文件只读,不改任何跑批逻辑。
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from typing import Any, Iterable, Sequence

# ────────────────────────────────────────────────────────────────────────
# 阈值 —— ★ 出处写明,不是拍的
# ────────────────────────────────────────────────────────────────────────

#: 某一个取值的占比超过这个数 → 这条判据几乎不产生区分。
#  出处:自检盘点-1029 §三·甲,策略组原话「若某一个值占比 > 95% → 报警」。
DOMINANT_SHARE = 0.95

#: 算不出来(NaN / 样本不足)的占比超过这个数 → 这个指标大部分时间是空的。
#  出处:同上,「若 NaN 占比 > 50% → 报警」。
NAN_SHARE = 0.50

#: 两个 Z 互为相反数的容差。严格镜像是**数学恒等**,所以容差只留浮点误差的量级。
MIRROR_TOL = 1e-6

#: 「算不出来」这一类桶的名字 —— ★ 必须按**本代码库实际在用的键名**写。
#  教训来自 user_facing_ban:第一版清单全英文,在我们自己的中文产物上拦不住东西。
_NAN_BUCKETS = {
    "nan", "na", "none", "null", "unknown",
    "insufficient_sample", "insufficient", "not_enough_sample",
    "算不出", "算不出来", "无法判断", "判不了", "样本不足", "缺数据",
}

#: 桶占比字典的键名长相(用于自动扫 results json)。
_SHARE_KEYS = ("state_share", "share", "占比分布", "取值占比")
_NAN_SHARE_KEYS = ("nan_share", "NaN占比", "算不出占比")


def _is_nan_bucket(name: Any) -> bool:
    return str(name).strip().lower() in _NAN_BUCKETS


# ────────────────────────────────────────────────────────────────────────
# ① 占比分布 → 问题清单
# ────────────────────────────────────────────────────────────────────────

def check_shares(name: str, shares: dict[Any, float],
                 *, nan_share: float | None = None) -> list[str]:
    """
    输入一个「取值 → 占比(或笔数)」的字典。占比不必已归一,内部会按总和归一。

    返回问题清单(空 = 通过)。
    """
    problems: list[str] = []
    vals = {k: float(v) for k, v in shares.items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)}
    total = sum(vals.values())
    if total <= 0:
        return [f"[{name}] ★ 占比分布总和 = {total} —— 这条判据没有任何输出,"
                f"无法判断它在干什么(★ 不许当成「通过」)"]

    norm = {k: v / total for k, v in vals.items()}

    # 1a · 某一个取值独占
    top_k, top_v = max(norm.items(), key=lambda kv: kv[1])
    if top_v > DOMINANT_SHARE:
        problems.append(
            f"[{name}] ★★ FAIL 这条判据几乎不产生区分:取值 `{top_k}` 占 "
            f"{top_v:.2%}(> {DOMINANT_SHARE:.0%})—— "
            f"它 {top_v:.1%} 的时间输出同一个答案,等于没在判断。"
            f"★ 它不会报错,所以只有这道闸能拦住它。")

    # 1b · 算不出来的占比
    nan_from_buckets = sum(v for k, v in norm.items() if _is_nan_bucket(k))
    eff_nan = nan_share if nan_share is not None else nan_from_buckets
    if eff_nan is not None and eff_nan > NAN_SHARE:
        problems.append(
            f"[{name}] ★★ FAIL 这个指标大部分时间算不出来:算不出/样本不足占 "
            f"{eff_nan:.2%}(> {NAN_SHARE:.0%})—— "
            f"报告里引用它的任何结论都只建立在剩下 {1 - eff_nan:.1%} 的格子上。")

    # 1c · 从未出现的取值 = 死分支
    zero = [k for k, v in norm.items() if v == 0.0]
    if zero and len(zero) < len(norm):
        problems.append(
            f"[{name}] ★ 命中率为 0 的取值:{zero} —— "
            f"要么是死代码,要么是这档阈值永远达不到。★ 两种都要给出判定。")

    return problems


def check_series(name: str, values: Sequence[Any]) -> list[str]:
    """
    输入一条判据的**逐格输出序列**(字符串标签 / 数值 / None / nan 混杂都行)。
    """
    cnt: Counter = Counter()
    n_nan = 0
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)) or _is_nan_bucket(v):
            n_nan += 1
            cnt["__算不出__"] += 1
        else:
            cnt[v] += 1
    n = len(values)
    if n == 0:
        return [f"[{name}] ★ 序列是空的 —— 这条判据一次都没有输出过"]
    return check_shares(name, dict(cnt), nan_share=n_nan / n)


# ────────────────────────────────────────────────────────────────────────
# ② 镜像分支 / 死代码
# ────────────────────────────────────────────────────────────────────────

def check_mirror_pair(name: str, z_a: float | None, z_b: float | None,
                      *, label_a: str = "做多", label_b: str = "做空"
                      ) -> list[str]:
    """
    两个本该独立的 Z 值,如果恒为相反数 → 其中一个没有信息量,
    而「两边都显著」那一类分支 ★ 永远不可能成立(死代码)。

    这正是极性反转这一关的实情:analyze 把信号和对照同时取负,
    μ→−μ、σ 不变,所以 Z_做空 ≡ −Z_做多。
    """
    if z_a is None or z_b is None:
        return []
    if not (math.isfinite(z_a) and math.isfinite(z_b)):
        return []
    if abs(z_a + z_b) <= MIRROR_TOL * max(1.0, abs(z_a)):
        return [
            f"[{name}] ★★ FAIL 严格镜像、零信息量:{label_a} Z={z_a:+.6f}、"
            f"{label_b} Z={z_b:+.6f},两者恒为相反数 —— "
            f"「{label_b} Z 为正」不是一个独立结果,它只是「{label_a} Z 为负」"
            f"的另一种写法。★ 由此「两边都 ≥1.65」那一类分支**永远不可能成立** = "
            f"死代码;若它被算作「三套对照组」的第三套,那第三套一直是空的。"
        ]
    return []


# ────────────────────────────────────────────────────────────────────────
# ③ 扫一份 results json
# ────────────────────────────────────────────────────────────────────────

def _walk(obj: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, v
            yield from _walk(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            here = f"{path}[{i}]"
            yield here, v
            yield from _walk(v, here)


def scan_results(payload: Any, *, where: str = "<未命名>") -> list[str]:
    """
    扫一份跑批产物(已 json.load 的结构),自动找三类形状:
      · 桶占比字典(键名含 state_share / 占比 之类)
      · nan_share 这一类标量
      · 极性反转·做多 / 极性反转·做空 这一对 Z
    """
    problems: list[str] = []
    nan_at: dict[str, float] = {}
    polar: dict[str, dict[str, float]] = {}

    for path, value in _walk(payload):
        leaf = path.split(".")[-1].split("[")[0]

        if leaf in _NAN_SHARE_KEYS and isinstance(value, (int, float)):
            nan_at[path.rsplit(".", 1)[0]] = float(value)

        if isinstance(value, dict) and value and any(
                leaf == k or leaf.endswith("_" + k) for k in _SHARE_KEYS):
            if all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   for v in value.values()):
                problems += check_shares(f"{where}:{path}", value)

        # 极性反转的那一对
        if isinstance(value, dict) and "Z" in value and "极性反转" in path:
            base = path.rsplit(".", 1)[0]
            side = "做多" if "做多" in leaf else ("做空" if "做空" in leaf else None)
            if side and isinstance(value.get("Z"), (int, float)):
                polar.setdefault(base, {})[side] = float(value["Z"])

    for base, zz in sorted(polar.items()):
        if "做多" in zz and "做空" in zz:
            problems += check_mirror_pair(f"{where}:{base}",
                                          zz["做多"], zz["做空"])

    for base, v in sorted(nan_at.items()):
        if v > NAN_SHARE:
            problems.append(
                f"[{where}:{base}] ★★ FAIL nan_share = {v:.2%} "
                f"(> {NAN_SHARE:.0%})—— 这个指标大部分时间算不出来。")
    return problems


def assert_results(payload: Any, *, where: str = "<未命名>") -> None:
    problems = scan_results(payload, where=where)
    if problems:
        raise ValueError("恒定输出检测未通过(共 %d 项):\n  %s"
                         % (len(problems), "\n  ".join(problems)))


# ────────────────────────────────────────────────────────────────────────
# 四 · 自测 —— ★ 全部跑在仓库里现成的真实产物上
# ────────────────────────────────────────────────────────────────────────

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name: str) -> Any:
    with open(os.path.join(_ENGINE, name), encoding="utf-8") as fh:
        return json.load(fh)


def _selftest() -> None:
    # ── 真实产物 ①:results_1029_状态轴三版.json ──────────────────────
    #   状-3 XING 版 mixed = 0.9957、状-5 XING 版 insufficient_sample = 0.7347
    d = _load("results_1029_状态轴三版.json")

    got = check_shares("状-3.XING版.state_share", d["状-3"]["XING版"]["state_share"])
    assert any("几乎不产生区分" in g for g in got), got
    assert any("99.57%" in g for g in got), got
    print("  ① 状-3 XING版 →", got[0][:96], "…")

    got5 = check_shares("状-5.XING版.state_share", d["状-5"]["XING版"]["state_share"])
    assert any("大部分时间算不出来" in g for g in got5), got5
    assert any("73.47%" in g for g in got5), got5
    print("  ② 状-5 XING版 →", got5[0][:96], "…")

    # 全文件扫一遍:必须同时抓到上面两条(以及行业版 mixed 89.11% 不该报)
    all_got = scan_results(d, where="状态轴三版")
    assert any("状-3.XING版" in g and "几乎不产生区分" in g for g in all_got), all_got
    assert any("状-5.XING版" in g and "算不出来" in g for g in all_got), all_got
    #   ★ 不许误伤:行业版 mixed 占 89.11% < 95% → 不报
    assert not any("状-3.行业版" in g and "几乎不产生区分" in g for g in all_got), all_got
    print(f"  ③ 全文件扫出 {len(all_got)} 条,且未误伤 状-3.行业版(89.11% < 95%)")

    # ── 真实产物 ②:results_1028_流派一二.json ───────────────────────
    #   极性反转·做多 Z=+1.013179 / 做空 Z=−1.013179 —— 严格镜像
    d2 = _load("results_1028_流派一二.json")
    g2 = scan_results(d2, where="流派一二")
    mirrors = [g for g in g2 if "严格镜像" in g]
    assert mirrors, g2
    assert any("死代码" in g for g in mirrors)
    print(f"  ④ 极性反转镜像 → 抓到 {len(mirrors)} 对,例:{mirrors[0][:110]} …")

    # ── 不该拦的:三态大致均分 ───────────────────────────────────────
    assert check_shares("状-1.原著版", d["状-1"]["原著版"]["state_share"]) == []

    # ── 序列口径(给判据逐格输出用)──────────────────────────────────
    assert check_series("假判据", ["mixed"] * 996 + ["trend"] * 4), "该报没报"
    assert check_series("好判据", (["a"] * 40 + ["b"] * 35 + ["c"] * 25)) == []

    print("checks/constant_output 自测通过 —— "
          "★ 三类(恒定输出 · 大面积算不出 · 镜像死代码)都在真实产物上 FAIL 了")


if __name__ == "__main__":
    _selftest()
