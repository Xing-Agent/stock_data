#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ 「重进的笔 vs 首次进场的笔,每笔净R 有没有差」—— 显著性(2026-10-30)

★★★ 结论口径(策略组已拍板,不许违反):Z 不显著时**严禁**写「不成立」,
   一律写「在现有样本容量下未显现统计显著性」。
★ 方法:Welch 两样本 z(双尾)。★ 只摆数,不判生死。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import ledger_facts_1030 as LF                                       # noqa: E402

Z_BASIC = 1.65        # ★ 和 engine/stats_gate.py 的判定线同一个数,不另立


def welch_z(a: np.ndarray, b: np.ndarray) -> dict:
    a = a[np.isfinite(a)]; b = b[np.isfinite(b)]
    if len(a) < 2 or len(b) < 2:
        return {"Z": None, "说明": "任一侧笔数 < 2,算不出 —— ★ 不拿近似值顶上"}
    va, vb = a.var(ddof=1) / len(a), b.var(ddof=1) / len(b)
    se = float(np.sqrt(va + vb))
    if se <= 0:
        return {"Z": None, "说明": "标准误为 0,算不出"}
    z = float((b.mean() - a.mean()) / se)
    return {"首次_n": int(len(a)), "首次_每笔净R": float(a.mean()),
            "重进_n": int(len(b)), "重进_每笔净R": float(b.mean()),
            "差(重进 − 首次)": float(b.mean() - a.mean()),
            "Z": z, "|Z|≥1.65": bool(abs(z) >= Z_BASIC),
            "口径": ("|Z| < 1.65 → ★★★ 写「在现有样本容量下未显现统计显著性」,"
                     "**严禁**写「不成立」")}


def main() -> int:
    leds = LF.load_all()
    out = {"口径": {"方法": "Welch 两样本 z(双尾),比的是每笔净R 的均值",
                    "判定线": "Z ≥ 1.65(与 engine/stats_gate.py 同一个数)",
                    "★★★结论口径": "Z 不显著 = 「未显现统计显著性」,不是「不成立」",
                    "无止损链": "R 退化成收益率,★ 单独标出、不与有止损链同列比较"},
           "逐链": {}}
    pooled_a, pooled_b = [], []
    for name, d in leds.items():
        a = d.loc[~d["is_reentry"], "r_multiple_net"].astype(float).to_numpy()
        b = d.loc[d["is_reentry"], "r_multiple_net"].astype(float).to_numpy()
        rec = welch_z(a, b)
        rec["无止损链(R=收益率)"] = LF._no_stop(name)
        out["逐链"][name] = rec
        if not LF._no_stop(name):
            pooled_a.append(a); pooled_b.append(b)
    out["并池(只含有止损的链)"] = welch_z(np.concatenate(pooled_a),
                                          np.concatenate(pooled_b))
    dst = os.path.join(HERE, "sig_1030.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print("已写", dst)
        p = out["并池(只含有止损的链)"]
        print(f"并池: 首次 n={p['首次_n']} {p['首次_每笔净R']:.4f} | "
              f"重进 n={p['重进_n']} {p['重进_每笔净R']:.4f} | "
              f"差={p['差(重进 − 首次)']:+.4f} Z={p['Z']:.2f} 显著={p['|Z|≥1.65']}")
        for n, r in out["逐链"].items():
            if r.get("Z") is None:
                print(f"  {n[:44]:46s} {r.get('说明')}"); continue
            print(f"  {n[:44]:46s} 差={r['差(重进 − 首次)']:+.4f} Z={r['Z']:+6.2f} "
                  f"显著={r['|Z|≥1.65']}{' [无止损]' if r['无止损链(R=收益率)'] else ''}")
    except Exception as exc:
        print("打印出错(结果已写出):", repr(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
