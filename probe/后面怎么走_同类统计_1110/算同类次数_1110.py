"""
「后面怎么走」同类状态历史统计 —— 1110（Lin 1110 13:08 同意《128》的做法）

大白话：把研发池 2,224 只票、2010~2025 年每一天都看一遍，记下「那天是什么状态」，
再看它之后 20 个交易日先往上走、先往下走、还是横着走。最后按状态数次数。

★ 口径全部先写死在这里，跑完不许回头改（防事后挑数据）：
  状态（第一层·原则）：engine.stages 五状态（生产口径，参数不动）
  同类（第二层·统计）：五状态 × RSI(14) 档（<30 / 30~40 / 40~70 / ≥70）× 当天是否「放量创 20 日新高」
        放量创新高 = 收盘 > 前 20 天最高价，且当天量 > 前 20 天均量 × 1.5（Gemini《128》给的例子）
  三种走法（Gemini《128》）：从当天收盘起 20 个交易日内
        先碰到 收盘 + 2×ATR20（盘中最高）= 往上；先碰到 收盘 − 1×ATR20（盘中最低）= 往下；
        同一天两边都碰到 → 记往下（保守）；20 天都没碰到 = 横着
  ★ 副尺：对称版 ±2×ATR20（同样规则）—— 因为 +2/−1 不对称，「往下」天生就多，必须有对称版对照
  价格：按 split_coefficient 复权（只拆股，不做分红复权，和 engine.stages 同口径）
  池子：研发池 2,224 只（probe/新策略_1106/holdout_newpool_1106.json）；★ 考卷 / 留出池一只不碰
        ★ B 类那 8 只票本身剔除（不让题目自己进统计）
  时间：信号日 2010-01-01 ~ 2025-11-28（之后不够 20 天看结果）；按年分开记，方便看稳不稳

输出：probe/后面怎么走_同类统计_1110/counts.csv（cell × 年 × 走法 次数）
跑法：python3 probe/后面怎么走_同类统计_1110/算同类次数_1110.py   （可续跑：每 200 只落一次盘）
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from engine.stages import compute_stages  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "counts.csv")
PART = os.path.join(HERE, "_parts")
START, END = "2010-01-01", "2025-11-28"
H = 20
B8 = {"META", "NUAN", "ED", "BGS", "ENTA", "EXPR", "ECL", "PODD"}


def rsi_bucket(r):
    return np.select([r < 30, r < 40, r < 70], ["<30", "30~40", "40~70"], ">=70")


def wilder(x, n):
    return x.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def one(sym):
    blob = json.load(gzip.open(os.path.join(REPO, f"market_ext_1105/{sym}/daily.json.gz")))
    df = pd.DataFrame(blob["data"])
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    sc = df["split_coefficient"].fillna(1.0).replace(0, 1.0).astype(float)
    # 当天的拆股系数作用在「之前」的价格上
    fac = sc[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float) / fac
    df["volume"] = df["volume"].astype(float) * fac
    df = df.dropna(subset=["close"])
    df = df[df["close"] > 0]
    if len(df) < 260:
        return None
    st = compute_stages(df[["close"]])["stage"]
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    d = c.diff()
    rs = wilder(d.clip(lower=0), 14) / wilder((-d).clip(lower=0), 14)
    rsi = 100 - 100 / (1 + rs)
    pc = c.shift(1)
    tr = np.fmax(np.fmax(h - l, (h - pc).abs()), (l - pc).abs())
    atr = wilder(tr, 20)
    brk = (c > h.shift(1).rolling(20).max()) & (v > 1.5 * v.shift(1).rolling(20).mean())

    C, Hh, Ll, A = c.to_numpy(), h.to_numpy(), l.to_numpy(), atr.to_numpy()
    T = len(C)
    idx = df.index
    keep = (idx >= START) & (idx <= END) & np.isfinite(A) & np.isfinite(rsi.to_numpy()) & \
           np.isin(st.to_numpy(), ["STAGE_2", "BULL_PULLBACK", "STAGE_4", "BEAR_RALLY", "CHOP"])
    out = []
    for t in np.flatnonzero(keep):
        if t + H >= T:
            continue
        hh, ll = Hh[t + 1:t + H + 1], Ll[t + 1:t + H + 1]
        if not (np.isfinite(hh).all() and np.isfinite(ll).all()):
            continue
        res = []
        for up_k, dn_k in ((2.0, 1.0), (2.0, 2.0)):
            up, dn = C[t] + up_k * A[t], C[t] - dn_k * A[t]
            iu = np.flatnonzero(hh >= up)
            idn = np.flatnonzero(ll <= dn)
            fu = iu[0] if len(iu) else 99
            fd = idn[0] if len(idn) else 99
            if fu == 99 and fd == 99:
                res.append("横着")
            elif fd <= fu:
                res.append("往下")
            else:
                res.append("往上")
        out.append((st.iloc[t], str(rsi_bucket(rsi.iloc[t])), bool(brk.iloc[t]), idx[t].year, res[0], res[1]))
    return out


def main():
    os.makedirs(PART, exist_ok=True)
    hold = json.load(open(os.path.join(REPO, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
    syms = [s for s in sorted(hold["研发池名单"]) if s.split("__")[0] not in B8]
    chunks = [syms[i:i + 200] for i in range(0, len(syms), 200)]
    t0 = time.time()
    for k, ch in enumerate(chunks):
        pf = os.path.join(PART, f"part_{k:02d}.csv")
        if os.path.exists(pf):
            continue
        rows = []
        for s in ch:
            try:
                r = one(s)
            except Exception as e:  # noqa: BLE001
                print("跳过", s, e, flush=True)
                continue
            if r:
                rows.extend(r)
        df = pd.DataFrame(rows, columns=["stage", "rsi", "brk", "year", "走法_不对称", "走法_对称"])
        g = df.groupby(["stage", "rsi", "brk", "year", "走法_不对称", "走法_对称"]).size().rename("n").reset_index()
        g.to_csv(pf, index=False)
        print(f"{k + 1}/{len(chunks)} 块完成，{len(rows)} 个样本日，{time.time() - t0:.0f}s", flush=True)
    allp = pd.concat([pd.read_csv(os.path.join(PART, f)) for f in sorted(os.listdir(PART))])
    allp.groupby(["stage", "rsi", "brk", "year", "走法_不对称", "走法_对称"])["n"].sum().reset_index().to_csv(OUT, index=False)
    print("完成", OUT, int(allp["n"].sum()), flush=True)


if __name__ == "__main__":
    main()
