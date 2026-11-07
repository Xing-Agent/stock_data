# -*- coding: utf-8 -*-
"""★★★ 随机对照的分布怎么读 —— 规矩㊾ 那三样（分位数 · 偏度 · 区间）到底能不能算。

★★ 这一份只读已落盘的 `probe/重测_1107/日序列_1107/` 和 `arms_1107/`，
  ★ 不跑回测、不碰 engine、不改任何既有产物。

★★★ 它要回答的三件（★ 前两件是《113》第八节自己标了「不能用」但没量清的）：
  ① 规矩㊾ 要的 2.5/97.5 分位数，N=10 时**到底存不存在** —— 不是「大概不够」，是算清楚。
  ② 把随机对照搬到**用户真正体验的那一层**（年化 / 回撤 / 净值倍数），
     ★★★ 而不只是「每笔净 R」—— 《113》第 4.3 节刚栽过一次：
     每笔口径「好 5.7 倍」，日频配对一条没过。
  ③ 《113》第十节拍板项② 那个「种子数 10 → 多少」，★★★ 给出**算出来的下限**，
     而不是「提到 30」这种拍的数。

★★ 口径（规矩㊼ 五字段）：全收益（分红再投，两侧同口径）· 摩擦档跟原样臂
  · 窗口 A 2005~2014 / B 2015~2025 · 池 并池2004 全量 3,858 只 · 标签滞后 1 天。
★★★ 本份**不引用基准一**（本批没算它，《113》第二节）。
"""
from __future__ import annotations
import glob, hashlib, json, os, sys

import numpy as np
import pandas as pd
from scipy import stats as sps

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DS   = os.path.join(ROOT, "probe", "重测_1107", "日序列_1107")
ARMS = os.path.join(ROOT, "probe", "重测_1107", "arms_1107")
OUT  = os.path.join(HERE, "随机对照分布_报告_1107.json")

TD = 252.0   # ★ 一年的交易日数，年化用它换算（★★ 不用 365，净值序列是交易日频）


def 臂hash(label: str) -> str:
    return hashlib.sha256(label.encode()).hexdigest()[:16]


