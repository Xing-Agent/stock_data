# -*- coding: utf-8 -*-
"""
★★★★★ 查「日净值里有没有物理上不可能的一天」—— ★ 可复用，任何 日净值 目录都能跑。

★★★ 判据（只用两条，都不需要外部数据）：
  ① **只做多、不加杠杆** → `exposure ≤ 1` 的那一天，组合净值单日变动不可能接近 ±100%。
  ② 同一个「段·族·技」下的兄弟臂年化波动应当同量级 —— ★ 一条比中位数高 3 倍以上就标出来。
★★ 门槛写在这里，★★★ 不许在读数时放宽（规矩⑯：响亮失败）。

用法：python3 probe/夏普SE_1109/查净值不可能日_1109.py [日净值目录 ...]
      ★ 不给参数就扫仓库里所有 日净值* 目录。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

单日门槛 = 0.25        # ★ exposure ≤ 1 时，单日 |变动| > 25% 一律标 🔴
波动门槛 = 0.50        # ★ 年化波动 > 50% 标 🔴
兄弟倍数 = 3.0         # ★ 比同组中位波动高这么多倍标 🟡


def 一个目录(d: str) -> dict:
    fs = sorted(glob.glob(os.path.join(d, "*.csv")))
    诊 = {}
    for p in fs:
        n = os.path.basename(p)[:-4]
        try:
            t = pd.read_csv(p)
            eq = pd.to_numeric(t["equity"], errors="coerce").dropna()
            r = eq.pct_change().dropna().to_numpy()
            ex = float(pd.to_numeric(t.get("exposure", 0), errors="coerce").max())
        except Exception as e:                                   # noqa: BLE001
            诊[n] = {"★读不了": str(e)[:80]}
            continue
        if len(r) < 2:
            诊[n] = {"★读不了": f"只有 {len(r)} 天"}
            continue
        诊[n] = {"天数": len(r), "年化波动": round(float(r.std() * np.sqrt(252)), 4),
                "最大单日": round(float(np.abs(r).max()), 4), "exposure最大": round(ex, 4),
                "最大单日日期": str(pd.to_datetime(t["date"]).iloc[int(np.argmax(np.abs(r))) + 1].date())
                if "date" in t.columns else None}
    # 兄弟组
    组: dict[str, list[str]] = {}
    for n in 诊:
        组.setdefault("·".join(n.split("·")[:4]), []).append(n)
    红, 黄 = [], []
    for n, v in 诊.items():
        if "★读不了" in v:
            continue
        if v["exposure最大"] <= 1.0001 and (v["最大单日"] > 单日门槛 or v["年化波动"] > 波动门槛):
            红.append(n)
    for k, ns in 组.items():
        vols = [诊[n]["年化波动"] for n in ns if "年化波动" in 诊[n]]
        if len(vols) < 3:
            continue
        med = float(np.median(vols))
        for n in ns:
            if "年化波动" in 诊[n] and med > 0 and 诊[n]["年化波动"] > 兄弟倍数 * med and n not in 红:
                黄.append(f"{n}（{诊[n]['年化波动']:.2f} vs 同组中位 {med:.2f}）")
    return {"目录": os.path.relpath(d, os.getcwd()), "文件数": len(fs),
            "★★★🔴不可能日/离谱波动": 红, "★🟡比兄弟高太多": 黄,
            "★★★判据": (f"exposure≤1 且（单日|变动|>{单日门槛:.0%} 或 年化波动>{波动门槛:.0%}）→ 🔴；"
                     f"★ 同组波动 > {兄弟倍数}× 中位 → 🟡"),
            "逐条": 诊}


def main(argv: list[str]) -> int:
    ds = argv[1:] or sorted(d for d in glob.glob("probe/**/日净值*", recursive=True) if os.path.isdir(d))
    if not ds:
        print("★ 没找到任何 日净值 目录")
        return 0
    报 = [一个目录(d) for d in ds]
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "查净值不可能日_报告_1109.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    坏 = 0
    for r in 报:
        坏 += len(r["★★★🔴不可能日/离谱波动"])
        print(f"{'🔴' if r['★★★🔴不可能日/离谱波动'] else '✅'} {r['目录']}  "
              f"{r['文件数']} 份 → 🔴 {len(r['★★★🔴不可能日/离谱波动'])} · 🟡 {len(r['★🟡比兄弟高太多'])}")
        for n in r["★★★🔴不可能日/离谱波动"]:
            v = r["逐条"][n]
            print(f"     🔴 单日 {v['最大单日']:+.1%} @{v['最大单日日期']} · 年化波动 "
                  f"{v['年化波动']:.1%} · exposure≤{v['exposure最大']:.2f}  {n[-50:]}")
    print("✅ 写出", p)
    return 1 if 坏 else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
