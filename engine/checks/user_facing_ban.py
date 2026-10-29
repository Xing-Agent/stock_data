"""
★ 用户面禁止项检查 —— 把「不许给用户看什么」从文档变成一道能跑的闸。

为什么要有这个文件(2026-10-29):
    今天最值得记的一条教训是 ——「★ 报告读完就放下,代码不会。」
    实例:残余 17 根假跳变的裁决只写进了报告的「待裁决」一节、没写进代码,
    于是那一类从来只认领了 3 只票,其余无人管。
    所以凡是「以后必须一直守住」的约定,都要落成一个会 FAIL 的检查,
    不能只写在文档里。

本文件守的是「数据契约 · 禁止字段清单」(手册附录 D.6)在用户面的延伸。
原清单的理由一句话:schema 会召唤数据 —— 字段存在,模型就会把它填满,
不管有没有依据。所以宁可少一个字段,也不要留一个会被填满的空槽。

★ 本文件【只约束用户面】。内部研究产物不受限制,而且其中几项内部必须保留:
  七步归因是我们判断「哪一步在起作用」的唯一工具 ——
  今天「三条链的价值都是出场那一步毁掉的」这个最重要的发现就是靠它看出来的。
"""

from __future__ import annotations

import re
from typing import Any, Iterable


# ────────────────────────────────────────────────────────────────────────
# 一 · 禁止出现在用户面的字段名
# ────────────────────────────────────────────────────────────────────────

BANNED_FIELDS: dict[str, str] = {
    # ── 手册附录 D.6 原有 ──
    "score": "任何 0–100 的综合分:合成之后不可追溯,而权重本身是判断",
    "position_factor": "手册 11.4 明文:不给具体仓位调整建议",
    "recommended_position_percent": "同上",
    "phase": "吸筹/派发是意图归因,形态上无法区分,只能事后解释(状-4 已锁死)",
    "market_stage": "同 phase",
    "mm_style": "做市商性格:不可证伪,且无法验证",
    "actionable_plan": "见决策流程 v6「合规边界」",

    # ── 2026-10-29 策略组拍板新增:七步归因不进用户面 ──
    "step_attribution": (
        "七步归因不进用户面。两个理由:"
        "① ★ 牛市里『止损』和『闸门』算出来的边际贡献几乎一定是负的,"
        "用户看到会想『原来加了止损反而少赚,那我不勾止损了』—— 等于在教用户把刹车拆掉;"
        "② ★ 序贯消融的结果取决于先加谁后加谁,先算选股再算止损与反之数字完全不同,"
        "即这个表在数学上没有唯一解。给用户看一个没有唯一解的表是假装精确。"
        "★ 内部必须保留 —— 它是我们判断哪一步在起作用的唯一工具。"
    ),
    "per_step_contribution": "同 step_attribution",
    "ablation": "同 step_attribution",

    # ── 2026-10-29 同批:统计检验量不进用户面 ──
    "z_score": (
        "★ 统计检验量不进用户面:没有零假设训练的读者会把 p=0.02 读成"
        "『我有 98% 的把握赚钱』,把『能不能拒绝运气假设』的学术度量"
        "变成过度自信的官方背书。★ 内部必须保留。"
    ),
    "p_value": "同 z_score",
    "empirical_p": "同 z_score",
    "sharpe": (
        "夏普比率惩罚向上波动:频繁小亏试错、偶尔抓一次暴涨的策略夏普往往很低,"
        "而微利就跑、遇大跌死扛的策略夏普往往很高 —— 摆在前面会让人精准挑中"
        "在悬崖边捡硬币的那一类。"
    ),
    "win_rate": (
        "裸单笔胜率会建立『这套系统极少出错』的错觉:遇到正常的连续三次止损"
        "用户就会认为策略坏了而手动推翻纪律,或靠死扛不卖人为维持高胜率。"
        "★ 要给用户的是『最长被套天数』『最长连续止损笔数』这类能代入生活耐受力的数。"
    ),
}

# ★★ 中文键名别名 —— 这一段是自测逼出来的,不是一开始想到的。
#   第一版清单全是英文,而我们整个代码库和报告用的是中文键名
#   (报告里七步归因那一节的键就叫「分步归因」)——
#   ★ 也就是说第一版这道闸在我们自己的产物上几乎拦不住任何东西。
#   ★ 教训:禁止清单必须按【本代码库实际在用的键名】写,不是按术语的英文写。
_ZH_ALIASES: dict[str, str] = {
    "分步归因": "step_attribution",
    "逐步归因": "step_attribution",
    "七步归因": "step_attribution",
    "每步贡献": "per_step_contribution",
    "各步贡献": "per_step_contribution",
    "综合分": "score",
    "综合评分": "score",
    "得分": "score",
    "评分": "score",
    "审校分": "score",
    "健康度": "score",
    "置信度": "score",
    "仓位建议": "position_factor",
    "建议仓位": "position_factor",
    "吸筹": "phase",
    "派发": "phase",
    "阶段归因": "phase",
    "做市商性格": "mm_style",
    "操作计划": "actionable_plan",
    "买卖计划": "actionable_plan",
    "目标价": "actionable_plan",
    "胜率": "win_rate",
    "夏普": "sharpe",
    "夏普比率": "sharpe",
    "经验p值": "empirical_p",
    "经验P值": "empirical_p",
    "四格z": "z_score",
    "判据z": "z_score",
    "效应量z": "z_score",
}

