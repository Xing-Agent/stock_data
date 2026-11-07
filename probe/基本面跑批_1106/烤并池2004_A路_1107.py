# -*- coding: utf-8 -*-
"""
★ 替主路那份 `probe/并池_1107/烤并池_1107.py` 跑 main —— ★★ 那份现在跑不起来:
  它断言 `自证基准["★★★SPY"]`,但 `接新基准_1107.install()` 的返回字段已改名成
  `自证基准["★★★基准自证"]["SPY"]`(★ 规矩㊼ 后半句那类错:改了返回字段名没 grep 调用方)→ KeyError。
★★ 这里**原样复用**那份的四处覆盖(目录表 / manifest / 读日线接起来 / 不排除考卷),
  只把那一句断言改成读新字段。不改那份文件。
"""
import json, os, sys, time
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
os.chdir(ROOT)
import 烤并池_1107 as P          # noqa: E402

t0 = time.time()
B = P.B
B.目录表 = P.目录表两处
B.新manifest = P.manifest两处
B.读日线 = P.读日线接起来
证 = P.BM.install()
spy = (证.get("★★★基准自证") or {}).get("SPY")
print("★ 基准自证 SPY:", spy, flush=True)
assert spy and str(spy)[:10] <= "2004-12-31", f"★★★ SPY 还没拉到 2004,停:{spy}"
B.考卷名单 = lambda: set()
B.OUT = P.OUT
os.makedirs(P.OUT, exist_ok=True)
rc = B.main()
print(f"★ 并池2004 烤盘完 用时 {time.time()-t0:.0f}s", flush=True)
raise SystemExit(rc)
