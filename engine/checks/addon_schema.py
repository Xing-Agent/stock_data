"""
★ 加仓槽位 schema 闸 —— 把「只许顺势加仓」从一句话变成一道会 FAIL 的检查。

三秒版:配置里只要出现逆势加仓(向下摊平),这道闸直接报错;
        均值回归类策略写了加仓槽位,也直接报错。

为什么要有这道闸(和 user_facing_ban.py 顶上那条教训同源):
    ★「报告读完就放下,代码不会。」
    「禁止向下摊平」原来挂在欧奈尔(技-4)名下 —— 挂人名下的禁令,
    用户换条策略就以为不适用。做进 schema + 一道闸,它才对所有策略生效。

规则定义在 engine/addon_slot.py;本文件只负责「拿真实配置跑一遍 + 自测」。
"""

from __future__ import annotations

import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine.addon_slot import (                                  # noqa: E402
    ADD_ON_ALIASES, AddOnSchemaError, STATE_MISSING,
    find_slot, validate_add_on,
)

_CONFIG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "configs")


def _load(path: str) -> dict:
    import yaml
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def check(config_dir: str | None = None) -> dict:
    """把 engine/configs/ 下每一份真实配置过一遍 add_on 校验。"""
    d = config_dir or _CONFIG_DIR
    paths = sorted(p for p in glob.glob(os.path.join(d, "*.yaml"))
                   if not os.path.basename(p).startswith("_TEMPLATE"))
    out: dict = {"配置数": len(paths), "违规": [], "有加仓槽位的": [],
                 "话": [], "级别": "OK"}
    for p in paths:
        name = os.path.basename(p)
        cfg = _load(p)
        key, _ = find_slot(cfg, ADD_ON_ALIASES)
        try:
            state = validate_add_on(cfg, where=name)
        except AddOnSchemaError as exc:
            out["违规"].append((name, str(exc)))
            continue
        if state != STATE_MISSING:
            out["有加仓槽位的"].append((name, key, state))

    if out["违规"]:
        out["级别"] = "FAIL"
        out["话"].append(f"★★ FAIL:{len(out['违规'])} 份配置的 add_on 槽位写错了。")
        for n, why in out["违规"]:
            out["话"].append(f"   {n}: {why.splitlines()[0]}")
    else:
        out["话"].append(
            f"✅ {len(paths)} 份真实配置全部通过 add_on 校验;"
            f"其中写了加仓槽位的 {len(out['有加仓槽位的'])} 份。")
    out["话"].append(
        "★ 实情提醒:现在 **0 份**配置有加仓 —— 这不是漏装,是原来**装不了**"
        "(7 个槽位里没有这一格)。本次只把格子和禁令做进 schema;"
        "★ 具体哪条策略该加仓、加几份,是下一步要逐条回原著定的事,不在本次范围。")
    return out


