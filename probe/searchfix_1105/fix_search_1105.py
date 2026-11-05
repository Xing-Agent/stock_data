# -*- coding: utf-8 -*-
"""
修搜索算法 · 覆盖层（2026-11-05）
预先登记：手册/47-修搜索-预先登记-1105.md
依据：Lin 11-05 10:33《拍板 · 随机对照：先修搜索，不换考法》

★★★ engine/ 一个字节不改。
★ 做法：用 inspect 把 engine 的函数源码**原样取出来**，只做下面列出的
  几处**命名替换**，再 exec 出新函数。
★★ 这样「改了哪几处」是可打印、可核的 —— 不是手抄一遍（手抄会悄悄跑偏）。

改的三处（对应预先登记里查出的三处缺陷）：
  ① _next_rate 换成「夹住 + 几何二分」—— 不再过滤 0 笔点、不再 ×4 跳
  ② `mc <= 0` 早停删掉 —— 碰 0 笔不准停
  ③ `mean_ctrl <= 0` 早停删掉 —— 同上
  另：轮次放宽（二分要几轮才收敛），容差 ±5% 一个字不动。
"""
from __future__ import annotations

import inspect
import re
import textwrap
from typing import Any

import numpy as np

from engine import analyze


class SaturatedNoUpperBracket(analyze.BenchmarkPremiseBroken):
    """
    ★★★ 触发率推到上限 1.0 仍然凑不够笔数 —— **找不到上端点**。

    ★ 为什么要单独一个类型：★★ 它和「笔数没对上」在报表上必须分开记
      （口径⑤：「算不出来」和「分数差」分开记）。
    ★★★ 这一种**不是搜索能修的** —— 二分法没有上端点就无从二分。
    """


# ================================================================ ① 新的下一步 rate

def next_rate_bracket(tries: list[dict[str, Any]], target: float,
                      ncol: str) -> float:
    """
    ★★★ 夹住 + 几何二分（替代原来的「弹性法 + ×4 夹子」）。

    ★ 和原来的三个区别：
      ① **0 笔的点不过滤** —— 原来 `engine/analyze.py:93` 把 n==0 的点扔掉，
         于是一塌到 0 就没有可用点。★★ 现在 0 笔就是「笔数偏少」的一个端点。
      ② **先夹住再收敛** —— 下端点 n < target、上端点 n > target 都有了之后，
         改成 `sqrt(r_lo * r_hi)`（几何中点，因为 rate 跨几个数量级）。
      ③ **没夹住时才扩张** —— 单边时 ×4 / ÷4 往外找端点，★ 这是**找端点**，
         不是「收敛时的步长」—— 原来的毛病是**收敛阶段也在 ×4**。

    ★ 只看笔数，不看成绩（engine 纪律 6 一个字没改）。
    """
    pts = [(float(t["rate"]), float(t[ncol])) for t in tries
           if float(t["rate"]) > 0]
    if not pts:
        return 1e-4
    lo = [(r, n) for r, n in pts if n < target]      # ★ 含 n == 0
    hi = [(r, n) for r, n in pts if n > target]
    if lo and hi:
        # ★★★ 夹住了 → 几何二分
        r_lo = max(r for r, _ in lo)
        r_hi = min(r for r, _ in hi)
        if r_hi > r_lo:
            return float(np.sqrt(r_lo * r_hi))
        # ★ 不单调（笔数对 rate 非单调）→ 退回到离目标最近那点附近微调
        r_best, n_best = min(pts, key=lambda p: abs(p[1] - target))
        return float(min(1.0, max(1e-7, r_best * (1.15 if n_best < target else 0.87))))
    if hi and not lo:
        # ★ 全都偏多 → 往稀的方向找下端点
        return float(max(1e-9, min(r for r, _ in hi) / 4.0))
    # ★★ 全都偏少（含全 0）→ 往密的方向找上端点
    r_max = max(r for r, _ in pts)
    if r_max >= 1.0 - 1e-12:
        # ★★★ rate 已经钉在上限 1.0（= 每天每只票都触发），笔数还不够 ——
        #   ★ 这是**找不到上端点**，不是搜索不够聪明。★★ 和「碰到 0 笔」是两回事：
        #     0 笔是「还没开始找」，这个是「找遍了」。★ 所以这一种要停，并单独报。
        raise SaturatedNoUpperBracket(
            "★★★ 找不到上端点:触发率已推到上限 1.0(每天每只票都触发),"
            "对照组平均笔数仍然比真链少。\n"
            f"    ★ 真链目标笔数 = {target:.0f} · "
            f"rate=1.0 时对照笔数 = {max(n for _, n in pts):.1f}\n"
            "    ★★ 这**不是**搜索算法的问题 —— 二分法只能在两个端点之间找,"
            "没有上端点就无从二分。\n"
            "    ★★★ 真因:这条链的**持有期太长**,随机组的槽位一直是满的,"
            "再提高触发频率也换不出更多笔数(槽位上限锁死了笔数)。")
    return float(min(1.0, max(1e-7, r_max * 4.0)))


