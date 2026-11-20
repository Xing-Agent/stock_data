#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二段时间 2005-01-03 → 2014-12-31：技术面策略原样 + 大盘闸几种写法 + 仓位几种做法（2026-11-20）

大白话：2015–2025 是大科技股带起来的十年。这里把同样的东西放到前一个十年（含 2008 年慢熊）再跑一遍，
看哪些结论换一段时间还成立。环境见 环境2004_1120.py；引擎用 engine_v2（关掉加仓时和旧引擎逐位相同）。
  · 全部技术面配置：原样跑一遍（手册第二段成绩）
  · 9 条趋势 / 突破 / 成长类另加：
      大盘闸：不挂闸 / 行业版（200 日线 + 20 日斜率）/ Faber 月线 10 个月 / 温斯坦周线 30 周且向上 / 三线投票至少 2 条
      仓位：  原仓位 + 总风险 10% / 原仓位涨 1.5 倍 ATR 加一次半仓（不设总风险、设 10%）/ XING 版（不设、10%）/
              海龟原著（总风险 15%）/ 跟着行情走（SPY÷RSP 在 150 日均线上方才允许加仓）
⚠ 这一段是 10 年，不是 11 年；流动性池门槛的美元数没按年代调。只有技术面，没有基本面。
"""
import copy, glob, io, json, os, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out_第二段")
九条 = ["trend_following", "trend_following-原著-唐奇安反向通道离场", "技-1", "技-3-XING", "技-3-原著", "技-4-原著-中值", "技-4-行业", "技-6-XING", "技-6-原著"]

def 名单():
    ns = [os.path.basename(f)[:-5] for f in sorted(glob.glob(os.path.join(ROOT, "probe/含分红重出_1116/技术面中档_out/*.json")))]
    ok = [n for n in ns if "跑失败" not in json.load(io.open(os.path.join(ROOT, "probe/含分红重出_1116/技术面中档_out", n + ".json"), encoding="utf-8"))]
    return 九条 + [n for n in ok if n not in 九条]

def 跑一条(名):
    sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
    import yaml, numpy as np, pandas as pd
    import 环境2004_1120 as ENV
    env = ENV.install(); dev = env["dev"]; hs = env["留出池"]
    from engine import matrices, data
    from engine_v2 import chain
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(HERE, "流动性池掩膜2004_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    idx = m.index; perf = mk.index; yrs = (perf[-1] - perf[0]).days / 365.25
    spy全 = data.load_benchmark("SPY")["close"].astype(float).dropna(); spy = spy全.reindex(idx).ffill()
    rsp = data.load_benchmark("RSP")["close"].astype(float).reindex(idx).ffill(); rel = spy / rsp
    def 挪(s): return s.reindex(idx).ffill().shift(1).fillna(False).to_numpy(dtype=bool)
    def 日线闸(n=200):
        ma = spy.rolling(n, min_periods=n).mean(); return 挪(((spy > ma) & (ma > ma.shift(20))).fillna(False))
    def faber():
        me = spy全.groupby([spy全.index.year, spy全.index.month]).tail(1); ok = me > me.rolling(10, min_periods=10).mean()
        return 挪(ok.astype(float).reindex(spy全.index).ffill().fillna(0).astype(bool))
    def weinstein():
        iso = spy全.index.isocalendar(); we = spy全.groupby([iso.year.values, iso.week.values]).tail(1); ma = we.rolling(30, min_periods=30).mean()
        return 挪(((we > ma) & (ma > ma.shift(1))).astype(float).reindex(spy全.index).ffill().fillna(0).astype(bool))
    def 投票(k=2): return 挪(sum((spy > spy.rolling(n, min_periods=n).mean()).astype(int) for n in (100, 150, 200)) >= k)
    reg0 = m.regime.copy(); 全开 = np.ones(len(idx), dtype=bool)
    def xing(**kw): return dict(type="xing", initial="vol_band", unit_risk=0.005, w_min=0.05, w_max=0.10, step_n=1.5, max_adds=2, add_ratios=[0.6, 0.4], min_gap=5, stop_on_add="breakeven", cap_single=0.20, **kw)
    加一次 = dict(type="xing", initial=None, step_n=1.5, max_adds=1, add_ratios=[0.5], min_gap=5, stop_on_add="breakeven", cap_single=0.20)
    方案 = {"原样": (reg0, None)}
    if 名 in 九条:
        方案.update({"闸_不挂": (全开, None), "闸_行业版200日带斜率": (日线闸(), None), "闸_Faber月线": (faber(), None), "闸_温斯坦周线": (weinstein(), None), "闸_三线投票至少2条": (投票(2), None),
                     "仓位_原仓位_总风险10pct": (reg0, dict(type="none", max_adds=0, cap_single=0.20, heat_cap=0.10)),
                     "仓位_加一次半仓_不设总风险": (reg0, 加一次), "仓位_加一次半仓_总风险10pct": (reg0, {**加一次, "heat_cap": 0.10}),
                     "仓位_XING版_不设总风险": (reg0, xing()), "仓位_XING版_总风险10pct": (reg0, xing(heat_cap=0.10)),
                     "仓位_海龟原著_总风险15pct": (reg0, dict(type="turtle", initial="unit_risk", unit_risk=0.01, step_n=0.5, max_adds=3, stop_on_add="turtle", cap_single=0.20, heat_cap=0.15)),
                     "仓位_跟着行情走_150日": (reg0, xing(allow=(rel > rel.rolling(150, min_periods=150).mean()).shift(1).fillna(False).to_numpy(dtype=bool)))})
    res = {}
    for nm, (reg, py) in 方案.items():
        m.regime = reg
        r = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, ENV.START, ENV.END, m=m, total_return=True, pyramid=py)
        L = r.ledger
        if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
        eq = r.equity.reindex(perf).ffill(); ann = (eq.iloc[-1] / 1e6) ** (1 / yrs) - 1; dd = eq / eq.cummax() - 1
        水下 = (eq < eq.cummax()).astype(int); 最长 = int(水下.groupby((水下 == 0).cumsum()).sum().max())
        pnl = L["net_pnl"].astype(float) if len(L) else pd.Series(dtype=float); w = pnl[pnl > 0].sum(); l = -pnl[pnl < 0].sum()
        整 = L[L["lot"] == "整笔"] if "lot" in L else L
        yr = eq.groupby(eq.index.year).last(); 年 = (yr / yr.shift(1).fillna(1e6) - 1)
        res[nm] = {"每年赚pct": round(ann * 100, 2), "最惨跌pct": round(float(dd.min()) * 100, 2), "卡玛": round(ann / abs(dd.min()), 3) if dd.min() < 0 else None,
                   "2008年pct": round(float(年.get(2008, np.nan)) * 100, 1), "最长多少天没创新高": 最长, "利润因子": round(float(w / l), 3) if l > 0 else None,
                   "赚钱的笔pct": round(float((整["net_pnl"] > 0).mean() * 100), 1) if len(整) else None, "笔数": int(len(整)),
                   "平均仓位pct": round(float(r.exposure.reindex(perf).fillna(0).mean() * 100), 1),
                   "最赚5笔占总利润pct": round(float(pnl.nlargest(5).sum() / pnl.sum() * 100), 1) if pnl.sum() > 0 else None,
                   "赚钱的年数": f"{int((年 > 0).sum())} / {len(年)}"}
        if nm == "原样":
            L.to_csv(os.path.join(OUT, f"流水__{名}.csv"), index=False); eq.to_csv(os.path.join(OUT, f"日净值__{名}.csv"))
        print("  ", nm, res[nm]["每年赚pct"], res[nm]["最惨跌pct"], flush=True)
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "方案": res}

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
    for 名 in 名单():
        if not os.path.exists(os.path.join(OUT, 名 + ".json")):
            subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True); return 0
if __name__ == "__main__": sys.exit(main(sys.argv[1:]))