# ────────────────────────────────────────────────────────────────────────
# 自测 —— ★ 跑在仓库里现成的真实配置上,并且证明它真的会 FAIL
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    import copy

    r = check()
    for line in r["话"]:
        print("  ", line)
    assert r["级别"] == "OK", r["违规"]
    # ★ 回归断言(不含模板)。★ 2026-10-31:48 → 49,新增
    #   `trend_following-原著-唐奇安反向通道离场.yaml`(把那条署名海龟的链里
    #   三处「自称原著其实不是原著」的部件改回原著)。
    assert r["配置数"] == 49, r["配置数"]

    # ── 拿**真实配置**当底子做反向自测(不是手搓的假 dict)────────────
    trend = _load(os.path.join(_CONFIG_DIR, "技-4-原著.yaml"))     # 欧奈尔,family: trend
    meanrev = _load(os.path.join(_CONFIG_DIR, "技-12.yaml"))       # 康纳斯,family: meanrev
    assert trend["benchmark"]["family"] == "trend"
    assert meanrev["benchmark"]["family"] == "meanrev"

    def expect_fail(cfg, tag, must_contain):
        try:
            validate_add_on(cfg, where=tag)
        except AddOnSchemaError as exc:
            assert must_contain in str(exc), (tag, str(exc))
            print(f"   ★ 反向自测 FAIL(符合预期)· {tag}")
            return str(exc)
        raise AssertionError(f"{tag} 居然过了 —— 这道闸没在工作")

    # ① 逆势加仓:按**类型名**堵
    c = copy.deepcopy(trend)
    c["add_on"] = {"type": "average_down",
                   "params": {"step_pct": 5.0, "max_units": 3},
                   "source": "某论坛"}
    expect_fail(c, "技-4-原著 + average_down", "向下摊平")

    # ② ★★ 换个无害的名字也堵不过去 —— 真正的牙齿是那个**数**
    c = copy.deepcopy(trend)
    c["add_on"] = {"type": "r_step_pyramid",
                   "params": {"direction": "with_trend",
                              "min_unrealized_r": -0.5,   # ★ 负数 = 正在亏还加
                              "max_units": 4},
                   "source": "原著(编的)"}
    expect_fail(c, "技-4-原著 + min_unrealized_r = −0.5", "是**负数**")

    # ③ 显式写 direction: counter_trend
    c = copy.deepcopy(trend)
    c["add_on"] = {"type": "atr_step_pyramid",
                   "params": {"direction": "counter_trend",
                              "min_unrealized_r": 1.0, "max_units": 3},
                   "source": "原著(编的)"}
    expect_fail(c, "技-4-原著 + direction: counter_trend", "只许 with_trend")

    # ④ ★ 均值回归类写 add_on → 报错(连 type: none 都不用写)
    c = copy.deepcopy(meanrev)
    c["add_on"] = {"type": "none", "source": "原著(康纳斯明确反对加仓)"}
    expect_fail(c, "技-12(meanrev)+ add_on", "meanrev")

    # ⑤ type: none 没有 source → 不许伪装成「明确为无」
    c = copy.deepcopy(trend)
    c["add_on"] = {"type": "none"}
    expect_fail(c, "技-4-原著 + none 无 source", "没有 source")

    # ⑥ 没有 max_units 的无限金字塔
    c = copy.deepcopy(trend)
    c["add_on"] = {"type": "breakout_pyramid",
                   "params": {"direction": "with_trend", "min_unrealized_r": 1.0},
                   "source": "原著(海龟:每 1/2 N 加一份)"}
    expect_fail(c, "技-4-原著 + 无 max_units", "max_units")

    # ⑦ ★ 别名也必须认得 —— 换个写法绕不过去(今天同一类 bug 的第四次教训)
    for alias in ("addon", "pyramid", "加仓", "scale_in"):
        c = copy.deepcopy(trend)
        c[alias] = {"type": "average_down",
                    "params": {"max_units": 3}, "source": "x"}
        expect_fail(c, f"技-4-原著 + 别名 {alias}", "向下摊平")

    # ── 正向:合法的顺势加仓必须过 ──────────────────────────────────
    from engine.addon_slot import STATE_HAS_VALUE, STATE_EXPLICIT_NONE
    c = copy.deepcopy(trend)
    c["add_on"] = {
        "type": "atr_step_pyramid",
        "params": {"direction": "with_trend", "min_unrealized_r": 0.5,
                   "step_atr": 0.5, "max_units": 4},
        "source": "原著(海龟交易法则:每涨 1/2 N 加一份,最多 4 份)",
    }
    assert validate_add_on(c, where="合法顺势") == STATE_HAS_VALUE

    c = copy.deepcopy(trend)
    c["add_on"] = {"type": "none",
                   "source": "原著(技-4 欧奈尔明确反对向下摊平;顺势加仓原著也未给阈值)"}
    assert validate_add_on(c, where="明确为无") == STATE_EXPLICIT_NONE

    # 槽位缺失 = 空着(现状:48 份全是这个状态)
    assert validate_add_on(copy.deepcopy(trend), where="空着") == STATE_MISSING

    # ★★ 整库级反向自测:往**真实配置文件**的副本目录里塞一条违规,
    #    证明 check() 在整库扫描时也会 FAIL(不只是单份校验会抛)
    import shutil
    import tempfile
    import yaml
    with tempfile.TemporaryDirectory() as td:
        for p in glob.glob(os.path.join(_CONFIG_DIR, "*.yaml")):
            shutil.copy(p, td)
        bad = os.path.join(td, "技-4-原著.yaml")
        cfg = _load(bad)
        cfg["add_on"] = {"type": "average_down",
                         "params": {"step_pct": 5.0, "max_units": 3},
                         "source": "某论坛"}
        with open(bad, "w", encoding="utf-8") as fh:
            yaml.safe_dump(cfg, fh, allow_unicode=True)
        r2 = check(td)
        assert r2["级别"] == "FAIL", r2
        print(f"   ★ 整库反向自测:塞 1 条向下摊平进真实配置副本 → "
              f"{r2['级别']}({len(r2['违规'])} 条违规)→ ★ 闸在工作")

    print("checks/addon_schema 自测通过 —— "
          "★ 禁令挂在 schema 上,不挂在欧奈尔名下;"
          "★★ 名字黑名单只是第一道,真正堵死的是 min_unrealized_r 的符号。")


if __name__ == "__main__":
    _selftest()
