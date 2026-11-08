# -*- coding: utf-8 -*-
"""★★★★★ Gemini 清单 #8「重叠交易按日期聚类」—— ★ 把一条**只有定性警告**的条目换成**一个数**。

★★★ 它要回答的是：★ 我们按「笔」算的那些数（每笔净R），如果拿它做参数检验，
  ★★ 因为同一天常常同时持有很多笔、而且一笔跨很多天，**笔与笔不独立** →
  ★★★ 朴素（iid）标准误会**偏小**，t 会**偏大**（看起来比实际显著）。

★★★★★ 本份是**描述性**的：**不设门槛、不产生任何「过/不过」判决、不改《130》任何结论**。
  ★ 它只量两件：① 朴素 t 比聚类 t 大多少倍（膨胀系数）② 有效样本量掉到多少。
★★ 自证：重算的「每笔净R」必须和 arms_赛道配对_1108 的 JSON 逐数一致（★ 不然流水读错了）。
"""
from __future__ import annotations
import glob, json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
LEDG = "probe/重测_1107/ledgers_1107"
ARMS = "probe/重测_1107/arms_赛道配对_1108"
OUT = os.path.join(HERE, "按日期聚类_报告_1108.json")

臂数 = {}
for f in glob.glob(ARMS + "/a_*.json"):
    d = json.load(open(f)); 臂数[d["链"]] = d


def 聚类t(x: np.ndarray, g: np.ndarray) -> tuple[float, int]:
    """★ 一维单向聚类标准误（CRVE）的 t —— ★★ 检验均值是不是 0。"""
    x = np.asarray(x, float); m = x.mean(); n = len(x); e = x - m
    s = pd.Series(e).groupby(pd.Series(g)).sum().to_numpy()
    V = float((s * s).sum()) / (n * n)
    G = int(len(s))
    # ★★ 小簇数修正（Cameron & Miller 2015 的常用那一版）
    c = (G / max(1.0, G - 1.0))
    return (float(m / np.sqrt(V * c)) if V > 0 else float("nan")), G


报 = {"★这一份是什么": "Gemini 清单 #8 —— 把「重叠交易按日期聚类」这条警告量成一个数",
     "★★★不是什么": ("★ **描述性，不设门槛，不产生任何过/不过判决**；"
                "★★★ 不改《130》《133》《134》任何一个结论 —— "
                "★★ 那三份的主判据走的是**日净值逐日配对**，本来就是「按日期」的，不吃这个毛病。"),
     "★★★自证": {}, "结果": {}}

for 链, rec in sorted(臂数.items()):
    if rec["臂"] != "A原样":
        continue
    p = os.path.join(LEDG, f"REAL__{链}.csv")
    if not os.path.exists(p):
        报["结果"][链] = {"★算不出来": f"没有流水：{p}"}
        continue
    d = pd.read_csv(p, parse_dates=["entry_date", "exit_date"])
    # ★★★★★ 1108 实测查出来的一件（★ 本份的自证当场挡下来的）：
    #   ★ B·震荡 和 A·震荡 的流水里**各有 1 笔 `r_multiple_net` 是 NaN**
    #     （例：ULTA 2017-07-31 当天进当天止损，holding_days=0、risk_per_share=0.0201）。
    #   ★★ 而臂 JSON 里的「每笔净R」是 **nanmean**（跳过它）—— ★★★ 跳得**没有任何地方记一笔**。
    #   → ★ 本份照同一个口径（跳过）才能和臂 JSON 对上，★★ 但**把跳了几笔报出来**，不静默。
    丢 = int(d["r_multiple_net"].isna().sum())
    d = d[d["r_multiple_net"].notna()].reset_index(drop=True)
    x = d["r_multiple_net"].astype(float).to_numpy()
    # ---- 自证：重算的每笔净R 必须和臂 JSON 一致
    对上 = abs(float(x.mean()) - rec["每笔净R"]) < 1e-9
    报["★★★自证"][链] = {"★流水重算每笔净R": round(float(x.mean()), 6),
                     "★臂JSON写的": round(rec["每笔净R"], 6),
                     "★笔数": [int(len(x) + 丢), int(rec["笔数"])],
                     "★★★丢掉的NaN笔数": 丢,
                     "★★★对上了吗": ("✅" if 对上 and len(x) + 丢 == rec["笔数"]
                                else "⚠ 没对上")}
    n = len(x)
    t_iid = float(x.mean() / (x.std(ddof=1) / np.sqrt(n)))
    t_出, G出 = 聚类t(x, d["exit_date"].dt.strftime("%Y-%m-%d").to_numpy())
    t_进, G进 = 聚类t(x, d["entry_date"].dt.strftime("%Y-%m-%d").to_numpy())
    t_月, G月 = 聚类t(x, d["exit_date"].dt.strftime("%Y-%m").to_numpy())
    # ---- 重叠有多重：平均同时在手几笔
    开 = pd.Series(1, index=d["entry_date"]).groupby(level=0).sum()
    关 = pd.Series(-1, index=d["exit_date"]).groupby(level=0).sum()
    净 = pd.concat([开, 关]).groupby(level=0).sum().sort_index().cumsum()
    天 = pd.date_range(净.index.min(), 净.index.max(), freq="B")
    同时 = 净.reindex(天).ffill().fillna(0.0)
    膨胀 = abs(t_iid / t_月) if t_月 and np.isfinite(t_月) and t_月 != 0 else float("nan")
    报["结果"][链] = {
        "★笔数": n, "★每笔净R均值": round(float(x.mean()), 4),
        "★★★t_朴素iid": round(t_iid, 2),
        "★★★t_按离场日聚类": round(t_出, 2), "★离场日簇数": G出,
        "★t_按进场日聚类": round(t_进, 2), "★进场日簇数": G进,
        "★★★t_按月聚类": round(t_月, 2), "★月簇数": G月,
        "★★★朴素比按月聚类大几倍": round(膨胀, 2) if np.isfinite(膨胀) else None,
        "★★★有效样本量_按月": (int(n / (膨胀 ** 2)) if np.isfinite(膨胀) and 膨胀 > 0 else None),
        "★★平均同时在手笔数": round(float(同时.mean()), 1),
        "★★最多同时在手": int(同时.max()),
        "★平均持有天数": round(float(d["holding_days"].mean()), 1)}
    print(f"{链.split('·')[0]}·{rec['族']}: n={n} · 每笔净R {x.mean():+.4f} · "
          f"t朴素 {t_iid:+.2f} → t按月聚类 {t_月:+.2f}（大 {膨胀:.2f} 倍）· "
          f"同时在手均 {同时.mean():.1f} 最多 {int(同时.max())} 笔", flush=True)

坏 = [k for k, v in 报["★★★自证"].items() if "⚠" in v["★★★对上了吗"]]
报["★★★自证"]["★★★★★总结"] = ("✅ 六条 A原样 的每笔净R 和笔数都和臂 JSON 逐数一致"
                       if not 坏 else f"⚠⚠ 对不上：{坏} —— ★★★ 下面的数不许用")
print(报["★★★自证"]["★★★★★总结"], flush=True)
json.dump(报, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("★ 写出:", OUT, flush=True)
