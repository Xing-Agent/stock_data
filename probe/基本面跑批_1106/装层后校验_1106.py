# -*- coding: utf-8 -*-
"""
★★★ 先装两层覆盖层，再调秒级校验器 —— ★ 否则校验器在自己的进程里看不到新零件。

★★ 两层:
  ① `接新财报库_1106`  —— 把引擎接到 fundamentals_ext/(4,005 家,覆盖 100%)
  ② `基本面零件_1106`  —— 补 9 个派生指标 + 8 个选股规则
★★★ engine 一个字节都没动(两层都是进程内替换函数指针)。

★ 用法:python3 probe/基本面跑批_1106/装层后校验_1106.py <配置.yaml> [更多...]
"""
import os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "补齐能力_1106"))
sys.path.insert(0, os.path.join(ROOT, "probe", "新策略_1106"))

import 接新财报库_1106 as EXT          # noqa: E402
import 基本面零件_1106 as PARTS        # noqa: E402

_e = EXT.install()
_p = PARTS.install()
print(f"★ 覆盖层: 财报库 {_e.get('★家数')} 家 · "
      f"新指标 {len(_p.get('★新指标') or [])} 个 · "
      f"新规则 {len(_p.get('★★新规则') or [])} 个 · engine 改动 零")

import 校验配置_1106 as V               # noqa: E402

if __name__ == "__main__":
    sys.argv = [sys.argv[0]] + sys.argv[1:]
    raise SystemExit(V.main(sys.argv[1:]))
