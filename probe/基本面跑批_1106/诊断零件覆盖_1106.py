# -*- coding: utf-8 -*-
"""
★ 诊断:每个零件在研发池里「算得出」的比例 + 每道条件单独放行的比例。
★★ 为什么要它:基-1 合格票日 = 0、基-16 只有 2 笔 —— ★ 先查是哪一道条件把人全卡掉,
   再决定是数据缺、还是我写错了(★★★ 规矩⑥:先当自己错了)。
★ 只抽 400 只(sha256 排序)以省内存;看 4 个年末断面。
"""
import hashlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 跑基本面_1106 as R                                   # noqa: E402

RC, 层 = R.装层()
import pandas as pd                                          # noqa: E402
from engine import fundamentals as F, cache, matrices as M   # noqa: E402
hold = json.load(open(R.HOLD, encoding="utf-8"))
dev = sorted(hold["研发池名单"], key=lambda s: hashlib.sha256(s.encode()).hexdigest())[:400]
close = cache.field("close", dev)
days = [d for d in ("2016-12-30", "2018-12-31", "2020-12-31", "2023-12-29") if pd.Timestamp(d) in close.index]
names = sys.argv[1:] or ["rev_ttm", "current_ratio", "ltd_over_nwc", "ni_pos_years", "div_years",
                         "eps3_avg_ps", "eps3_avg_ps_lag16", "roce", "fcf_conv", "liab_to_eq",
                         "fcf_ttm", "div_ttm_ps", "bvps", "eps_ttm_ps"]
out = {}
for n in names:
    p = F.get(n, dev).reindex(index=close.index, columns=dev)
    alive = close.loc[days].notna()
    out[n] = {d: {"算得出%": round(float((p.loc[d].notna() & alive.loc[d]).sum() / max(1, alive.loc[d].sum()) * 100), 1),
                  "中位": (round(float(p.loc[d].median()), 3) if p.loc[d].notna().any() else None)}
              for d in days}
print(json.dumps(out, ensure_ascii=False, indent=1))
