"""跑 11 条特征 × 两个池口径 × 五个年份段,输出原始表 + 汇总表。"""
from __future__ import annotations
import os, sys, json, time
import numpy as np
import pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)

import engine.data as D                       # noqa: E402
import features_1030 as F                     # noqa: E402
import pool_map_1030 as PM                    # noqa: E402

PERIODS = PM.PERIODS

#: 特征登记表:代号 → (名字, 主数值列, 判定方式, 最小事件数, 事件数列)
#  判定方式:fix0.5 = 固定 0.5 切两档 / tercile = 按当段全池三分位 / med = 按当段全池中位
FEATS = [
    ("T1", "它怎么做顶(二次触顶占比)",      "share_double_top",      "fix0.5",  4,   "n_tops"),
    ("T2", "它怎么做底(磨底占比)",          "share_grind",           "fix0.5",  4,   "n_bottoms"),
    ("T3", "顶底间距(顶→底跌幅中位)",       "median_top_to_bottom",  "tercile", 6,   "n_swings"),
    ("T4", "假突破率",                       "fake_breakout_rate",    "fix0.5",  5,   "n_breakouts"),
    ("F1", "跳空习惯(3 交易日回补率)",       "gap_fill_rate",         "fix0.5",  10,  "_n_F1"),
    ("F2", "波动聚集(大波动后 3 日倍数)",    "vol_cluster_ratio",     "tercile", 10,  "n_bigdays"),
    # ★★ F3 有两种写法,必须两边都报(文档括号里只写了宽定义,但文档举的数
    #   「全池中位 11%」只有严定义才接近 —— 宽定义机械地就在 50%)
    ("F3a", "长上影线频率(宽:收在下半部)",  "upper_wick_share",      "med",     200, "_n_F3"),
    ("F3b", "长上影线频率(严:还要上影≥半根)", "upper_wick_strict_share", "med",   200, "_n_F3"),
    ("F4", "均线反应(50 日线反弹率)",        "ma_bounce_rate",        "fix0.5",  5,   "n_ma_touch"),
    ("F5", "财报后漂移(方向一致率)",         "pead_agree_rate",       "fix0.5",  8,   "n_earnings"),
    ("F6", "和大盘的关系(beta)",             "beta",                  "tercile", 100, "_n_F6"),
    ("F7", "成交量性格(放量日收涨占比)",     "high_vol_up_share",     "fix0.5",  10,  "_n_F7"),
]


