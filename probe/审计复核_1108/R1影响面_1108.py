# -*- coding: utf-8 -*-
"""★★★ R1 影响面 —— 分红没做拆股折算，到底把成绩虚增了多少。

★★ 为什么不用跑回测就能量出来（这是本脚本唯一的推导，★ 请逐行核）：
  · 面板的 close 是**折算过的**：除息日在拆股之前的那些天，close_adj = close_raw × ratio_cum
    （ratio_cum = 该日之后所有拆股事件的 ratio 连乘，ratio = 1/split_coefficient）。
  · 现在用的分红是**没折算的** raw_div。
  · 全收益口径里分红那一块贡献 = div / close。
      ★ 正确的    = raw_div × ratio_cum / close_adj = raw_div / close_raw
      ★★ 现在在用的 = raw_div            / close_adj = raw_div /(close_raw × ratio_cum)
    → ★★★ **现在在用的 = 正确的 ÷ ratio_cum = 正确的 × coef_cum**。
  · 所以虚增倍数就是「该次分红之后的累计拆股系数」，★ 一个纯数据量，不用回测。

★ 只读源头 daily.json，★★ 不碰面板、不跑回测、不改任何生产文件。
"""
from __future__ import annotations
import csv, glob, gzip, json, os, sys
from collections import defaultdict

ROOT = os.path.abspath(".")
sys.path.insert(0, ROOT)

_股票目录 = ("exam_1042", "exam_pre2016_1107", "pilot_300", "pilot_50")
_基准目录 = ("market_macro_1105", "market_extra_1107", "market_ext_1105",
            "market_etf_1107", "market_etf_1106")
_COEF_EPS = 1e-9


def 扫(dirs):
    出 = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            p = os.path.join(d, sub)
            if not os.path.isdir(p):
                continue
            fs = [f for f in sorted(glob.glob(os.path.join(p, "*")))
                  if "daily" in os.path.basename(f).lower()]
            if fs:
                出.setdefault(sub, []).extend(fs)
    return 出


def 读行(f):
    op = gzip.open if f.endswith(".gz") else open
    try:
        o = json.load(op(f, "rt", encoding="utf-8"))
    except Exception:
        return []
    return o if isinstance(o, list) else (o.get("data") or o.get("results") or [])


def 一只(files):
    """★ 返回 {日期: (close_raw, div_raw, coef)}，多段按日期合并（后读到的为准）。"""
    m = {}
    for f in files:
        for r in 读行(f):
            d = str(r.get("date", ""))[:10]
            if len(d) != 10:
                continue
            try:
                c = float(r.get("close") or 0) or None
            except (TypeError, ValueError):
                c = None
            try:
                v = float(r.get("dividend_amount") or 0)
            except (TypeError, ValueError):
                v = 0.0
            try:
                k = float(r.get("split_coefficient") or 1.0)
            except (TypeError, ValueError):
                k = 1.0
            if k != k or k <= _COEF_EPS:
                k = 1.0
            m[d] = (c, v, k)
    return m


窗口 = {"A_2004到2014": ("2004-01-02", "2014-12-31"),
        "B_2015到2025": ("2015-01-01", "2025-12-31")}

股票表, 基准表 = 扫(_股票目录), 扫(_基准目录)
路径表 = dict(股票表); 路径表.update(基准表)        # ★ 和覆盖层同一套（Y4 那个 update 也一样）

池票 = sorted({x["symbol"] for x in csv.DictReader(
    open("probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"))})
重仓十只 = ["XOM", "AMZN", "WMT", "TSLA", "AAPL", "MRK", "GOOG", "T", "NFLX", "UNH"]
基准 = ["SPY", "QQQ", "IWM", "IWD", "IWF"]

结果 = {w: {} for w in 窗口}
明细 = {w: [] for w in 窗口}
无文件 = [t for t in 池票 if t not in 路径表]

