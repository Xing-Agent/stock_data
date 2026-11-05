# -*- coding: utf-8 -*-
"""
把修搜索正式落进 engine（2026-11-05）

★ 拍板依据：Lin 1105 12:45「修」（《24》第 42 条）。
★★ 在此之前 engine/ 一直是零改动；★★★ 这一次是**经过拍板的正式改动**。

★★★ 为什么写成脚本而不是手改：
  · ★ 每一处改动都有**唯一性断言**（★★ 原文必须且只能出现一次，否则拒绝改）
  · ★★ 改了哪几处是**可打印、可核**的
  · ★★★ 带 `--check` 和 `--revert`：★ 随时能验证状态、随时能回退

用法：
  python3 -I probe/searchfix_1105/apply_to_engine_1105.py --check    # ★ 只看，不改
  python3 -I probe/searchfix_1105/apply_to_engine_1105.py --apply    # ★★ 落进 engine
  python3 -I probe/searchfix_1105/apply_to_engine_1105.py --revert   # ★★★ 回退

⚠ 口径（★ 一个字不许动的）：
  · **容差 ±5% 不放宽**（CONTROL_TOL = 0.05 原样）
  · **判的仍然是 50 个种子的平均笔数**（断言句 `abs(dev) > CONTROL_TOL` 原样）
  · **校准只看笔数，不看成绩**（engine 纪律 6）
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
TARGET = os.path.join(ROOT, "engine", "analyze.py")
BACKUP = os.path.join(HERE, "analyze.py.改之前备份")

# ══════════════════════════════════════════════════════════════════════════
# ★ 新的 _next_rate —— 夹住 + 几何二分
# ══════════════════════════════════════════════════════════════════════════

_NEW_NEXT_RATE = '''class SaturatedNoUpperBracket(BenchmarkPremiseBroken):
    """
    ★★★ 触发率推到上限 1.0 仍然凑不够笔数 —— **找不到上端点**。

    ★ 为什么单独一个类型：★★ 它和「笔数没对上」在报表上必须分开记
      （「算不出来」和「分数差」分开记）。
    ★★★ 这一种**不是搜索能修的** —— 二分法没有上端点就无从二分。
      ★ 真因通常是:这条链的**持有期太长**,随机组的槽位一直是满的,
        再提高触发频率也换不出更多笔数(槽位上限锁死了笔数)。
    """


def _next_rate(tries: list[dict[str, Any]], target: float, ncol: str) -> float:
    """
    ★★ 校准的下一步该把 rate 调到多少 —— ★★★ **夹住 + 几何二分**。

    ★ 【2026-11-05 改】原来是「弹性(对数-对数割线)法 + 单步夹在 [0.25, 4]」。
      ★★ 实跑查出它有两个毛病:
        ① ★★★ **把笔数为 0 的点过滤掉** —— 于是一塌到 0 就没有可用的点,
           只能 `rate × 2` 慢慢爬;
        ② ★★★ **收敛阶段也在 ×4 跳** —— 在低笔数链上一步从 48 笔跳到 63 笔,
           **跨过了 ±5% 那个窄区间**(39 笔的 ±5% 只有 ±2 笔)。

    ★ 现在的做法(Lin 1105 拍板的三条):
      ① **0 笔的点不过滤** —— ★★ 0 笔就是「笔数偏少」的一个端点;
      ② **先夹住**:下端点 n < target、上端点 n > target 都有了之后,
         ★★ 改成几何中点 `sqrt(r_lo × r_hi)`(★ 因为 rate 跨几个数量级);
      ③ **没夹住时才扩张**:单边时 ×4 / ÷4 往外**找端点** ——
         ★★★ 这是找端点,不是收敛时的步长。

    ★★★ 触发率推到上限 1.0 还凑不够笔数 → 抛 `SaturatedNoUpperBracket`
      (★ 这是「找不到上端点」,**不是**搜索不够聪明)。

    ★ 这一步只看笔数,不看成绩(纪律 6 没变)。
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
        # ★ 笔数对 rate 非单调 → 退回到离目标最近那点附近微调
        r_best, n_best = min(pts, key=lambda p: abs(p[1] - target))
        return float(min(1.0, max(1e-7,
                                  r_best * (1.15 if n_best < target else 0.87))))
    if hi and not lo:
        # ★ 全都偏多 → 往稀的方向找下端点
        return float(max(1e-9, min(r for r, _ in hi) / 4.0))
    # ★★ 全都偏少(含全 0)→ 往密的方向找上端点
    r_max = max(r for r, _ in pts)
    if r_max >= 1.0 - 1e-12:
        raise SaturatedNoUpperBracket(
            "★★★ 找不到上端点:触发率已推到上限 1.0(每天每只票都触发),"
            "对照组平均笔数仍然比真链少。\\n"
            f"    ★ 真链目标笔数 = {target:.0f} · "
            f"rate=1.0 时对照笔数 = {max(n for _, n in pts):.1f}\\n"
            "    ★★ 这**不是**搜索算法的问题 —— 二分法只能在两个端点之间找,"
            "没有上端点就无从二分。\\n"
            "    ★★★ 真因:这条链的**持有期太长**,随机组的槽位一直是满的,"
            "再提高触发频率也换不出更多笔数(槽位上限锁死了笔数)。")
    return float(min(1.0, max(1e-7, r_max * 4.0)))'''

_OLD_NEXT_RATE_HEAD = 'def _next_rate(tries: list[dict[str, Any]], target: float, ncol: str) -> float:'
_OLD_NEXT_RATE_TAIL = '''    step = float((target / n2) ** (1.0 / e))
    step = float(min(4.0, max(0.25, step)))
    return min(1.0, max(1e-7, r2 * step))'''

# ══════════════════════════════════════════════════════════════════════════
# ★ 逐处命名改动
# ══════════════════════════════════════════════════════════════════════════

EDITS: list[tuple[str, str, str]] = [
    ("① 删掉单种子校准的「碰 0 笔就停」(analyze.py:163 —— ★★★ 实跑真正炸掉的那一处)",
     "        if gap <= tol or n_ctrl == 0:\n            break",
     "        if gap <= tol:\n            break\n"
     "        # ★★★ 【1105 改】原来是 `or n_ctrl == 0: break` —— 碰 0 笔就当收敛退出。\n"
     "        #   ★ 这一处是实跑里**真正炸掉**的那个:它被 pooled_random_control\n"
     "        #     **逐种子**调用,一个种子 0 笔就停,然后 strict 断言直接抛。\n"
     "        #   ★★ Lin 1105 拍板:「碰到 0 笔**不准停**,要往触发更密的方向回退」。"),

    ("② 删掉校准段的「碰 0 笔就停」(analyze.py:563)",
     "        if abs(dv) <= cal_tol or mc <= 0:\n            break",
     "        if abs(dv) <= cal_tol:\n            break\n"
     "        # ★★★ 【1105 改】原来是 `or mc <= 0: break`。★ 同①,碰 0 笔不准停。"),

    ("③ 删掉核验段的「碰 0 笔就停」(analyze.py:587)",
     "        if abs(dev) <= CONTROL_TOL or mean_ctrl <= 0:\n            break",
     "        if abs(dev) <= CONTROL_TOL:\n            break\n"
     "        # ★★★ 【1105 改】原来是 `or mean_ctrl <= 0: break`。★ 同①。"),

    ("④ 饱和检测改成只记录、不早停",
     '                cal_tries[-1]["★早停"] = ("笔数对 rate 已经饱和(两轮变动 <1%),"\n'
     '                                          "再调也到不了容差内")\n'
     '                break',
     '                cal_tries[-1]["★饱和痕迹"] = (\n'
     '                    "笔数对 rate 两轮变动 <1% —— ★ 【1105 改】只记录,**不早停**。"\n'
     '                    "★★ 真饱和会由 _next_rate 抛 SaturatedNoUpperBracket,"\n'
     '                    "★★★ 那才是「找不到上端点」。")'),

    ("⑤ 真链 0 笔要单独报,不能混进「笔数没对上」",
     "    rate0 = random_control_rate(n_tr, n_days, n_syms)",
     "    if n_tr <= 0:\n"
     "        # ★★★ 【1105 新增】真链 0 笔 = 没有可对齐的目标。\n"
     "        #   ★ 这**不是**搜索算法的问题,也不是「笔数没对上」——\n"
     "        #   ★★ 真因在上游:这条链在这个窗口**一只票都没入选**。\n"
     "        raise BenchmarkPremiseBroken(\n"
     "            \"★★★ 真链成交笔数 = 0,基准一没有可对齐的目标,禁止往下算:\\n\"\n"
     "            \"    ★ 校准的目标是「对上真链笔数」,目标本身是 0,\\n\"\n"
     "            \"      再好的搜索也无从对齐。\\n\"\n"
     "            \"    ★★ 真因在上游:这条链在这个窗口**一只票都没入选**。\")\n"
     "    rate0 = random_control_rate(n_tr, n_days, n_syms)"),

    ("⑥ 单种子校准轮次放宽(★ 二分要几轮才收敛;★★★ 容差一个字没动)",
     "                           max_iter: int = 6, tol: float = CONTROL_TOL",
     "                           max_iter: int = 16, tol: float = CONTROL_TOL"),

    ("⑦ 两段校准轮次放宽(★ 同⑥)",
     "                           cal_iter: int = 5, cal_seeds: int = 8,\n"
     "                           verify_iter: int = 2) -> dict[str, Any]:",
     "                           cal_iter: int = 14, cal_seeds: int = 8,\n"
     "                           verify_iter: int = 6) -> dict[str, Any]:"),
]


def _read() -> str:
    with open(TARGET, encoding="utf-8") as fh:
        return fh.read()


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def _swap_next_rate(src: str) -> str:
    i = src.index(_OLD_NEXT_RATE_HEAD)
    j = src.index(_OLD_NEXT_RATE_TAIL) + len(_OLD_NEXT_RATE_TAIL)
    return src[:i] + _NEW_NEXT_RATE + src[j:]


def build(src: str) -> tuple[str, list[str]]:
    applied = []
    # ★ 先整体换掉 _next_rate(★★ 它是整函数替换,不是片段替换)
    assert src.count(_OLD_NEXT_RATE_HEAD) == 1, "★★★ _next_rate 签名不唯一,拒绝改"
    assert src.count(_OLD_NEXT_RATE_TAIL) == 1, "★★★ _next_rate 尾部不唯一,拒绝改"
    src = _swap_next_rate(src)
    applied.append("⓪ _next_rate 整函数换成「夹住 + 几何二分」"
                   "(★ 并新增 SaturatedNoUpperBracket)")
    for name, old, new in EDITS:
        cnt = src.count(old)
        if cnt != 1:
            raise AssertionError(
                f"★★★ 拒绝改:{name} —— 原文在源码里出现 {cnt} 次(必须恰好 1 次)\n"
                f"    找的是:{old!r}")
        src = src.replace(old, new, 1)
        applied.append(name)
    return src, applied


def _invariants(src: str) -> dict[str, str]:
    """★★★ 这几条是「一个字不许动」的 —— ★ 改完必须逐条过。"""
    return {
        "容差 CONTROL_TOL = 0.05": ("过" if "CONTROL_TOL = 0.05" in src
                                    else "★★★ 不过"),
        "判的还是 50 种子平均(断言句原样)": (
            "过" if "if abs(dev) > CONTROL_TOL:" in src else "★★★ 不过"),
        "★ 容差没在任何地方被放宽": (
            "过" if "CONTROL_TOL * " not in src and "tol * 2" not in src
            else "★★★ 不过"),
        "校准只看笔数不看成绩(纪律 6 的话还在)": (
            "过" if "只看笔数" in src else "★★★ 不过"),
    }


def main(argv: list[str]) -> int:
    mode = (argv[1] if len(argv) > 1 else "--check")
    cur = _read()
    patched = ("SaturatedNoUpperBracket" in cur)

    if mode == "--check":
        print(f"★ engine/analyze.py 现状:"
              f"{'**已经是改过的版本**' if patched else '原版(未改)'}")
        print(f"★ sha256 = {_sha(cur)}")
        if not patched:
            new, applied = build(cur)
            print(f"★★ 可以改,★ 一共 {len(applied)} 处:")
            for a in applied:
                print("   ·", a)
            print(f"★★ 改后 sha256 = {_sha(new)}")
            print(f"★★ 行数 {len(cur.splitlines())} → {len(new.splitlines())}")
            print("★★★ 不许动的几条(改后自检):")
            for k, v in _invariants(new).items():
                print(f"   {v}  {k}")
        return 0

    if mode == "--apply":
        if patched:
            print("★ 已经是改过的版本,不重复改。")
            return 0
        new, applied = build(cur)
        bad = {k: v for k, v in _invariants(new).items() if v != "过"}
        if bad:
            print("★★★ 自检没过,**拒绝落盘**:", bad)
            return 2
        shutil.copy2(TARGET, BACKUP)
        with open(TARGET, "w", encoding="utf-8") as fh:
            fh.write(new)
        print(f"★★★ 已落进 engine/analyze.py —— ★ {len(applied)} 处:")
        for a in applied:
            print("   ·", a)
        print(f"★ 改之前的备份:{BACKUP}")
        print(f"★★ 改前 sha256 = {_sha(cur)}\n★★ 改后 sha256 = {_sha(new)}")
        print("★★★ 不许动的几条:", _invariants(new))
        print("\n⚠ ★★★ 下一步必须做:**技术面 45 条全部重跑**,结论一条都不许变。")
        return 0

    if mode == "--revert":
        if not os.path.exists(BACKUP):
            print("★★★ 没有备份,无法回退。")
            return 2
        shutil.copy2(BACKUP, TARGET)
        print(f"★ 已从备份回退:{BACKUP} → {TARGET}")
        print(f"★★ 现在 sha256 = {_sha(_read())}")
        return 0

    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
