# -*- coding: utf-8 -*-
"""★★★★★ 把《136》第四节那段**推理**换成实测 —— ★ 10 条随机臂也按月聚类算一遍。

★★★ 要回答的一句：尺子③ 那个「随机单次标准差」（= 10 条随机臂每笔净R 的跨臂标准差），
  ★★ 它到底是**真的种子之间的差异**，还是**每条臂自己估不准**堆出来的？
★ 判法：拿「跨臂标准差」比「单臂自己的聚类标准误（中位）」——
  ★★ 比值 **远大于 1** → 跨臂差异是真的，尺子③ 的分母站得住；
  ★★★ 比值 **≈1 或更小** → 那个分母里**主要是估计噪声**，★ 尺子③ 的 z 要重新解读。
★★★★★ 本份仍然是**描述性**：不设门槛、不改任何已报结论。
★★ 自证：每条臂重算的「每笔净R」必须和臂 JSON 逐数一致。
"""
from __future__ import annotations
import glob, json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
LEDG = "probe/重测_1107/ledgers_1107"
ARMS = "probe/重测_1107/arms_赛道配对_1108"
OUT = os.path.join(HERE, "随机臂也聚类_报告_1108.json")
# ★ 《130》第五节 (a) 那一栏，照抄当对账
SD130 = {("B_2015到2025", "大波段"): 0.1992, ("B_2015到2025", "突破"): 0.0479,
        ("B_2015到2025", "震荡"): 0.0478, ("A_2004到2014", "大波段"): 0.0531,
        ("A_2004到2014", "突破"): 0.0468, ("A_2004到2014", "震荡"): 0.0405}
均130 = {("B_2015到2025", "大波段"): 0.0586, ("B_2015到2025", "突破"): 0.0573,
        ("B_2015到2025", "震荡"): -0.1429, ("A_2004到2014", "大波段"): 0.0539,
        ("A_2004到2014", "突破"): 0.0825, ("A_2004到2014", "震荡"): -0.1039}

臂 = {}
for f in glob.glob(ARMS + "/a_*.json"):
    d = json.load(open(f)); 臂[d["链"]] = d


def 聚类se(x, g):
    x = np.asarray(x, float); m = x.mean(); n = len(x); e = x - m
    s = pd.Series(e).groupby(pd.Series(g)).sum().to_numpy()
    G = len(s); V = float((s * s).sum()) / (n * n) * (G / max(1.0, G - 1.0))
    return float(np.sqrt(V)), G


报 = {"★这一份是什么": "《136》第四节那段推理的实测版 —— 10 条随机臂也按月聚类",
     "★★★不是什么": "★ 描述性，不设门槛，不改《130》《133》《134》任何结论",
     "★★★自证": {"对不上的臂": []}, "结果": {}}

for 窗 in ("B_2015到2025", "A_2004到2014"):
    for 族, fn in (("大波段", "技-1"), ("突破", "技-6-原著"), ("震荡", "技-14-原著")):
        均s, ses, ns = [], [], []
        真均 = 真se = None
        for 链, rec in sorted(臂.items()):
            if rec["族"] != 族 or not 链.startswith(窗):
                continue
            if not (rec["臂"] == "A原样" or rec["臂"].startswith("R随机")):
                continue
            p = os.path.join(LEDG, f"REAL__{链}.csv")
            if not os.path.exists(p):
                报["★★★自证"]["对不上的臂"].append(f"{链} 没流水"); continue
            d = pd.read_csv(p, parse_dates=["exit_date"])
            丢 = int(d["r_multiple_net"].isna().sum())
            d = d[d["r_multiple_net"].notna()]
            x = d["r_multiple_net"].astype(float).to_numpy()
            if abs(float(x.mean()) - rec["每笔净R"]) > 1e-9 or len(x) + 丢 != rec["笔数"]:
                报["★★★自证"]["对不上的臂"].append(链); continue
            se, _ = 聚类se(x, d["exit_date"].dt.strftime("%Y-%m").to_numpy())
            if rec["臂"] == "A原样":
                真均, 真se = float(x.mean()), se
            else:
                均s.append(float(x.mean())); ses.append(se); ns.append(len(x))
        if 真均 is None or len(均s) < 5:
            报["结果"][f"{窗}·{族}"] = {"★算不出来": f"随机臂只凑到 {len(均s)} 条"}
            continue
        跨臂SD = float(np.std(均s, ddof=1))
        单臂se中位 = float(np.median(ses))
        比 = 跨臂SD / 单臂se中位
        z新 = (真均 - float(np.mean(均s))) / 跨臂SD
        报["结果"][f"{窗}·{族}"] = {
            "★随机臂条数": len(均s),
            "★★★跨臂标准差_我重算的": round(跨臂SD, 4),
            "★《130》写的随机单次SD": SD130[(窗, 族)],
            "★★★对上了吗": ("✅" if abs(跨臂SD - SD130[(窗, 族)]) < 0.0006 else "⚠ 没对上"),
            "★随机臂均值_我重算的": round(float(np.mean(均s)), 4),
            "★《130》写的随机均值": 均130[(窗, 族)],
            "★★★单臂聚类标准误_中位": round(单臂se中位, 4),
            "★★★★★跨臂SD ÷ 单臂聚类SE": round(比, 2),
            "★★★怎么读": ("★ 远大于 1 → 分母主要是真的种子差异，尺子③ 站得住；"
                      "★★★ ≈1 或更小 → 分母里主要是估计噪声"),
            "★真臂每笔净R": round(真均, 4),
            "★真臂聚类标准误": round(真se, 4),
            "★z_用跨臂SD": round(z新, 2)}
        print(f"{窗}·{族}: 跨臂SD {跨臂SD:.4f}（《130》{SD130[(窗,族)]}）· "
              f"单臂聚类SE中位 {单臂se中位:.4f} · 比 {比:.2f} · z {z新:+.2f}", flush=True)

坏 = 报["★★★自证"]["对不上的臂"]
报["★★★自证"]["★★★★★总结"] = ("✅ 参与计算的臂，每笔净R 和笔数都和臂 JSON 逐数一致"
                       if not 坏 else f"⚠⚠ 对不上/缺流水：{坏}")
print(报["★★★自证"]["★★★★★总结"], flush=True)
json.dump(报, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("★ 写出:", OUT, flush=True)
