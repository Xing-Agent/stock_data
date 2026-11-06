# -*- coding: utf-8 -*-
"""
★★★ 补两条必备缺口：**技 5.1 突破后的跟进表现** + **技 5.2 回踩时的量价健康度**。
★ engine 零改动 —— 只读流水 + 价格面板。

★★ 为什么这两条原来是 ❌（《78》的原话）：
  · 技 5.1：「★ 引擎只记进场日和离场日，**没有「进场后第 N 天跟进得怎么样」这一类诊断**」
  · 技 5.2：「★★ 零件齐、但**全在进场侧**（pullback_to_ma · volume_dryup · RVOL）。
      持仓期间只有抬止损和离场判定，**没有「这次回踩健不健康」这个输出**」
★★★ 所以缺的不是指标，是**一个面向持仓期的输出**。这一份就是那个输出。

★★ 口径纪律：
  · 算不出就是 NaN，★★★ 单独报数，**不猜不补**
  · ★ 只给数和样本量，**不给形容词**（★★ 这是 Lin 定的「股票说明书」口径）
  · ★★★ 少于 10 次的，明写「**说明不了倾向**」
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = "probe/持仓期诊断_1106"
最少样本 = 10
_P = None


def 面板():
    global _P
    if _P is None:
        _P = pd.read_parquet(PANEL)
    return _P


# ════════════════════════════════════════════════════════════════════
# ★★★ 技 5.1 · 突破后几天的跟进表现
# ════════════════════════════════════════════════════════════════════
def 跟进(d: pd.DataFrame, cl: pd.DataFrame, hi: pd.DataFrame) -> dict:
    """★ 问的是:「买进来之后,它**跟上了没有**?」
       ★★ 三个数(每个都是**可数的事实**,不是形容词):
         ① **第 3 天还在进场价上方**的比例 —— ★ 突破有没有「立刻被打回去」
         ② **进场后 10 天内创出新高**的比例 —— ★★ 有没有真的往上走
         ③ **进场后第 1 天就跌破进场价**的比例 —— ★★★ 这叫「当日就失败」
       ★ 出处档:②档 行业通行(欧奈尔/米奈尔维尼都看「突破后的跟进」),
         ★★★ 但「第 3 天 / 10 天」这两个数是**惯例,不是原著** → 跑相邻三点。"""
    out = {}
    for n3 in (2, 3, 5):                      # ★ 相邻三点
        守住, 可算 = 0, 0
        for s, t, px in zip(d["symbol"], d["entry_date"], d["entry_price"]):
            c = cl.get(s)
            if c is None:
                continue
            i = c.index.searchsorted(pd.Timestamp(t))
            if i + n3 >= len(c):
                continue
            v = c.iloc[i + n3]
            if not np.isfinite(v):
                continue
            可算 += 1
            if v > px:
                守住 += 1
        out[f"①第{n3}天还在进场价上方"] = {
            "可算笔数": 可算,
            "比例": (round(守住 / 可算 * 100, 1) if 可算 else None),
            "★说明不了倾向": 可算 < 最少样本,
        }
    for n10 in (5, 10, 20):                   # ★ 相邻三点
        创高, 可算 = 0, 0
        for s, t, px in zip(d["symbol"], d["entry_date"], d["entry_price"]):
            h = hi.get(s)
            if h is None:
                continue
            i = h.index.searchsorted(pd.Timestamp(t))
            seg = h.iloc[i + 1:i + 1 + n10].dropna()
            if seg.empty:
                continue
            可算 += 1
            # ★ 「创出新高」= 超过**进场当天的最高价**(★★ 不是超过进场价 —— 那太松)
            基 = h.iloc[i]
            if np.isfinite(基) and (seg.max() > 基):
                创高 += 1
        out[f"②进场后{n10}天内创出新高"] = {
            "可算笔数": 可算,
            "比例": (round(创高 / 可算 * 100, 1) if 可算 else None),
            "★说明不了倾向": 可算 < 最少样本,
            "★口径": "超过**进场当天的最高价**（★ 不是超过进场价）",
        }
    破, 可算 = 0, 0
    for s, t, px in zip(d["symbol"], d["entry_date"], d["entry_price"]):
        c = cl.get(s)
        if c is None:
            continue
        i = c.index.searchsorted(pd.Timestamp(t))
        if i + 1 >= len(c):
            continue
        v = c.iloc[i + 1]
        if not np.isfinite(v):
            continue
        可算 += 1
        if v < px:
            破 += 1
    out["③进场后第1天就跌破进场价"] = {
        "可算笔数": 可算,
        "比例": (round(破 / 可算 * 100, 1) if 可算 else None),
        "★说明不了倾向": 可算 < 最少样本,
        "★★这是什么": "★★★ 「当日就失败」—— ★ 比例高说明进场点太晚/太冲",
    }
    return out


# ════════════════════════════════════════════════════════════════════
# ★★★ 技 5.2 · 回踩时的量价健康度（★ 持仓期诊断）
# ════════════════════════════════════════════════════════════════════
def 回踩(d: pd.DataFrame, cl: pd.DataFrame, lo: pd.DataFrame,
         vo: pd.DataFrame) -> dict:
    """★ 问的是:「持仓期间它回踩的时候,**是健康的回踩还是要崩**?」
       ★★ 原著的「健康」判法只有一条可算:**回踩要缩量**
         (★★★ 威科夫/欧奈尔都这么说:放量下跌 = 有人在出货)。
       ★ 所以这一份只量两件可数的事实:
         ① 持仓期间的**回踩次数**（跌到 20 日均线附近）
         ② ★★★ 这些回踩里,**缩量的占多少**（当日量 < 50 日均量）
       ★★ 出处档:②档 行业通行;★★★ 「20 日均线」「50 日均量」是**惯例**,不是原著数 →
         跑相邻三点。"""
    out = {}
    for ma_n in (10, 20, 50):                 # ★ 相邻三点
        回踩次, 缩量次, 可算笔 = 0, 0, 0
        for s, a, b in zip(d["symbol"], d["entry_date"], d["exit_date"]):
            c, l_, v_ = cl.get(s), lo.get(s), vo.get(s)
            if c is None or l_ is None or v_ is None:
                continue
            ma = c.rolling(ma_n, min_periods=ma_n).mean()
            vma = v_.rolling(50, min_periods=50).mean()
            b2 = b if pd.notna(b) else c.index[-1]
            m = (c.index > pd.Timestamp(a)) & (c.index <= pd.Timestamp(b2))
            seg_l, seg_ma = l_[m], ma[m]
            seg_v, seg_vma = v_[m], vma[m]
            ok = seg_l.notna() & seg_ma.notna()
            if not ok.any():
                continue
            可算笔 += 1
            # ★ 「回踩」= 当日最低价摸到均线 1% 以内或以下
            touch = ok & (seg_l <= seg_ma * 1.01)
            回踩次 += int(touch.sum())
            vv = touch & seg_v.notna() & seg_vma.notna()
            缩量次 += int((vv & (seg_v < seg_vma)).sum())
        out[f"均线{ma_n}日"] = {
            "可算笔数": 可算笔,
            "回踩总次数": 回踩次,
            "其中缩量次数": 缩量次,
            "缩量占比": (round(缩量次 / 回踩次 * 100, 1) if 回踩次 else None),
            "★说明不了倾向": 回踩次 < 最少样本,
            "★口径": "回踩 = 当日最低价 ≤ 均线 × 1.01；缩量 = 当日量 < 50 日均量",
        }
    return out


def 一条(f: str, P) -> dict | None:
    d = pd.read_csv(f)
    need = {"symbol", "entry_date", "exit_date", "entry_price"}
    if d.empty or not need <= set(d.columns):
        return None
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    d["entry_price"] = pd.to_numeric(d["entry_price"], errors="coerce")
    d = d.dropna(subset=["symbol", "entry_date", "entry_price"])
    if d.empty:
        return None
    syms = sorted(set(d["symbol"].astype(str)))
    有 = [s for s in syms if ("close", s) in P.columns]
    缺 = len(syms) - len(有)
    if not 有:
        return {"★跑失败": "面板里没有这条臂的任何票"}
    cl = {s: P[("close", s)].dropna() for s in 有}
    hi = {s: P[("high", s)].dropna() for s in 有}
    lo = {s: P[("low", s)].dropna() for s in 有}
    vo = {s: P[("volume", s)].dropna() for s in 有}
    return {"①总笔数": int(len(d)),
            "★面板里缺的票数": 缺,
            "技5.1_突破后跟进": 跟进(d, cl, hi),
            "技5.2_回踩健康度": 回踩(d, cl, lo, vo)}


def main() -> int:
    报 = {"★这两条补的是什么": {
        "技5.1": "★ 突破后几天的跟进表现 —— ★★ 引擎原来只记进场日和离场日，"
               "**没有「进场后第 N 天跟进得怎么样」这一类诊断**",
        "技5.2": "★ 回踩时的量价健康度 —— ★★ 零件齐但**全在进场侧**，"
               "**持仓期间没有「这次回踩健不健康」这个输出**",
        "★★★口径": "只给数和样本量，**不给形容词**；"
                 "★ 少于 10 次的明写「说明不了倾向」；★★ 算不出单独报数，不猜不补",
        "engine改动": "零",
    }}
    P = 面板()
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            r = 一条(f, P)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
        if r:
            报[名] = r
            if "★跑失败" in r:
                失败 += 1
                print("⚠ 失败", 名, r["★跑失败"][:120], flush=True)
            else:
                print("✓", 名, flush=True)
    # ★★★ 规矩⑯:失败要大声报
    报["★★★失败条数"] = 失败
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "持仓期诊断_报告_1106.json"), "w",
              encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
