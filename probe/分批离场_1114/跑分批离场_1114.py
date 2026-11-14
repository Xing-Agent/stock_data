#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分批离场小对照（2026-11-14 · Lin 1112 拍板《172》第 3 条）

大白话：同一条趋势策略跑三版 ——
  只晚走   原来的离场规则，一个账户
  只早走   原来的离场规则 + 「大型顶背离」一出现就先走，一个账户
  各一半   两个账户各拿一半本金：甲账户 = 只早走，并且同一只票卖出后 15 个交易日内不再买回；
          乙账户 = 只晚走。两条净值各占一半相加（之后不再互相调拨）。
跑前写死的判据：「各一半」的卡玛明显好过前两版里较好的那个，才考虑推广。

顶背离「XING 版」（照 Gemini 五步；数全是它给的 → 标「推断」，每个数跑相邻三点）：
  1 波峰：最高价是前后各 3 天里最高、同一天 MFI(14) 也是前后各 3 天里最高；3 天后才算确认（不偷看）
  2 大型：两峰相隔 15~60 个交易日；第一峰 MFI >= 75；两峰之间 MFI 跌到过 55 以下
  3 背离：第二峰最高价比第一峰高出 0.25 个 ATR 以上；第二峰 MFI 比第一峰低 8 点以上
  4 扳机：第二峰确认后 10 个交易日内，收盘跌破前 3 日最低，且 MFI < 50 → 当天收盘记离场
  5 作废：扳机前最高价比第二峰再高出 1 个 ATR → 作废
  两处没照做，写明：第 5 步的「放量」没加（没给量的门槛）；「15 天内没触发作废」被第 4 步的 10 天窗口盖住了。
  「同峰」另备一个宽一点的口径（MFI 取价格峰前后 3 天内的最高值），只在照字面的信号太少时当对照，标明是我们放宽的。

