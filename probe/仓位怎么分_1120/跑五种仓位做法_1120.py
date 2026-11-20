#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五种仓位做法在趋势 / 突破 / 成长类策略上跑（2026-11-20 · Lin《323》拍板第 2、3 条）

大白话：同一条策略、同一批信号，只换「怎么分批买、每只最多给多少」。用新引擎 engine_v2（旧引擎没动；
关掉加仓时两者逐位相同，见 一致性检查_1120.py）。2015-01-02 → 2025-12-31，研发池，流动性池中档，含分红。
  ① 等权对照         策略原来的仓位，不加仓
  ② 海龟原著         账户 1% ÷ N 定一个单位；每涨 0.5N 加一个单位，最多 4 个单位；加仓后止损抬到最新买价下 2N
  ③ 欧奈尔原著       先买标准仓的六成；离买点涨 2%~5% 之间加一次（四成）；超过 5% 不再加
  ④ XING 版（Gemini 推荐） 起始仓位按波动定在 5%~10%；每涨 1.5 倍 ATR 加一次，最多两次，量 1 : 0.6 : 0.4，
                     两次加仓至少隔 5 天，加之前把止损抬到成本以上。1.5 倍这个数跑 1.0 / 1.5 / 2.0 三点
  ⑤ 跟着行情走       ④ 的基础上，只有「大票通吃」时才允许加仓：SPY ÷ RSP（等权标普）在它自己 N 日均线上方。
                     N 跑 60 / 100 / 150 三点。关着的时候不加仓，等于回到分散
  另：④ 加「只卖加仓部分」（收盘跌回最近加仓价下面 1 个 N，就把加的那部分卖掉、留底仓）
上限（测试参数）：单票 20%；所有持仓打到止损的总亏损 ≤ 账户 6%（④ 上另跑 4% / 8%）。②~⑤ 都带这两个上限。
N = 买入前一天的 ATR（各策略配置自己的周期）。加仓一律收盘判断、第二天开盘成交；止损被跳空越过按开盘价成交（引擎原有规则）。
没做的：行业上限 35%（仓库里没有行业分类数据）；高度相关两只合计 30%；2004–2014 那一段（缺 2014 年以前的 SPY、RSP）。
"""
import copy, io, json, os, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out_五种做法"); POOL = os.path.join(ROOT, "probe/流动性池_1114")
名单 = ["trend_following", "trend_following-原著-唐奇安反向通道离场", "技-1", "技-3-XING", "技-3-原著", "技-4-原著-中值", "技-4-行业", "技-6-XING", "技-6-原著"]

def 跑一条(名):
    sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    import yaml, numpy as np, pandas as pd
    import 跑基本面_1106 as B
    B.装层()
    import 补分红_1107 as DIV; DIV.install()
    from engine import matrices, data
    from engine_v2 import chain
    hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    idx = m.index; perf = mk.index; yrs = (perf[-1] - perf[0]).days / 365.25
    spy = data.load_benchmark("SPY")["close"].astype(float); rsp = data.load_benchmark("RSP")["close"].astype(float)
    rel = (spy / rsp).reindex(idx).ffill()
    def 开关(n): return (rel > rel.rolling(n, min_periods=n).mean()).shift(1).fillna(False).to_numpy(dtype=bool)
    CAP = dict(cap_single=0.20, heat_cap=0.06)
    def xing(step=1.5, **kw): return dict(type="xing", initial="vol_band", unit_risk=0.005, w_min=0.05, w_max=0.10, step_n=step, max_adds=2, add_ratios=[0.6, 0.4], min_gap=5, stop_on_add="breakeven", **{**CAP, **kw})
    方案 = {"①等权对照": None,
            "②海龟原著": dict(type="turtle", initial="unit_risk", unit_risk=0.01, step_n=0.5, max_adds=3, stop_on_add="turtle", **CAP),
            "③欧奈尔原著": dict(type="oneil", initial="frac", first_frac=0.6, add_frac=0.4, add_lo=0.02, add_hi=0.05, max_adds=1, **CAP),
            "④XING版_1.0倍ATR": xing(1.0), "④XING版_1.5倍ATR": xing(1.5), "④XING版_2.0倍ATR": xing(2.0),
            "④XING版_总风险4pct": xing(heat_cap=0.04), "④XING版_总风险8pct": xing(heat_cap=0.08),
            "④XING版_加只卖加仓部分": xing(trim_n=1.0),
            "⑤跟着行情走_60日": xing(allow=开关(60)), "⑤跟着行情走_100日": xing(allow=开关(100)), "⑤跟着行情走_150日": xing(allow=开关(150))}
    res = {}
    for nm, py in 方案.items():
        r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True, pyramid=py)
        L = r.ledger
        if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
        eq = r.equity.reindex(perf).ffill(); ann = (eq.iloc[-1] / 1e6) ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1)
        水下 = (eq < eq.cummax()).astype(int); 最长 = int(水下.groupby((水下 == 0).cumsum()).sum().max())
        pnl = L["net_pnl"].astype(float) if len(L) else pd.Series(dtype=float); w = pnl[pnl > 0].sum(); l = -pnl[pnl < 0].sum()
        整 = L[L["lot"] == "整笔"] if "lot" in L else L
        res[nm] = {"每年赚pct": round(ann * 100, 2), "最惨跌pct": round(float(dd.min()) * 100, 2), "卡玛": round(ann / abs(dd.min()), 3) if dd.min() < 0 else None,
                   "最长多少天没创新高": 最长, "利润因子": round(float(w / l), 3) if l > 0 else None, "赚钱的笔pct": round(float((整["net_pnl"] > 0).mean() * 100), 1) if len(整) else None,
                   "笔数": int(len(整)), "平均仓位pct": round(float(r.exposure.reindex(perf).fillna(0).mean() * 100), 1),
                   "最赚5笔占总利润pct": round(float(pnl.nlargest(5).sum() / pnl.sum() * 100), 1) if pnl.sum() > 0 else None,
                   "加过仓的笔数": int((整["n_adds"] > 0).sum()) if "n_adds" in 整 else 0,
                   "单票占比最高到过pct": None, "备注": [n for n in r.notes if "v2" in n]}
        if py is not None and len(L): L.to_csv(os.path.join(OUT, f"流水__{名}__{nm}.csv"), index=False)
        print("  ", nm, res[nm]["每年赚pct"], res[nm]["最惨跌pct"], flush=True)
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "对标": "满仓标普同期 13.44% / −33.7%", "方案": res,
            "⑤开关开着的天数占比pct": {n: round(float(pd.Series(开关(n), index=idx).reindex(perf).mean() * 100), 1) for n in (60, 100, 150)}}

def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]; t = time.time()
        try: rec = 跑一条(名)
        except Exception as e: rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2500:]}
        rec["总秒"] = round(time.time() - t, 1)
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, rec["总秒"], flush=True); return 0
    import subprocess
    for 名 in 名单:
        if not os.path.exists(os.path.join(OUT, 名 + ".json")):
            subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True); return 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