def main():
    t0 = time.time()
    man = D.load_manifest(); syms = sorted(man)
    print(f"[核对] 有日线的票 {len(syms)} 只(已知 300)")
    pool = PM.load_pool()
    print(f"[核对] 池子 {len(pool)} 行(已知 74,268)")
    cids = PM.resolve_company_ids(pool, syms)
    mem = PM.membership(pool, cids)
    scope = PM.scope_sets(mem)
    for k, v in scope.items():
        print(f"[池] {k}: {len(v)} 只在口径内,{len(syms)-len(v)} 只被排除")

    spy = D.load_benchmark("SPY")
    rows = []
    bad = []
    for n_i, s in enumerate(syms):
        try:
            b = F.base(s)
        except Exception as e:
            bad.append((s, repr(e)[:60])); continue
        if b is None:
            bad.append((s, "日线不足 300 根")); continue
        sr = spy["close"].reindex(b["idx"]).pct_change().to_numpy(float)
        try:
            eds = F.earnings_dates(s) if man[s].fundamentals_path else []
        except Exception:
            eds = []
        for pname, years in PERIODS.items():
            m = F._mask(b["idx"], years)
            if m.sum() < 60:
                continue
            r = {"symbol": s, "period": pname, "trading_days": int(m.sum()),
                 "has_fundamentals": bool(man[s].fundamentals_path)}
            r.update(F.f_T1_top_shape(b, m));      r["_n_T1"] = r.pop("_n")
            r.update(F.f_T2_bottom_shape(b, m));   r["_n_T2"] = r.pop("_n")
            r.update(F.f_T3_swing_size(b, m));     r["_n_T3"] = r.pop("_n")
            r.update(F.f_T4_fake_breakout(b, m));  r["_n_T4"] = r.pop("_n")
            r.update(F.f_F1_gap(b, m));            r["_n_F1"] = r.pop("_n")
            r.update(F.f_F2_vol_cluster(b, m));    r["_n_F2"] = r.pop("_n")
            r.update(F.f_F3_upper_wick(b, m));     r["_n_F3"] = r.pop("_n")
            r.update(F.f_F4_ma_reaction(b, m));    r["_n_F4"] = r.pop("_n")
            r.update(F.f_F5_pead(b, m, eds));      r["_n_F5"] = r.pop("_n")
            r.update(F.f_F6_market(b, m, sr));     r["_n_F6"] = r.pop("_n")
            r.update(F.f_F7_volume(b, m));         r["_n_F7"] = r.pop("_n")
            rows.append(r)
        if (n_i + 1) % 50 == 0:
            print(f"  …{n_i+1}/{len(syms)}  {time.time()-t0:.0f}s")
    raw = pd.DataFrame(rows)
    raw.to_csv(os.path.join(HERE, "raw_features_1030.csv"), index=False)
    print(f"[核对] 原始表 {len(raw)} 行 = {raw.symbol.nunique()} 票 × 段;读失败 {len(bad)} 只 {bad[:5]}")
    json.dump({"bad": bad, "scope_counts": {k: len(v) for k, v in scope.items()},
               "scope_filter_line": PM.SCOPE_FILTER_LINE,
               "elapsed_s": round(time.time()-t0, 1)},
              open(os.path.join(HERE, "run_meta.json"), "w"), ensure_ascii=False, indent=1)
    return raw, scope


# ────────────────────────────────── 判定 + 汇总
def verdict(vals: pd.Series, mode: str, thr=None):
    """数值 → 档位标签。thr 给定时用给定的(固定口径),否则按本段全池算(相对口径)。"""
    v = vals.astype(float)
    if mode == "fix0.5":
        return v.map(lambda x: None if not np.isfinite(x) else ("高" if x >= 0.5 else "低")), 0.5
    if mode == "med":
        t = thr if thr is not None else float(v.median())
        return v.map(lambda x: None if not np.isfinite(x) else ("高于中位" if x >= t else "低于中位")), t
    if mode == "tercile":
        if thr is None:
            thr = (float(v.quantile(1/3)), float(v.quantile(2/3)))
        a, bq = thr
        return v.map(lambda x: None if not np.isfinite(x) else
                     ("低档" if x < a else ("中档" if x < bq else "高档"))), thr
    raise ValueError(mode)


def agree(x: pd.Series, y: pd.Series):
    """一致率 + 偶然一致率 + kappa。"""
    ok = x.notna() & y.notna()
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 20:
        return dict(n=n, obs=None, exp=None, kappa=None)
    obs = float((x == y).mean())
    px, py = x.value_counts(normalize=True), y.value_counts(normalize=True)
    exp = float(sum(px.get(k, 0)*py.get(k, 0) for k in set(px.index) | set(py.index)))
    return dict(n=n, obs=obs, exp=exp,
                kappa=(None if exp >= 1 else round((obs-exp)/(1-exp), 3)))


