"""
状-2 温斯坦四阶段 · 阶段跳转拓扑改动(1029 拍板)—— 重跑 + 出分布 + 出对齐物料。

================================================================================
三秒版
================================================================================
这个文件回答三个问题:
  ① 把「强制 1→2→3→4 单一循环」改成放行三条路径之后,阶段二候选多了多少、
     四个阶段的占比变了多少、被解禁的那些候选现在归到哪一类。
  ② 走平阈值换三个取值,上面那些数各是多少 ——
     ★ 这两个参数是**乘在一起**的,只报一个数会把人带偏。
  ③ 给运营出两样东西:一张参数对齐表(人读) + 一份逐日状态 CSV(机器对答案)。

★ 状-2 不产生交易信号 → 不跑回测、不出 Z 值。产出只有分布统计。

跑法:
    python -m engine.state2_topology_1029 --out engine/results_1029_状-2拓扑.json
    python -m engine.state2_topology_1029 --detail-only       # 只出逐日 CSV

★ 内存纪律:8GB 机器,串行跑,面板算完一个 spec 就丢。峰值目标 < 1.5GB。
"""

from __future__ import annotations

import gc
import json
import os
import resource
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data, state_axis_tri_1029 as tri

OUT_DEFAULT = "engine/results_1029_状-2拓扑.json"
DETAIL_CSV = "/home/claude/给运营-状-2逐日状态-10只票-1029.csv"

# ★ 恒定输出体检的报警线:某一个状态值占比超过这个数 → 这条判据几乎不产生区分
CONSTANT_ALARM = 0.95


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _cache_fingerprint() -> dict:
    """★ 共享工作树上单靠 commit hash 不足以定位一份结果 —— 把缓存身份也记下来。"""
    out = {}
    for label, path in (("ohlcv_panel.parquet", cache.PANEL_PARQUET),
                        ("panel_meta.parquet", cache.META_PARQUET)):
        if os.path.exists(path):
            st = os.stat(path)
            out[label] = {
                "path": path,
                "bytes": st.st_size,
                "构建时间(mtime, 本地)": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime)),
            }
        else:
            out[label] = "★ 拿不到:文件不存在"
    return out


def _blank(arr: np.ndarray, t: int, j: int) -> None:
    """把 [t, j) 这一段阶段二降级为 transition,★ 但不动 WARMUP 格。"""
    seg = arr[t:j]
    arr[t:j] = np.where(seg == tri.WARMUP, tri.WARMUP, "transition")


def _fwd_stats(evs: list[dict], key: str = "fwd60") -> dict:
    v = np.array([e[key] for e in evs if e.get(key) is not None], dtype=float)
    if len(v) == 0:
        return {"n": 0, "note": "★ 拿不到:没有可用样本"}
    return {
        "n": int(len(v)),
        "n_truncated(样本右端不足60日)": int(sum(1 for e in evs if e.get(key) is None)),
        "median_pct": round(float(np.median(v)) * 100, 2),
        "mean_pct": round(float(v.mean()) * 100, 2),
        "p25_pct": round(float(np.percentile(v, 25)) * 100, 2),
        "p75_pct": round(float(np.percentile(v, 75)) * 100, 2),
        "hit_rate_gt0": round(float((v > 0).mean()), 4),
    }


# ============================================================================
# 一个 spec 跑一遍:改动前(强制循环) vs 改动后(生产三路径)
# ============================================================================

