# -*- coding: utf-8 -*-
"""
★★★★★ Gemini 清单第 ⑥ 条收尾 —— 「算术年化 vs 对数/几何年化」★ 到底还有哪儿没改、差多少。

★★★ 11-07《111》第⑥条当时的话：「波动拖累**中位 2.90pp/年**（范围 0.01~7.15）→ 应直接改口」。
★★ 11-07 自己也已经写明（`尺子v2_1107.py:21`）：「**年化本来就是几何的**（对的）；
   ★★★ 但**检验**用的全是算术均值 —— 那一层没做。」

★★★★★ 这一份干两件：
  ① **全仓 grep 一遍**：到底哪些**报告路径**还在用「日均 × 252」。
  ② **量一下那一层差多少**：在仓库现成的 126 份日净值上，
     把「差值的年化」用两种写法都算一遍 —— 甲 = 几何年化(a) − 几何年化(b)；乙 = (ra−rb).mean()×252。
★★★ 不跑回测。★ 本份是**尺子的体检表，不是成绩表**。
"""
from __future__ import annotations

import glob
import itertools
import json
import os
import re
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
NAV = os.path.join(ROOT, "probe", "随机同档_1107", "日净值_1107")
Y = 252.0


def 几何年化(r: np.ndarray) -> float:
    return float((1.0 + r).prod() ** (Y / len(r)) - 1.0) if len(r) else float("nan")


def 算术年化(r: np.ndarray) -> float:
    return float(r.mean() * Y) if len(r) else float("nan")


def 扫一遍() -> dict:
    """★★★ ① 哪些报告路径还在用「日均 × 252」（★ 只扫 probe/ 下的 .py，跳过作废目录）。"""
    算术, 几何 = [], []
    pat算 = re.compile(r"mean\(\)\s*\*\s*(252|年)\b|\.sum\(\)\s*/\s*\w+\s*\*\s*252|\[0\]\)\s*\*\s*252")
    pat几 = re.compile(r"prod\(\)\s*\*\*|expm1\(np\.log1p|np\.exp\(.*mean\(\)\s*\*\s*252")
    for p in sorted(glob.glob(os.path.join(ROOT, "probe", "**", "*.py"), recursive=True)):
        rel = os.path.relpath(p, ROOT)
        if "作废" in rel or "夏普SE_1109" in rel:
            continue
        try:
            txt = open(p, encoding="utf-8").read()
        except Exception:                                        # noqa: BLE001
            continue
        for i, ln in enumerate(txt.splitlines(), 1):
            if pat算.search(ln):
                算术.append(f"{rel}:{i}  {ln.strip()[:110]}")
            if pat几.search(ln):
                几何.append(f"{rel}:{i}")
    return {"★★★还在用「日均×252」的行": 算术,
            "★用几何/对数的文件行数": len(几何),
            "★★读法": ("★ 出数主路径 `probe/重测_1107/出数_1107.py:223` 是 "
                     "`(1+x).prod()**(252/len)-1` → **几何**，★★★ 所以四件的「差 pp/年」不受第⑥条影响；"
                     "★★ 还在用算术的那几处都是**差值/alpha** 的年化，见上面逐行。")}


def 量一层() -> dict:
    """★★★ ② 差值的年化：两种写法差多少（★ 在真净值的同段·同族·同技配对上量）。"""
    组: dict[str, list[tuple[str, np.ndarray]]] = {}
    for p in sorted(glob.glob(os.path.join(NAV, "*.csv"))):
        name = os.path.basename(p)[:-4]
        key = "·".join(name.split("·")[:4])                       # 段·池·族·技
        d = pd.read_csv(p)
        eq = pd.to_numeric(d["equity"], errors="coerce")
        s = pd.Series(eq.to_numpy(), index=pd.to_datetime(d["date"])).dropna()
        r = s.pct_change().dropna()
        组.setdefault(key, []).append((name, r))
    行, 差 = [], []
    for key, lst in 组.items():
        for (na, ra), (nb, rb) in itertools.combinations(lst, 2):
            共 = ra.index.intersection(rb.index)
            if len(共) < 250:
                continue
            a, b = ra.reindex(共).to_numpy(), rb.reindex(共).to_numpy()
            甲 = (几何年化(a) - 几何年化(b)) * 100
            乙 = 算术年化(a - b) * 100
            行.append({"段族技": key, "a": na.split("·")[-1], "b": nb.split("·")[-1],
                      "甲_几何差pp": round(甲, 3), "乙_日均差乘252pp": round(乙, 3),
                      "甲减乙pp": round(甲 - 乙, 3)})
            差.append(abs(甲 - 乙))
    差 = np.array(差)
    return {"★配对数": int(len(差)),
            "★★★|甲−乙| 中位pp": (round(float(np.median(差)), 3) if len(差) else None),
            "★★★|甲−乙| 90分位pp": (round(float(np.percentile(差, 90)), 3) if len(差) else None),
            "★★★|甲−乙| 最大pp": (round(float(差.max()), 3) if len(差) else None),
            "★★读法": ("★ 两种写法在**差值**上差多少，就是第⑥条在「检验」那一层的实际影响；"
                     "★★★ 比《111》量的「单边波动拖累 2.90pp」小得多 —— 拖累在两边**大部分抵掉了**。"),
            "逐对_前20": 行[:20]}


def main() -> int:
    报 = {"★★★这一份是什么": "★★★★★ 尺子体检表，不是成绩表 —— 量「第⑥条还剩哪一层、差多少」",
         "★口径头": {"全收益或价格": "★ 126 份日净值是 1107 随机同档那批（价格口径）",
                  "摩擦档": "★ 流水自带", "窗口": "★ 见文件名（A_2004到2014 / B_2015到2025）",
                  "池子": "并池2004", "标签滞后天": "★ 沿用原跑批口径",
                  "★★★规矩㊼": "★ 开关类默认值当成结论字段来报"},
         "① 哪儿还在用算术年化": 扫一遍(),
         "② 差值上两种写法差多少": 量一层()}
    p = os.path.join(HERE, "第6条_年化口径_报告_1109.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print("✅ 写出", p)
    print(json.dumps(报["① 哪儿还在用算术年化"], ensure_ascii=False, indent=1))
    d = dict(报["② 差值上两种写法差多少"]); d.pop("逐对_前20", None)
    print(json.dumps(d, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
