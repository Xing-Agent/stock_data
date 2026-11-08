# -*- coding: utf-8 -*-
"""★★★ R1 独立复核 —— 只做运行时证据，不跑回测、不改任何生产文件。
★ 三层错一层一层证：① 少传参数 ② SplitEvent 不能下标 ③ 方向是除不是乘。
"""
import json, inspect
from engine import split_gate

out = {}
sig = str(inspect.signature(split_gate.ratio_events_from_rows))
out["①签名"] = sig

rows = [
    {"date": "2020-08-31", "close": "129.04", "split_coefficient": "4.0", "dividend_amount": "0.0"},
    {"date": "2020-05-08", "close": "310.13", "split_coefficient": "1.0", "dividend_amount": "0.82"},
]

# ① 少传一个参数
try:
    split_gate.ratio_events_from_rows(rows)
    out["①一个参数"] = "★ 竟然成功了（和审计不符）"
except TypeError as e:
    out["①一个参数"] = f"TypeError: {e}"

# 两个参数（正确调法）
evs = split_gate.ratio_events_from_rows("AAPL", rows)
out["①两个参数"] = [f"date={e.date} ratio={e.ratio} coef={e.coefficient}" for e in evs]

# ② 覆盖层写的 ev[0], ev[1] 能不能用
try:
    _ = evs[0][0]
    out["②能下标吗"] = "★ 能（和判断不符）"
except TypeError as e:
    out["②能下标吗"] = f"TypeError: {e}  → ★★★ 就算把参数补上，这一行还是会抛"

# ③ 方向：engine 是乘，覆盖层是除
out["③engine的方向"] = "s.loc[除息日之前] = s.loc[...] * ev.ratio   （engine/data.py:280）"
out["③覆盖层的方向"] = "s.loc[s.index < 日] /= 比                   （分红覆盖层_1107.py:118）"
r = evs[0].ratio
out["③差多少倍"] = f"ratio={r} → 乘得 {0.82*r:.4f}，除得 {0.82/r:.4f}，★ 相差 {(1/r)/r:.0f} 倍"

print(json.dumps(out, ensure_ascii=False, indent=2))
json.dump(out, open("probe/审计复核_1108/R1运行时证据_1108.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