def run_one_spec(symbols: list[str], spec: tri.StageSpec) -> dict:
    """
    返回这个 spec 下的全部产出。★ 面板在本函数内用完即弃,不往外带。
    """
    p = cache.load()
    cl = p["close"]
    ma = cl.rolling(150, min_periods=150).mean()
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    spy = data.load_benchmark("SPY")["close"].reindex(idx).ffill().to_numpy()

    panel_before: dict[str, np.ndarray] = {}
    panel_after: dict[str, np.ndarray] = {}
    events: list[dict] = []
    # 迁移矩阵:(改动前状态 → 改动后状态) 的「票·日」计数,只统计计分窗口内
    migrate: dict[tuple[str, str], int] = {}

    for s in symbols:
        raw = tri._raw_stage(cl[s].to_numpy(), ma[s].to_numpy(), spec)
        daily, evs = tri._confirm_sequence(raw, spec.min_bars)
        d_before, d_after = daily.copy(), daily.copy()
        c = cl[s].to_numpy()
        for k, ev in enumerate(evs):
            f_ok, _g_ok, q_ok, lab = tri._topology(ev)
            ev.update(symbol=s, path=lab, forced_ok=f_ok, prod_ok=q_ok,
                      date=str(idx[ev["i"]].date()))
            if ev["stage"] != "2":
                continue
            j = evs[k + 1]["i"] if k + 1 < len(evs) else len(daily)
            t, t60 = ev["i"], ev["i"] + 60
            ev["episode_bars"] = int(j - t)
            ev["in_window"] = bool(idx[t] >= pd.Timestamp(tri.START))
            ev["fwd60"] = ev["fwd60_excess"] = None
            if t60 < len(c) and np.isfinite(c[t]) and c[t] > 0 and np.isfinite(c[t60]):
                fwd = c[t60] / c[t] - 1.0
                ev["fwd60"] = round(float(fwd), 6)
                ev["fwd60_excess"] = round(float(fwd - (spy[t60] / spy[t] - 1.0)), 6)
            # 被挡掉的阶段二降级为 transition。
            # ★ 只改非 WARMUP 的格子:一个阶段二区间里可能夹着预热/停牌/退市后的
            #   WARMUP 格(价格 NaN)。原来是整段 slice 直接覆盖,把「没数据」
            #   写成了「震荡」—— 这两件事混在一起,运营就没法定位分叉。
            if not f_ok:
                _blank(d_before, t, j)
            if not q_ok:
                _blank(d_after, t, j)
        a, b = d_before[keep], d_after[keep]
        panel_before[s] = a
        panel_after[s] = b
        for x, y in zip(a, b):
            if x != y:
                key = (str(x), str(y))
                migrate[key] = migrate.get(key, 0) + 1
        events.extend(evs)

    s2 = [e for e in events if e["stage"] == "2" and e.get("in_window")]
    before_pass = [e for e in s2 if e["forced_ok"]]
    after_pass = [e for e in s2 if e["prod_ok"]]
    unblocked = [e for e in s2 if e["prod_ok"] and not e["forced_ok"]]

    by_path: dict[str, dict] = {}
    for e in unblocked:
        by_path.setdefault(e["path"], []).append(e)
    path_detail = {
        k: {"n": len(v),
            "后续60日": _fwd_stats(v),
            "后续60日_超额(对 SPY)": _fwd_stats(v, "fwd60_excess"),
            "阶段二持续根数_中位": float(np.median([x["episode_bars"] for x in v]))}
        for k, v in sorted(by_path.items(), key=lambda kv: -len(kv[1]))}

    # ★ 全样本(含预热)里各条路径各出现多少次 —— 用来证明 2→1→2 / 3→1→2 是 0
    all_paths = dict(pd.Series([e["path"] for e in events if e["stage"] == "2"]
                               ).value_counts())

    dist_before = tri.distribution(panel_before, tri.STAGE_STATES)
    dist_after = tri.distribution(panel_after, tri.STAGE_STATES)

    # 4→2 的时间集中度保留意见
    post = pd.Timestamp("2020-03-01")
    v42 = by_path.get("4→2", [])
    n42_post = sum(1 for e in v42 if pd.Timestamp(e["date"]) >= post)

    del panel_before, panel_after, cl, ma
    gc.collect()

    return {
        "spec": {"name": spec.name, "flat_mode": spec.flat_mode,
                 "flat_thr": spec.flat_thr, "min_bars": spec.min_bars,
                 "box_bars": spec.box_bars, "box_amp": spec.box_amp,
                 "note": spec.note},
        "阶段二候选数": {
            "原始确认(未加拓扑)": len(s2),
            "改动前_强制循环放行": len(before_pass),
            "改动后_生产三路径放行": len(after_pass),
            "被解禁(改动后多出来的)": len(unblocked),
            "改动前放行率": round(len(before_pass) / max(1, len(s2)), 4),
            "改动后放行率": round(len(after_pass) / max(1, len(s2)), 4),
        },
        "被解禁候选的归类": path_detail,
        "改动前放行组的后续60日": _fwd_stats(before_pass),
        "改动前放行组的后续60日_超额(对 SPY)": _fwd_stats(before_pass, "fwd60_excess"),
        "4→2 时间集中度(保留意见)": {
            "4→2 总次数": len(v42),
            "2020-03 之后": n42_post,
            "占比": round(n42_post / max(1, len(v42)), 4),
        },
        "全样本各路径出现次数(含预热)": {str(k): int(v) for k, v in all_paths.items()},
        "分布_改动前": dist_before,
        "分布_改动后": dist_after,
        "票日迁移(改动前→改动后, 只计分窗口内)": {
            f"{a} → {b}": n for (a, b), n in
            sorted(migrate.items(), key=lambda kv: -kv[1])},
        "恒定输出体检": constant_check(dist_after),
    }


