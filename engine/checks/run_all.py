"""
把 engine/checks/ 下所有检查的自测**串行**跑一遍。

三秒版:一条命令,证明这些闸在我们自己的真实产物上真的会 FAIL。

跑法:python3 engine/checks/run_all.py
★ 串行,不并行 —— 另一个 agent 在同一台机器上跑回测(2 核 / 7GB)。
★ 全部只读:不改配置、不改跑批逻辑、不动暂存区。
"""

from __future__ import annotations

import importlib.util
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))

#: 顺序 = 策略组拍的落地顺序(自检盘点-1029 §五)。
ORDER = [
    ("user_facing_ban", "用户面禁止字段闸(已有)"),
    ("constant_output", "① 恒定输出检测(一条抓三类)"),
    ("concentration_degenerate", "② 集中度退化检测"),
    ("time_scale_unit", "③ 时间尺度口径声明"),
    ("threshold_vs_distribution", "④ 阈值 vs 分布体检"),
    ("pending_registry", "⑤「报告里写了、代码里没写」登记项"),
    ("verdict_inputs", "⑥ 判据不许混线"),
    ("anchor_health", "⑦ 上 · 锚点自身体检"),
    ("staged_scope", "⑦ 下 · 提交前暂存区检查"),
    # ★ 第八条:2026-10-29 晚朴素基准那件事逼出来的。
    #   「残余跳变清单(单根 bar)」挡不住「已知数据断裂清单(整只票)」——
    #   实测剔掉 0.0016%,而污染是 8.05%,差 4,898 倍。
    ("jump_removal_coverage", "⑧ 「已剔除假跳变」到底剔了多少"),
    # ★★ 1030 第九~十二条:加仓槽位那一批(策略组已拍板)。
    #   ⑨ 配置原来只有 7 个槽位、**没有加仓** —— 所以 67 条策略一条都不可能有加仓。
    #     加上这一格,并把「向下摊平」做进 schema:禁令挂在结构上,
    #     ★ 不挂在欧奈尔(技-4)名下 —— 挂人名下,用户换条策略就以为不适用。
    ("addon_schema", "⑨ 加仓槽位 schema(只许顺势;均值回归类不给)"),
    #   ⑩ R 的分母锁死首仓初始风险。★ 第二条理由是纯数学:止损抬到保本
    #     → 名义风险 0 → 分母除以 0 → 公式崩溃。
    ("r_denominator_lock", "⑩ R 的分母锁死首仓初始风险"),
    #   ⑪ 四槽位齐全闸。★ 这道闸自己的坑是「两套槽位命名」——
    #     stop_init/stop_trail(七个大师配置)vs initial_stop/trailing_stop(技-*),
    #     第一版只认后者,误报 6 个大师配置「缺止损」。自测专门在两套命名上各跑一遍。
    ("four_slot_complete", "⑪ 四槽位齐全(进场/加仓/离场/止损)"),
    #   ⑫ 静默截断。★ 另一种幸存者偏差:票还在池子里,但最惨的那段历史被切了
    #     (SQBG 的 −97.8% 那一段就在被切掉的里面)。
    ("silent_truncation", "⑫ 静默截断(引擎序列 vs 原始 daily.json)"),
]


def _load(mod: str):
    path = os.path.join(_HERE, mod + ".py")
    spec = importlib.util.spec_from_file_location("checks_" + mod, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                 # type: ignore
    return m


def main() -> int:
    bad = []
    for mod, title in ORDER:
        print("=" * 72)
        print(f"★ {title}   [{mod}.py]")
        print("=" * 72)
        try:
            _load(mod)._selftest()
        except Exception:                                      # noqa: BLE001
            traceback.print_exc()
            bad.append(mod)
        print()
    print("=" * 72)
    if bad:
        print(f"★★ 有 {len(bad)} 个检查的自测没过:{bad}")
        return 1
    print(f"✅ {len(ORDER)} 个检查的自测全部通过 —— "
          f"★ 全部跑在仓库里现成的真实报告 / 流水 / 配置上")
    return 0


if __name__ == "__main__":
    sys.exit(main())
