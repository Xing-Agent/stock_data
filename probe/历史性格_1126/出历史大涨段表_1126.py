# -*- coding: utf-8 -*-
"""每只票的「历史性格」：过去几轮大涨大跌的节奏（Lin 11-26 定：分析一只票先扫它的长历史）。
只读日线（复权价），不碰引擎。给技术面大师卡当参考表。

定义（写进卡里，回答时现算也照这个）：
- 用**周线收盘**（每周最后一个交易日的复权收盘）做「大波段」：从一个低点涨了 X% 以上才算一轮大涨开始成立，
  从高点回落 X% 以上才算这一轮见顶。X：普通 ETF 20%；三倍杠杆 ETF、个股 40%。
- 每一轮大涨记四样：① 起涨前：上一轮高点到这次低点跌了多少、用了多久（下跌 + 磨底一共多久）；
  ② 涨了多少、用了多久；③ 见顶后：跌到下一个低点跌了多少、用了多久；④ 年份。
- 最后一段还没走完的，单独写「现在走到哪了」。
"""
import os, io, sys, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
D = os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线")
名 = {"SPY": "标普 500", "QQQ": "纳指 100", "IWM": "罗素 2000 小盘", "DIA": "道指", "XLK": "科技", "SMH": "半导体", "XLF": "金融", "KRE": "地区银行",
      "XLE": "能源", "XLV": "医疗", "XLI": "工业", "XLY": "可选消费", "XLP": "必需消费", "XLU": "公用事业", "XLB": "材料", "XLRE": "房地产", "XLC": "通信",
      "TQQQ": "三倍做多纳指", "SOXL": "三倍做多半导体"}
杠杆 = {"TQQQ", "SOXL"}


def 周线(sym):
    d = pd.read_csv(os.path.join(D, sym + "_日线.csv"), parse_dates=["date"]).set_index("date").sort_index()
    c = d.close_adj.astype(float)
    if sym == "XLF":   # 2016-09-19 分出 XLRE，数据前后没接上（假跌 6.9%），按「那天平盘」接上（同《减仓》脚本的处理）
        t = pd.Timestamp("2016-09-19"); i = c.index.get_loc(t); c.loc[c.index < t] *= c.iloc[i] / c.iloc[i - 1]
    jump = (c / c.shift(1) - 1).abs()
    assert not (jump > (0.6 if sym in 杠杆 else 0.3)).any(), f"{sym} 有单日大跳，先核数据"
    return c.resample("W-FRI").last().dropna()


def 大波段(w, X):
    """周线 zigzag：返回拐点列表 [(日期, 价, '低'/'高'), ...]，最后一个是还没确认的当前极值。"""
    pts = []; 方向 = None; ext_i = 0
    v = w.values; idx = w.index
    lo_i = hi_i = 0
    for i in range(1, len(v)):
        if 方向 is None:
            if v[i] > v[lo_i] * (1 + X): pts.append((idx[lo_i], v[lo_i], "低")); 方向 = "上"; ext_i = i
            elif v[i] < v[hi_i] * (1 - X): pts.append((idx[hi_i], v[hi_i], "高")); 方向 = "下"; ext_i = i
            else:
                if v[i] < v[lo_i]: lo_i = i
                if v[i] > v[hi_i]: hi_i = i
            continue
        if 方向 == "上":
            if v[i] > v[ext_i]: ext_i = i
            elif v[i] < v[ext_i] * (1 - X): pts.append((idx[ext_i], v[ext_i], "高")); 方向 = "下"; ext_i = i
        else:
            if v[i] < v[ext_i]: ext_i = i
            elif v[i] > v[ext_i] * (1 + X): pts.append((idx[ext_i], v[ext_i], "低")); 方向 = "上"; ext_i = i
    pts.append((idx[ext_i], v[ext_i], "高?" if 方向 == "上" else "低?"))
    return pts, (idx[-1], v[-1])


def 周数(a, b): return int(round((b - a).days / 7))


def 一只(sym):
    w = 周线(sym); X = 0.40 if sym in 杠杆 else 0.20
    pts, (今天, 现价) = 大波段(w, X)
    轮 = []
    for k, (t, p, kind) in enumerate(pts):
        if kind != "低" or k + 1 >= len(pts) or pts[k + 1][2] != "高": continue
        t2, p2, _ = pts[k + 1]
        前 = pts[k - 1] if k >= 1 and pts[k - 1][2] == "高" else None
        后 = pts[k + 2] if k + 2 < len(pts) else None
        轮.append(dict(起=t, 起价=p, 顶=t2, 顶价=p2, 涨=p2 / p - 1, 涨周=周数(t, t2),
                      前跌=(p / 前[1] - 1) if 前 else None, 前周=周数(前[0], t) if 前 else None,
                      后跌=(后[1] / p2 - 1) if 后 else None, 后周=周数(t2, 后[0]) if 后 else None, 后确认=bool(后 and 后[2] == "低")))
    # 现在走到哪了
    lt, lp, lk = pts[-1]; pt, pp, pk = pts[-2] if len(pts) >= 2 else (None, None, None)
    if lk == "高?":   # 还在涨的一段里
        现在 = f"从 {pt:%Y-%m} 低点涨了 {100*(现价/pp-1):+.0f}%、{周数(pt, 今天)} 周；离这段最高 {100*(现价/lp-1):+.0f}%"
    else:
        现在 = f"从 {pt:%Y-%m} 高点跌了 {100*(现价/pp-1):+.0f}%、{周数(pt, 今天)} 周"
    return X, 轮, 现在, 今天