def constant_check(dist: dict) -> dict:
    """
    ★ 硬纪律四:新实现跑完必须查「这条判据是不是几乎不产生区分」。
    某一个状态值占比 > 95% → 报警。
    """
    share = dist["state_share"]
    worst = max(share.items(), key=lambda kv: kv[1])
    alarm = worst[1] > CONSTANT_ALARM
    return {
        "最大占比状态": worst[0],
        "最大占比": worst[1],
        "报警线": CONSTANT_ALARM,
        "报警": alarm,
        "结论": ("★ 报警:这条判据几乎不产生区分 —— "
                 f"{worst[0]} 占了 {worst[1]*100:.1f}%" if alarm
                 else f"正常:最大占比 {worst[0]} {worst[1]*100:.1f}%,未触发报警线"),
    }


# ============================================================================
# 逐日明细 —— ★ 给运营对答案用,中间值必须全给
# ============================================================================

def stage_detail(sym: str, spec: tri.StageSpec) -> pd.DataFrame:
    """
    一只票的逐日状态 + 判定所依据的每一个中间值。

    ★ 为什么中间值必须给:运营对不上的时候,只知道「最后结果不一样」是没用的,
      要能定位到**哪一步开始分叉** —— 是均线不同、还是斜率不同、
      还是斜率一样但走平阈值切在了两边。
    """
    p = cache.load()
    cl = p["close"][sym]
    idx = cl.index
    c = cl.to_numpy()
    ma = cl.rolling(150, min_periods=150).mean().to_numpy()
    n = len(c)

    # 斜率 —— 和 _raw_stage 里**同一套算法**,不许另写一遍
    if spec.flat_mode == "pct_per_week":
        lag, div, unit = 10 * tri.WEEK, 10.0, "%/周(SMA150 近10周变化率 ÷ 10)"
    else:
        lag, div, unit = 20, 1.0, "%/20日(SMA150 的 20 日变化率)"
    slope = np.full(n, np.nan)
    slope[lag:] = (ma[lag:] / ma[:-lag] - 1.0) * 100.0 / div

    raw = tri._raw_stage(c, ma, spec)
    daily, evs = tri._confirm_sequence(raw, spec.min_bars)

    # 逐日:原始标签已连续几根
    raw_run = np.zeros(n, dtype=np.int64)
    cur, run = None, 0
    for i in range(n):
        if raw[i] == tri.WARMUP:
            cur, run = None, 0
        elif raw[i] == cur:
            run += 1
        else:
            cur, run = raw[i], 1
        raw_run[i] = run

    # 逐日:前序阶段 / 前前序阶段 / 当前阶段已持续天数 / 本段阶段二的路径
    # ★ 空值一律填成「尚无」/「非阶段二」,不留真空 ——
    #   留空运营会以为是数据缺失,又是一轮来回。
    prev = np.full(n, "尚无(预热期)", dtype=object)
    prev2 = np.full(n, "尚无(预热期)", dtype=object)
    path = np.full(n, "非阶段二,不适用", dtype=object)
    pass_prod = np.full(n, "非阶段二,不适用", dtype=object)
    pass_before = np.full(n, "非阶段二,不适用", dtype=object)
    stage_days = np.zeros(n, dtype=np.int64)
    after = daily.copy()

    for k, ev in enumerate(evs):
        t = ev["i"]
        j = evs[k + 1]["i"] if k + 1 < len(evs) else n
        prev[t:j] = ev["prev"] or "无"
        prev2[t:j] = ev["prev2"] or "无"
        stage_days[t:j] = np.arange(1, j - t + 1)
        if ev["stage"] == "2":
            f_ok, _g, q_ok, lab = tri._topology(ev)
            path[t:j] = lab
            pass_prod[t:j] = "放行" if q_ok else "挡掉"
            pass_before[t:j] = "放行" if f_ok else "挡掉"
            if not q_ok:
                _blank(after, t, j)

    out = pd.DataFrame({
        "日期": idx,
        "代码": sym,
        "阶段": after,
        "收盘价": np.round(c, 4),
        "MA150_150日均线": np.round(ma, 4),
        f"MA150斜率_{unit}": np.round(slope, 5),
        "走平阈值": spec.flat_thr,
        "斜率是否在走平带内": np.where(np.isfinite(slope),
                                      np.abs(slope) <= spec.flat_thr, None),
        "价格相对均线位置_pct": np.round((c / ma - 1.0) * 100.0, 4),
        "价格在均线上方": np.where(np.isfinite(ma), c > ma, None),
        "原始标签": raw,
        "原始标签已连续根数": raw_run,
        "最短持续要求根数": spec.min_bars,
        "当前阶段已持续天数": stage_days,
        "前序阶段": prev,
        "前前序阶段": prev2,
        "阶段二跳转路径": path,
        "阶段跳转_改动后是否放行": pass_prod,
        "阶段跳转_改动前是否放行": pass_before,
        "阶段_改动前": daily,
    })
    return out.loc[out["日期"] >= pd.Timestamp(tri.START)].reset_index(drop=True)