# ================================================================ ②③ 删掉两处 0 笔早停

_EDITS: list[tuple[str, str, str]] = [
    # (名字, 原文, 换成)
    ("②删掉校准段的 0 笔早停",
     "if abs(dv) <= cal_tol or mc <= 0:\n            break",
     "if abs(dv) <= cal_tol:\n            break\n"
     "        # ★★★ 原来这里是 `or mc <= 0: break` —— 碰 0 笔就当收敛退出。\n"
     "        #   Lin 11-05:「碰到 0 笔**不准停**,要往触发更密的方向回退」→ 删掉。"),
    ("③删掉核验段的 0 笔早停",
     "if abs(dev) <= CONTROL_TOL or mean_ctrl <= 0:\n            break",
     "if abs(dev) <= CONTROL_TOL:\n            break\n"
     "        # ★★★ 同上:原来 `or mean_ctrl <= 0` 会在 0 笔处停住。"),
    ("①校准段换搜索",
     'rate = _next_rate(cal_tries, n_tr, "对照平均笔数")',
     'rate = _NEXT("cal", cal_tries, n_tr, "对照平均笔数")'),
    ("①核验段换搜索",
     'rate = _next_rate(verify, n_tr, "对照平均笔数")',
     'rate = _NEXT("verify", verify, n_tr, "对照平均笔数")'),
    ("★饱和检测改成只记录,不早停",
     'cal_tries[-1]["★早停"] = ("笔数对 rate 已经饱和(两轮变动 <1%),"\n'
     '                                          "再调也到不了容差内")\n'
     '                break',
     'cal_tries[-1]["★饱和痕迹"] = ("笔数对 rate 两轮变动 <1%"\n'
     '                                              " —— ★ 只记录,不早停(修搜索轮)")'),
    ("★真链 0 笔要单独报,不能混进「笔数没对上」",
     'rate0 = random_control_rate(n_tr, n_days, n_syms)',
     'if n_tr <= 0:\n'
     '        raise BenchmarkPremiseBroken(\n'
     '            "★★★ 真链成交笔数 = 0,基准一没有可对齐的目标,禁止往下算:\\n"\n'
     '            "    ★ 这**不是**搜索算法的问题 —— 校准的目标是「对上真链笔数」,\\n"\n'
     '            "      目标本身是 0,再好的搜索也无从对齐。\\n"\n'
     '            "    ★★ 真因在上游:这条链在这个窗口**一只票都没入选**。")\n'
     '    rate0 = random_control_rate(n_tr, n_days, n_syms)'),
]


# ================================================================ ④ 第二条校准路径
# ★★★ 1105 10:55 跑第一条臂时查出来的:**「碰到 0 笔就停」不止一处。**
#   · analyze.py:163  `if gap <= tol or n_ctrl == 0: break`   ← ★★★ 真正触发的是这一个
#   · analyze.py:563  `or mc <= 0`
#   · analyze.py:587  `or mean_ctrl <= 0`
# ★ 163 这一处在 `calibrated_random_rate` 里,它被 `pooled_random_control`
#   (判据「三套对照组」的第①套)**逐种子**调用,strict=True → 一个种子 0 笔就炸。
# ★★ 所以只替换 random_entry_benchmark 不够 —— 这条路径要一起修。

