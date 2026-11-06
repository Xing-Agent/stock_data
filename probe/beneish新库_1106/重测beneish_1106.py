# -*- coding: utf-8 -*-
"""
★★★ 用**新财报库**重测 Beneish M-Score 的覆盖率 —— ★ engine 零改动。

★★ 来历：基 3.2「造假概率」是 13 条必备缺口之一，★ 判 ❌ 的理由是
  「**主档 0% 算不出**：池内 3,031 家实体里 `financial_versions` 有 SG&A 的是 **0 家**；
    旁路（SG&A 从 `raw_tags` 拼）只覆盖 **16.87%**，天花板 18.23%」。
★★★ 1106 发现：**那是老库（pilot_300，280 家）的情况** ——
  新库 `fundamentals_ext/`（4,005 家）里**有正式科目**
  `SellingGeneralAndAdministrativeExpense`。
→ ★★ 所以算子**根本不用重写**（`probe/redflag_gates_1103/ops_redflag_1103.py` 早就有），
  ★★★ 只要：① 接新库 ② 把 SG&A 的来源从 `raw_tags` 换成正式科目 ③ 重测覆盖率。

★ 口径：八项全齐才给 M-Score（★★ 缺一项 = 算不出，不猜不补）。
"""
import json, os, sys, hashlib
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "补齐能力_1106"))
sys.path.insert(0, os.path.join(ROOT, "probe", "redflag_gates_1103"))

import 接新财报库_1106 as EXT                                  # noqa: E402
import 基本面零件_1106 as PARTS                                # noqa: E402
_E = EXT.install()
_P = PARTS.install()          # ★ 这一步顺带把 SG&A 登记成**流量**科目

import ops_redflag_1103 as R                                   # noqa: E402

# ★★★ 换 SG&A 的来源:raw_tags 拼的 → **新库的正式科目**
_旧 = R._COLS["sga"]
R._COLS["sga"] = ("SellingGeneralAndAdministrativeExpense", "ttm")
for fn in (getattr(R, "frame", None), getattr(R, "metric_q", None),
           getattr(R, "get", None)):
    if fn is not None and hasattr(fn, "cache_clear"):
        fn.cache_clear()


def main() -> int:
    报 = {"★口径": {
        "engine改动": "零",
        "SG&A来源_改前": list(_旧),
        "SG&A来源_改后": list(R._COLS["sga"]),
        "★★为什么改": "★ 老库 financial_versions 里 SG&A 是 0 家 → 只能从 raw_tags 拼(16.87%);"
                   "★★★ 新库有正式科目",
        "八项": "★ 全齐才给 M-Score —— 缺一项 = 算不出,不猜不补",
        "接的库": _E, "补的零件": {k: _P.get(k) for k in ("★补登记的流量科目",)},
    }}
    man = pd.read_csv("probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv")
    syms = sorted(set(man["symbol"].astype(str)))
    samp = sorted(syms, key=lambda x: hashlib.sha256(x.encode()).hexdigest())[:300]
    报["★抽样"] = {"家数": len(samp), "切法": "sha256 排序取前 300 —— ★ 不用随机数"}

    计 = {"m_score": 0, "m_score_no_sgai": 0, "sga单项": 0}
    期 = {k: [] for k in 计}
    for s in samp:
        # ★ SG&A 单项有没有(★★ 分开报:好把「SG&A 有没有」和「八项全齐」分开看)
        try:
            o = R.frame(s)[0]
            if "sga" in o.columns and o["sga"].notna().any():
                计["sga单项"] += 1
                期["sga单项"].append(int(o["sga"].notna().sum()))
        except Exception:
            pass
        for n in ("m_score", "m_score_no_sgai"):
            try:
                v, _ = R.metric_q(s, n)
            except Exception:
                v = pd.Series(dtype=float)
            k = int(v.notna().sum()) if len(v) else 0
            if k:
                计[n] += 1; 期[n].append(k)
    for n in 计:
        报[n] = {
            "有实际数值的家数": 计[n],
            "覆盖率": f"{计[n]/max(len(samp),1)*100:.1f}%",
            "每家期数中位": (int(np.median(期[n])) if 期[n] else None),
        }
    报["m_score"]["★★★对比_改前"] = ("主档 **0%**(financial_versions 无 SG&A);"
                                "旁路 16.87%,天花板 18.23%")
    报["★★★结论"] = ("★ 看 m_score 的覆盖率:★★ 过了 18.23% 这个老天花板,"
                  "就说明换库真的解开了这条缺口")
    os.makedirs("probe/beneish新库_1106", exist_ok=True)
    with open("probe/beneish新库_1106/重测beneish_报告_1106.json", "w",
              encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(json.dumps({k: 报[k] for k in ("m_score", "m_score_no_sgai", "sga单项")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
