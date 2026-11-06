# -*- coding: utf-8 -*-
"""★ 秒级校验器的包装:先装 pat6 + 技789 覆盖层,再调 probe/新策略_1106/校验配置_1106.py 的 main(不改那份)。"""
import os, sys, importlib.util
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "技789_1106"))
from engine import pat6_ops
pat6_ops.install()
import 技789覆盖层_1106 as O
O.install()
spec = importlib.util.spec_from_file_location("v", os.path.join(ROOT, "probe/新策略_1106/校验配置_1106.py"))
v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
raise SystemExit(v.main(sys.argv[1:]))
