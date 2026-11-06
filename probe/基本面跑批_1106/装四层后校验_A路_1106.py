# -*- coding: utf-8 -*-
"""
★★★ A 路用的秒级校验器:先装**四层**覆盖层,再调同一个校验器。
★ 原来那份(装层后校验_1106.py)只装两层 —— 本路新增的排序 / 离场 / 规则它认不得。
★ 用法:python3 probe/基本面跑批_1106/装四层后校验_A路_1106.py <配置.yaml> [...]
"""
import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
for d in ("probe/补齐能力_1106", "probe/基本面跑批_1106", "probe/新策略_1106"):
    sys.path.insert(0, os.path.join(ROOT, d))
import 接新财报库_1106 as EXT, 瘦身财报库_1106 as SLIM          # noqa: E402
import 基本面零件_1106 as PARTS, 策略零件_1106 as MINE            # noqa: E402
EXT.install(); SLIM.install(); PARTS.install(); MINE.install()
import 校验配置_1106 as V                                        # noqa: E402
if __name__ == "__main__":
    raise SystemExit(V.main(sys.argv[1:]))
