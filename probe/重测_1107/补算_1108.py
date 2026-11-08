# -*- coding: utf-8 -*-
"""
★★★ 1108 补算 —— ★ **只读**已落盘的日净值，不跑回测。

★★ 补三样（都是《102》《93》和 Gemini 清单里点名要、而 出数_1107.py 还没做的）：
  ① ★★★ **尺子③ 也做配对检验**：A原样 vs 每一条随机对照臂，**逐日相减** + Newey-West（滞后 8）。
     ★ 为什么能配：两条臂同窗口、同池、同摩擦档，日净值逐日对得上 ——
       ★★ 差别只有「挑法」。★★★ 这不在跑前登记里，是**事后补的描述性检验**，
       所以 10 条臂的 t **全部列出**，不许挑其中一条当结论（这是 30 次检验，不是 1 次）。
  ② ★★ **规矩㊾ 三种 bootstrap 区间 + 偏度**：均值±2sd / 分位数 / 反向分位
     —— ★★★ 三种都排除 0 才算信号。★ 块重排用 engine.stats_gate.circular_block_sampler
       （Politis & Romano 1994），不自己另写一套。
  ③ ★ **夏普 + Lo (2002) 的自相关修正标准误**（《93》3.2 必填字段里的夏普）。

★★★ 自证脚本不许预先写结论句（规矩(53)）—— 本文件只打印数字。
"""
from __future__ import annotations
import glob, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
from engine.stats_gate import circular_block_sampler              # noqa: E402

# ★ 1108 主路：目录可配置（和跑批/出数一致），默认值不变
CURV = os.path.join(HERE, os.environ.get("XING_NAV_DIR", "日净值_1107"))
ARMS = os.path.join(HERE, os.environ.get("XING_ARMS_DIR", "arms_1107"))
B_BOOT = 2000
LAG = 8
门槛_第四档 = 3.0

窗口 = {"B_2015到2025": ("2015-01-01", "2025-12-31"),
       "A_2004到2014": ("2004-01-02", "2014-12-31")}
族链 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}