def 读日序列(label: str):
    p = os.path.join(DS, f"d_{臂hash(label)}.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, parse_dates=["日期"]).set_index("日期")


def 净值指标(label: str):
    """★ 从日净值曲线算用户体验到的那几个数。★★ 一个都不手写，全从曲线上算。"""
    d = 读日序列(label)
    if d is None or len(d) < 60:
        return None
    nv = d["净值"].astype(float)
    r = nv.pct_change().dropna()
    n = len(nv)
    年 = (n - 1) / TD
    if 年 <= 0 or nv.iloc[0] <= 0 or nv.iloc[-1] <= 0:
        return None
    年化 = (nv.iloc[-1] / nv.iloc[0]) ** (1.0 / 年) - 1.0
    峰 = nv.cummax()
    回撤 = (nv / 峰 - 1.0).min()
    # ★ 「多少天没新高」：净值低于历史峰的连续交易日最长一段
    低于峰 = (nv < 峰 - 1e-12).to_numpy()
    最长, 当前 = 0, 0
    for b in 低于峰:
        当前 = 当前 + 1 if b else 0
        最长 = max(最长, 当前)
    σ = float(r.std(ddof=1))
    return {
        "年化": float(年化),
        "最大回撤": float(回撤),
        "期末倍数": float(nv.iloc[-1] / nv.iloc[0]),
        "日波动年化": σ * np.sqrt(TD),
        "夏普_无风险按0": float(r.mean() / σ * np.sqrt(TD)) if σ > 0 else None,
        "最长没新高_交易日": int(最长),
        "交易日数": int(n),
        "年数": round(年, 3),
    }


# ───────────────────────────────────────────── 规矩㊾：N 够不够估分位数（★ 算清楚）
def 分位数能力(n: int) -> dict:
    """★★★ 这一段是本份的核心 —— 不是「感觉不够」，是把三条门槛都算出来。

    ★ ① 经验分位数要落在**真实的次序统计量**上：p 分位要 n·p ≥ 1 → n ≥ 1/p。
      ★★ 2.5% 分位 → n ≥ 40。n 比这小的时候，`np.percentile(x, 2.5)` 给的是
      ★★★ **在最小值附近做的线性插值**，不是分位数估计 —— 它永远不会低于 min。
    ★ ② 无分布假设的区间：用 [min, max] 当区间时，它覆盖总体的期望比例是 (n−1)/(n+1)。
      ★★ 要期望覆盖 95% → n ≥ 39。
    ★ ③ 秩检验（本份用的那把）：真信号在 n+1 个里的秩给单边 p = 秩/(n+1)。
      ★★★ 所以**最好情况下**能达到的 p 是 1/(n+1) —— n=10 时是 0.0909，
      ★ 也就是说 **N=10 时，这把尺子连 0.05 都够不着，跟结果好不好无关。**
    """
    return {
        "N": n,
        "①_2.5分位要的最小N": 40,
        "①_当前N能不能给2.5分位": n >= 40,
        "①_说明": ("N=%d 时 2.5%% 分位要的是第 %.2f 个次序统计量 —— 不存在，"
                   "np.percentile 只会在最小值附近插值" % (n, n * 0.025)),
        "②_minmax区间的期望覆盖": round((n - 1) / (n + 1), 4),
        "②_要期望覆盖95%的最小N": 39,
        "③_秩检验单边p的下限": round(1.0 / (n + 1), 4),
        "③_要p≤0.05的最小N": 19,
        "③_要p≤0.01的最小N": 99,
        "★★★ 结论": ("三条门槛取最严：要按规矩㊾ 报 2.5/97.5 分位数，**N ≥ 40**；"
                      "只要一个期望覆盖 95% 的无分布区间，**N ≥ 39**；"
                      "只要秩检验能摸到 p≤0.05，**N ≥ 19**。"
                      "★★★ N=10 三条**一条都不满足**。"),
    }


def 随机分布(vals: list[float], 真值: float | None, 越大越好: bool = True) -> dict:
    """★ 报规矩㊾ 要的三样 + 真值的秩。★★★ 分位数那两格按能力诚实填/留空。"""
    x = np.asarray([v for v in vals if v is not None], dtype=float)
    n = len(x)
    out = {
        "N": n,
        "随机_均值": float(x.mean()),
        "随机_中位数": float(np.median(x)),
        "随机_单次标准差": float(x.std(ddof=1)),           # ★ 规矩㊹：比单次用标准差
        "随机_均值的标准误": float(x.std(ddof=1) / np.sqrt(n)),
        "随机_最小": float(x.min()),
        "随机_最大": float(x.max()),
        # ★★★ 规矩㊾ 第三样：偏度必须跟着区间一起报
        "随机_偏度_g1无偏": float(sps.skew(x, bias=False)),
        "随机_偏度告警": ("★★ N=%d 时偏度本身的标准误约 %.2f（≈√(6/N)）—— "
                          "方向可看，数值不可引用" % (n, np.sqrt(6.0 / n))),
    }
    cap = 分位数能力(n)
    if cap["①_当前N能不能给2.5分位"]:
        out["随机_2.5分位"] = float(np.percentile(x, 2.5))
        out["随机_97.5分位"] = float(np.percentile(x, 97.5))
    else:
        out["随机_2.5分位"] = None
        out["随机_97.5分位"] = None
        out["随机_分位数为空的原因"] = cap["①_说明"]
    out["★minmax区间"] = [float(x.min()), float(x.max())]
    out["★minmax区间的期望覆盖"] = cap["②_minmax区间的期望覆盖"]

    if 真值 is not None:
        同向 = x >= 真值 if 越大越好 else x <= 真值
        不差于真值 = int(同向.sum())
        秩 = 不差于真值 + 1                     # ★ 1 = 真值最好
        out["真值"] = float(真值)
        out["真值的秩_1最好"] = int(秩)
        out["共几个_真值+随机"] = int(n + 1)
        out["秩检验_单边p"] = round(秩 / (n + 1.0), 4)
        out["秩检验_这个N的p下限"] = cap["③_秩检验单边p的下限"]
        out["真值_减_随机中位数"] = float(真值 - np.median(x))
        out["真值在随机minmax区间内吗"] = bool(x.min() <= 真值 <= x.max())
    out["规矩㊾_分位数能力"] = cap
    return out


def main() -> int:
    arms = [json.load(open(f, encoding="utf-8")) for f in glob.glob(os.path.join(ARMS, "*.json"))]
    if not arms:
        print("★★★ 一个臂文件都没读到 —— 大声报，不打空表（规矩⑯）", file=sys.stderr)
        return 2

    报告 = {
        "★本次口径": ("全收益（分红再投，策略侧与基准侧同口径，《104》）· 摩擦档跟原样臂"
                      "· 窗口 A 标签 2004 实际 2005~2014（《113》第七节）/ B 2015~2025"
                      "· 池 并池2004 全量 3,858 只 · 标签滞后 1 天"),
        "★不许引用": "基准一（同环境随机进场）本批没算（《113》第二节）",
        "★这一份比的是什么": ("H0 = 「ADV20 降序这个**排序旋钮**不比随机排序好」。"
                              "★ 只有排序这一步被随机化，进场扳机 / 仓位 / 摩擦 / 窗口 / 池子全部固定 "
                              "→ ★★★ 所以它只能证伪『排序这一步』，不能证伪进场信号。"),
        "★秩检验的前提（诚实写）": ("秩检验要求 H0 下真值与 N 个随机值可交换。"
                                   "★ 这里随机化的恰好就是被检验的那一步（排序），"
                                   "★★ 所以属于随机组合检验那一类标准设计；"
                                   "★★★ 但它检验的是这一个旋钮，换成别的旋钮要另起一组。"),
        "★★★ 规矩㊾ 的 N 门槛（与结果无关，纯算出来的）": 分位数能力(10),
        "分族": {},
        "★缺的": [],
    }

    by = {}
    for a in arms:
        段 = a["链"].split("·")[0]
        by.setdefault((段, a["族"]), {})[a["臂"]] = a

    for (段, 族) in sorted(by):
        d = by[(段, 族)]
        if "A原样" not in d:
            报告["★缺的"].append(f"{段}·{族}: 没有 A原样 臂")
            continue
        随机名 = sorted(k for k in d if k.startswith("R随机"))
        if len(随机名) < 3:
            报告["★缺的"].append(f"{段}·{族}: 随机臂只有 {len(随机名)} 条")
            continue

        块 = {"段": 段, "族": 族, "随机臂数": len(随机名), "随机臂": 随机名}

        # ① 每笔净 R —— ★ 和《113》第 4.1 节同一个量，用来对账
        块["每笔净R"] = 随机分布([d[k]["每笔净R"] for k in 随机名],
                                 d["A原样"]["每笔净R"], 越大越好=True)
        块["笔数"] = {"真臂": d["A原样"]["笔数"],
                      "随机_中位数": float(np.median([d[k]["笔数"] for k in 随机名])),
                      "随机_最小": int(min(d[k]["笔数"] for k in 随机名)),
                      "随机_最大": int(max(d[k]["笔数"] for k in 随机名))}

        # ② ★★★ 用户体验那一层：从日净值曲线算（《113》4.3 的教训：每笔口径会骗人）
        真 = 净值指标(d["A原样"]["链"])
        随机指标 = {k: 净值指标(d[k]["链"]) for k in 随机名}
        缺 = [k for k, v in 随机指标.items() if v is None]
        if 真 is None or 缺:
            报告["★缺的"].append(f"{段}·{族}: 日序列缺 真={真 is None} 随机缺={缺}")
        块["真臂_净值层"] = 真
        if 真 is not None and not 缺:
            for 字段, 越大越好 in (("年化", True), ("最大回撤", True),
                                   ("夏普_无风险按0", True),
                                   ("期末倍数", True),
                                   ("最长没新高_交易日", False)):
                块.setdefault("净值层", {})[字段] = 随机分布(
                    [随机指标[k][字段] for k in 随机名], 真[字段], 越大越好=越大越好)
        报告["分族"][f"{段}·{族}"] = 块

    json.dump(报告, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", OUT)
    print("族数", len(报告["分族"]), "缺的", 报告["★缺的"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
