#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""先挑票 → 技术面进出场 → 分仓位,连起来试(Lin 11-19/11-20 说的那条链)· 2026-11-22
大白话:同一条技术面策略,只换「它能在哪些票里挑」和「每只买多大」。engine/ 不动;仓位用 engine_v2。
  挑票 v0(★ 这是主 chat 自己起的第一版,不是原著、不是 Lin 定的,先看方向):
    动量 = 过去 12 个月涨幅(跳过最近 1 个月)在流动性池里排前 20%(另跑 10% / 30%)
    增长 = 最近四个季度营收合计比一年前同口径高,增速在流动性池里排前 30%(另跑 20% / 40%),且增速为正;财报公布后第二个交易日才生效
  臂:A 原样 / B 只加动量 / C 只加增长 / D 动量+增长 / E = D + 每笔按「打到止损亏账户 0.5%」定大小、单票最多 20%
  对照:buy_and_hold 配置套 D 的范围(只挑票不择时)
窗口 2015-01-02 → 2025-12-31(基本面只有这一段),研发池,流动性池中档,含分红。一条策略一个子进程,可续跑。
"""
import copy, io, json, os, subprocess, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out"); POOL = os.path.join(ROOT, "probe/流动性池_1114")
名单 = ["trend_following", "技-1", "技-3-XING", "技-4-行业", "技-6-XING", "buy_and_hold"]

def 装():
    sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106")); sys.path.insert(0, os.path.join(ROOT, "probe/含分红重出_1116"))
    import 跑基本面_1106 as B
    B.装层()
    import 补分红_1107 as DIV; DIV.install()
    import 按表折算_1118 as FIX; FIX.install()
    return B, FIX

def 做掩膜():
    import numpy as np, pandas as pd
    B, FIX = 装()
    from engine import cache, fundamentals as F
    hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev = hold["研发池名单"]
    P = cache._PANEL; cols = [s for s in dev if s in P["close"].columns]
    c = P["close"][cols].astype(float); idx = c.index
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet")).reindex(index=idx, columns=cols).fillna(False).astype(bool)
    mom = (c.shift(21) / c.shift(252) - 1).where(mk)
    rk = mom.rank(axis=1, pct=True, ascending=False)
    g = {}
    for i, s in enumerate(cols):
        try:
            vals, ef = F.quarter_frame(s)
            if vals.empty or "rev" not in vals: continue
            r = vals["rev"]; gr = (r / r.shift(4).where(r.shift(4) > 0) - 1)
            eff = pd.concat([ef["rev"], ef["rev"].shift(4)], axis=1).max(axis=1)
            d = F._to_daily(gr, eff, idx)
            if d.notna().any(): g[s] = d
        except Exception:
            pass
    G = pd.DataFrame(g).reindex(index=idx, columns=cols).where(mk)
    # 财报太旧(超过 200 天没更新)的不算
    grk = G.rank(axis=1, pct=True, ascending=False)
    os.makedirs(OUT, exist_ok=True)
    for p in (10, 20, 30): (rk <= p / 100).to_parquet(os.path.join(OUT, f"掩膜_动量前{p}.parquet"))
    for p in (20, 30, 40): ((grk <= p / 100) & (G > 0)).to_parquet(os.path.join(OUT, f"掩膜_增长前{p}.parquet"))
    rep = {"研发池在面板里": len(cols), "有营收增速的票": int(G.notna().any().sum()),
           "每天流动性池里几只_中位": int(mk.loc["2015":"2025"].sum(axis=1).median()),
           "每天动量前20几只_中位": int((rk <= 0.2).loc["2015":"2025"].sum(axis=1).median()),
           "每天增长前30几只_中位": int(((grk <= 0.3) & (G > 0)).loc["2015":"2025"].sum(axis=1).median()),
           "每天两样都中几只_中位": int(((rk <= 0.2) & (grk <= 0.3) & (G > 0)).loc["2015":"2025"].sum(axis=1).median()),
           "流动性池里有增速数据的占比_中位pct": round(float((G.notna().sum(axis=1) / mk.sum(axis=1)).loc["2015":"2025"].median() * 100), 1)}
    json.dump(rep, io.open(os.path.join(OUT, "掩膜_报告.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1); print(rep)

def 跑一条(名):
    import yaml, numpy as np, pandas as pd
    B, FIX = 装()
    from engine import matrices, data
    from engine_v2 import chain
    hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    FIX.拿掉(m)
    def 膜(f): return pd.read_parquet(os.path.join(OUT, f)).reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    liq = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet")); perf = liq.index
    liq = liq.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    base = m.universe & liq; yrs = (perf[-1] - perf[0]).days / 365.25
    M = {p: 膜(f"掩膜_动量前{p}.parquet") for p in (10, 20, 30)}; G = {p: 膜(f"掩膜_增长前{p}.parquet") for p in (20, 30, 40)}
    # 选中之后信号在收盘定、第二天才用:掩膜往后挪一天
    sh = lambda a: np.vstack([np.zeros((1, a.shape[1]), bool), a[:-1]])
    SZ = dict(type="turtle", initial="unit_risk", unit_risk=0.005, max_adds=0, cap_single=0.20)
    臂 = {"A_原样": (base, None), "B_动量前20": (base & sh(M[20]), None), "C_增长前30": (base & sh(G[30]), None),
          "D_动量20加增长30": (base & sh(M[20]) & sh(G[30]), None), "E_D加按风险定仓位": (base & sh(M[20]) & sh(G[30]), SZ),
          "B_动量前10": (base & sh(M[10]), None), "B_动量前30": (base & sh(M[30]), None),
          "C_增长前20": (base & sh(G[20]), None), "C_增长前40": (base & sh(G[40]), None),
          "D_动量30加增长40": (base & sh(M[30]) & sh(G[40]), None), "D_动量10加增长20": (base & sh(M[10]) & sh(G[20]), None)}
    if 名 == "buy_and_hold": 臂 = {k: v for k, v in 臂.items() if not k.startswith("E_")}
    res = {}
    for nm, (u, py) in 臂.items():
        m.universe = u
        r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True, pyramid=py)
        L = r.ledger
        if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
        eq = r.equity.reindex(perf).ffill(); ann = (eq.iloc[-1] / 1e6) ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1)
        水下 = (eq < eq.cummax()).astype(int); 最长 = int(水下.groupby((水下 == 0).cumsum()).sum().max())
        yr = eq.groupby(eq.index.year).last(); yret = (yr / yr.shift(1).fillna(1e6) - 1)
        pnl = L["net_pnl"].astype(float) if len(L) else pd.Series(dtype=float); w = pnl[pnl > 0].sum(); l = -pnl[pnl < 0].sum()
        top5 = pnl.nlargest(5).sum() / pnl.sum() * 100 if len(pnl) and pnl.sum() > 0 else None
        res[nm] = {"每年赚pct": round(ann * 100, 2), "最惨跌pct": round(float(dd.min()) * 100, 2), "每跌一分赚几分": round(ann / abs(dd.min()), 3) if dd.min() < 0 else None,
                   "最长多少天没创新高": 最长, "最差一年pct": round(float(yret.min()) * 100, 1), "赚钱的年数": f"{int((yret > 0).sum())}/{len(yret)}",
                   "利润因子": round(float(w / l), 3) if l > 0 else None, "赚钱的笔pct": round(float((pnl > 0).mean() * 100), 1) if len(pnl) else None,
                   "笔数": int(len(L)), "买过几只票": int(L["symbol"].nunique()) if len(L) else 0, "平均仓位pct": round(float(r.exposure.reindex(perf).fillna(0).mean() * 100), 1),
                   "最赚5笔占总利润pct": round(float(top5), 1) if top5 is not None else None,
                   "按年pct": {int(k): round(float(v) * 100, 1) for k, v in yret.items()}, "可选的票日": int(u.sum())}
        print(名, nm, {k: res[nm][k] for k in ("每年赚pct", "最惨跌pct", "笔数", "平均仓位pct")}, flush=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump({"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "臂": res}, io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--mask": 做掩膜(); sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--one":
        try: 跑一条(sys.argv[2])
        except Exception:
            os.makedirs(OUT, exist_ok=True); json.dump({"名": sys.argv[2], "跑失败": traceback.format_exc()[-1500:]}, io.open(os.path.join(OUT, sys.argv[2] + ".json"), "w", encoding="utf-8"), ensure_ascii=False); raise
        sys.exit(0)
    if not os.path.exists(os.path.join(OUT, "掩膜_增长前30.parquet")): subprocess.run([sys.executable, __file__, "--mask"], check=True)
    for n in 名单:
        if os.path.exists(os.path.join(OUT, n + ".json")): continue
        t = time.time(); subprocess.run([sys.executable, __file__, "--one", n]); print("==", n, round(time.time() - t), "秒", flush=True)
