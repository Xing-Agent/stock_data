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
