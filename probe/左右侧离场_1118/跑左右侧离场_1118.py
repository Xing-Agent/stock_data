#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""左右侧结合离场 · 顶部形态当「早走」规则（2026-11-18 · Lin 拍板《303-Gemini回复与判断》三条）

大白话：同一条趋势策略跑三版 ——
  只晚走（右侧）  原来的离场规则
  只早走（左侧）  原来的离场规则 + 「顶部形态一确认就走」
  各一半          两个账户各一半本金：甲 = 只早走，且卖出后 15 个交易日不买回；乙 = 只晚走
跑前写死的判据（沿用 11-12）：各一半的卡玛（每年赚 ÷ 最惨跌掉）要明显好过前两版里较好的那个，才留。
另外必看：只晚走版里最赚钱的 5 笔，在只早走版里被砍掉了多少。

顶部形态「XING 版」—— 数的归属写在每一行；右顶要过 3 天才确认（不偷看）：
  波峰        当天最高价是前后各 3 天里最高的；3 天后才算数
  双顶        两峰相隔 21~65 个交易日（下限：Edwards & Magee「约一个月以上」；上限 65：Gemini 推荐）
              两峰高度相差 <= 3%（E&M / Bulkowski，待核）
              中间最低点比第一峰低 >= 10%（行业软件口径；E&M 是 15%~20%，Gemini 推荐 8%）
  三重顶      三峰两两相隔 10~40 天，三峰极差 <= 3%，两个谷底都比前峰低 >= 10%（Bulkowski / 行业，待核）
  头肩顶      三峰两两相隔 10~35 天；头比两肩都高 >= 3%；两肩相差 <= 5%；两个谷底比头低 >= 10%（行业常用）
  「严重」版  在上面基础上再加两条（Gemini 推荐）：第一峰之前 120 天内涨过 >= 40%；右顶那 5 天的平均成交量小于左顶那 5 天
              ★ Gemini 的「严重」是四条满足三条，另外两条没做：派发日（它的定义和 O'Neil 原著不一样，待核）、看跌 K 线（没给可算的定义）
