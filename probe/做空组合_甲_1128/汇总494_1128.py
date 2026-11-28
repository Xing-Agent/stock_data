# -*- coding: utf-8 -*-
"""《494》重跑 + 两道过滤 · 汇总。先核原始数和《494》表一致，再逐道加过滤，配随机对照 1,000 次和扣大盘。"""
import os, sys, json, glob, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out_494")
sp = importlib.util.spec_from_file_location("核心", os.path.join(HERE, "组合核心_1128.py")); C = importlib.util.module_from_spec(sp); sp.loader.exec_module(C)
T = pd.read_csv(os.path.join(OUT, "逐笔.csv"), parse_dates=["t"])
spy = pd.read_csv(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线/SPY_日线.csv"), parse_dates=["date"]).set_index("date").loc[:"2021-12-31"]
池 = {}
for f in sorted(glob.glob(os.path.join(OUT, "池_*.pkl"))): 池.update(pd.read_pickle(f))


def S(x, 随机=False, 种子=0):
    s = C.统计(x.R, x.收益pct)
    if len(x):
        s["时间段"] = f"{x.t.min().date()} ~ {x.t.max().date()}"
        # 扣大盘：持有期大约 = 进场当天到之后 N 根；这里用「进场当天开盘到 10 个交易日后收盘」的 SPY 涨跌近似（4 小时线最多 60 根≈30 天，原逐笔没记出场时间）
        d0 = x.t.dt.normalize(); i0 = spy.index.searchsorted(d0); i1 = np.minimum(i0 + 10, len(spy) - 1)
        mk = (spy.close_adj.to_numpy()[i1] / spy.open_adj.to_numpy()[np.minimum(i0, len(spy) - 1)] - 1) * 100
        s["同期大盘10天%"] = round(float(np.nanmean(mk)), 2); s["扣掉大盘后每笔%"] = round(float(np.nanmean(x.收益pct.to_numpy() + mk)), 2)
        s["按年"] = {int(k): (int(len(g)), round(float(g.R.mean()), 2)) for k, g in x.groupby(x.t.dt.year)}
    if 随机 and len(x) >= 1:
        rnd = C.随机对照(池, list(zip(x.风险pct / 100 * x.进 / x.atr4, [np.nan] * len(x))), 1000, 目标=3.0, 最长=60, 种子=种子)
        s["随机对照"] = {"随机每笔R中位": round(float(np.median(rnd)), 3), "5%~95%": [round(float(np.percentile(rnd, 5)), 3), round(float(np.percentile(rnd, 95)), 3)], "我们排在第几分位": C.分位(s["每笔R"], rnd), "过95分位": bool(s["每笔R"] > np.percentile(rnd, 95))}
    return s


out = {"核对《494》原表": {}}
for (开, 过), g in T.groupby(["开关", "过滤"]): out["核对《494》原表"][f"{开}·{过}"] = (len(g), round(g.R.mean(), 2), round(g.收益pct.mean(), 2))
主 = T[(T.开关 == "均线") & (T.过滤 == "过滤0.8")]
out["均线·过滤0.8（《494》主口径）"] = {
    "原样": S(主),
    "+大盘开关": S(主[主.大盘开关], True, 1),
    "+下面1.2R无支撑（只加这一道）": S(主[主.支撑R_250 >= 1.2]),
    "+大盘开关 +下面1.2R无支撑（拍板第4条）": S(主[主.大盘开关 & (主.支撑R_250 >= 1.2)], True, 2),
    "  另试 支撑1.0R": S(主[主.大盘开关 & (主.支撑R_250 >= 1.0)]), "  另试 支撑1.5R": S(主[主.大盘开关 & (主.支撑R_250 >= 1.5)]),
    "  另试 回看120天": S(主[主.大盘开关 & (主.支撑R_120 >= 1.2)]), "  另试 回看500天": S(主[主.大盘开关 & (主.支撑R_500 >= 1.2)]),
    "两道 + 自己在200日线下": S(主[主.大盘开关 & (主.支撑R_250 >= 1.2) & 主.自己在200下]),
    "两道 + 自己在200日线下 + 财报前5天不做（拍板第4条全部）": S(主[主.大盘开关 & (主.支撑R_250 >= 1.2) & 主.自己在200下 & ~主.财报5天内], True, 3),
}
for (开, 过), g in T.groupby(["开关", "过滤"]):
    if (开, 过) == ("均线", "过滤0.8"): continue
    out.setdefault("其他七种开关×过滤，加两道之后", {})[f"{开}·{过}"] = S(g[g.大盘开关 & (g.支撑R_250 >= 1.2)])
spyreg = T.drop_duplicates("t")
out["说明"] = {"大盘开关打开的交易日（2015–2021）": None}
y = spy.close_adj; s50, s200 = y.rolling(50).mean(), y.rolling(200).mean(); reg = ((y < s200) & (s50 < s200)).loc["2015":"2021"]
out["说明"]["大盘开关打开的交易日（2015–2021）"] = int(reg.sum()); out["说明"]["分年"] = {int(k): int(v) for k, v in reg.groupby(reg.index.year).sum().items()}
json.dump(out, open(os.path.join(OUT, "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(json.dumps(out, ensure_ascii=False, default=str, indent=0)[:6000])