_EDITS_CAL: list[tuple[str, str, str]] = [
    ("④删掉单种子校准的 0 笔早停",
     "if gap <= tol or n_ctrl == 0:\n            break",
     "if gap <= tol:\n            break\n"
     "        # ★★★ 原来是 `or n_ctrl == 0: break` —— ★ 这是第三处「碰 0 笔就停」,\n"
     "        #   也是 1105 实跑里**真正触发**的那一处。Lin:「碰到 0 笔不准停」→ 删掉。"),
    ("④单种子校准也换成夹住+二分",
     'rate = _next_rate(tries, target_trades, "对照成交笔数")',
     'rate = _NEXT("single", tries, target_trades, "对照成交笔数")'),
    ("④轮次放宽(二分要几轮)",
     "max_iter: int = 6, tol: float = CONTROL_TOL",
     "max_iter: int = 16, tol: float = CONTROL_TOL"),
]


def _build():
    src = textwrap.dedent(inspect.getsource(analyze.random_entry_benchmark))
    applied = []
    for name, old, new in _EDITS:
        if old not in src:
            raise AssertionError(f"★★★ 改不动:{name} —— 原文没找到,engine 变了?\n{old!r}")
        if src.count(old) != 1:
            raise AssertionError(f"★★★ {name} 在源码里出现 {src.count(old)} 次,不唯一")
        src = src.replace(old, new, 1)
        applied.append(name)
    # ★ 轮次放宽:二分要几轮才收敛(容差 ±5% 一个字不动)
    src = src.replace("cal_iter: int = 5, cal_seeds: int = 8,\n"
                      "                           verify_iter: int = 2)",
                      "cal_iter: int = 14, cal_seeds: int = 8,\n"
                      "                           verify_iter: int = 6)")
    src = src.replace("def random_entry_benchmark(", "def random_entry_benchmark_fixed(")
    return src, applied


def _build_cal():
    src = textwrap.dedent(inspect.getsource(analyze.calibrated_random_rate))
    applied = []
    for name, old, new in _EDITS_CAL:
        if src.count(old) != 1:
            raise AssertionError(
                f"★★★ 改不动:{name} —— 在源码里出现 {src.count(old)} 次,不唯一\n{old!r}")
        src = src.replace(old, new, 1)
        applied.append(name)
    src = src.replace("def calibrated_random_rate(",
                      "def calibrated_random_rate_fixed(")
    return src, applied


_SRC, _APPLIED = _build()
_SRC_CAL, _APPLIED_CAL = _build_cal()

# ★ 搜索轮次日志(按阶段分开记,便于跑完核「二分有没有真的在二分」)
_TRACE: dict[str, list[dict[str, Any]]] = {"cal": [], "verify": [], "single": []}


def _NEXT(stage: str, tries, target, ncol):
    r = next_rate_bracket(tries, target, ncol)
    pts = [(float(t["rate"]), float(t[ncol])) for t in tries if float(t["rate"]) > 0]
    lo = [1 for _, n in pts if n < target]
    hi = [1 for _, n in pts if n > target]
    _TRACE[stage].append({
        "轮": len(tries), "上一个rate": pts[-1][0] if pts else None,
        "上一个笔数": pts[-1][1] if pts else None, "目标": target,
        "下一个rate": r,
        "★阶段": "二分(已夹住)" if (lo and hi) else
                  ("往密找上端点" if not hi else "往稀找下端点")})
    return r


# ★ exec 出新函数 —— 命名空间就是 engine.analyze 的,保证所有依赖一模一样
_NS = dict(vars(analyze))
_NS["_NEXT"] = _NEXT
_NS["SaturatedNoUpperBracket"] = SaturatedNoUpperBracket
exec(compile(_SRC_CAL,
             "<searchfix_1105 · engine.analyze.calibrated_random_rate 的改写版>",
             "exec"), _NS)