相邻三点（只动双顶，每次一个数）：间隔上限 45 / 90；回落 8% / 15%；同高 2% / 4%。
MFI 顶背离版（11-14 那套五步）并排放一版。
「创新高买回」不做（Lin 11-18 定）。选股范围：流动性池中档。含分红。engine/ 一个字节不改。只用研发池。
"""
import copy, io, json, os, subprocess, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
POOL = os.path.join(ROOT, "probe/流动性池_1114")
挑 = ["技-1", "trend_following", "trend_following-原著-唐奇安反向通道离场"]
中 = {"双顶间隔下": 21, "双顶间隔上": 65, "同高": 0.03, "回落": 0.10}
三点 = {"双顶间隔上": (45, 90), "回落": (0.08, 0.15), "同高": (0.02, 0.04)}


def 找波峰(h, k=3):
    import numpy as np
    T = len(h)
    out = []
    for p in range(k, T - k):
        if not np.isfinite(h[p]):
            continue
        w = h[p - k:p + k + 1]
        if np.isfinite(w).all() and h[p] >= w.max():
            if out and p - out[-1] <= k and h[out[-1]] >= h[p]:
                continue
            out.append(p)
    return out


def 形态矩阵(hi, lo, vol, P, 严重=False, 只双顶=False):
    """返回 [日 x 票] 布尔：这一天收盘确认了顶部形态（右顶之后第 3 天）。只用当天及以前的数据。"""
    import numpy as np
    T, N = hi.shape
    sig = np.zeros((T, N), dtype=bool)
    数 = {"双顶": 0, "三重顶": 0, "头肩顶": 0}
    for j in range(N):
        h, l, v = hi[:, j], lo[:, j], vol[:, j]
        if np.isfinite(h).sum() < 200:
            continue
        pk = 找波峰(h)

        def 严重吗(p1, p2):
            a = max(0, p1 - 120)
            base = np.nanmin(l[a:p1 + 1]) if p1 > a else np.nan
            if not np.isfinite(base) or base <= 0 or h[p1] / base - 1 < 0.40:
                return False
            v1, v2 = np.nanmean(v[max(0, p1 - 2):p1 + 3]), np.nanmean(v[max(0, p2 - 2):p2 + 3])
            return np.isfinite(v1) and np.isfinite(v2) and v2 < v1

        for b in range(1, len(pk)):
            p2 = pk[b]
            t = p2 + 3
            if t >= T:
                continue
            hit = None
            # 双顶
            for a_ in range(b - 1, -1, -1):
                p1 = pk[a_]
                gap = p2 - p1
                if gap > P["双顶间隔上"]:
                    break
                if gap < P["双顶间隔下"]:
                    continue
                top = max(h[p1], h[p2])
                if abs(h[p1] - h[p2]) / top > P["同高"]:
                    continue
                if np.nanmax(h[p1 + 1:p2]) > top:
                    continue
                V = np.nanmin(l[p1:p2 + 1])
                if (h[p1] - V) / h[p1] < P["回落"]:
                    continue
                if 严重 and not 严重吗(p1, p2):
                    continue
                hit = "双顶"
                break
            # 三重顶 / 头肩顶（用相邻的三个波峰）
            if hit is None and not 只双顶 and b >= 2:
                p1, pm = pk[b - 2], pk[b - 1]
                g1, g2 = pm - p1, p2 - pm
                h1, hm, h2 = h[p1], h[pm], h[p2]
                V1, V2 = np.nanmin(l[p1:pm + 1]), np.nanmin(l[pm:p2 + 1])
                if 10 <= g1 <= 40 and 10 <= g2 <= 40:
                    mx, mn = max(h1, hm, h2), min(h1, hm, h2)
                    if (mx - mn) / mx <= 0.03 and (h1 - V1) / h1 >= 0.10 and (hm - V2) / hm >= 0.10:
                        if not 严重 or 严重吗(p1, p2):
                            hit = "三重顶"
                if hit is None and 10 <= g1 <= 35 and 10 <= g2 <= 35:
                    if hm >= h1 * 1.03 and hm >= h2 * 1.03 and abs(h1 - h2) / max(h1, h2) <= 0.05 \
                            and (hm - V1) / hm >= 0.10 and (hm - V2) / hm >= 0.10:
                        if not 严重 or 严重吗(p1, p2):
                            hit = "头肩顶"
            if hit:
                sig[t, j] = True
                数[hit] += 1
    return sig, 数


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    sys.path.insert(0, POOL)
    sys.path.insert(0, os.path.join(ROOT, "probe/分批离场_1114"))
    import yaml, numpy as np, pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data, pat6_ops, cache
    from 跑技术面换池_1114 import 指标
    from 跑分批离场_1114 import 顶背离矩阵, 中 as 背离中
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    idx, perf = m.index, mk.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    start, end = data.PERF_START, data.PERF_END
    vol = cache._PANEL["volume"].reindex(index=idx, columns=list(m.symbols)).to_numpy(dtype=float)
    mf = pat6_ops.mfi(14, list(m.symbols)).reindex(idx).to_numpy(dtype=float)
    exit0, entry0 = m.exit_sig.copy(), m.entry.copy()
    pos = {d: i for i, d in enumerate(idx)}

    def 跑():
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, start, end, m=m, total_return=True)
        if len(res.ledger) and (set(res.ledger["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        return res

    def 摘(res):
        eq = res.equity.reindex(perf).ffill()
        led = res.ledger
        r = {"笔数": int(len(led)), "平均仓位pct": round(float(res.exposure.reindex(perf).fillna(0).mean() * 100), 1), **指标(eq, yrs)}
        if len(led):
            x = (led["net_pnl"] / led["notional_in"]).astype(float)
            赢, 亏 = x[x > 0], x[x < 0]
            r["胜率pct"] = round(float((x > 0).mean() * 100), 1)
            r["盈亏比"] = round(float(赢.mean() / -亏.mean()), 2) if len(赢) and len(亏) else None
            y0 = eq.resample("YE").last()
            ys = [float(y0.iloc[0] / eq.dropna().iloc[0] - 1)] + list(y0.pct_change().dropna().values)
            r["赚钱的年数"] = f"{sum(1 for v in ys if v > 0)} / {len(ys)}"
        return r, eq / float(eq.dropna().iloc[0]), led

    def 早走版(sig, 冷却=False):
        m.exit_sig = exit0 | sig
        m.entry = entry0.copy()
        res = 跑()
        轮 = 违 = 0
        if 冷却:
            for 轮 in range(1, 9):
                led = res.ledger
                违 = 0
                for s, g in led.groupby("symbol"):
                    ex = [pos.get(pd.Timestamp(x)) for x in g["exit_date"]]
                    en = [pos.get(pd.Timestamp(x)) for x in g["entry_date"]]
                    j = m.col[str(s)]
                    for e in ex:
                        if e is None:
                            continue
                        if any(x is not None and e < x <= e + 15 for x in en):
                            违 += 1
                        m.entry[e:e + 16, j] = False
                if 违 == 0:
                    break
                res = 跑()
        r, eq, led = 摘(res)
        if 冷却:
            r.update({"冷却迭代轮数": 轮, "最后一轮仍违反冷却的笔数": 违})
        m.exit_sig, m.entry = exit0, entry0
        return r, eq, led

    版 = {}
    m.exit_sig, m.entry = exit0, entry0
    版["只晚走_右侧"], eq晚, led晚 = 摘(跑())
    前5 = led晚.nlargest(5, "net_pnl")[["symbol", "entry_date", "exit_date", "net_pnl"]].copy() if len(led晚) else None

    def 砍了多少(led早):
        # 1118 改：原先按「同一只票 + 同一个进场日」去对，结果全对不上（早走后腾出位子，后面买的票和日子都变了）。
        # 现在按「同一只票、在只晚走那笔的持有期间内进场的所有交易」合计来比。
        if 前5 is None or not len(led早):
            return None
        e早 = pd.to_datetime(led早["entry_date"]); sym早 = led早["symbol"].astype(str)
        out, 晚和, 早和 = [], 0.0, 0.0
        for _, t in 前5.iterrows():
            a, b = pd.Timestamp(t["entry_date"]), pd.Timestamp(t["exit_date"])
            sel = (sym早 == str(t["symbol"])) & (e早 >= a - pd.Timedelta(days=7)) & (e早 <= b)
            早 = float(led早.loc[sel, "net_pnl"].sum())
            晚和 += float(t["net_pnl"]); 早和 += 早
            out.append({"票": str(t["symbol"]), "只晚走进场": str(a.date()), "只晚走离场": str(b.date()),
                        "只晚走赚": round(float(t["net_pnl"])), "只早走同期同票笔数": int(sel.sum()), "只早走同期同票合计赚": round(早)})
        return {"逐笔": out, "只晚走前5笔合计": round(晚和), "同票同期在只早走版合计": round(早和),
                "保住的比例pct": round(早和 / 晚和 * 100, 1) if 晚和 > 0 else None}

    def 一组(标, sig, 数=None):
        a, _, led早 = 早走版(sig)
        甲, eq甲, _ = 早走版(sig, 冷却=True)
        半 = 指标(0.5 * eq甲 + 0.5 * eq晚, yrs)
        较好 = max([x for x in (版["只晚走_右侧"]["卡玛"], a["卡玛"]) if x is not None], default=None)
        版[标] = {"信号票日数": int(sig.sum()), "各形态确认次数": 数, "只早走_左侧": a, "各一半": 半,
                 "各一半的甲账户": 甲,
                 "各一半卡玛_减_前两版较好者": None if (较好 is None or 半["卡玛"] is None) else round(半["卡玛"] - 较好, 3),
                 "最赚钱5笔被砍了多少": 砍了多少(led早)}

    sig, 数 = 形态矩阵(m.high, m.low, vol, 中)
    一组("顶部形态_基础版", sig, 数)
    sig, 数 = 形态矩阵(m.high, m.low, vol, 中, 严重=True)
    一组("顶部形态_严重版", sig, 数)
    div, _, _ = 顶背离矩阵(m.high, m.low, m.close, mf, m.atr, 背离中)
    一组("MFI顶背离_1114那套", div)
    扫 = {}
    for k, (lo_, hi_) in 三点.items():
        for v in (lo_, hi_):
            P = dict(中); P[k] = v
            sig, 数 = 形态矩阵(m.high, m.low, vol, P, 只双顶=True)
            a, _, _ = 早走版(sig)
            甲, eq甲, _ = 早走版(sig, 冷却=True)
            扫[f"{k}={v}"] = {"信号票日数": int(sig.sum()), "只早走": {x: a.get(x) for x in ("笔数", "复合年化pct", "最大回撤pct", "卡玛")},
                             "各一半": 指标(0.5 * eq甲 + 0.5 * eq晚, yrs)}
    sig, 数 = 形态矩阵(m.high, m.low, vol, 中, 只双顶=True)
    a, _, _ = 早走版(sig); 甲, eq甲, _ = 早走版(sig, 冷却=True)
    扫["中间点_只双顶"] = {"信号票日数": int(sig.sum()), "只早走": {x: a.get(x) for x in ("笔数", "复合年化pct", "最大回撤pct", "卡玛")},
                      "各一半": 指标(0.5 * eq甲 + 0.5 * eq晚, yrs)}
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内流动性池中档", "分红": "含分红",
            "中间点参数": 中, "各版": 版, "相邻三点_只双顶": 扫}


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
