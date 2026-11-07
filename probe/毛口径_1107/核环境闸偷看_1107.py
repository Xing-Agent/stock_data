# -*- coding: utf-8 -*-
"""★★★★★ 独立复核 #70「环境闸偷看一天」—— ★ 口径⑥：让我们**难看**的结论也一样要核（#77）。

★★ 为什么要核这一处：《104-环境闸偷看一天》判定 `engine/chain.py:759` 用
  `m.regime[i+1]`（明天收盘）决定明天开盘买不买 = **偷看一整天**，
  ★ 依据是「`engine/matrices.py:1379` 入包时**没有 shift**」。
★★★ 而 `regime_mask` 这个函数**自己的最后一行**（`engine/matrices.py:666`）是：
      return ok.shift(1, fill_value=False).fillna(False).astype(bool)
  → ★★ 也就是说 shift **在函数里面**，入包那一行当然看不见它。

★★★ 本份不靠读代码下结论（规矩：两种查法各一次）—— ★ 直接数值验：
  ① 自己独立算 raw[k] = (SPY收盘[k] > 200日均[k])
  ② 调 `regime_mask` 拿 regime[k]
  ③ ★★★ 断言 regime[k] == raw[k−1] 逐点成立
  → ★ 成立 ⇒ chain 里 `m.regime[i+1] == raw[i]` = **第 i 天收盘**（已知）
    决定**第 i+1 天开盘**买不买 ⇒ **不偷看**。

★★ engine 零改动；★ 只读。
"""
from __future__ import annotations
import json, os, sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
os.chdir(ROOT)

from engine import matrices as M, data                              # noqa: E402
import 接新基准_1107 as BM                                            # noqa: E402

OUT = os.path.join(HERE, "核环境闸偷看_报告_1107.json")


def main() -> int:
    自证基准 = BM.install()
    idx = pd.bdate_range("2015-01-02", "2025-12-31")
    b = data.load_benchmark("SPY")["close"].reindex(idx).ffill()
    报告 = {"★这一份在核什么": "#70「环境闸偷看一天」—— ★ 它说入包时没有 shift",
            "★基准自证": 自证基准.get("★★★基准自证", {}).get("SPY"),
            "★代码事实": {
                "engine/matrices.py:666 (regime_mask 的 return)":
                    "return ok.shift(1, fill_value=False).fillna(False).astype(bool)",
                "engine/matrices.py:1379 (入包)":
                    "regime=regime_mask(...).to_numpy(dtype=bool)  ← ★ 这里确实没有 shift",
                "engine/chain.py:759":
                    "regime_next = bool(m.regime[i + 1])",
                "★★★ 合起来": "shift 在函数里面 → m.regime[i+1] = 第 i 天收盘算的状态",
            },
            "逐档": {}}
    全过 = True
    for n in (100, 200, 300):
        spec = {"rules": [{"type": "index_above_ma",
                           "params": {"symbol": "SPY", "ma": n}}]}
        mask = M.regime_mask(spec, idx, None, None)
        ma = b.rolling(n, min_periods=n).mean()
        raw = (b > ma).fillna(False)
        # ★★★ 判据：regime[k] 必须等于 raw[k−1]
        左 = mask.to_numpy()[1:]
        右 = raw.to_numpy()[:-1]
        等 = bool(np.array_equal(左, 右))
        # ★ 对照组：如果它等于 raw[k] 本身，那才是偷看
        同日 = bool(np.array_equal(mask.to_numpy(), raw.to_numpy()))
        报告["逐档"][f"MA{n}"] = {
            "天数": int(len(idx)),
            "开闸天占比_regime": round(float(mask.mean()), 4),
            "开闸天占比_raw": round(float(raw.mean()), 4),
            "★★★ regime[k] == raw[k−1] 吗": 等,
            "★ regime[k] == raw[k] 吗（这个为真才是偷看）": 同日,
            "★首个不等的位置": (None if 等 else int(np.argmax(左 != 右))),
            "★判": ("✅ 滞后一天，**不偷看**" if 等 and not 同日
                     else "★★★ 不符合预期 —— 停"),
        }
        全过 = 全过 and 等 and not 同日
    报告["★★★结论"] = (
        "✅ #70 是**误判**：`regime_mask` 自己的最后一行就 `shift(1)`，"
        "《104》只读了入包那一行（matrices.py:1379），没读函数的 return（:666）。"
        "★★★ chain.py:759 的 `[i+1]` 正好被这个 shift 抵消 → "
        "「今天收盘（已知）决定明天开盘买不买」，**口径是对的**。"
        if 全过 else "★★★ 核不过 —— 本份结论作废，按 #70 原判处理")
    报告["★★★ 这件要连着说的"] = (
        "★ 《104》那组 A/B（B = 再往后挪一天）量出来的差很大（融-2 甚至变号）—— "
        "★★ 那个差是**真的**，但它证明的是「结果对这一格很敏感」，"
        "★★★ 不是「A 错了」。★ 既然 A 已经是正确口径，B 就是**多滞后了一天**。")
    json.dump(报告, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(报告, ensure_ascii=False, indent=1))
    return 0 if 全过 else 3


if __name__ == "__main__":
    raise SystemExit(main())