def pick_demo_symbols(symbols: list[str], spec: tri.StageSpec,
                      n_each: int = 4) -> dict:
    """
    ★ 选 10 只有代表性的票:
      · 至少一只走过 4→2(V 型反转)
      · 至少一只走过 3→2(上升中继)
      · 至少一只长期 transition
      其余按「阶段齐全」补满,好让运营一份表里能把四个阶段都对到。
    """
    p = cache.load()
    cl = p["close"]
    ma = cl.rolling(150, min_periods=150).mean()
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))

    rows = []
    for s in symbols:
        raw = tri._raw_stage(cl[s].to_numpy(), ma[s].to_numpy(), spec)
        daily, evs = tri._confirm_sequence(raw, spec.min_bars)
        paths = set()
        for k, ev in enumerate(evs):
            if ev["stage"] != "2":
                continue
            if idx[ev["i"]] < pd.Timestamp(tri.START):
                continue
            paths.add(tri._topology(ev)[3])
        a = daily[keep]
        live = a[a != tri.WARMUP]
        if len(live) < 500:          # 样本太短,对答案看不出东西
            continue
        rows.append({
            "symbol": s,
            "has_42": "4→2" in paths,
            "has_32": "3→2" in paths,
            "has_4120": "4→1→2" in paths,
            "trans_share": float((live == "transition").mean()),
            "n_stages": len({x for x in live if x in ("1", "2", "3", "4")}),
            "live": len(live),
        })
    del cl, ma
    gc.collect()

    df = pd.DataFrame(rows)
    chosen: list[str] = []
    reason: dict[str, str] = {}

    def take(sub: pd.DataFrame, why: str, k: int):
        for s in sub["symbol"]:
            if len(chosen) >= 10 or s in chosen:
                continue
            chosen.append(s)
            reason[s] = why
            k -= 1
            if k <= 0:
                return

    # 1) 走过 4→2 的,优先挑阶段齐全的
    take(df[df["has_42"]].sort_values(["n_stages", "live"], ascending=False),
         "走过 4→2(V 型反转)—— 改动后新放行的那一类", 3)
    # 2) 走过 3→2 的
    take(df[df["has_32"]].sort_values(["n_stages", "live"], ascending=False),
         "走过 3→2(上升中继)—— 改动后新放行的那一类", 3)
    # 3) 长期 transition
    take(df.sort_values("trans_share", ascending=False),
         "长期 transition —— 判不出阶段的那一类,专门用来对 transition 的边界", 2)
    # 4) 阶段齐全 + 走标准路径的
    take(df[df["has_4120"]].sort_values(["n_stages", "live"], ascending=False),
         "走过 4→1→2(标准反转)—— 改动前后都放行,用来验证改动没动到它", 2)
    take(df.sort_values(["n_stages", "live"], ascending=False), "阶段齐全,补满 10 只", 10)

    return {"symbols": chosen, "reason": reason,
            "table": df[df["symbol"].isin(chosen)].to_dict("records")}