def pct(x): return "—" if x is None else f"{100*x:+.0f}%"



_末d = pd.read_csv(os.path.join(D, "SPY_日线.csv")).date.max()
L = ["# 每只票的历史性格：过去几轮大涨大跌的节奏（19 只 ETF）", "",
     "> 给技术面大师卡「先扫这只票的历史性格」那一步用（Lin 11-26 定）。2026-11-26 算的，数据到 " + _末d + "；脚本 `probe/历史性格_1126/出历史大涨段表_1126.py`。",
     "> **怎么算**：用周线收盘（复权）。从低点涨 X% 以上算一轮大涨成立，从高点回落 X% 以上算见顶。X：普通 ETF 20%，三倍杠杆 ETF 40%（个股现算时也用 40%）。",
     "> **每一轮写四样**：起涨前（上一轮高点跌到这次低点，跌了多少、多少周）→ 涨了多少、多少周 → 见顶后跌了多少、多少周。最后一段没走完的写在「到数据最后一天走到哪」。",
     "> 🔴 这是历史上发生过的节奏，**不代表这一次**；只用来说清「这只票通常怎么走、这一波像不像」，不改扳机、止损、目标位。轮数少（多数只有 2~5 轮），中位数只是个大概。",
     "> 🔴 只有活到现在的 ETF；用的是复权价，和用户截图上的不复权价位对不上，讲涨跌幅和时间，不讲价位。", "",
     "## 汇总（每只一行）", "",
     "| 代码 | 是什么 | 从哪年算起 | 门槛 | 大涨几轮 | 每轮涨幅（中位 / 最大） | 每轮用时（中位） | 见顶后回撤（中位 / 最深） | 起涨前跌 + 磨底用时（中位） | 到 " + _末d + " 走到哪 |",
     "|---|---|---|---:|---:|---|---:|---|---:|---|"]
明细 = ["", "## 每一轮明细", ""]
for s, cn in 名.items():
    X, 轮, 现在, 今天 = 一只(s)
    if not 轮: continue
    涨 = np.array([r["涨"] for r in 轮]); 周 = np.array([r["涨周"] for r in 轮])
    后 = np.array([r["后跌"] for r in 轮 if r["后跌"] is not None and r["后确认"]]); 前周 = [r["前周"] for r in 轮 if r["前周"] is not None]
    start = 周线(s).index[0].year
    L.append(f"| {s} | {cn} | {start} | {100*X:.0f}% | {len(轮)} | {100*np.median(涨):+.0f}% / {100*涨.max():+.0f}% | {np.median(周):.0f} 周 | "
             f"{(f'{100*np.median(后):.0f}% / {100*后.min():.0f}%') if len(后) else '—'} | {(f'{np.median(前周):.0f} 周') if 前周 else '—'} | {现在} |")
    明细.append(f"**{s}（{cn}）**")
    for r in 轮:
        前 = f"之前跌 {pct(r['前跌'])}、{r['前周']} 周 → " if r["前跌"] is not None else ""
        后s = (f" → 见顶后跌 {pct(r['后跌'])}、{r['后周']} 周" + ("" if r["后确认"] else "（还没走完）")) if r["后跌"] is not None else ""
        明细.append(f"- {前}{r['起']:%Y-%m} 起涨，涨 {pct(r['涨'])}、{r['涨周']} 周，{r['顶']:%Y-%m} 见顶{后s}")
    明细.append("")
L += 明细
L += ["## 用法",
      "- 用户问的票在表里 → 讲那一行：大涨过几轮、一般涨多少用多久、见顶后一般回撤多深，再说现在这一波走了多少、多久，像历史上哪一段。",
      "- 不在表里（个股、A 股、币）→ 有日线就照上面「怎么算」现算（个股门槛 40%）；只有截图就照图说，写明「这是看图估的」，请用户补一张月线或周线全历史图。🔴 不许编轮数和回撤。",
      "- 讲完必须接一句：「这是过去的节奏，不代表这一次；最后还是看这一次盘面。」", ""]
out = os.path.join(ROOT, "skills_v2/xing-ta-master/references/history_big_moves.md")
io.open(out, "w", encoding="utf-8").write("\n".join(L)); print(len(L), "行 →", out)
