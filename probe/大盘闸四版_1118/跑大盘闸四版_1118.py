#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大盘闸四种写法并排 + 「扫一片」（2026-11-18 夜 · Lin 1118《308》三条拍板）

大白话：大盘闸 = 大盘不好时不开新仓（不强平）。Lin 定了闸按「防大跌」来考，不按「多赚钱」考。
这里在 2015-01-02 → 2025-12-31、研发池、流动性池中档（打过断档票补丁）、含分红上，对三条大波段策略各跑：
  不挂闸            基准（Covel / 海龟原著的立场：不加大盘闸）
  原著版A Faber     每月最后一个交易日判一次：SPY 月末收盘在 10 个月均线（月末收盘的均值）上方才开新仓，管到下个月末
  原著版B 温斯坦    每周最后一个交易日判一次：SPY 周收盘在 30 周均线上方、且均线比上一周高，管到下周末
  行业版            SPY 在 200 日线上方 + 200 日线比 20 天前高（现在卡里这版）
  三线投票_简化     SPY 站上 100 / 150 / 200 日线里的至少 2 条才开。
                    ⚠ Gemini 推荐的原样是「按站上几条定最多拿几只」；引擎的持仓只数上限是固定配置项，engine 不许改，所以这里只做了「开 / 关」的简化版
  扫一片            均线 150 / 175 / 200 / 225 / 250 × 判定日往后挪 0–5 天（都带 20 日斜率），共 30 格
每版记：年化、最大回撤、卡玛、最差 5% 月份的平均月收益、拿掉最赚 5 笔后的总盈亏、笔数、平均仓位、闸开着的天数占比。
所有闸都只用前一天及更早的收盘（和引擎自带的闸同样往后挪一天），不偷看。engine/ 一个字节不改：闸是在内存里换 m.regime。
还没做的：2004–2014 那一段；随机挑票 100 次；欧奈尔派发日版。
"""
import copy, io, json, os, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
POOL = os.path.join(ROOT, "probe/流动性池_1114")
名单 = ["技-1", "trend_following", "trend_following-原著-唐奇安反向通道离场"]


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    sys.path.insert(0, POOL)
    import yaml, numpy as np, pandas as pd
    import 跑基本面_1106 as B
    B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data
    from 跑技术面换池_1114 import 指标
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    idx = m.index
    start, end = data.PERF_START, data.PERF_END
    perf = mk.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    spy全 = data.load_benchmark("SPY")["close"].astype(float).dropna()
    spy = spy全.reindex(idx).ffill()

    def 挪一天(s):   # s：当天收盘后才知道的布尔序列 → 第二天才能用
        return s.reindex(idx).ffill().shift(1).fillna(False).to_numpy(dtype=bool)

    def 日线闸(n, 斜率=True):
        ma = spy.rolling(n, min_periods=n).mean()
        ok = spy > ma
        if 斜率:
            ok &= ma > ma.shift(20)
        return 挪一天(ok.fillna(False))

    def faber():
        me = spy全.groupby([spy全.index.year, spy全.index.month]).tail(1)      # 每月最后一个交易日的收盘
        ok = me > me.rolling(10, min_periods=10).mean()
        return 挪一天(ok.astype(float).reindex(spy全.index).ffill().fillna(0).astype(bool))

    def weinstein():
        iso = spy全.index.isocalendar()
        we = spy全.groupby([iso.year.values, iso.week.values]).tail(1)
        ma = we.rolling(30, min_periods=30).mean()
        ok = (we > ma) & (ma > ma.shift(1))
        return 挪一天(ok.astype(float).reindex(spy全.index).ffill().fillna(0).astype(bool))

    def 投票(need=2):
        c = sum((spy > spy.rolling(n, min_periods=n).mean()).astype(int) for n in (100, 150, 200))
        return 挪一天(c >= need)

    def 跑(reg, 挪=0):
        r = reg.copy()
        if 挪:
            r = np.concatenate([np.zeros(挪, dtype=bool), r[:-挪]])
        m.regime = r
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, start, end, m=m, total_return=True)
        L = res.ledger
        if len(L) and (set(L["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        eq = res.equity.reindex(perf).ffill()
        ex = res.exposure.reindex(perf).fillna(0.0)
        mo = eq.groupby([eq.index.year, eq.index.month]).tail(1).pct_change().dropna()
        k = max(1, int(round(len(mo) * 0.05)))
        pnl = L["net_pnl"].astype(float) if len(L) else pd.Series(dtype=float)
        开 = pd.Series(r, index=idx).reindex(perf)
        return {"笔数": int(len(L)), "平均仓位pct": round(float(ex.mean() * 100), 1),
                "闸开着的天数占比pct": round(float(开.mean() * 100), 1), **指标(eq, yrs),
                "最差5pct月份_平均月收益pct": round(float(mo.nsmallest(k).mean() * 100), 2),
                "最差单月pct": round(float(mo.min() * 100), 2),
                "总盈亏": round(float(pnl.sum())), "拿掉最赚5笔后的总盈亏": round(float(pnl.sum() - pnl.nlargest(5).sum()))}

    版 = {"不挂闸": 跑(np.ones(len(idx), dtype=bool)),
          "原著版A_Faber月线10个月": 跑(faber()),
          "原著版B_温斯坦周线30周且向上": 跑(weinstein()),
          "行业版_200日线带20日斜率": 跑(日线闸(200)),
          "三线投票_至少2条_简化成开关": 跑(投票(2)),
          "三线投票_至少1条": 跑(投票(1)), "三线投票_3条全站上": 跑(投票(3))}
    扫 = {}
    for n in (150, 175, 200, 225, 250):
        g = 日线闸(n)
        for k in range(6):
            扫[f"均线{n}_挪{k}天"] = 跑(g, 挪=k)
    基 = 版["不挂闸"]
    def 好(v, key, 大好=True):
        return (v[key] > 基[key]) if 大好 else (v[key] < 基[key])
    计 = {"30格里_最大回撤比不挂闸浅的格数": sum(好(v, "最大回撤pct") for v in 扫.values()),
          "30格里_卡玛比不挂闸高的格数": sum(好(v, "卡玛") for v in 扫.values() if v["卡玛"] is not None),
          "30格里_最差5pct月份比不挂闸亏得少的格数": sum(好(v, "最差5pct月份_平均月收益pct") for v in 扫.values()),
          "30格里_年化比不挂闸高的格数": sum(好(v, "复合年化pct") for v in 扫.values() if v["复合年化pct"] is not None)}
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内流动性池中档（已拿掉断档票）",
            "分红": "含分红", "四版": 版, "扫一片_30格": 扫, "扫一片_计数": 计}


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        t = time.time()
        try:
            rec = 跑一条(名)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2000:]}
        rec["总秒"] = round(time.time() - t, 1)
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    import subprocess
    for 名 in 名单:
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
