# -*- coding: utf-8 -*-
"""
★★★ 出「大师测试」用的行情素材。
★ Lin 1105 18:29 定的判据:以 Gemini 为准,目的是看**我们抄得对不对**;
  两边**同题同约束**,拿到一模一样的数据。

★★ 纪律:
  · ⚠ 只用研发池(从 friction_rerun_1104 的流水里取 symbol) —— **考卷那 1,042 只不碰**
  · 每段只给到「提问日」为止的数据;后面 40 个交易日另存答案卷,★★★ 提问时不给
  · 三类环境各 2 段(照 Lin 的三分法:震荡 / 突破 / 大波段),★ 按客观规则挑,不是我挑的
"""
from __future__ import annotations
import glob, io, json, os, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.abspath("."))
from engine import cache                      # noqa: E402

OUT = "probe/大师测试_1105"
WIN, FWD = 120, 40                            # 给 120 根,答案看后面 40 根


def 研发池() -> list[str]:
    s = set()
    for f in glob.glob("probe/friction_rerun_1104/ledgers_1104/REAL__*.csv"):
        d = pd.read_csv(f, usecols=["symbol"])
        s |= set(d["symbol"].astype(str))
    return sorted(s)


def main() -> int:
    p = cache.load()
    cl, hi, lo, op, vol = p["close"], p["high"], p["low"], p["open"], p["volume"]
    syms = [s for s in 研发池() if s in cl.columns]
    idx = cl.index
    # ★ 候选提问日:2019-01 ~ 2025-06(前后都留够)
    cand = idx[(idx >= "2019-01-01") & (idx <= "2025-06-30")]
    rows = []
    for s in syms:
        c = cl[s]
        for t in cand[::21]:                  # ★ 每月一个点,降计算量
            i = idx.get_loc(t)
            if i < WIN or i + FWD >= len(idx):
                continue
            w = c.iloc[i - WIN + 1:i + 1]
            if w.isna().any() or (w <= 0).any():
                continue
            # ★ 三个客观刻度(全部只用窗口内数据)
            lr = np.log(w.to_numpy())
            x = np.arange(len(lr))
            k, b = np.polyfit(x, lr, 1)
            # ★★★ 这里原来写成 corrcoef(x, k*x+b) —— 那永远等于 1(拿 x 和 x 的线性
            #   函数求相关)。★ 正确的是 x 和真实序列 lr 求相关。
            r2 = float(np.corrcoef(x, lr)[0, 1] ** 2)
            斜率 = float(k * 252)
            幅宽 = float((w.max() - w.min()) / w.min())
            rows.append((s, t, 斜率, r2, 幅宽))
    d = pd.DataFrame(rows, columns=["symbol", "date", "斜率", "R2", "幅宽"])
    # ★★ 客观挑法(★ 规则写死,不是我看图挑的):
    picks = {
        "大波段(单边上行)": d[(d.斜率 > 0.5) & (d.R2 > 0.8)].nlargest(2, "R2"),
        "震荡(来回磨)":    d[(d.斜率.abs() < 0.15) & (d.R2 < 0.1)
                              & (d.幅宽.between(0.15, 0.45))].nsmallest(2, "R2"),
        "下行(单边向下)":  d[(d.斜率 < -0.5) & (d.R2 > 0.8)].nlargest(2, "R2"),
    }
    素材, 答案 = [], []
    seen = set()
    for 类, sub in picks.items():
        for _, r in sub.iterrows():
            if r.symbol in seen:
                continue
            seen.add(r.symbol)
            i = idx.get_loc(r.date)
            w = slice(i - WIN + 1, i + 1)
            bars = pd.DataFrame({
                "date": idx[w].strftime("%Y-%m-%d"),
                "open": op[r.symbol].iloc[w].round(2).to_numpy(),
                "high": hi[r.symbol].iloc[w].round(2).to_numpy(),
                "low":  lo[r.symbol].iloc[w].round(2).to_numpy(),
                "close": cl[r.symbol].iloc[w].round(2).to_numpy(),
                "volume": vol[r.symbol].iloc[w].astype("int64").to_numpy(),
            })
            f = slice(i + 1, i + 1 + FWD)
            fwd = pd.DataFrame({
                "date": idx[f].strftime("%Y-%m-%d"),
                "high": hi[r.symbol].iloc[f].round(2).to_numpy(),
                "low":  lo[r.symbol].iloc[f].round(2).to_numpy(),
                "close": cl[r.symbol].iloc[f].round(2).to_numpy(),
            })
            素材.append({"编号": f"行情-{len(素材)+1}", "类": 类,
                        "★代码已隐去": True, "真实代码": r.symbol,
                        "提问日": str(r.date.date()),
                        "客观刻度": {"年化斜率": round(float(r.斜率), 3),
                                   "R2": round(float(r.R2), 3),
                                   "窗口幅宽": round(float(r.幅宽), 3)},
                        "bars": bars.to_dict("records")})
            答案.append({"编号": f"行情-{len(答案)+1}", "真实代码": r.symbol,
                        "提问日": str(r.date.date()),
                        "后40根": fwd.to_dict("records")})
    os.makedirs(OUT, exist_ok=True)
    io.open(f"{OUT}/行情素材_1105.json", "w", encoding="utf-8").write(
        json.dumps(素材, ensure_ascii=False, indent=1))
    io.open(f"{OUT}/行情素材_答案卷_1105.json", "w", encoding="utf-8").write(
        json.dumps(答案, ensure_ascii=False, indent=1))
    print(f"★ {len(素材)} 段 · 每段 {WIN} 根 · 答案卷各 {FWD} 根")
    for m in 素材:
        print(f"   {m['编号']} {m['类']:14s} {m['真实代码']:6s} "
              f"提问日 {m['提问日']} 斜率{m['客观刻度']['年化斜率']:+.2f} "
              f"R2={m['客观刻度']['R2']:.2f} 幅宽{m['客观刻度']['窗口幅宽']:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
