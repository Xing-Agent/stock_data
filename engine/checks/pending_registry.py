"""
★★ 五 ·「报告里写了、代码里没写」登记项检查。

三秒版:★★「报告读完就放下,代码不会。」
        所以报告里每一条「待裁决 / 待修 / 待确认」都必须在代码里有一个
        grep 得到的对应物;grep 不到,它就只是一句话。

为什么要有这个文件(2026-10-29 真实案例):
    残余 17 根假跳变的裁决只写进了报告的「待裁决」一节、没写进代码 ——
    于是那一类长期只认领了少数几只票,其余无人管。
  ★★ 同时留痕一条**我自己的错误诊断**:我当时说「CUT_SERIES 被清空」,
    ★ 这是错的 —— 它一直在(现在 10 条)。真实的问题是另一件:
    报告「待裁决」一节里的条目没有全部写进代码,而我把两件事混成了一件。
  ★ 所以这道闸查的不是「清单空不空」,是「报告里的每一条有没有对应物」。

两档输出(★ 刻意不同档):
  · 状态 = 已落地,而 code_anchor grep 不到      → ★★ FAIL(登记簿自己在骗人)
  · 状态 = 待修,  而 code_anchor grep 不到      → ★ 警告清单(这是常态,但不许消失)
  · 代码里出现了 TODO/待裁决 而登记簿里没有这条   → ★ 警告清单(漏登记)

★ 本文件只读,不改任何跑批逻辑。
"""

from __future__ import annotations

import glob
import os
import re

try:
    import yaml
except ImportError:                                    # pragma: no cover
    yaml = None

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ENGINE)
REGISTRY = os.path.join(_HERE, "pending_registry.yaml")

#: 报告里出现这些词 → 必须登记。★ 按本代码库实际在用的词写。
PENDING_WORDS = ("待裁决", "待修", "待确认", "待核实", "待校准",
                 "待拍板", "待补", "待办", "要回去问")

LANDED = "已落地"
OPEN_STATES = ("待修", "待裁决", "待确认", "待核实", "待校准", "待补")


