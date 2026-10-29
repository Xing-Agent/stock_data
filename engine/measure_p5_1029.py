"""
measure_p5_1029 —— 批五修正的实测脚本(2026-10-29)。不跑链,只量东西。

大白话(三秒):专家这次给的是【能被我们的数据否掉的预测】。
这个脚本把那几个数真的量出来,和它给的数逐一对上去 ——
★ 对不上就写对不上,不许因为是专家说的就往那个方向解释。

量四件:
  第二件 · 走带
    ① 连续穿轨天数的【游程分布】—— 它预测 k=1 约 78% / k=2 约 16% /
       k≥4 不足 2.5%。★ 逐一对比。
    ② k≥3 子样本的【最大逆向波动 MAE】—— 它预测单笔平均跌幅超 −28%。
       ★ 另外单独报「跳空穿透止损」的比例。
    ③ 触轨后 20 日收益的【完整分位分布】(p1/p5/p25/p50/p75/p95/p99)
       —— 验证「期望略正 + 左尾厚尾负偏」这个形状。
  第一件 · 技-11
    ④ 下刺深度分档(≤0.3 / 0.3~0.8 / 0.8~1.5 / >1.5 ATR)的后续 60 日表现
       —— ★ 验证「越深越好」是否单调,★ 以及 >1.5ATR 是否真的该禁。

★ 窗口:预热 2014 起,统计 2018-01-02 .. 2025-12-31。
★ 游程口径:游程在**全历史数组**上找,只保留【起点落在统计窗口内】的游程
  —— ★ 先按窗口裁数组再找游程会把窗口边界上的游程切断,分布就假了
  (旧的 pat6_measure.q4 就是先裁后找,★ 本脚本的分布与它不可直接比)。

跑法:python3 -m engine.measure_p5_1029
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data, matrices, pat6_ops

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_批五实测.json")

CONSTANT_ALARM = 0.95          # ★ 恒定输出体检报警线(硬纪律 6)


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _cache_fingerprint() -> dict:
    out = {}
    for label, path in (("ohlcv_panel.parquet", cache.PANEL_PARQUET),
                        ("panel_meta.parquet", cache.META_PARQUET)):
        st = os.stat(path)
        out[label] = {"path": path, "bytes": st.st_size,
                      "构建时间(mtime, 本地)": time.strftime(
                          "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
    return out


def _perf_mask(index) -> np.ndarray:
    return np.asarray((index >= pd.Timestamp(data.PERF_START))
                      & (index <= pd.Timestamp(data.PERF_END)))


def _dist(a, qs=(1, 5, 10, 25, 50, 75, 90, 95, 99)) -> dict:
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "均值": float(a.mean()),
            "标准差": float(a.std(ddof=1)) if a.size > 1 else None,
            "偏度": float(pd.Series(a).skew()) if a.size > 2 else None,
            **{f"p{p}": float(np.percentile(a, p)) for p in qs}}


# ===========================================================================
# 第二件 ① · 连续穿轨天数的游程分布
# ===========================================================================

def q_run_length(syms: list[str], period: int = 20, k: float = 2.0) -> dict:
    _, _, lo, _, _ = pat6_ops.bollinger(period, k, syms)
    close = cache.field("close", syms)
    idx = close.index
    pm = _perf_mask(idx)
    below = np.asarray((close < lo).fillna(False).to_numpy(bool))

    runs = []                               # 每个游程:(起点行, 长度)
    T, N = below.shape
    for j in range(N):
        col = below[:, j]
        i = 0
        while i < T:
            if col[i]:
                s = i
                while i < T and col[i]:
                    i += 1
                runs.append((s, i - s))
            else:
                i += 1
    # ★ 只保留起点落在统计窗口内的游程
    runs = [(s, L) for s, L in runs if pm[s]]
    lens = np.asarray([L for _, L in runs], dtype=int)
    tot = int(lens.size)

    share = {}
    for kk in range(1, 8):
        share[f"k={kk}"] = round(float((lens == kk).mean()), 4) if tot else None
    share["k≥4"] = round(float((lens >= 4).mean()), 4) if tot else None
    share["k≥3"] = round(float((lens >= 3).mean()), 4) if tot else None
    share["k≥8"] = round(float((lens >= 8).mean()), 4) if tot else None

    pred = {"k=1": 0.78, "k=2": 0.16, "k≥4": 0.025}
    compare = []
    for key, p in pred.items():
        got = share.get(key)
        compare.append({
            "项": key, "专家预测": p, "我们实测": got,
            "差": round(got - p, 4) if got is not None else None,
            "★对上了吗": ("★★ 没对上" if got is None or abs(got - p) > 0.05
                          else "对上了(差 ≤5 个百分点)"),
        })
    # ★ 恒定输出体检(硬纪律 6):某一个 k 值占比 >95% → 这个分布几乎不产生区分
    mx = max([v for kk, v in share.items() if kk.startswith("k=")
              and v is not None], default=0.0)
    return {
        "题目": "第二件① 走带:收盘价连续位于布林下轨下方的游程长度 k 的分布",
        "★口径": f"布林带 {period} 日 / ±{k}σ(原著标准);"
                  f"穿轨 = 收盘 < 下轨;一个游程算一条;"
                  f"★ 游程在全历史上找,只保留起点落在 {data.PERF_START} 之后的",
        "游程总数": tot,
        "逐k占比": share,
        "长度分布": _dist(lens, qs=(50, 75, 90, 95, 99)),
        "最长游程天数": int(lens.max()) if tot else 0,
        "★★ 逐一对比专家预测": compare,
        "恒定输出体检": ("★★ 报警:某一个 k 值占比 >95%,这个分布几乎不产生区分"
                         if mx > CONSTANT_ALARM else
                         f"过(最大单值占比 {mx:.1%} ≤ {CONSTANT_ALARM:.0%})"),
        "怎么读": "★ 对上 → 它的框架成立,我们之前量的「单点触轨反转概率」确实量错了;"
                  "★ 对不上 → 必须说明差在哪,不许往它的方向解释。",
    }


# ===========================================================================
# 第二件 ② · k≥3 子样本的 MAE + 跳空穿透止损
# ===========================================================================

def q_tail_risk(syms: list[str], period: int = 20, k: float = 2.0,
                atr_period: int = 14, stop_atr_mult: float = 0.3) -> dict:
    _, _, lo, _, _ = pat6_ops.bollinger(period, k, syms)
    close = cache.field("close", syms)
    low = cache.field("low", syms)
    opn = cache.field("open", syms)
    atr = matrices.atr_matrix(atr_period, syms)
    idx = close.index
    pm = _perf_mask(idx)
    below = np.asarray((close < lo).fillna(False).to_numpy(bool))
    ca, la, oa, aa = (close.to_numpy(float), low.to_numpy(float),
                      opn.to_numpy(float), atr.to_numpy(float))
    T, N = below.shape

    # 先把每个游程找出来(全历史),再按起点落窗口筛
    episodes = []
    for j in range(N):
        col = below[:, j]
        i = 0
        while i < T:
            if col[i]:
                s = i
                while i < T and col[i]:
                    i += 1
                if pm[s]:
                    episodes.append((j, s, i - s))
            else:
                i += 1

    def _bucket(sel_len) -> dict:
        """
        口径(逐条写死,★ 不许靠猜):
          · 触发日 d = 游程里第 k0 根(k0 = min(3, 游程长度)),
            即「走带被认出来的那一天」—— ★ k≥3 的子样本里 d = 第 3 根
          · 进场价 = d 的次日开盘(和引擎的 fill: next_open 一致)
          · MAE_H = min over 未来 H 天的 (Low / 进场价 − 1)
          · 止损 = Low(d) − stop_atr_mult × ATR(d)(= 引擎 day_low_minus_atr)
          · 跳空穿透 = 未来 H 天里出现某一天 Open < 止损
        """
        rows_mae = {20: [], 60: []}
        rows_mae_walk = []
        gap20, gap60, fwd20 = [], [], []
        used = 0
        for j, s, L in episodes:
            if not sel_len(L):
                continue
            k0 = min(3, L)
            d = s + k0 - 1
            e = d + 1                                  # 次日开盘进场
            if e >= T or not np.isfinite(oa[e, j]) or oa[e, j] <= 0:
                continue
            px = oa[e, j]
            stop = la[d, j] - stop_atr_mult * aa[d, j]
            used += 1
            for H in (20, 60):
                hi = min(T, e + H)
                seg = la[e:hi, j]
                seg = seg[np.isfinite(seg)]
                if seg.size:
                    rows_mae[H].append(seg.min() / px - 1.0)
                op = oa[e:hi, j]
                g = bool(np.nanmin(op) < stop) if np.isfinite(op).any() else False
                (gap20 if H == 20 else gap60).append(g)
            # 走带结束为止(游程剩余 + 之后 1 天)
            hi = min(T, s + L + 1)
            seg = la[e:hi, j]
            seg = seg[np.isfinite(seg)]
            if seg.size:
                rows_mae_walk.append(seg.min() / px - 1.0)
            # 20 日收益(收盘对收盘,从进场价起算)
            u = e + 20
            if u < T and np.isfinite(ca[u, j]):
                fwd20.append(ca[u, j] / px - 1.0)
        return {
            "子样本笔数": used,
            "★MAE_未来20日": _dist(rows_mae[20], qs=(1, 5, 25, 50, 75, 95, 99)),
            "★MAE_未来60日": _dist(rows_mae[60], qs=(1, 5, 25, 50, 75, 95, 99)),
            "MAE_到走带结束为止": _dist(rows_mae_walk, qs=(1, 5, 25, 50, 75, 95, 99)),
            "★跳空穿透止损比例_20日窗口":
                round(float(np.mean(gap20)), 4) if gap20 else None,
            "跳空穿透止损比例_60日窗口":
                round(float(np.mean(gap60)), 4) if gap60 else None,
            "进场后20日收益": _dist(fwd20, qs=(1, 5, 25, 50, 75, 95, 99)),
        }

    out = {
        "题目": "第二件② 条件尾部风险:k≥3 子样本的最大逆向波动 MAE,"
                "以及跳空穿透止损的比例",
        "★口径": "触发日 = 游程第 3 根(k≥3 子样本);进场 = 次日开盘"
                  "(和引擎 fill: next_open 一致);"
                  f"止损 = 触发日 Low − {stop_atr_mult}×ATR{atr_period}"
                  "(和引擎 day_low_minus_atr 一致);"
                  "MAE = 未来 H 天最低价相对进场价的最大跌幅",
        "k≥3(走带)": _bucket(lambda L: L >= 3),
        "k=1(对照)": _bucket(lambda L: L == 1),
        "k=2(对照)": _bucket(lambda L: L == 2),
        "k≥4(真正的走带)": _bucket(lambda L: L >= 4),
    }
    m = out["k≥3(走带)"]["★MAE_未来60日"].get("均值")
    out["★★ 对比专家预测的 −28%"] = {
        "专家预测": -0.28,
        "我们实测_k≥3_MAE未来60日均值": round(m, 4) if m is not None else None,
        "★对上了吗": ("拿不到" if m is None else
                      ("对上了" if abs(m - (-0.28)) <= 0.05 else "★★ 没对上")),
        "★注": "MAE 的量级对 H(看多久)极度敏感 —— 所以三个 H 都报出来,"
                "★ 不许只挑一个对得上的报。",
    }
    return out


# ===========================================================================
# 第二件 ③ · 触轨后 20 日收益的完整分位分布
# ===========================================================================

def q_tag_tail_shape(syms: list[str], period: int = 20, k: float = 2.0) -> dict:
    _, _, lo, _, _ = pat6_ops.bollinger(period, k, syms)
    close = cache.field("close", syms)
    idx = close.index
    pm = _perf_mask(idx)
    tag = np.asarray((close < lo).fillna(False).to_numpy(bool))
    ca = close.to_numpy(float)
    T, N = tag.shape
    out = {"题目": "第二件③ 触轨后 20 日收益的完整分布 —— "
                   "验证「期望略正 + 左尾厚尾负偏」这个形状",
           "★口径": f"布林带 {period}/{k}σ;触轨 = 收盘 < 下轨;"
                     "每一个触轨日×票算一条(★ 不做事件化,"
                     "所以同一段走带里的每一天都算一条);"
                     "收益 = Close_{t+H}/Close_t − 1"}
    for H in (20, 60):
        nxt = np.full_like(ca, np.nan)
        nxt[:-H, :] = ca[H:, :]
        r = nxt / ca - 1.0
        sel = tag & pm[:, None] & np.isfinite(r)
        rr = r[sel]
        d = _dist(rr)
        d["★继续下跌比例"] = round(float((rr < 0).mean()), 4) if rr.size else None
        d["★跌超20%的比例"] = round(float((rr < -0.20).mean()), 4) if rr.size else None
        d["★跌超40%的比例"] = round(float((rr < -0.40).mean()), 4) if rr.size else None
        d["涨超20%的比例"] = round(float((rr > 0.20).mean()), 4) if rr.size else None
        # 左右尾厚度对比:|p1| vs p99,以及均值 − 中位(负偏的另一种看法)
        if rr.size:
            d["★左尾/右尾厚度比_|p1|÷p99"] = (
                round(abs(d["p1"]) / d["p99"], 3) if d["p99"] > 0 else None)
            d["均值−中位"] = round(d["均值"] - d["p50"], 5)
        out[f"{H}日"] = d
    out["怎么读"] = ("★ 均值略正、中位也正、但 p1/p5 比 p95/p99 的绝对值大很多 "
                     "→ 就是专家说的「期望略正 + 左尾厚尾负偏」;"
                     "★ 如果左右尾差不多厚,那这个形状在我们数据上不成立。")
    return out


# ===========================================================================
# 第一件 ③ · 下刺深度分档的后续 60 日表现
# ===========================================================================

def q_spring_depth(syms: list[str]) -> dict:
    close = cache.field("close", syms)
    ca = close.to_numpy(float)
    cols = {s: i for i, s in enumerate(close.columns)}
    idx = close.index
    pm = _perf_mask(idx)

    def _fwd(df, row_col):
        v20, v60 = [], []
        for _, r in df.iterrows():
            i, j = int(r[row_col]), cols[r["symbol"]]
            for H, box in ((20, v20), (60, v60)):
                u = i + H
                box.append(ca[u, j] / ca[i, j] - 1.0 if u < len(idx) else np.nan)
        df = df.copy()
        df["fwd20"], df["fwd60"] = v20, v60
        return df

    def _buckets(df, row_col, name):
        df = _fwd(df[df[row_col].map(lambda r: bool(pm[int(r)]))].copy(), row_col)
        edges = [(0.0, 0.3, "≤0.3 ATR"), (0.3, 0.8, "0.3~0.8 ATR"),
                 (0.8, 1.5, "0.8~1.5 ATR"), (1.5, 1e9, "★ >1.5 ATR(专家说该禁)")]
        rows = []
        for lo, hi, nm in edges:
            g = df[(df["dep_atr"] >= lo) & (df["dep_atr"] < hi)]
            d = {"深度档": nm, "个数": int(len(g)),
                 "占比": round(len(g) / max(1, len(df)), 4)}
            for H in (20, 60):
                a = g[f"fwd{H}"].dropna().to_numpy(float)
                d[f"★{H}日均值"] = round(float(a.mean()), 5) if a.size else None
                d[f"{H}日中位"] = round(float(np.median(a)), 5) if a.size else None
                d[f"{H}日上涨比例"] = (round(float((a > 0).mean()), 4)
                                       if a.size else None)
                d[f"{H}日p5"] = round(float(np.percentile(a, 5)), 5) if a.size else None
                d[f"{H}日n"] = int(a.size)
            rows.append(d)
        means = [r["★60日均值"] for r in rows if r["★60日均值"] is not None]
        mono = (len(means) == len(rows)
                and all(means[i] < means[i + 1] for i in range(len(means) - 1)))
        return {"母集": name, "母集总数": int(len(df)), "逐档": rows,
                "★「越深越好」是否单调递增(按 60 日均值)":
                    "★ 单调" if mono else "★★ 不单调"}

    pool = pat6_ops.spring_day1_pool(
        syms, lookback=20, min_age=4, atr_period=14, vol_slow=50,
        reclaim_atr_multiple=0.10, spring_vol_min_ratio=1.0)
    two, diag = pat6_ops.spring_two_day(
        syms, dict(lookback=20, min_bars_before=4, atr_period=14,
                   reclaim_atr_multiple=0.10, spring_vol_min_ratio=1.0,
                   depth_hard_cap_atr=None, test_max_bars=3,
                   test_vol_max_ratio=0.65, vol_slow_period=50))

    out = {
        "题目": "第一件③ 下刺深度分档的后续表现 —— 验证「越深越好」是否单调,"
                "以及 >1.5ATR 是否真的该禁",
        "★口径": "深度 = (前 20 日低点 − 当日最低价) / ATR14;"
                  "后续收益从【信号日收盘】起算(★ 不含滑点与摩擦,"
                  "★ 这不是交易成绩,只是形态的事后分布)",
        "母集A_Spring日(下刺+收复+当日量≥1.0×SMA50,★ 不设深度上限)":
            _buckets(pool, "row", "Day 1 Spring 母集"),
    }
    if len(diag):
        d2 = diag.rename(columns={"test_row": "row"})
        out["母集B_两日结构事件(Spring量≥1.0× + Test窗口3日缩量≤0.65×)"] = \
            _buckets(d2, "row", "两日结构事件(按 Test 日起算)")
        out["母集B_深度分布"] = _dist(diag["dep_atr"].to_numpy(float),
                                      qs=(5, 25, 50, 75, 95))
    out["怎么读"] = ("★ 如果 60 日均值随深度单调上升 → 「下刺越深反而越好」成立;"
                     "★ >1.5ATR 这一档要分开看:均值高但 p5 极差 = "
                     "它是「赢多赔大」而不是「该禁」;均值也差 = 该禁。")
    return out


# ===========================================================================

def main() -> int:
    t0 = time.time()
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    pat6_ops.install()
    syms = cache.symbols()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    print(f"池子 {len(syms)} 只;统计窗口 {data.PERF_START} .. {data.PERF_END}")

    out = {"git_commit": head, "池子只数": len(syms),
           "统计窗口": [data.PERF_START, data.PERF_END],
           "缓存身份": _cache_fingerprint()}
    for name, fn in (("第二件①_走带游程分布", q_run_length),
                     ("第二件②_k≥3尾部风险与跳空", q_tail_risk),
                     ("第二件③_触轨后收益完整分布", q_tag_tail_shape),
                     ("第一件③_下刺深度分档", q_spring_depth)):
        t = time.time()
        print(f"\n跑 {name} ...")
        out[name] = fn(syms)
        print(f"  用了 {time.time()-t:.1f} 秒;RSS {_rss_mb():.0f} MB")
        print(json.dumps(out[name], ensure_ascii=False, indent=1)[:3000])

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(总共 {time.time()-t0:.0f} 秒;峰值 RSS {_rss_mb():.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