def summarize(raw: pd.DataFrame, scope: dict, label: str, scope_name_a: str,
              scope_name_b: str, pa: str, pb: str, ctl_a: str, ctl_b: str):
    out = []
    full = raw[raw.period == "全期2018-2025"].set_index("symbol")
    S_full = scope["全期2018-2025"] if label != "老池300" else sorted(raw.symbol.unique())
    for code, name, col, mode, minn, ncol in FEATS:
        fu = full.loc[[s for s in S_full if s in full.index]]
        n_ok = fu[ncol].astype(float) >= minn
        val = fu[col].astype(float).where(n_ok)
        cov = float(val.notna().mean())
        q = val.dropna()
        # 固定阈值:用全期全池算,两段共用 —— 这样才能分清「票变了」和「阈值跟着年份跑」
        _, thr_fixed = verdict(q, mode)
        rec = dict(code=code, name=name, col=col, pool=label,
                   n_sample=int(len(fu)), coverage=round(cov, 4),
                   median=None if q.empty else round(float(q.median()), 4),
                   q25=None if q.empty else round(float(q.quantile(.25)), 4),
                   q75=None if q.empty else round(float(q.quantile(.75)), 4),
                   n_events_median=None if fu.empty else float(fu[ncol].astype(float).median()),
                   thr_fixed=thr_fixed)
        vq, _ = verdict(q, mode, thr_fixed)
        vc = vq.dropna().value_counts(normalize=True)
        rec["top_bucket"] = None if vc.empty else str(vc.index[0])
        rec["top_bucket_share"] = None if vc.empty else round(float(vc.iloc[0]), 4)
        rec["n_distinct_values"] = int(q.nunique())

        # 两段一致性
        for tag, p1, p2, s1, s2 in (("main", pa, pb, scope_name_a, scope_name_b),
                                    ("ctl", ctl_a, ctl_b, ctl_a, ctl_b)):
            A = raw[raw.period == p1].set_index("symbol")
            B = raw[raw.period == p2].set_index("symbol")
            if label == "老池300":
                common = sorted(set(A.index) & set(B.index))
            else:
                common = sorted(set(A.index) & set(B.index) & set(scope[s1]) & set(scope[s2]))
            A, B = A.loc[common], B.loc[common]
            va = A[col].astype(float).where(A[ncol].astype(float) >= minn)
            vb = B[col].astype(float).where(B[ncol].astype(float) >= minn)
            # ① 固定阈值档位一致
            fa, _ = verdict(va, mode, thr_fixed); fb, _ = verdict(vb, mode, thr_fixed)
            r1 = agree(fa, fb)
            # ② 相对阈值(每段各自算三分位/中位)—— 看排名稳不稳
            ra, _ = verdict(va, mode); rb, _ = verdict(vb, mode)
            r2 = agree(ra, rb)
            # ③ 连续值的 Spearman
            ok = va.notna() & vb.notna()
            rho = p = None
            if ok.sum() >= 20:
                rr = stats.spearmanr(va[ok], vb[ok])
                rho, p = round(float(rr.statistic), 3), float(rr.pvalue)
            rec.update({f"{tag}_n": r1["n"],
                        f"{tag}_fixed_agree": None if r1["obs"] is None else round(r1["obs"], 4),
                        f"{tag}_fixed_chance": None if r1["exp"] is None else round(r1["exp"], 4),
                        f"{tag}_fixed_kappa": r1["kappa"],
                        f"{tag}_rel_agree": None if r2["obs"] is None else round(r2["obs"], 4),
                        f"{tag}_rel_kappa": r2["kappa"],
                        f"{tag}_spearman": rho, f"{tag}_spearman_p": p})
        out.append(rec)
    return pd.DataFrame(out)


if __name__ == "__main__":
    raw, scope = main()
    tabs = []
    tabs.append(summarize(raw[raw.symbol.isin(set().union(*scope.values()))], scope,
                          "大中盘(rank≤2000)", "2018-2022", "2023-2025",
                          "2018-2022", "2023-2025", "2018-2020", "2021-2022"))
    tabs.append(summarize(raw, scope, "老池300", "2018-2022", "2023-2025",
                          "2018-2022", "2023-2025", "2018-2020", "2021-2022"))
    t = pd.concat(tabs, ignore_index=True)
    t.to_csv(os.path.join(HERE, "summary_1030.csv"), index=False)
    pd.set_option("display.width", 250, "display.max_columns", 50)
    print(t[["code", "pool", "n_sample", "coverage", "median", "q25", "q75",
             "top_bucket_share", "main_n", "main_fixed_agree", "main_fixed_chance",
             "main_fixed_kappa", "main_rel_agree", "main_rel_kappa", "main_spearman"]].to_string())
