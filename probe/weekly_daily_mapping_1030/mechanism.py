"""
★★ 机制核对 —— 回答协调方补充材料里的四件事。

三秒版:Gemini 说「周线领先是端点采样 vs 块均值采样的群时延,2.0~3.0 天」。
        这里拿真实数据验三件:恒等式对不对、两个可证伪预测成不成立、
        我们实测的中位 4 天和它预言的 2.5~3.0 天差在哪。

四件:
  ① 代数恒等式:周五网格上 SMA150(日线) ≡ SMA30(周内 5 日均价)—— 残差多大
  ② 占比对账:我们的 96.2%(日线格、交易日)vs Gemini 的 43.6%(周五格、周线 bar)
     ★ 是不是同一件事换了格子粒度
  ③ 预测 2:采样点从周五改周三 → 领先中位应从 −4 天缩到 ≈ −2 或 0
  ④ 预测 3:双周线(10 个交易日 1 根)SMA15 → 群时延应从 2.0 放大到 4.5 天,
     领先中位应从 −4 扩到 −6 ~ −7
  ⑤ 中位数之差的归属:(a) 离散化把 2.5~3.0 推成 0 / 5 的混合,还是 (b) 第三个机制

★ 本文件只读。engine/ 和既有 probe 一行未碰 —— 口径函数直接 import 上一轮的,
  ★ 为了让数字和 probe/phaseshift_1030 逐行可比。

跑法:python3 probe/weekly_daily_mapping_1030/mechanism.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)

from engine import cache                                  # noqa: E402
from engine import state_axis_tri_1029 as tri             # noqa: E402

# ★ 只读加载上一轮的口径函数(weekly_close / raw_stage_bars)——
#   和 probe/phaseshift_1030/run_probe.py 做的是同一件事,照抄它的做法。
_PREV = os.path.join(_REPO, "probe", "timeframe_rs_1030", "run_probe.py")
_spec = importlib.util.spec_from_file_location("_prev_probe_1030", _PREV)
prev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prev)

OUT = os.path.join(_HERE, "mechanism_1030.json")
SPEC = tri.STAGE_VERSIONS["XING版"]


# ══════════════════════════════════════════════════════════════════════════
# 工具 —— 领先滞后配对,★ 和 phaseshift_1030 的 _leadlag 同一口径
# ══════════════════════════════════════════════════════════════════════════

def _flips(raw) -> list[tuple[int, str]]:
    out, cur = [], None
    for i, r in enumerate(raw):
        if r in ("ADV", "FLAT", "DEC") and r != cur:
            out.append((i, r))
            cur = r
    return out


def _leadlag(A: dict, B: dict, syms, tol: int, unit: str) -> dict:
    """★ 正 = A 先转。B 的每个事件去配 A 里同标签、最近、未被用过的那个。"""
    g = []
    for s in syms:
        a, b = A[s], B[s]
        used = set()
        for pb, r in b:
            best, bg = None, None
            for j, (pa, ra) in enumerate(a):
                if j in used or ra != r:
                    continue
                d = pb - pa
                if abs(d) <= tol and (bg is None or abs(d) < abs(bg)):
                    best, bg = j, d
            if best is not None:
                used.add(best)
                g.append(int(bg))
    arr = np.asarray(g)
    if arr.size == 0:
        return {"★": "一个都没配上"}
    return {
        "单位": unit, "配对容差": f"±{tol} {unit}", "配上的对数": int(arr.size),
        "中位": float(np.median(arr)), "均值": round(float(arr.mean()), 3),
        "下四分位": float(np.percentile(arr, 25)),
        "上四分位": float(np.percentile(arr, 75)),
        "A先(>0)比例": round(float((arr > 0).mean()), 4),
        "同时(=0)比例": round(float((arr == 0).mean()), 4),
        "B先(<0)比例": round(float((arr < 0).mean()), 4),
        "_arr": arr.tolist(),
    }


def _strip(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "_arr"}


# ══════════════════════════════════════════════════════════════════════════
# ① 代数恒等式
# ══════════════════════════════════════════════════════════════════════════

def identity_check(cl: pd.DataFrame) -> dict:
    """
    SMA150(日线) 取到周五格  ≟  SMA30(周内 5 日均价)
    ★ 前者是「过去 150 个交易日收盘的均值」;后者是「过去 30 个『周内 5 日均价』的均值」。
      两者展开后是同一个 150 项等权和 —— 只要每周恰好 5 个交易日。
    ★ 所以真实数据上残差**不会**是 0:美股有假期短周(实测 112 个 4 天周、2 个更短)。
      这一条必须说清,否则「残差 2.8e-14」会被当成在真实数据上成立。
    """
    sma_d = cl.rolling(150, min_periods=150).mean()
    # 周内 5 日均价(每周一根),再取 30 周均值
    wk_mean = cl.resample("W-FRI").mean()
    sma_w_of_mean = wk_mean.rolling(30, min_periods=30).mean()
    fri = sma_d.reindex(sma_w_of_mean.index, method="ffill")
    diff = (sma_w_of_mean - fri).abs()
    rel = (diff / fri.abs()).loc["2018-01-01":"2025-12-31"]
    a = rel.to_numpy(float).ravel()
    a = a[np.isfinite(a)]

    # ★ 只取「前 30 周全是 5 天周」的格子 —— 恒等式的前提成立的那些格子
    cnt = cl.iloc[:, 0].groupby(pd.Grouper(freq="W-FRI")).size()
    full = cnt.rolling(30, min_periods=30).min() == 5
    idx_full = full[full.fillna(False)].index
    rel_full = rel.reindex(rel.index.intersection(idx_full))
    b = rel_full.to_numpy(float).ravel()
    b = b[np.isfinite(b)]

    return {
        "题目": "周五网格上 SMA150(日线) ≟ SMA30(周内 5 日均价)",
        "★这是恒等式的前提": "每周恰好 5 个交易日。实测 513 个 5 天周、112 个 4 天周、2 个更短。",
        "全部格子_相对残差": {
            "中位": float(np.median(a)), "p95": float(np.percentile(a, 95)),
            "最大": float(a.max()), "n": int(a.size)},
        "★只取前30周全是5天周的格子_相对残差": {
            "中位": float(np.median(b)) if b.size else None,
            "p95": float(np.percentile(b, 95)) if b.size else None,
            "最大": float(b.max()) if b.size else None, "n": int(b.size)},
        "★结论": (
            "恒等式在「连续 30 个 5 天周」的格子上成立到浮点精度;"
            "★ 但真实美股日历里这样的格子只占一部分 —— 有假期短周时两边**不等**。"
            "所以 Gemini 给的『残差 2.8e-14』只在合成的满 5 天日历上成立,"
            "★ 真实数据上必须带这个限定说。"),
    }


def group_delay() -> dict:
    """端点采样 vs 块均值采样的群时延 —— 纯算术,不用数据。"""
    # 150 个交易日窗口,最新一根编号 0,最老 149
    #  端点采样(周五收盘):每周取 1 个点 → 取到的是 0, 5, 10, ... 145
    endpoint = np.arange(0, 150, 5)
    #  块均值采样:每周 5 天全取 → 0..149
    block = np.arange(0, 150)
    return {
        "题目": "群时延(重心)—— 端点采样 vs 块均值采样",
        "端点采样_重心": float(endpoint.mean()),
        "块均值采样_重心": float(block.mean()),
        "★群时延差_交易日": round(float(block.mean() - endpoint.mean()), 2),
        "★算术": "块均值重心 74.5 − 端点重心 72.5 = 2.0 个交易日。"
                  "一般式:(k−1)/2,k = 每根 bar 的交易日数。",
        "双周线(k=10)的预言": round((10 - 1) / 2, 2),
        "★和Gemini给的数对账": "2.0 / 72.5 / 74.5 三个数全部对上。",
    }


# ══════════════════════════════════════════════════════════════════════════
# ②③④⑤ 采样点与 bar 宽度的扫描
# ══════════════════════════════════════════════════════════════════════════

def _resample_close(cl: pd.DataFrame, rule: str) -> pd.DataFrame:
    return cl.resample(rule).last().dropna(how="all")


def _nbar_close(cl: pd.DataFrame, n: int) -> pd.DataFrame:
    """每 n 个**交易日**取一根 bar(取该段最后一个交易日的收盘)。"""
    pos = np.arange(len(cl))
    grp = pos // n
    out = cl.groupby(grp).last()
    out.index = cl.index[[np.flatnonzero(grp == g)[-1] for g in out.index]]
    return out


def sampling_scan(cl: pd.DataFrame, syms) -> dict:
    """
    对照组:日线 SMA150 的 RAW 转向(★ 在**日线格**上,不网格化)。
    实验组:各种采样方案的长期均线 RAW 转向,位置映射回日线格。
    ★ 正 = 日线先;负 = 实验组(周线侧)先。和附录五同一个符号约定。
    """
    idx = cl.index
    pos_of = {t: i for i, t in enumerate(idx)}
    ma_d = cl.rolling(150, min_periods=150).mean()
    raw_d = {s: prev.raw_stage_bars(cl[s].to_numpy(), ma_d[s].to_numpy(),
                                    SPEC.flat_thr, 10 * tri.WEEK, 10.0)
             for s in syms}
    fd = {s: _flips(raw_d[s]) for s in syms}

    cases = [
        ("周五采样_SMA30周(基线,= 附录五的 RAW 层)", "W-FRI", 30),
        ("★预测2_周三采样_SMA30周", "W-WED", 30),
        ("周一采样_SMA30周(对称性旁证)", "W-MON", 30),
        ("周二采样_SMA30周(对称性旁证)", "W-TUE", 30),
        ("周四采样_SMA30周(对称性旁证)", "W-THU", 30),
    ]
    out = {}
    for label, rule, per in cases:
        wk = _resample_close(cl, rule)
        ma_w = wk.rolling(per, min_periods=per).mean()
        fw = {}
        for s in syms:
            rw = prev.raw_stage_bars(wk[s].to_numpy(), ma_w[s].to_numpy(),
                                     SPEC.flat_thr, 10, 10.0)
            # 周线 bar 位置 → 日线格位置
            fw[s] = [(pos_of[wk.index[i]], r) for i, r in _flips(rw)
                     if wk.index[i] in pos_of]
        out[label] = _leadlag(fd, fw, syms, 40, "交易日")

    # ★ 预测 3:双周线 —— 每 10 个交易日一根,SMA15(15 × 10 = 150 日)
    for n, per, tag in ((10, 15, "★预测3_双周线(10个交易日1根)_SMA15"),
                        (5, 30, "单周线(5个交易日1根)_SMA30 —— 对照,应与周五采样同量级"),
                        (20, 8, "四周线(20个交易日1根)_SMA8(=160日,最接近150的整数)")):
        bb = _nbar_close(cl, n)
        ma_b = bb.rolling(per, min_periods=per).mean()
        fb = {}
        for s in syms:
            rb = prev.raw_stage_bars(bb[s].to_numpy(), ma_b[s].to_numpy(),
                                     SPEC.flat_thr, 10, 10.0)
            fb[s] = [(pos_of[bb.index[i]], r) for i, r in _flips(rb)
                     if bb.index[i] in pos_of]
        out[tag] = _leadlag(fd, fb, syms, 40, "交易日")
        out[tag]["群时延预言_交易日"] = round((n - 1) / 2, 2)
    return out


def reconcile_grid(base: dict) -> dict:
    """
    ★★ ② 占比对账:同一批事件,在**日线格(交易日)**上量 vs 在**周五格(周线 bar)**上量。
    ★ 把每个领先量除以 5 并向零取整(= 「差不到一整根 bar 就算并列」),
      这正是 Gemini 在周五格上以周线 bar 为单位量时发生的事。
    """
    arr = np.asarray(base["_arr"], dtype=float)
    bars = np.trunc(arr / 5.0)        # 向零取整
    return {
        "题目": "我们的 96.2%(日线格 · 交易日)vs Gemini 的 43.6%(周五格 · 周线 bar)",
        "日线格_交易日": {
            "n": int(arr.size),
            "周线先(<0)": round(float((arr < 0).mean()), 4),
            "并列(=0)": round(float((arr == 0).mean()), 4),
            "日线先(>0)": round(float((arr > 0).mean()), 4),
            "中位": float(np.median(arr)),
        },
        "★同一批事件_换成周线bar粒度": {
            "n": int(bars.size),
            "周线先(<0)": round(float((bars < 0).mean()), 4),
            "并列(=0)": round(float((bars == 0).mean()), 4),
            "日线先(>0)": round(float((bars > 0).mean()), 4),
            "中位": float(np.median(bars)),
        },
        "★周线先或并列_日线格": round(float((arr <= 0).mean()), 4),
        "★周线先或并列_周线bar格": round(float((bars <= 0).mean()), 4),
    }


def quantization(base: dict) -> dict:
    """
    ★★ ⑤ 中位数之差的归属:机制预言连续领先 2.0~3.0 个交易日,
       我们实测 RAW 中位 −4。是离散化造成的,还是另有机制?

    判法:看领先量的**直方图**。
      · 若是「连续 2.5~3.0 被周五网格离散化」→ 质量应堆在 0 和 −5 两处(以及 −5 的倍数),
        中间的 −1 −2 −3 −4 应该很空。
      · 若直方图在 −1..−9 上是**连续铺开**的 → 离散化解释不掉,是第三个机制。
    """
    arr = np.asarray(base["_arr"], dtype=int)
    cnt = Counter(arr.tolist())
    hist = {int(k): int(cnt[k]) for k in sorted(cnt)}
    neg = arr[arr < 0]
    mod5 = Counter((-neg % 5).tolist())
    on_grid = int(sum(v for k, v in mod5.items() if k == 0))
    return {
        "题目": "RAW 层领先量的直方图 —— 中位 −4 是「0 和 −5 的混合」还是连续分布",
        "直方图_交易日": hist,
        "负侧_对5取模的分布": {int(k): int(v) for k, v in sorted(mod5.items())},
        "★负侧落在5的整数倍上的比例": round(on_grid / max(1, neg.size), 4),
        "★若是纯离散化_这个比例应接近1": "实测见上。",
        "负侧样本量": int(neg.size),
        "中位": float(np.median(arr)),
        "均值": round(float(arr.mean()), 3),
    }


def main() -> None:
    p = cache.load()
    syms = list(cache.symbols())
    cl = p["close"][syms]
    print(f"★ {len(syms)} 只票,{len(cl)} 个交易日")

    res = {"样本": {"票数": len(syms), "交易日数": int(len(cl)),
                    "窗口": f"{cl.index[0].date()} ~ {cl.index[-1].date()}"}}
    res["①代数恒等式"] = identity_check(cl)
    res["①b群时延算术"] = group_delay()
    print("  ① 恒等式 / 群时延 ✓")

    scan = sampling_scan(cl, syms)
    base_key = "周五采样_SMA30周(基线,= 附录五的 RAW 层)"
    res["②占比对账"] = reconcile_grid(scan[base_key])
    res["⑤中位数归属_离散化还是第三机制"] = quantization(scan[base_key])
    res["③④采样点与bar宽度扫描"] = {k: _strip(v) for k, v in scan.items()}
    print("  ②③④⑤ 扫描 ✓")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"→ {OUT}\n")
    for k in ("①代数恒等式", "①b群时延算术", "②占比对账",
              "⑤中位数归属_离散化还是第三机制"):
        print(f"── {k} ──")
        print(json.dumps(res[k], ensure_ascii=False, indent=1))
    print("── ③④ 扫描(只看中位与占比) ──")
    for k, v in res["③④采样点与bar宽度扫描"].items():
        print(f"  {k}: 中位={v.get('中位')} 周线先={v.get('B先(<0)比例')} "
              f"并列={v.get('同时(=0)比例')} n={v.get('配上的对数')} "
              f"群时延预言={v.get('群时延预言_交易日', '—')}")


if __name__ == "__main__":
    main()
