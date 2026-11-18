#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换挑法（2026-11-18 · Lin 同意的回测次序第一件）

大白话：同一天信号多于空位时，先买谁？现在是按成交额从大到小。这里同一条策略、别的都不变，只换「先买谁」：
  成交额（现在的做法）
  当天涨幅、一周涨幅（Lin 11-18：他自己看「天、周」，谁涨得快先买谁）
  一个月涨幅、三个月涨幅（对照）
  随机抽（5 个不同的随机种子；这是「瞎挑」的水平，任何挑法至少要好过它才算有用）
排序只用信号当天收盘及以前的数据。做法：在内存里把 m.rank_score 换掉，engine/ 一个字节不改。
选股范围：流动性池中档（已拿掉 4 只断档票）。含分红。只用研发池。2015–2025。
还没做：「基本面先过滤再挑」（融合派那一版），要先接财报数据，下一步做。
"""
import copy, io, json, os, subprocess, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
POOL = os.path.join(ROOT, "probe/流动性池_1114")
挑 = ["技-1", "trend_following", "trend_following-原著-唐奇安反向通道离场", "技-6-XING", "技-5-XING", "技-3-XING", "技-4-原著-中值"]


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    sys.path.insert(0, POOL)
    import yaml, numpy as np, pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data, cache
    from 跑技术面换池_1114 import 指标
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    idx, perf = m.index, mk.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    cl = cache._PANEL["close"].reindex(index=idx, columns=list(m.symbols)).astype(float)
    rs0 = m.rank_score.copy()

    def 涨幅(n):
        x = (cl / cl.shift(n) - 1.0).to_numpy(dtype=float)
        return np.where(np.isfinite(x), x, -1e9)

    def 跑(score):
        m.rank_score = score
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True)
        led = res.ledger
        if len(led) and (set(led["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        eq = res.equity.reindex(perf).ffill()
        r = {"笔数": int(len(led)), "平均仓位pct": round(float(res.exposure.reindex(perf).fillna(0).mean() * 100), 1), **指标(eq, yrs)}
        if len(led):
            x = (led["net_pnl"] / led["notional_in"]).astype(float)
            赢, 亏 = x[x > 0], x[x < 0]
            tot = float(led["net_pnl"].sum())
            top = led.nlargest(5, "net_pnl")
            y0 = eq.resample("YE").last()
            ys = [float(y0.iloc[0] / eq.dropna().iloc[0] - 1)] + list(y0.pct_change().dropna().values)
            r.update({"胜率pct": round(float((x > 0).mean() * 100), 1),
                      "盈亏比": round(float(赢.mean() / -亏.mean()), 2) if len(赢) and len(亏) else None,
                      "赚钱的年数": f"{sum(1 for v in ys if v > 0)} / {len(ys)}",
                      "最赚的两笔占全部利润pct": round(float(led["net_pnl"].nlargest(2).sum()) / tot * 100) if tot > 0 else None,
                      "最赚的五笔": [f"{s} {str(a)[:10]} 赚{round(float(p))}" for s, a, p in zip(top["symbol"], top["entry_date"], top["net_pnl"])],
                      "每笔赚超过一倍的笔数": int((x > 1.0).sum())})
        return r

    版 = {"按成交额_现在的做法": 跑(rs0)}
    for 标, n in (("按当天涨幅_Lin的做法", 1), ("按一周涨幅_Lin的做法", 5), ("按一个月涨幅_对照", 21), ("按三个月涨幅_对照", 63)):
        版[标] = 跑(涨幅(n))
    随 = []
    for seed in range(5):
        rng = np.random.default_rng(1118 + seed)
        随.append(跑(rng.random(rs0.shape)))
    def 中位(k):
        v = sorted(x[k] for x in 随 if x.get(k) is not None)
        return v[len(v) // 2] if v else None
    版["随机抽_5次"] = {"每次": 随, "复合年化pct_中位": 中位("复合年化pct"), "复合年化pct_最低最高": [min(x["复合年化pct"] for x in 随), max(x["复合年化pct"] for x in 随)],
                    "最大回撤pct_中位": 中位("最大回撤pct"), "卡玛_中位": 中位("卡玛"), "卡玛_最低最高": [min(x["卡玛"] for x in 随), max(x["卡玛"] for x in 随)]}
    m.rank_score = rs0
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内流动性池中档（已拿掉 4 只断档票）", "分红": "含分红", "各版": 版}


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]
        t = time.time()
        try:
            rec = 跑一条(名)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2500:]}
        rec["总秒"] = round(time.time() - t, 1)
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    for 名 in 挑:
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
