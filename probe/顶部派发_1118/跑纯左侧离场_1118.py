#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯左侧离场 · 放进账户里跑（2026-11-18 · Lin 同意）

大白话：「数左侧信号」已经数出纯左侧信号 11 年只有约 800 次、之后七成会跌破 50 日线。
       这里把它放进真实的 10 个位子账户里，三版并排：
  只右侧      原来的离场规则
  只左侧      原来的离场规则 + 纯左侧信号一出现就走（两个前提 + 高位停留 + 量上派发 + 指标顶背离，不看跌破）
  各一半      两个账户各一半本金：甲 = 只左侧，卖出后 15 个交易日不买回；乙 = 只右侧
判据（沿用 11-12）：各一半的卡玛（每年赚 ÷ 最惨跌掉）明显好过前两版里较好的那个才留。
另看：最惨跌掉变化多少；只右侧版最赚的 5 笔，在只左侧版里保住多少。
数全是 Gemini 推荐（《309》），每次只动一个数、往两边各挪一档：
  之前涨幅 35% → 25% / 45%；离高点 15% → 10% / 20%；高位停留 20 天 → 15 / 30；派发日 4 个 → 3 / 5；RSI 回落 5 → 3 / 8。
流动性池中档（已拿掉 4 只断档票）。含分红。只用研发池。2015–2025。engine/ 一个字节不改。
"""
import copy, io, json, os, subprocess, sys, time, traceback
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, "out_账户")
POOL = os.path.join(ROOT, "probe/流动性池_1114")
挑 = ["技-1", "trend_following", "trend_following-原著-唐奇安反向通道离场", "技-3-XING", "技-6-XING"]
中 = {"涨幅": 0.35, "离高点": 0.15, "停留": 20, "派发日": 4, "RSI回落": 5.0}
三点 = {"涨幅": (0.25, 0.45), "离高点": (0.10, 0.20), "停留": (15, 30), "派发日": (3, 5), "RSI回落": (3.0, 8.0)}


def 左侧矩阵(H, L, C, V, P):
    import numpy as np, pandas as pd
    idx = C.index; cv = C.to_numpy(); T, N = cv.shape
    pc = C.shift(1)
    tr = pd.concat([H - L, (H - pc).abs(), (L - pc).abs()]).groupby(level=0).max().reindex(idx)
    atr = tr.rolling(14, min_periods=14).mean()
    hi252 = H.rolling(252, min_periods=120).max()
    前提A = (H.rolling(120, min_periods=60).max() / L.rolling(120, min_periods=60).min() - 1) >= P["涨幅"]
    近高 = C >= (1 - P["离高点"]) * hi252
    停留 = (近高.rolling(60, min_periods=20).sum() >= P["停留"]).to_numpy()
    ret = C / pc - 1
    vol20 = V.rolling(20, min_periods=20).mean()
    dd = ((ret <= -np.maximum(0.01, 0.5 * atr / pc)) & (V > V.shift(1)) & (V > 1.1 * vol20)).to_numpy()
    ddcnt = np.zeros((T, N), dtype=np.int16)
    for k in range(0, 25):
        d = np.zeros((T, N), dtype=bool); d[k:] = dd[:T - k]
        ck = np.full((T, N), np.nan); ck[k:] = cv[:T - k]
        ddcnt += (d & (cv <= 1.05 * ck)).astype(np.int16)
    up = (V * (ret > 0)).rolling(20, min_periods=20).sum(); dn = (V * (ret < 0)).rolling(20, min_periods=20).sum()
    量 = (ddcnt >= P["派发日"]) | ((up / dn) < 0.85).to_numpy()
    dlt = C.diff(); g = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    ls = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rsi = (100 - 100 / (1 + g / ls)).to_numpy()
    背离 = np.zeros((T, N), dtype=bool)
    pk = (C == C.rolling(7, center=True, min_periods=7).max()).to_numpy()
    for j in range(N):
        ps = np.where(pk[:, j])[0]
        for b in range(1, len(ps)):
            t1, t2 = ps[b - 1], ps[b]
            if 10 <= t2 - t1 <= 60 and t2 + 3 < T and cv[t2, j] >= 0.99 * cv[t1, j] and rsi[t1, j] >= 70 and rsi[t2, j] <= rsi[t1, j] - P["RSI回落"]:
                背离[t2 + 3:min(T, t2 + 3 + 10), j] = True
    return (前提A & 近高).to_numpy() & 停留 & 量 & 背离


def 跑一条(名):
    sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106")); sys.path.insert(0, POOL)
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
    H, L, C, V = (cache._PANEL[k].reindex(index=idx, columns=list(m.symbols)).astype(float) for k in ("high", "low", "close", "volume"))
    exit0, entry0 = m.exit_sig.copy(), m.entry.copy()
    pos = {d: i for i, d in enumerate(idx)}

    def 跑():
        res = chain.run_chain(chain.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True)
        if len(res.ledger) and (set(res.ledger["symbol"].astype(str)) & hs):
            raise RuntimeError("留出池漏进来")
        return res

    def 摘(res):
        eq = res.equity.reindex(perf).ffill(); led = res.ledger
        r = {"笔数": int(len(led)), **指标(eq, yrs)}
        if len(led):
            x = (led["net_pnl"] / led["notional_in"]).astype(float); 赢, 亏 = x[x > 0], x[x < 0]
            r["胜率pct"] = round(float((x > 0).mean() * 100), 1)
            r["盈亏比"] = round(float(赢.mean() / -亏.mean()), 2) if len(赢) and len(亏) else None
            r["因左侧信号离场的笔数"] = None
        return r, eq / float(eq.dropna().iloc[0]), led

    def 左版(sig, 冷却=False):
        m.exit_sig = exit0 | sig; m.entry = entry0.copy()
        res = 跑()
        if 冷却:
            for _ in range(8):
                led = res.ledger; 违 = 0
                for s, g in led.groupby("symbol"):
                    ex = [pos.get(pd.Timestamp(x)) for x in g["exit_date"]]; en = [pos.get(pd.Timestamp(x)) for x in g["entry_date"]]
                    j = m.col[str(s)]
                    for e in ex:
                        if e is None: continue
                        if any(x is not None and e < x <= e + 15 for x in en): 违 += 1
                        m.entry[e:e + 16, j] = False
                if 违 == 0: break
                res = 跑()
        out = 摘(res)
        m.exit_sig, m.entry = exit0, entry0
        return out

    r晚, eq晚, led晚 = 摘(跑())
    前5 = led晚.nlargest(5, "net_pnl") if len(led晚) else None

    def 保住(led早):
        if 前5 is None or not len(led早): return None
        e早 = pd.to_datetime(led早["entry_date"]); sym = led早["symbol"].astype(str); a_ = b_ = 0.0
        for _, t in 前5.iterrows():
            sel = (sym == str(t["symbol"])) & (e早 >= pd.Timestamp(t["entry_date"]) - pd.Timedelta(days=7)) & (e早 <= pd.Timestamp(t["exit_date"]))
            a_ += float(t["net_pnl"]); b_ += float(led早.loc[sel, "net_pnl"].sum())
        return round(b_ / a_ * 100, 1) if a_ > 0 else None

    def 一组(P):
        sig = 左侧矩阵(H, L, C, V, P)
        持仓中触发 = None
        a, _, led早 = 左版(sig)
        甲, eq甲, _ = 左版(sig, 冷却=True)
        半 = 指标(0.5 * eq甲 + 0.5 * eq晚, yrs)
        较好 = max([x for x in (r晚["卡玛"], a["卡玛"]) if x is not None], default=None)
        return {"信号票日数": int(sig.sum()), "只左侧": a, "各一半": 半,
                "各一半卡玛_减_前两版较好者": None if (较好 is None or 半["卡玛"] is None) else round(半["卡玛"] - 较好, 3),
                "只右侧最赚5笔_在只左侧版保住pct": 保住(led早)}

    out = {"名": 名, "窗口": f"{perf[0].date()} → {perf[-1].date()}", "池": "研发池内流动性池中档（已拿掉 4 只断档票）", "分红": "含分红",
           "只右侧": r晚, "中间值": 一组(中), "相邻三点": {}}
    for k, (lo_, hi_) in 三点.items():
        for v in (lo_, hi_):
            P = dict(中); P[k] = v
            g = 一组(P)
            out["相邻三点"][f"{k}={v}"] = {"信号票日数": g["信号票日数"], "只左侧_每年赚": g["只左侧"]["复合年化pct"], "只左侧_最惨跌掉": g["只左侧"]["最大回撤pct"],
                                        "只左侧_卡玛": g["只左侧"]["卡玛"], "各一半_卡玛": g["各一半"]["卡玛"], "各一半_最惨跌掉": g["各一半"]["最大回撤pct"],
                                        "各一半卡玛_减_较好者": g["各一半卡玛_减_前两版较好者"], "最赚5笔保住pct": g["只右侧最赚5笔_在只左侧版保住pct"]}
    return out


def main(argv):
    os.makedirs(OUT, exist_ok=True)
    if "--one" in argv:
        名 = argv[argv.index("--one") + 1]; t = time.time()
        try:
            rec = 跑一条(名)
        except Exception as e:
            rec = {"名": 名, "跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-2500:]}
        rec["总秒"] = round(time.time() - t, 1)
        io.open(os.path.join(OUT, 名 + ".json"), "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("FAIL " if "跑失败" in rec else "ok   ") + 名, flush=True)
        return 0
    for 名 in 挑:
        if os.path.exists(os.path.join(OUT, 名 + ".json")): continue
        subprocess.run([sys.executable, os.path.abspath(__file__), "--one", 名], cwd=ROOT)
    print("ALL_DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