for t in 池票 + [b for b in 基准 if b not in 池票]:
    files = 路径表.get(t)
    if not files:
        continue
    m = 一只(files)
    if not m:
        continue
    日 = sorted(m)
    # ★ ratio_cum(该日) = 该日**之后**（严格大于）所有 coef!=1 的 ratio 连乘
    拆 = [(d, 1.0 / m[d][2]) for d in 日 if abs(m[d][2] - 1.0) > _COEF_EPS]
    for w, (s, e) in 窗口.items():
        真, 虚, 笔, 最大倍 = 0.0, 0.0, 0, 1.0
        for d in 日:
            if not (s <= d <= e):
                continue
            c, v, _ = m[d]
            if not c or c <= 0 or v <= 0:
                continue
            rc = 1.0
            for dd, rr in 拆:
                if dd > d:
                    rc *= rr
            真 += v / c
            虚 += v / (c * rc)
            笔 += 1
            最大倍 = max(最大倍, 1.0 / rc)
        if 笔:
            结果[w][t] = {"笔": 笔, "真实分红收益率合计": 真,
                          "现在在用的（虚增）": 虚, "虚增": 虚 - 真,
                          "最大单笔虚增倍数": 最大倍}
            if 虚 - 真 > 1e-9:
                明细[w].append((t, 虚 - 真, 最大倍, 笔))

年数 = {"A_2004到2014": 11.0, "B_2015到2025": 11.0}
汇总 = {}
for w in 窗口:
    d = 结果[w]
    受影响 = [t for t in d if d[t]["虚增"] > 1e-9]
    池内 = [t for t in d if t in set(池票)]
    池内受影响 = [t for t in 池内 if d[t]["虚增"] > 1e-9]
    汇总[w] = {
        "有分红记录的票": len(池内),
        "★被这个错打到的票": f"{len(池内受影响)}/{len(池内)} = {len(池内受影响)/max(1,len(池内))*100:.1f}%",
        "★★等权买入持有：真实分红贡献/年": f"{sum(d[t]['真实分红收益率合计'] for t in 池内)/max(1,len(池内))/年数[w]*100:.3f} pp",
        "★★等权买入持有：现在在用的/年": f"{sum(d[t]['现在在用的（虚增）'] for t in 池内)/max(1,len(池内))/年数[w]*100:.3f} pp",
        "★★★等权虚增/年": f"{sum(d[t]['虚增'] for t in 池内)/max(1,len(池内))/年数[w]*100:.3f} pp",
        "★★★虚增最大的十只": [
            {"票": t, "虚增合计": f"{x*100:.2f}pp", "最大单笔虚增倍数": f"{r:.1f}×", "笔": n}
            for t, x, r, n in sorted(明细[w], key=lambda z: -z[1])[:10]],
        "★★重仓十只（B段大波段）": {
            t: ({"真实/年": f"{d[t]['真实分红收益率合计']/年数[w]*100:.3f}pp",
                 "在用/年": f"{d[t]['现在在用的（虚增）']/年数[w]*100:.3f}pp",
                 "★虚增/年": f"{d[t]['虚增']/年数[w]*100:.3f}pp",
                 "最大单笔倍数": f"{d[t]['最大单笔虚增倍数']:.1f}×"}
                if t in d else "★ 窗口内无分红记录")
            for t in 重仓十只},
        "★★★基准侧（两侧同口径要看这个）": {
            b: ({"真实/年": f"{d[b]['真实分红收益率合计']/年数[w]*100:.3f}pp",
                 "在用/年": f"{d[b]['现在在用的（虚增）']/年数[w]*100:.3f}pp",
                 "★虚增/年": f"{d[b]['虚增']/年数[w]*100:.3f}pp"}
                if b in d else "★ 窗口内无分红记录")
            for b in 基准},
    }

报告 = {"★这是什么": "R1（分红没做拆股折算）的影响面，纯数据算，没跑回测",
        "★池子": f"并池2004 {len(池票)} 只；★ 扫不到日线文件的 {len(无文件)} 只",
        "★★★推导": "现在在用的分红贡献 = 正确的 × 该次分红之后的累计拆股系数",
        "汇总": 汇总}
json.dump(报告, open("probe/审计复核_1108/R1影响面_1108.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print(json.dumps(报告, ensure_ascii=False, indent=2))
