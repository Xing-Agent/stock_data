# -*- coding: utf-8 -*-
"""
★ 在**并池面板**上重扫「没调整的并股 / 拆股」—— ★ 判据**原样复用**主路那份(probe/假跳变_1107/扫假跳变_1107.py
  的 窗 / 跳变门槛 / 量反向容差 三个常数 + 同一套中位数判据),只换面板。不改那份文件。
★ 输出:本目录 假跳变_并池_1107.json(symbol → 疑似日列表),跑批器用它给每笔打「跨过假跳变」标记。
"""
import importlib, io, json, os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe", "假跳变_1107"))
os.chdir(ROOT)
扫 = importlib.import_module("扫假跳变_1107")
PANEL = "probe/并池_1107/ohlcv_panel_newpool.parquet"
w = pd.read_parquet(PANEL)
cl, vol = w["close"], w["volume"]
del w
窗 = 扫.窗
前 = lambda x: x.shift(1).rolling(窗, min_periods=窗).median()                      # noqa: E731
后 = lambda x: x.iloc[::-1].rolling(窗, min_periods=窗).median().iloc[::-1]         # noqa: E731
pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
      | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
脏 = {}
for i, j in zip(*np.where(疑.to_numpy())):
    脏.setdefault(str(cl.columns[j]), []).append(str(cl.index[i].date()))
out = {"★口径": f"复用 扫假跳变_1107 的判据(窗={窗}, 门槛={扫.跳变门槛}, 量反向={扫.量反向容差});面板 {PANEL}",
       "只数": len(脏), "疑似日数": sum(len(v) for v in 脏.values()), "脏日": 脏}
io.open(os.path.join(HERE, "假跳变_并池_1107.json"), "w", encoding="utf-8").write(
    json.dumps(out, ensure_ascii=False))
print(out["★口径"], "只数", out["只数"], "疑似日数", out["疑似日数"])
