# -*- coding: utf-8 -*-
"""★★★★★ 《141》配对检验 · **两侧脏日口径对齐**（赛道侧 D0 vs D1，重定一律每季）。

★★★ 本文件 = probe/赛道季度_1108/配对_季度_1108.py 的复制，只改一件：
  ★★ 主检验的外层从「每年 / 每季」换成「**D1 剔脏日 / D0 不剔**」，重定固定成**每季**（《139》已定）。
★★★ 为什么 D0 才是同口径：★ 策略侧那 84 条臂**本来就没剔脏日** → ★★ 赛道侧也不剔才对得齐。
★★★ 门槛、三种情形：**全部写死在《141》第一节**（跑之前已单独 commit）。★ 跑完不许动。
★★★★★ 自证①：D1 那六个 t 必须复现《140》第五节（B −0.76/−1.90/−3.93 · A −2.30/−1.81/−3.82）。
"""
from __future__ import annotations
import json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)

NAV = "probe/重测_1107/日净值_季度配对_1108"
曲线 = pd.read_parquet(os.path.join(HERE, "赛道日收益_季度对照_1108.parquet"))
OUT = os.path.join(HERE, "配对_脏日对齐_报告_1108.json")
滞后, 门槛, 年 = 8, 3.0, 252.0

族表 = {"大波段技-1": "大波段·技-1", "突破技-6": "突破·技-6-原著", "震荡技-14": "震荡·技-14-原著"}
Z门槛 = 2.5     # ★ 《102》第六节：策略 vs 标普 是**单次**配对，门槛 2.5（★ 只用于自证①）
期望t = {"B_2015到2025": {"大波段技-1": -1.23, "突破技-6": -2.89, "震荡技-14": -4.95},
       "A_2004到2014": {"大波段技-1": -1.72, "突破技-6": -1.30, "震荡技-14": -3.42}}
期望年化 = {"B_2015到2025": {"大波段技-1": 5.96, "突破技-6": 3.25, "震荡技-14": -5.74},
         "A_2004到2014": {"大波段技-1": -0.41, "突破技-6": 4.14, "震荡技-14": -5.46}}


def nw_t(x: np.ndarray, lag: int = 滞后) -> float:
    """★ Bartlett 核的 Newey-West 修正 t（★★ 检验均值是不是 0）。"""
    x = np.asarray(x, float); n = len(x); m = x.mean(); e = x - m
    S = float((e * e).sum() / n)
    for l in range(1, lag + 1):
        S += 2.0 * (1.0 - l / (lag + 1.0)) * float((e[l:] * e[:-l]).sum() / n)
    return float(m / np.sqrt(S / n)) if S > 0 else float("nan")


def 年化(x) -> float:
    x = pd.Series(x).dropna().astype(float)
    return float((1.0 + x).prod() ** (年 / len(x)) - 1.0)


def boot(d: np.ndarray, 种=12345) -> dict:
    """★★ 规矩㊾ 三种 bootstrap 的 95% 区间（★★★ 附加描述性，不在《132》判据里）。"""
    rng = np.random.default_rng(种); n = len(d); 出 = {}
    for 名, blk in (("iid", 1), ("块20", 20), ("块60", 60)):
        ms = []
        for _ in range(2000):
            if blk == 1:
                ms.append(d[rng.integers(0, n, n)].mean())
            else:
                k = int(np.ceil(n / blk))
                s = rng.integers(0, max(1, n - blk), k)
                ms.append(np.concatenate([d[i:i + blk] for i in s])[:n].mean())
        lo, hi = np.percentile(ms, [2.5, 97.5])
        出[名] = {"区间": [round(lo * 1e4, 3), round(hi * 1e4, 3)], "排除0": bool(lo > 0 or hi < 0)}
    出["★★★三种都排除0"] = all(v["排除0"] for v in 出.values() if isinstance(v, dict))
    return 出


报 = {"★预先登记": "手册/141 第一节（★ 跑之前单独 commit · 门槛 |t|>3 · 滞后 8 · 6 次检验 · 三种情形写死）",
     "★★★策略侧": f"{NAV}（★ 本容器重跑 84 条臂；和 arms_修分红_1108 **84/84 逐数一致，0 条不同** —— 第二个独立容器的复现）",
     "★★★自证": {}, "结果": {}}