def load_registry(path: str = REGISTRY) -> list[dict]:
    if yaml is None:                                   # pragma: no cover
        raise RuntimeError("环境里没有 pyyaml")
    with open(path, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    return list(doc.get("items") or [])


# ────────────────────────────────────────────────────────────────────────
# 一 · code_anchor 在不在
# ────────────────────────────────────────────────────────────────────────

def _anchor_found(anchor: str) -> tuple[bool, str]:
    """
    anchor 形如 "engine/split_gate.py:CUT_EVENTS" 或裸符号。
    返回 (找到没有, 说明)。
    """
    if ":" in anchor:
        where, symbol = anchor.rsplit(":", 1)
    else:
        where, symbol = "engine", anchor
    target = os.path.join(_REPO, where)
    if os.path.isfile(target):
        files = [target]
    elif os.path.isdir(target):
        files = sorted(glob.glob(os.path.join(target, "**", "*.py"),
                                 recursive=True)) + \
            sorted(glob.glob(os.path.join(target, "**", "*.yaml"),
                             recursive=True))
    else:
        return False, f"路径 `{where}` 不存在"
    pat = re.compile(r"\b" + re.escape(symbol) + r"\b")
    for f in files:
        try:
            with open(f, encoding="utf-8") as fh:
                if pat.search(fh.read()):
                    return True, os.path.relpath(f, _REPO)
        except (OSError, UnicodeDecodeError):
            continue
    return False, f"在 `{where}` 下 grep 不到符号 `{symbol}`"


# ────────────────────────────────────────────────────────────────────────
# 二 · 检查
# ────────────────────────────────────────────────────────────────────────

def check(path: str = REGISTRY) -> tuple[list[str], list[str]]:
    """返回 (FAIL 清单, 警告清单)。"""
    fails: list[str] = []
    warns: list[str] = []
    items = load_registry(path)
    if not items:
        return (["★★ FAIL 登记簿是空的 —— "
                 "报告里一定有「待裁决」的条目,空登记簿只说明没人登记"], [])

    for it in items:
        name = str(it.get("条目", "<无名>"))
        state = str(it.get("状态", "")).strip()
        anchor = str(it.get("code_anchor", "")).strip()
        report = str(it.get("报告", "")).strip()

        if not report:
            fails.append(f"★★ FAIL 登记项「{name}」没写出自哪份报告 —— "
                         f"没有出处的登记项没法回头核。")
        if not anchor:
            fails.append(f"★★ FAIL 登记项「{name}」没写 code_anchor —— "
                         f"那这一条还是只活在报告里。")
            continue

        found, why = _anchor_found(anchor)
        if state == LANDED and not found:
            fails.append(
                f"★★ FAIL 登记簿自己在骗人:「{name}」标的是「{LANDED}」,"
                f"而 {why}。★ 标了已落地却 grep 不到对应物,"
                f"比不登记更危险 —— 它会让人以为这件事有人管。")
        elif state in OPEN_STATES and not found:
            warns.append(
                f"★ 待修清单:「{name}」—— {why}。"
                f"出处:{report}。★ 报告写了、代码里还没有对应物。")
        elif state in OPEN_STATES and found:
            warns.append(
                f"★ 已有占位但状态仍是「{state}」:「{name}」(见 {why})—— "
                f"★ 要么把状态改成已落地,要么说明还差什么。")
        elif state == "待拍板":
            warns.append(f"★ 待拍板:「{name}」(代码里已登记并每次打印,见 {why})")
        elif state not in (LANDED, "待拍板") + tuple(OPEN_STATES):
            fails.append(f"★★ FAIL 登记项「{name}」的状态 `{state}` 不认识 —— "
                         f"允许的是 {LANDED} / 待拍板 / {'/'.join(OPEN_STATES)}。")
    return fails, warns


def check_sources_registered(paths: list[str], path: str = REGISTRY
                             ) -> list[str]:
    """
    反向查:给一批报告 / 配置,把里面出现「待裁决」这类词、
    而登记簿里找不到相近条目的,列成漏登记清单。
    """
    items = load_registry(path)
    blob = " ".join(str(it.get("条目", "")) + str(it.get("备注", ""))
                    + str(it.get("报告", "")) + str(it.get("code_anchor", ""))
                    for it in items)
    out: list[str] = []
    for p in paths:
        try:
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        hits = [w for w in PENDING_WORDS if w in text]
        if not hits:
            continue
        base = os.path.basename(p)
        stem = re.sub(r"[-_.](yaml|md|py)$", "", base)
        stem = re.split(r"[-_.]", stem)[0]
        if stem and stem in blob:
            continue
        out.append(f"★ 漏登记?{base} 里出现了 {hits} —— "
                   f"★ 登记簿里找不到和 `{stem}` 相近的条目。"
                   f"★ 请确认这些「待…」是否都已登记。")
    return out


def report(path: str = REGISTRY) -> str:
    fails, warns = check(path)
    lines = ["★★ 待办登记簿体检:"]
    lines += [f"  {x}" for x in fails] or ["  ✅ 没有「标了已落地却找不到对应物」的"]
    lines.append(f"  ★ 警告清单({len(warns)} 条):")
    lines += [f"      {x}" for x in warns]
    return "\n".join(lines)


# ────────────────────────────────────────────────────────────────────────
# 三 · 自测 —— ★ 跑在仓库里现成的真实登记簿 / 真实配置上
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    fails, warns = check()
    # ★ 登记簿里标「已落地」的那几条,anchor 必须真的 grep 得到
    assert not fails, "★ 登记簿里有标了已落地却 grep 不到的:\n  " + "\n  ".join(fails)
    assert warns, "★ 警告清单是空的 —— 那这道闸是摆设"
    print(f"  ① 真实登记簿 {len(load_registry())} 条:"
          f"「已落地」的全部 grep 到了对应物;"
          f"★ 警告清单 {len(warns)} 条 —— 这就是「报告写了、代码里没写」的那一批")
    for w in warns[:4]:
        print("     ·", w[:112], "…")

    # ★ 证明它真的会 FAIL:把一条已落地的 anchor 改成不存在的符号
    import copy
    items = copy.deepcopy(load_registry())
    victim = next(i for i in items if i["状态"] == LANDED)
    victim["code_anchor"] = "engine/split_gate.py:CUT_SERIES"   # ★ 真实的误称
    tmp = os.path.join(_HERE, "__pending_probe.yaml")
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump({"items": items}, fh, allow_unicode=True)
    try:
        f2, _ = check(tmp)
        assert any("登记簿自己在骗人" in x for x in f2), f2
        print(f"  ② 把一条「已落地」的 anchor 换成当时误称的 `CUT_SERIES` → "
              f"立刻 FAIL:{f2[0][:118]} …")
    finally:
        os.remove(tmp)

    # ★ 真实配置的反向查:engine/configs/ 里出现「待核实 / 要回去问」的文件
    cfgs = sorted(glob.glob(os.path.join(_ENGINE, "configs", "*.yaml")))
    miss = check_sources_registered(cfgs)
    n_has = sum(1 for p in cfgs
                if any(w in open(p, encoding="utf-8").read()
                       for w in PENDING_WORDS))
    print(f"  ③ engine/configs/ 真实配置:{n_has} 份里写着「待…/要回去问」,"
          f"其中 {len(miss)} 份在登记簿里找不到相近条目 → 进漏登记清单")
    for m in miss[:4]:
        print("     ·", m[:104], "…")
    assert miss, "★ 反向查一条都没查出来 —— 不可能,真实配置里到处是「待核实」"

    print("checks/pending_registry 自测通过 —— "
          "★ 已落地的 anchor 全部真实存在;待修的进警告清单;"
          "把 anchor 换成当时的误称 `CUT_SERIES` 立刻 FAIL")


if __name__ == "__main__":
    print(report())
    print()
    _selftest()
