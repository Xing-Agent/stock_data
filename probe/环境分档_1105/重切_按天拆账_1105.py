# -*- coding: utf-8 -*-
"""
★★★ 重切 —— 照第 39 轮 Gemini 指出的两条问题改。
★ Lin 1105 18:32 转来并同意。

★★ 改三件:
 ① **标签贴错** → 原来按「进场那天」给整笔交易贴标签。
    改成**按持有天数分摊**:一笔交易的 R,按它持有期里落在各档的天数比例分摊。
    ★★★ 这是我们能做到的最接近「按天拆账」的做法 —— 流水只有进/出两天,
       没有逐日盈亏,所以**分摊是近似,不是真的按天记账**,这一点必须标明。
 ② **样本不独立** → 普通标准误作废。改用**按区间聚簇**的标准误
    (同一段「大盘在线上/线下」的连续区间算一个簇)。
 ③ **V 型反转验证**(★ Gemini 的推断,我们自己验):
    在 200 日线下方进场的交易,按「**持有期间大盘有没有重新站上 200 日线**」分两组。
    ★★★ 若好成绩几乎都在「站回去了」那组 → 赚的是大盘反弹的钱,不是突破在熊市好使。
"""
from __future__ import annotations
import glob, io, json, os, re, sys
import numpy as np, pandas as pd
sys.path.insert(0, os.path.abspath("."))
from engine import data as edata              # noqa: E402

LED = "probe/friction_rerun_1104/ledgers_1104"
OUT = "probe/环境分档_1105"
MIN_N = 30


def 大盘() -> tuple[pd.Series, pd.Series]:
    spy = edata.load_benchmark("SPY")
    px = spy["close"].astype(float)
    ma = px.rolling(200, min_periods=200).mean()
    above = (px > ma).where(ma.notna())
    seg = (above != above.shift()).cumsum()    # ★ 连续区间编号 = 聚簇单位
    return above, seg


def 聚簇SE(r: np.ndarray, cl: np.ndarray) -> float:
    """★★ 按簇算均值的标准误(簇间方差),★ 簇内怎么相关都不管。"""
    df = pd.DataFrame({"r": r, "c": cl})
    g = df.groupby("c")["r"]
    n_c, m_c = g.size().to_numpy(float), g.mean().to_numpy(float)
    G = len(n_c)
    if G < 2:
        return float("nan")
    w = n_c / n_c.sum()
    mu = float((w * m_c).sum())
    v = float((w ** 2 * ((m_c - mu) ** 2)).sum()) * G / (G - 1)
    return float(np.sqrt(v))


def 格(r: np.ndarray, cl: np.ndarray, w: np.ndarray | None = None) -> dict:
    n = len(r)
    if n == 0:
        return {"笔数": 0, "★状态": "算不出(没有交易)"}
    mu = float(np.average(r, weights=w)) if w is not None else float(r.mean())
    se_p = float(r.std(ddof=1) / np.sqrt(n)) if n > 1 else float("nan")
    se_c = 聚簇SE(r, cl)
    G = int(pd.Series(cl).nunique())
    o = {"笔数": n, "★簇数": G, "每笔净R": round(mu, 4),
         "普通标准误(作废·仅作对比)": None if not np.isfinite(se_p) else round(se_p, 4),
         "★聚簇标准误": None if not np.isfinite(se_c) else round(se_c, 4)}
    if n < MIN_N or G < 5:
        o["★状态"] = f"笔数<{MIN_N} 或 簇数<5(只给数,不给结论)"
    elif not np.isfinite(se_c) or abs(mu) <= 2 * se_c:
        o["★状态"] = "和0分不开(按聚簇标准误)"
    else:
        o["★状态"] = "赚" if mu > 0 else "亏"
    if np.isfinite(se_p) and np.isfinite(se_c) and se_p > 0:
        o["★聚簇SE是普通SE的几倍"] = round(se_c / se_p, 2)
    return o


def main() -> int:
    above, seg = 大盘()
    aidx = above.index
    amap, smap = above.to_dict(), seg.to_dict()
    pos = {d: i for i, d in enumerate(aidx)}
    arr = above.to_numpy()

    rows = []
    for f in sorted(glob.glob(os.path.join(LED, "REAL__*.csv"))):
        链 = os.path.basename(f)[len("REAL__"):-len(".csv")]
        m = re.search(r"(技-\d+)", 链)
        d = pd.read_csv(f)
        if not {"entry_date", "exit_date", "r_multiple_net"} <= set(d.columns):
            continue
        d["entry_date"] = pd.to_datetime(d["entry_date"])
        d["exit_date"] = pd.to_datetime(d["exit_date"])
        for _, t in d.iterrows():
            i0, i1 = pos.get(t.entry_date), pos.get(t.exit_date)
            if i0 is None or i1 is None or i1 < i0:
                continue
            w = arr[i0:i1 + 1]
            w = w[pd.notna(w)]
            if len(w) == 0:
                continue
            frac_up = float(np.mean(w.astype(bool)))      # ★ 持有期在线上的天数占比
            ent_up = amap.get(t.entry_date)
            rows.append({
                "链": 链, "方法": m.group(1) if m else "其他",
                "r": float(t.r_multiple_net), "簇": smap.get(t.entry_date),
                "进场时在线上": (None if pd.isna(ent_up) else bool(ent_up)),
                "持有期在线上占比": frac_up,
                # ★★★ V 型验证:下方进场、持有期内重新站上 200 日线
                "站回去了": (bool(frac_up > 0) if ent_up is False else None),
            })
    D = pd.DataFrame(rows).dropna(subset=["r", "簇"])

    out = {"口径": {
        "基线": "probe/friction_rerun_1104",
        "★改了什么": [
            "①标签:原按进场日贴整笔 → 改为**按持有天数分摊**(权重=持有期落在该档的天数占比)。"
            "★★★ 近似:流水只有进/出两天,没有逐日盈亏,所以这不是真的按天记账。",
            "②标准误:普通标准误作废,改用**按连续区间聚簇**(同一段线上/线下算一个簇)。",
            "③新增 V 型反转验证。",
        ],
        "不给结论的门槛": f"笔数<{MIN_N} 或 簇数<5",
    }, "按方法": {}, "V型验证": {}}

    for 方法, g in D.groupby("方法"):
        up = g[g["进场时在线上"] == True]                      # noqa: E712
        dn = g[g["进场时在线上"] == False]                     # noqa: E712
        out["按方法"][方法] = {
            "①旧切法_按进场日": {
                "线上": 格(up.r.to_numpy(), up.簇.to_numpy()),
                "线下": 格(dn.r.to_numpy(), dn.簇.to_numpy()),
            },
            "②新切法_按持有天数分摊": {
                "线上": 格(g.r.to_numpy(), g.簇.to_numpy(),
                          w=g["持有期在线上占比"].to_numpy()),
                "线下": 格(g.r.to_numpy(), g.簇.to_numpy(),
                          w=(1 - g["持有期在线上占比"]).to_numpy()),
            },
        }
        a = dn[dn["站回去了"] == True]                         # noqa: E712
        b = dn[dn["站回去了"] == False]                        # noqa: E712
        out["V型验证"][方法] = {
            "线下进场_持有期站回200日线": 格(a.r.to_numpy(), a.簇.to_numpy()),
            "线下进场_一直没站回去": 格(b.r.to_numpy(), b.簇.to_numpy()),
        }

    p = os.path.join(OUT, "重切_按天拆账_1105.json")
    io.open(p, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1))
    print(f"★ 写到 {p} · {len(D)} 笔 · {D.方法.nunique()} 个方法")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