冷却的做法（引擎不改）：先跑一遍，把甲账户每笔卖出后 15 个交易日的进场信号在内存里抹掉，再跑，直到没有违反为止（最多 8 轮）。
冷却对甲账户所有卖出都生效（引擎的流水分不出「因顶背离走」和「因原规则走」）。
选股范围：流动性池「中」档。策略侧含分红。engine/ 一个字节不改。只用研发池。
"""
import copy
import io
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out")
POOL = os.path.join(ROOT, "probe/流动性池_1114")
挑 = ["技-1", "trend_following", "技-1-原著-唐奇安反向通道离场"]
中 = {"间隔下": 15, "间隔上": 60, "首峰MFI": 75.0, "回落MFI": 55.0, "价差ATR": 0.25, "MFI差": 8.0}
三点 = {"首峰MFI": (70.0, 80.0), "回落MFI": (50.0, 60.0), "价差ATR": (0.0, 0.5), "MFI差": (5.0, 11.0),
        "间隔": ((10, 40), (20, 80))}


def 顶背离矩阵(hi, lo, cl, mf, atr, P, 宽同峰=False):
    """返回 [日 x 票] 布尔：这一天收盘触发顶背离离场。全部只用当天及以前的数据。"""
    import numpy as np
    T, N = hi.shape
    out = np.zeros((T, N), dtype=bool)
    n峰 = n对 = 0
    for j in range(N):
        h, l, c, f, a = hi[:, j], lo[:, j], cl[:, j], mf[:, j], atr[:, j]
        if not np.isfinite(f).any():
            continue
        peaks = []
        for p in range(3, T - 3):
            if not (np.isfinite(h[p]) and np.isfinite(f[p])):
                continue
            wh = h[p - 3:p + 4]
            wf = f[p - 3:p + 4]
            if not np.isfinite(wh).all() or h[p] < np.nanmax(wh):
                continue
            if 宽同峰:
                fv = np.nanmax(wf)
            else:
                if not np.isfinite(wf).all() or f[p] < np.nanmax(wf):
                    continue
                fv = f[p]
            peaks.append((p, fv))
        n峰 += len(peaks)
        for b in range(1, len(peaks)):
            p2, f2 = peaks[b]
            for a_ in range(b - 1, -1, -1):
                p1, f1 = peaks[a_]
                gap = p2 - p1
                if gap > P["间隔上"]:
                    break
                if gap < P["间隔下"] or f1 < P["首峰MFI"]:
                    continue
                if np.nanmin(f[p1:p2 + 1]) >= P["回落MFI"]:
                    continue
                if not np.isfinite(a[p2]) or h[p2] < h[p1] + P["价差ATR"] * a[p2] or f2 > f1 - P["MFI差"]:
                    continue
                n对 += 1
                for t in range(p2 + 4, min(p2 + 3 + 10, T - 1) + 1):
                    if np.nanmax(h[p2 + 1:t + 1]) > h[p2] + a[p2]:
                        break
                    if c[t] < np.nanmin(l[t - 3:t]) and f[t] < 50.0:
                        out[t, j] = True
                        break
                break
    return out, n峰, n对


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
    sys.path.insert(0, POOL)
    import yaml
    import numpy as np
    import pandas as pd
    import 跑基本面_1106 as B
    RC, _ = B.装层()
    import 补分红_1107 as DIV
    DIV.install()
    from engine import chain, matrices, data, pat6_ops
    from 跑技术面换池_1114 import 指标
    hold = json.load(io.open(B.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    mk = pd.read_parquet(os.path.join(POOL, "流动性池掩膜_中.parquet"))
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    idx = m.index
    perf = mk.index
    yrs = (perf[-1] - perf[0]).days / 365.25
    start, end = data.PERF_START, data.PERF_END
    mf = pat6_ops.mfi(14, list(m.symbols)).reindex(idx).to_numpy(dtype=float)
    exit0, entry0 = m.exit_sig.copy(), m.entry.copy()
    pos = {d: i for i, d in enumerate(idx)}

    def 跑():
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, start, end, m=m,
                              total_return=True)
        if len(res.ledger) and (set(res.ledger["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        return res

    def 摘(res):
        eq = res.equity.reindex(perf).ffill()
        led = res.ledger
        r = {"笔数": int(len(led)), "平均仓位pct": round(float(res.exposure.reindex(perf).fillna(0).mean() * 100), 1),
             **指标(eq, yrs)}
        if len(led):
            r["离场原因笔数"] = {str(k): int(v) for k, v in led["reason"].value_counts().items()}
        return r, eq / float(eq.iloc[0])

    def 早走版(P, 宽=False, 冷却=False):
        div, n峰, n对 = 顶背离矩阵(m.high, m.low, m.close, mf, m.atr, P, 宽)
        m.exit_sig = exit0 | div
        m.entry = entry0.copy()
        res = 跑()
        轮 = 违 = 0
        if 冷却:
            for 轮 in range(1, 9):
                led = res.ledger
                违 = 0
                for s, g in led.groupby("symbol"):
                    g = g.sort_values("entry_date")
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
        r, eq = 摘(res)
        r.update({"确认的波峰数": int(n峰), "成立的背离对数": int(n对), "顶背离触发的票日数": int(div.sum())})
        if 冷却:
            r.update({"冷却迭代轮数": 轮, "最后一轮仍违反冷却的笔数": 违})
        m.exit_sig, m.entry = exit0, entry0
        return r, eq

    版 = {}
    m.exit_sig, m.entry = exit0, entry0
    版["只晚走"], eq晚 = 摘(跑())
    版["只早走"], _ = 早走版(中)
    甲, eq甲 = 早走版(中, 冷却=True)
    eq半 = 0.5 * eq甲 + 0.5 * eq晚
    版["各一半"] = {"甲账户_早走加冷却": 甲, **指标(eq半, yrs)}
    较好 = max([x for x in (版["只晚走"]["卡玛"], 版["只早走"]["卡玛"]) if x is not None], default=None)
    版["各一半"]["卡玛_减_前两版较好者"] = (None if (较好 is None or 版["各一半"]["卡玛"] is None)
                                   else round(版["各一半"]["卡玛"] - 较好, 3))
    # 放宽同峰口径的对照（我们放宽的，不是五步原文）
    版["只早走_放宽同峰"], _ = 早走版(中, 宽=True)
    甲宽, eq甲宽 = 早走版(中, 宽=True, 冷却=True)
    版["各一半_放宽同峰"] = {"甲账户_早走加冷却": 甲宽, **指标(0.5 * eq甲宽 + 0.5 * eq晚, yrs)}
    # 相邻三点：每次只动一个数，看「只早走」和「各一半」
    扫 = {}
    for k, (lo_, hi_) in 三点.items():
        for 标, v in (("低", lo_), ("高", hi_)):
            P = dict(中)
            if k == "间隔":
                P["间隔下"], P["间隔上"] = v
            else:
                P[k] = v
            a, _ = 早走版(P)
            b, eqb = 早走版(P, 冷却=True)
            扫[f"{k}={v}"] = {"只早走": {x: a[x] for x in ("笔数", "复合年化pct", "最大回撤pct", "卡玛", "顶背离触发的票日数")},
                             "各一半": 指标(0.5 * eqb + 0.5 * eq晚, yrs)}
    return {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内的流动性池「中」档",
            "分红": "策略侧含分红", "中间点参数": 中, "各版": 版, "相邻三点": 扫}


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
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    import subprocess
    for 名 in 挑:
        if os.path.exists(os.path.join(OUT, 名 + ".json")):
            continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
