# -*- coding: utf-8 -*-
"""★★★★★ 尺子③(a) 那个 z 稳不稳 —— ★ 去掉**一条**随机臂看它动多少（leave-one-out）。

★★★ 为什么问这个：z 的分母是 **10 条随机臂每笔净R 的跨臂标准差**。
  ★★ N=10 的时候，**一条臂的运气就能定这个分母** → ★★★ z 可能根本不稳。
★★★★★ 本份是**稳定性诊断，不是替代估计** ——
  ★ 去掉一条之后的 z **一个都不许当成结果引用**（★★ 那就是挑樱桃）。
★★ 自证：重算的跨臂SD / 随机均值 / z 必须和《130》第五节 (a) 那一栏逐数一致。
"""
from __future__ import annotations
import glob, json, os
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
OUT = os.path.join(HERE, "尺子三稳不稳_报告_1108.json")
Z130 = {("B_2015到2025", "大波段"): 0.16, ("B_2015到2025", "突破"): 0.17,
       ("B_2015到2025", "震荡"): 1.56, ("A_2004到2014", "大波段"): -0.90,
       ("A_2004到2014", "突破"): 0.27, ("A_2004到2014", "震荡"): 1.48}

arms = {}
for f in glob.glob("probe/重测_1107/arms_赛道配对_1108/a_*.json"):
    d = json.load(open(f)); arms[d["链"]] = d

报 = {"★这一份是什么": "尺子③(a) 的 z 的 leave-one-out 稳定性诊断",
     "★★★★★不许怎么用": ("★ 去掉一条之后的 z **不是结果**，一个都不许引用 —— "
                   "★★★ 本份只回答「这把尺子在 N=10 上稳不稳」"),
     "结果": {}}
for 窗 in ("B_2015到2025", "A_2004到2014"):
    for 族 in ("大波段", "突破", "震荡"):
        rs = {k.split("·")[-1]: v["每笔净R"] for k, v in arms.items()
              if v["族"] == 族 and k.startswith(窗) and v["臂"].startswith("R随机")}
        真 = [v["每笔净R"] for k, v in arms.items()
             if v["族"] == 族 and k.startswith(窗) and v["臂"] == "A原样"][0]
        names = list(rs); x = np.array([rs[n] for n in names])
        sd = float(x.std(ddof=1)); mu = float(x.mean()); z = (真 - mu) / sd
        zs = []
        for i in range(len(x)):
            y = np.delete(x, i)
            zs.append(((真 - float(y.mean())) / float(y.std(ddof=1))), )
        zs = [float(a[0]) if isinstance(a, tuple) else float(a) for a in zs]
        imax = int(np.argmax(np.abs(np.array(zs) - z)))
        报["结果"][f"{窗}·{族}"] = {
            "★随机臂条数": len(x),
            "★★★跨臂SD": round(sd, 4), "★随机均值": round(mu, 4),
            "★★★z_全部10条": round(z, 2), "★《130》写的z": Z130[(窗, 族)],
            "★★★对上了吗": "✅" if abs(z - Z130[(窗, 族)]) <= 0.02 else "⚠ 没对上",
            "★随机臂每笔净R范围": [round(float(x.min()), 4), round(float(x.max()), 4)],
            "★★★去掉一条后的z_范围": [round(min(zs), 2), round(max(zs), 2)],
            "★★★★★最大挪动": round(float(zs[imax] - z), 2),
            "★挪得最多是去掉哪一条": f"{names[imax]}（每笔净R {x[imax]:+.4f}）",
            "★★怎么读": ("★ 「最大挪动」= 只去掉 1 条随机臂，z 最多变多少。"
                     "★★★ 绝对值大 → 这把尺子在 N=10 上**不稳**")}
        print(f"{窗}·{族}: z {z:+.2f}（《130》{Z130[(窗,族)]:+.2f}）· "
              f"去掉一条后 z ∈ [{min(zs):+.2f}, {max(zs):+.2f}] · "
              f"最大挪动 {zs[imax]-z:+.2f}（去掉 {names[imax]}）", flush=True)

坏 = [k for k, v in 报["结果"].items() if "⚠" in v["★★★对上了吗"]]
报["★★★自证"] = ("✅ 六格的 z 都和《130》第五节 (a) 逐数一致" if not 坏
             else f"⚠⚠ 对不上：{坏} —— ★★★ 下面的数不许用")
print(报["★★★自证"], flush=True)
json.dump(报, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("★ 写出:", OUT, flush=True)
