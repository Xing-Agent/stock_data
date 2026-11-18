#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换默认挑法 · 全部技术面版本（2026-11-18 · Lin 同意）

大白话：信号多于空位时先买谁。现在是「成交额大的先买」，全信号量法查出这是最差的一种。
这里在全部技术面版本上并排比：
  成交额大的先买（现在的做法）
  成交额小的先买（把现在的反过来；池子本身已保证每天成交 1000 万美元以上）
  当天涨幅大的先买，但去掉当天最疯的那一小撮（Lin 的做法加一道保险）
      「最疯的一小撮」= 当天候选信号里涨幅最高的 2%（向上取整，候选不足 10 个的日子不去）；另跑 5%、10% 两档看稳不稳
  随机抽 20 次（「瞎挑」的水平；一种挑法要好过随机抽的大多数才算真有用）
排序只用信号当天收盘及以前的数据；在内存里换 m.rank_score，engine/ 一个字节不改。
流动性池中档（已拿掉 4 只断档票）。含分红。只用研发池。2015–2025。
"""
import copy, glob, io, json, math, os, subprocess, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out_全技术面")
POOL = os.path.join(ROOT, "probe/流动性池_1114")


def 清单():
    L = [os.path.basename(f)[:-5] for f in sorted(glob.glob(os.path.join(ROOT, "engine/configs/技-*.yaml")))]
    return L + ["trend_following", "trend_following-原著-唐奇安反向通道离场"]


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
    vol = cache._PANEL["volume"].reindex(index=idx, columns=list(m.symbols)).astype(float)
    rs0 = m.rank_score.copy()
    adv = (cl * vol).rolling(20, min_periods=20).mean().to_numpy(dtype=float)
    g1 = (cl / cl.shift(1) - 1.0).to_numpy(dtype=float)
    cand = m.entry & m.universe
    每天候选 = cand.sum(axis=1)

    def 当天涨幅去尖(q):
        s = np.where(np.isfinite(g1), g1, -1e9)
        for i in np.where(每天候选 >= 10)[0]:
            js = np.where(cand[i])[0]
            k = int(math.ceil(q * len(js)))
            if k <= 0:
                continue
            top = js[np.argsort(-s[i, js])[:k]]
            s[i, top] = -1e8
        return s

    def 跑(score):
        m.rank_score = score
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True)
        led = res.ledger
        if len(led) and (set(led["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        eq = res.equity.reindex(perf).ffill()
        r = {"笔数": int(len(led)), **指标(eq, yrs)}
        if len(led):
            x = (led["net_pnl"] / led["notional_in"]).astype(float)
            赢, 亏 = x[x > 0], x[x < 0]
            tot = float(led["net_pnl"].sum())
            r.update({"胜率pct": round(float((x > 0).mean() * 100), 1),
                      "盈亏比": round(float(赢.mean() / -亏.mean()), 2) if len(赢) and len(亏) else None,
                      "最赚的两笔占全部利润pct": round(float(led["net_pnl"].nlargest(2).sum()) / tot * 100) if tot > 0 else None})
        return r

    版 = {"成交额大的先买_现在": 跑(rs0),
         "成交额小的先买": 跑(np.where(np.isfinite(adv), -adv, -1e18)),
         "当天涨幅_去掉最疯2pct": 跑(当天涨幅去尖(0.02)),
         "当天涨幅_去掉最疯5pct": 跑(当天涨幅去尖(0.05)),
         "当天涨幅_去掉最疯10pct": 跑(当天涨幅去尖(0.10))}
    随 = []
    挑得动 = bool((每天候选 > 1).any())
    for seed in range(20):
        rng = np.random.default_rng(20261118 + seed)
        随.append(跑(rng.random(rs0.shape)))
    m.rank_score = rs0
    def 排位(k, key):
        base = [x[key] for x in 随 if x.get(key) is not None]
        v = 版[k].get(key)
        return None if (v is None or not base) else int(sum(1 for b in base if v > b))
    def 分位(key, q):
        v = sorted(x[key] for x in 随 if x.get(key) is not None)
        return v[min(len(v) - 1, int(q * len(v)))] if v else None
    汇 = {"随机20次_每年赚": {"最低": 分位("复合年化pct", 0), "中间": 分位("复合年化pct", 0.5), "最高": 分位("复合年化pct", 0.999)},
         "随机20次_卡玛": {"最低": 分位("卡玛", 0), "中间": 分位("卡玛", 0.5), "最高": 分位("卡玛", 0.999)},
         "随机20次_最惨跌掉": {"最浅": 分位("最大回撤pct", 0.999), "中间": 分位("最大回撤pct", 0.5), "最深": 分位("最大回撤pct", 0)}}
    for k in 版:
        版[k]["好过随机20次里的几次_按每年赚"] = 排位(k, "复合年化pct")
        版[k]["好过随机20次里的几次_按卡玛"] = 排位(k, "卡玛")
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内流动性池中档（已拿掉 4 只断档票）", "分红": "含分红",
            "候选多于10个的交易日数": int((每天候选 > 10).sum()), "每天候选信号数_中位": float(np.median(每天候选[每天候选 > 0])) if (每天候选 > 0).any() else 0,
            "各版": 版, "随机对照": 汇, "随机每次": 随}


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
    for 名 in 清单():
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