for 窗名 in ("B_2015到2025", "A_2004到2014"):
    spy = 曲线[f"{窗名}|SPY全收益|-|-"].dropna()
    报["结果"][窗名] = {}
    for 族名, 片 in 族表.items():
        label = f"{窗名}·并池2004·{片}·A原样"
        p = os.path.join(NAV, label.replace("/", "_").replace(" ", "") + ".csv")
        if not os.path.exists(p):
            报["结果"][窗名][族名] = {"★算不出来": f"没有日净值：{p}"}
            continue
        eq = pd.read_csv(p, parse_dates=["date"]).set_index("date")["equity"].astype(float).dropna()
        r = eq.pct_change().dropna()

        # ---- 自证①：策略 vs SPY，必须重算出《130》那六个 t
        共 = r.index.intersection(spy.index)
        d_spy = (r.reindex(共) - spy.reindex(共)).to_numpy()
        t_spy = nw_t(d_spy)
        年化策 = 年化(r.reindex(共)) * 100
        报["★★★自证"].setdefault(窗名, {})[族名] = {
            "★策略vs标普_我算的NWt": round(t_spy, 2),
            "★《130》写的": 期望t[窗名][族名],
            "★★★对上了吗": "✅" if abs(t_spy - 期望t[窗名][族名]) <= 0.02 else "⚠ 没对上",
            "★策略年化_我算的": f"{年化策:+.2f}%",
            "★《130》的策略年化": f"{期望年化[窗名][族名]:+.2f}%",
            "★★★年化对上了吗": "✅" if abs(年化策 - 期望年化[窗名][族名]) <= 0.02 else "⚠ 没对上",
            "★重叠交易日": int(len(共))}

        # ---- 主检验：策略 vs 赛道（三种加权，D1 剔脏日）★★★ 《139》：两种重定都算
        #   ★★ 「每年」那一组是**自证**：必须复现《134》第三节那六个 t（容差 0.02）
        出 = {}
        for dn, wn in [(d, w) for d in ("D1_剔脏日", "D0_不剔")
                       for w in ("W1_成交额平方根", "W2_成交额", "W3_等权")]:
            重定 = "每季"          # ★ 《139》已定：每季重定是合规口径，本轮不动它
            sec = 曲线[f"{窗名}|{重定}|{wn}|{dn}"].dropna()
            c2 = r.index.intersection(sec.index)
            d = (r.reindex(c2) - sec.reindex(c2)).dropna()
            dv = d.to_numpy()
            t = nw_t(dv)
            出[f"{dn}·{wn}"] = {
                "★★★X_年化差": f"{(年化(r.reindex(c2)) - 年化(sec.reindex(c2)))*100:+.2f}pp/年",
                "★逐日差均值": f"{dv.mean()*1e4:+.3f} 个基点/天",
                "★★★NW修正t": round(t, 2),
                "★滞后": 滞后, "★天数": int(len(dv)),
                "★★★过没过门槛": (f"门槛 |t|>{门槛:.0f}（6 次检验，跑前写死）→ "
                            + ("**过了**" if abs(t) > 门槛 else "**没过**")),
                "★偏度": round(float(pd.Series(dv).skew()), 2),
                "★★附加_三种bootstrap": boot(dv)}
            k = f"{dn}·{wn}"
            print(f"{窗名} {族名} {dn} {wn}: X {出[k]['★★★X_年化差']} · NW t {t:+.2f} · "
                  f"{'过' if abs(t) > 门槛 else '没过'} · 偏度 {出[k]['★偏度']}", flush=True)
        报["结果"][窗名][族名] = 出

# ★★★ 自证③：「每年重定」那六个 t 必须复现《134》第三节（W1 主口径）
T134 = {"B_2015到2025": {"大波段技-1": -0.76, "突破技-6": -1.90, "震荡技-14": -3.93},
       "A_2004到2014": {"大波段技-1": -2.30, "突破技-6": -1.81, "震荡技-14": -3.82}}
自证3 = {}
for w in T134:
    for f, 期 in T134[w].items():
        g = 报["结果"].get(w, {}).get(f, {}).get("D1_剔脏日·W1_成交额平方根")
        我 = g["★★★NW修正t"] if isinstance(g, dict) else None
        自证3[f"{w}·{f}"] = {"★我算的": 我, "★《140》第五节写的": 期,
                           "★★★对上了吗": ("✅" if 我 is not None and abs(我 - 期) <= 0.02
                                      else "⚠ 没对上")}
报["★★★自证"]["★★★自证①_D1复现《140》第五节"] = 自证3
print("★★★ 自证①(D1复现《140》):", json.dumps(自证3, ensure_ascii=False), flush=True)

坏 = [f"{w}·{f}" for w in 报["★★★自证"] if isinstance(报["★★★自证"][w], dict)
     and w in ("B_2015到2025", "A_2004到2014") for f in 报["★★★自证"][w]
     if "⚠" in 报["★★★自证"][w][f]["★★★对上了吗"]
     or "⚠" in 报["★★★自证"][w][f]["★★★年化对上了吗"]]
报["★★★自证"]["★★★★★总结"] = ("✅ 六格的「策略vs标普 NW t」和「策略年化」都和《130》逐数对上 "
                       "→ ★ NW 代码和日净值都是对的"
                       if not 坏 else f"⚠⚠ 对不上的：{坏} —— ★★★ 主检验的 t 不许用")
print(报["★★★自证"]["★★★★★总结"], flush=True)
json.dump(报, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("★ 写出:", OUT, flush=True)