def 日收益(label: str):
    p = os.path.join(CURV, f"{label.replace('/', '_').replace(' ', '')}.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p, parse_dates=["date"]).set_index("date")
    eq = d["equity"].astype(float).dropna()
    return eq.pct_change().dropna() if len(eq) >= 30 else None


def nw_t(x: np.ndarray, L: int = LAG):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    if n < 60:
        return None
    m = x.mean(); e = x - m
    s = float((e * e).sum() / n)
    for k in range(1, L + 1):
        s += 2.0 * (1.0 - k / (L + 1.0)) * float((e[k:] * e[:-k]).sum() / n)
    return None if s <= 0 else float(m / np.sqrt(s / n))


def 偏度(x: np.ndarray) -> float:
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    sd = x.std(ddof=1)
    return float(np.nan) if sd == 0 else float((((x - x.mean()) / sd) ** 3).mean())


def 三种区间(x: np.ndarray, seed: int = 20261108) -> dict:
    """★★★ 规矩㊾：三种算法都算，三种都排除 0 才算信号。★ 块重排保住自相关。"""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    θ = float(x.mean())
    smp = circular_block_sampler(x, n_draw=len(x))
    rng = np.random.default_rng(seed)
    bs = np.array([float(np.mean(smp(rng))) for _ in range(B_BOOT)])
    sd = float(bs.std(ddof=1))
    q025, q975 = (float(v) for v in np.percentile(bs, [2.5, 97.5]))
    区 = {"均值±2sd": [θ - 2 * sd, θ + 2 * sd],
         "分位数": [q025, q975],
         "反向分位": [2 * θ - q975, 2 * θ - q025]}
    排除0 = {k: bool(lo > 0 or hi < 0) for k, (lo, hi) in 区.items()}
    return {"点估计(基点/天)": round(θ * 1e4, 3),
            "★★★偏度": round(偏度(x), 3),
            "★块长": max(1, int(np.ceil(len(x) ** (1 / 3)))), "★B": B_BOOT,
            "三种区间(基点/天)": {k: [round(lo * 1e4, 3), round(hi * 1e4, 3)]
                           for k, (lo, hi) in 区.items()},
            "逐种是否排除0": 排除0,
            "★★★三种都排除0吗": bool(all(排除0.values()))}


def 夏普(r: np.ndarray, L: int = LAG) -> dict:
    """★ 年化夏普（无风险利率记 0，和仓库里其他处一致）+ Lo (2002) 自相关修正。"""
    r = np.asarray(r, float); r = r[np.isfinite(r)]
    n = len(r); mu = r.mean(); sd = r.std(ddof=1)
    if n < 60 or sd == 0:
        return {"★算不出来": f"n={n}"}
    sr_d = mu / sd
    # ★ Lo (2002) 的 η：把 iid 年化因子 √252 换成考虑自相关之后的那个
    ρ = [float(np.corrcoef(r[:-k], r[k:])[0, 1]) for k in range(1, L + 1)]
    η = np.sqrt(252.0) / np.sqrt(1.0 + 2.0 * sum((252.0 - k) / 252.0 * ρ[k - 1]
                                                 for k in range(1, L + 1)))
    se_iid = np.sqrt((1.0 + 0.5 * sr_d ** 2) / n)          # ★ Lo (2002) 式 (9)
    return {"年化夏普(iid年化)": round(float(sr_d * np.sqrt(252.0)), 3),
            "★★★年化夏普(Lo2002自相关修正)": round(float(sr_d * η), 3),
            "★日频夏普的标准误(iid)": round(float(se_iid), 4),
            "★年化夏普t(用iid标准误)": round(float(sr_d / se_iid), 2),
            "★一阶自相关ρ1": round(ρ[0], 4), "★天数": int(n),
            "★★口径": "无风险利率记 0 · 年化因子 √252 · Lo(2002) 修正后 η="
                     f"{float(η):.3f}"}


def main() -> int:
    报 = {"★★★这一份是什么": __doc__.strip()[:1200], "逐窗口": {}}
    for 窗, (起, 止) in 窗口.items():
        块窗 = {}
        for 族, cfg in 族链.items():
            前缀 = f"{窗}·并池2004·{族}·{cfg}"
            a = 日收益(f"{前缀}·A原样")
            if a is None:
                块窗[族] = {"★算不出来": "A原样 没有日净值"}
                continue
            a = a[(a.index >= pd.Timestamp(起)) & (a.index <= pd.Timestamp(止))]
            # ① 尺子③ 配对
            随机 = sorted(glob.glob(os.path.join(CURV, f"{前缀}·R随机*.csv")))
            逐条 = {}
            for p in 随机:
                名 = os.path.basename(p)[:-4].split("·")[-1]
                b = 日收益(f"{前缀}·{名}")
                if b is None:
                    continue
                共 = a.index.intersection(b.index)
                if len(共) < 250:
                    continue
                d = (a.reindex(共) - b.reindex(共)).to_numpy(float)
                t = nw_t(d)
                逐条[名] = {"逐日差均值(基点/天)": round(float(np.nanmean(d)) * 1e4, 3),
                          "NW_t": None if t is None else round(t, 2),
                          "★天数": int(len(共))}
            ts = [v["NW_t"] for v in 逐条.values() if v["NW_t"] is not None]
            # ★ 并池：把 10 条随机臂的日收益**先按天取平均**，再和真臂配对（一次检验）
            并 = None
            if 随机:
                cols = {}
                for p in 随机:
                    名 = os.path.basename(p)[:-4].split("·")[-1]
                    b = 日收益(f"{前缀}·{名}")
                    if b is not None:
                        cols[名] = b
                if cols:
                    M = pd.DataFrame(cols).dropna(how="all")
                    共 = a.index.intersection(M.index)
                    if len(共) >= 250:
                        d = (a.reindex(共) - M.reindex(共).mean(axis=1)).to_numpy(float)
                        t = nw_t(d)
                        并 = {"★★★口径": "10 条随机臂**按天取平均**成一条「随机组合」，"
                                      "再和真臂逐日相减（★ 这是 1 次检验，不是 10 次）",
                             "逐日差均值(基点/天)": round(float(np.nanmean(d)) * 1e4, 3),
                             "★★★NW_t": None if t is None else round(t, 2),
                             "★天数": int(len(共)),
                             "★★★规矩㊾": 三种区间(d)}
            块 = {"★★★尺子③_配对检验_逐条": 逐条,
                 "★★★尺子③_配对检验_小结": {
                     "条数": len(ts),
                     "t中位": None if not ts else round(float(np.median(ts)), 2),
                     "t范围": None if not ts else [min(ts), max(ts)],
                     "★★★|t|>3 的条数": sum(1 for t in ts if abs(t) > 门槛_第四档),
                     "★★注意": "★★★ 这是 10 次检验（三族两窗共 60 次），"
                              "**不在跑前登记里** → 只当描述性，不许挑一条当结论"},
                 "★★★尺子③_并池配对": 并,
                 "★夏普_真臂": 夏普(a.to_numpy(float))}
            # ② 第四档：三种区间 + 偏度
            四 = {}
            for ma in (100, 200, 300):
                b = 日收益(f"{前缀}·B挂开关MA{ma}")
                if b is None:
                    四[f"MA{ma}"] = {"★算不出来": "没有日净值"}
                    continue
                共 = a.index.intersection(b.index)
                if len(共) < 250:
                    四[f"MA{ma}"] = {"★算不出来": f"重叠 {len(共)} 天"}
                    continue
                d = (b.reindex(共) - a.reindex(共)).to_numpy(float)
                t = nw_t(d)
                四[f"MA{ma}"] = {"NW_t": None if t is None else round(t, 2),
                               "★★★规矩㊾": 三种区间(d)}
            块["★★★第四档_规矩㊾三种区间"] = 四
            # ③ 对数收益口径（Gemini 清单 #6）—— ★ 纯算法层，照规矩 61 可以直接换
            lg = {}
            for ma in (100, 200, 300):
                b = 日收益(f"{前缀}·B挂开关MA{ma}")
                if b is None:
                    continue
                共 = a.index.intersection(b.index)
                if len(共) < 250:
                    continue
                d = (np.log1p(b.reindex(共).to_numpy(float))
                     - np.log1p(a.reindex(共).to_numpy(float)))
                t = nw_t(d)
                lg[f"MA{ma}"] = {"逐日差均值(基点/天)": round(float(np.nanmean(d)) * 1e4, 3),
                                "NW_t": None if t is None else round(t, 2)}
            块["★第四档_对数收益口径"] = lg
            块窗[族] = 块
        报["逐窗口"][窗] = 块窗
    out = os.path.join(HERE, "补算_1108.json")
    io.open(out, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写到 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