# ============================================================================
# 主流程
# ============================================================================

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="状-2 阶段跳转拓扑改动 · 重跑")
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--csv", default=DETAIL_CSV)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--detail-only", action="store_true")
    a = ap.parse_args(argv)

    t0 = time.time()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    if a.limit:
        syms = syms[:a.limit]
    idx = cache.load()["close"].index
    win = idx[idx >= pd.Timestamp(tri.START)]
    print(f"池子 {len(syms)} 只 × 计分窗口 {len(win)} 天 "
          f"({win[0].date()} ~ {win[-1].date()}),预热自 {idx[0].date()}")
    print(f"RSS 峰值 {_rss_mb():.0f} MB")

    prod_spec = tri.STAGE_VERSIONS["XING版"]      # ★ 生产口径

    res: dict = {
        "meta": {
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd="/home/claude/xing-agent-stock_data").stdout.strip(),
            "git_commit_说明": "★ 这是**跑之前**的 HEAD。本次改动的提交在它之后。",
            "缓存身份": _cache_fingerprint(),
            "symbols": len(syms),
            "scoring_days": len(win),
            "scoring_start": str(win[0].date()),
            "scoring_end": str(win[-1].date()),
            "warmup_start": str(idx[0].date()),
            "no_backtest": "状-2 不产生交易信号 → 不跑回测、不出 Z 值。",
            "改动": {
                "改动前": "强制 1→2→3→4 单一循环(阶段二只在 4→1→2 时放行)",
                "改动后": f"放行三条路径 {tri.STAGE2_PATHS_PRODUCTION}"
                          f" + 左端截断两类 {tri.STAGE2_PATHS_LEFT_TRUNCATED}",
            },
            "走平阈值换算": tri.FLAT_THR_PER_WEEK,
        }
    }

    if not a.detail_only:
        for label, sweep in (("A_只变走平阈值(其余固定在 XING 口径)", tri.STAGE_FLAT_SWEEP),
                             ("B_按三版原样(各带自己的最短持续与箱体)", tri.STAGE_ASIS_SWEEP)):
            res[label] = {}
            for name, spec in sweep.items():
                print(f"[{label}] {name} …", flush=True)
                res[label][name] = run_one_spec(syms, spec)
                gc.collect()
                print(f"   候选 {res[label][name]['阶段二候选数']}  "
                      f"RSS {_rss_mb():.0f} MB", flush=True)

    print("选 10 只有代表性的票 …", flush=True)
    pick = pick_demo_symbols(syms, prod_spec)
    res["逐日CSV_选票"] = pick
    print("  " + ", ".join(pick["symbols"]))

    frames = [stage_detail(s, prod_spec) for s in pick["symbols"]]
    det = pd.concat(frames, ignore_index=True)
    det.to_csv(a.csv, index=False, encoding="utf-8-sig")
    print(f"写好 {a.csv}:{len(det)} 行 × {len(det.columns)} 列")
    res["逐日CSV"] = {
        "path": a.csv, "rows": len(det), "cols": list(det.columns),
        "spec": prod_spec.note,
        "每只票的阶段占比": {
            s: {k: round(v, 4) for k, v in
                det.loc[det["代码"] == s, "阶段"].value_counts(normalize=True).items()}
            for s in pick["symbols"]},
    }
    res["impl_notes"] = tri.IMPL_NOTES
    res["meta"]["RSS峰值_MB"] = round(_rss_mb(), 1)

    with open(a.out, "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print(f"写好 {a.out},用了 {time.time()-t0:.1f} 秒,RSS 峰值 {_rss_mb():.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