calibrated_random_rate_fixed = _NS["calibrated_random_rate_fixed"]
# ★★★ 让改写版的 random_entry_benchmark 也走改好的单种子校准
_NS["calibrated_random_rate"] = calibrated_random_rate_fixed
exec(compile(_SRC, "<searchfix_1105 · engine.analyze.random_entry_benchmark 的改写版>",
             "exec"), _NS)
random_entry_benchmark_fixed = _NS["random_entry_benchmark_fixed"]


def install() -> dict[str, str]:
    """
    ★★★ 运行时替换 —— ★ 这是本轮唯一的行为改动，engine/ 一个字节不改。

    ★★ 三处都要换，少换一处就白跑：
      · `random_entry_benchmark`  —— 基准一本体（50 种子平均笔数那道闸）
      · `calibrated_random_rate`  —— ★★★ **单种子校准**；它被
        `pooled_random_control`（判据「三套对照组」第①套）**逐种子**调用，
        ★ 1105 实跑里**真正炸掉的就是这一处**
      · `_next_rate`              —— ★ 兜底：engine 里任何别处再用到它，也走新搜索
    """
    analyze.random_entry_benchmark = random_entry_benchmark_fixed
    analyze.calibrated_random_rate = calibrated_random_rate_fixed
    analyze._next_rate = lambda tries, target, ncol: _NEXT(
        "single", tries, target, ncol)
    return {
        "random_entry_benchmark": "→ 改写版（夹住+二分 · 删 2 处 0 笔早停 · 真链 0 笔单独报）",
        "calibrated_random_rate": "→ 改写版（★★★ 删掉 `or n_ctrl == 0` 那处早停）",
        "_next_rate": "→ next_rate_bracket（不过滤 0 笔点 · 不再 ×4 收敛）",
    }


def reset_trace():
    _TRACE["cal"].clear()
    _TRACE["verify"].clear()


def get_trace() -> dict[str, list[dict[str, Any]]]:
    return {k: list(v) for k, v in _TRACE.items()}


def 改了哪几处() -> list[str]:
    return list(_APPLIED)


def 源码自证() -> dict[str, Any]:
    """★ 跑完要连这个一起归档 —— 证明改的只有列出来那几处。"""
    import hashlib
    orig = textwrap.dedent(inspect.getsource(analyze.random_entry_benchmark))
    return {
        "engine 原函数 sha256": hashlib.sha256(orig.encode()).hexdigest(),
        "改写版 sha256": hashlib.sha256(_SRC.encode()).hexdigest(),
        "改了哪几处": list(_APPLIED),
        "原函数行数": len(orig.splitlines()),
        "改写版行数": len(_SRC.splitlines()),
        "★第二条路径(calibrated_random_rate)改了哪几处": list(_APPLIED_CAL),
        "★第二条路径 engine 原函数 sha256": hashlib.sha256(
            textwrap.dedent(
                inspect.getsource(analyze.calibrated_random_rate)).encode()
        ).hexdigest() if analyze.calibrated_random_rate is not
        calibrated_random_rate_fixed else "(已被替换,见下一行)",
        "★第二条路径改写版 sha256": hashlib.sha256(_SRC_CAL.encode()).hexdigest(),
        "★容差有没有动": ("没有 —— CONTROL_TOL = %r,源码里 CONTROL_TOL 出现 %d 次,"
                          "和原函数一样 %d 次"
                          % (analyze.CONTROL_TOL, _SRC.count("CONTROL_TOL"),
                             orig.count("CONTROL_TOL"))),
        "★判的还是不是 50 种子平均": (
            "是 —— 断言句 `abs(dev) > CONTROL_TOL` 原样保留:%s"
            % ("abs(dev) > CONTROL_TOL" in _SRC)),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(源码自证(), ensure_ascii=False, indent=2))