for _zh, _en in _ZH_ALIASES.items():
    BANNED_FIELDS[_zh] = BANNED_FIELDS[_en]

# 概率常量:任何没有分母的概率数字
_BARE_PROBABILITY = re.compile(
    r"(probability|prob|likelihood|chance|odds|胜算|概率)", re.IGNORECASE
)


# ────────────────────────────────────────────────────────────────────────
# 二 · 检查
# ────────────────────────────────────────────────────────────────────────

def _walk_keys(obj: Any, path: str = "") -> Iterable[tuple[str, Any]]:
    """递归吐出 (路径, 值),用于扫嵌套 dict/list。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, v
            yield from _walk_keys(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            here = f"{path}[{i}]"
            yield from _walk_keys(v, here)


def check_user_facing(payload: Any, *, where: str = "<未命名>") -> list[str]:
    """
    扫一个【即将送到用户面】的结构,返回违规清单(空列表 = 通过)。

    用法:凡是会进 Skill 输出、研报、前端卡片的结构,送出去之前过一遍这个函数。
    ★ 内部报告不要调用它 —— 内部必须保留这些量。
    """
    problems: list[str] = []
    for path, value in _walk_keys(payload):
        leaf = path.split(".")[-1].split("[")[0].lower()

        if leaf in BANNED_FIELDS:
            problems.append(
                f"[{where}] 禁止字段 `{path}` —— {BANNED_FIELDS[leaf]}"
            )
            continue

        # 无分母的概率常量:字段名像概率,而值是个裸浮点数
        if _BARE_PROBABILITY.search(leaf) and isinstance(value, (int, float)):
            problems.append(
                f"[{where}] 疑似无分母概率常量 `{path}` = {value} —— "
                "用户没法验证,而它会直接改变他的行为。"
                "★ 若确有分母,请改成同时给出分子与分母的形状。"
            )

    return problems


def assert_user_facing(payload: Any, *, where: str = "<未命名>") -> None:
    """同上,但违规即抛异常 —— ★ 用在送出前的最后一道,不许只警告。"""
    problems = check_user_facing(payload, where=where)
    if problems:
        raise ValueError(
            "用户面禁止项检查未通过(共 %d 项):\n  %s"
            % (len(problems), "\n  ".join(problems))
        )


# ────────────────────────────────────────────────────────────────────────
# 三 · 自测
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    # 该拦的
    bad = {
        "ticker": "AAPL",
        "step_attribution": {"选股": 0.77, "出场": -0.09},
        "detail": [{"z_score": 2.1}],
        "fake_breakout_probability": 0.68,
    }
    got = check_user_facing(bad, where="selftest.bad")
    assert len(got) == 3, got          # step_attribution · z_score · 裸概率常量
    assert any("step_attribution" in g for g in got)
    assert any("z_score" in g for g in got)
    assert any("probability" in g.lower() for g in got)

    # ★★ 中文键名必须同样拦得住 —— 这一条是自测逼出来的:
    #   第一版清单全是英文,而我们报告里的键是中文(如「分步归因」),
    #   ★ 等于这道闸在我们自己的产物上几乎拦不住任何东西。
    zh_bad = {
        "代码": "AAPL",
        "分步归因": {"选股": 0.77, "出场": -0.09},
        "侧栏": {"审校分": 95},
        "明细": [{"四格z": 2.03}, {"胜率": 0.602}],
    }
    zh_got = check_user_facing(zh_bad, where="selftest.zh")
    assert len(zh_got) == 4, zh_got
    assert any("分步归因" in g for g in zh_got)
    assert any("审校分" in g for g in zh_got)   # 研报侧栏那个「审校 95 分」
    assert any("四格z" in g for g in zh_got)
    assert any("胜率" in g for g in zh_got)

    # 不该拦的:普通内容
    ok = {
        "ticker": "AAPL",
        "最长被套天数": 1839,
        "最长连续止损笔数": 9,
        "平均持仓天数": 7.0,
        "entry_reason": "突破前 5 天内出现单日地量",
    }
    assert check_user_facing(ok, where="selftest.ok") == []

    # 内部结构不该走这个函数 —— 这里只验证函数本身不误伤普通键名
    assert check_user_facing({"scores_note": "说明文字"}) == []

    print("checks/user_facing_ban 自测通过")


if __name__ == "__main__":
    _selftest()
