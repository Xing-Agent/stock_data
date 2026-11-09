"""
B 类（实战判断）· 我方答卷 + 和 Gemini Pro 对账 + 开答案卷（后视镜）—— 1109

大白话：给 8 段真实行情（带代码和日期），我们这边**只用引擎能算的东西**回答六问，
再和 Gemini Pro 的回答逐格比，最后翻开「后来真实发生了什么」看两边谁的价位先被碰到、
以及 Gemini 有没有可能「认出了这只票、知道后来怎么走」。

★ 口径（工程/方法论层面，Claude 定，写死在这里，跑之前定好、跑之后不改）：
  ① 趋势  = engine.stages.compute_stages（生产口径，参数不许动）在窗口最后一天的状态。
           它要 150 日均线 → 用的是窗口**之前**的历史（Gemini 只看到 120 根，这一点我们多知道）。
  ② 支撑  = 窗口内、低于最后收盘价的「摆动低点」，取最近的两个（由近到远、由高到低）。
  ③ 压力  = 窗口内、高于最后收盘价的「摆动高点」，取最近的两个。
           摆动点 = 前后各 5 根里的最高 / 最低（分型 n=5，同 engine.matrices 的 VCP 分型写法）；
           ★ 最后 5 根还没有右边的确认，不算摆动点（不偷看）。
           ★ 上方没有任何摆动高点（价格在窗口最高处）→ 「给不出」：大师卡第六节第三条，
             上方没有历史成交堆积，阻力在物理上不存在。
  ④ 止损位（失效位）= 支撑①，★ **按收盘跌破算数**（大师卡 C 类必须说清收盘还是盘中）；
           另给吊灯止损原始值（近 22 根最高 − 3×ATR20，engine.matrices.chandelier_raw_matrix 同式）作参考。
  ⑤ 目标位 = 压力①；给名义空间 %。净空间要扣买卖价差 —— ★ 我们没有价差数据 → 写「我们没有这个数」。
           注脚（6.19）：「这是先收一半的位置，不是我们预测它会到这儿。」
  ⑥ 后面怎么走 = 大师卡 E 类：列互斥的几种，每种带验证条件，★ **不选一个**（卡上明文不许选）。

  对账口径：价位两边相差 ≤ 1%（或落在 Gemini 给的区间里）→ 一致；否则不一致。
           一方给不出、另一方给了 → 我们少了 / 我们多了。
           趋势只比「方向大类」：上（上涨 / 上涨中的回调）· 下（下跌 / 下跌中的反弹）· 震荡。

跑法：python3 probe/大师测试_1105/B类我方答卷_1109.py  → 写 手册/127-B类-我方答卷与对账-1109.md
"""
from __future__ import annotations

import gzip
import json
import os
import re
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from engine.stages import compute_stages, STAGE_PLAIN  # noqa: E402

SRC = os.path.join(REPO, "probe/大师测试_1105/去盲素材_1108")
OUT = os.path.join(REPO, "手册/127-B类-我方答卷与对账-1109.md")
N_PIV = 5
TOL = 0.01

# ---- Gemini Pro 的回答（照《123》原文摘数；B2/B4 用重问版，第一次断了）----
# 价位：单值 或 (低,高) 区间；None = 它说给不出
G = {
 1: dict(trend="长线多头，短期高位箱体震荡", fam="上", sup=[(309.84, 310.00)], res=[(325.35, 326.20)], stop=308.50, tgt=325.00, path="310~326 区间震荡（其次回补缺口到 301）"),
 2: dict(trend="上升趋势里的高位横盘", fam="上", sup=[(31.95, 32.18)], res=[(34.12, 34.34)], stop=31.85, tgt=40.18, path="突破延续（选了这一个）"),
 3: dict(trend="宽幅震荡（次级折返）", fam="震荡", sup=[93.94, 91.40], res=[(98.61, 99.06)], stop=91.30, tgt=98.50, path="先窄幅震荡再测区间上沿（选了这一个）"),
 4: dict(trend="中期见底反弹后，短线偏弱震荡", fam="震荡", sup=[13.55, (13.20, 13.30)], res=[(14.40, 14.52), 15.00], stop=13.49, tgt=14.45, path="震荡上行再测 14.40~14.50（选了这一个）"),
 5: dict(trend="明确下降趋势", fam="下", sup=[8.20], res=[10.29, 9.30], stop=8.15, tgt=10.29, path="弱反弹后继续跌（选了这一个）"),
 6: dict(trend="明确强烈下降趋势", fam="下", sup=None, res=[(47.0, 47.4), (49.4, 50.0)], stop=43.7, tgt=47.0, path="跌势延续（选了这一个）"),
 7: dict(trend="极强多头，刚完成结构性突破", fam="上", sup=[211.24, 209.31], res=None, stop=208.90, tgt=234.00, path="高位震荡消化后延续向上（选了这一个）"),
 8: dict(trend="极强多头突破", fam="上", sup=[158.18, 152.40], res=None, stop=151.90, tgt=189.81, path="1~3 天高位缩量横盘后继续上攻（选了这一个）"),
}
FAM = {"STAGE_2": "上", "BULL_PULLBACK": "上", "STAGE_4": "下", "BEAR_RALLY": "下", "CHOP": "震荡"}


def load(n):
    t = open(os.path.join(SRC, f"行情-{n}.txt"), encoding="utf-8").read()
    sym, a, b = re.search(r"股票代码: (\S+)\s+区间: (\S+) ~ (\S+)", t).groups()
    rows = [list(map(float, l.split(","))) for l in t.splitlines() if re.match(r"^\d+,", l)]
    w = pd.DataFrame(rows, columns=["i", "open", "high", "low", "close", "volume"])
    raw = pd.DataFrame(json.load(gzip.open(os.path.join(REPO, f"market_ext_1105/{sym}/daily.json.gz")))["data"])
    raw["date"] = pd.to_datetime(raw["date"])
    raw = raw.set_index("date").sort_index()
    raw = raw[~raw.index.duplicated(keep="last")]
    # 素材是拆股调整后的价（EXPR 后来 1:20 并股）→ 用窗口末日的比值把原始数据对齐到素材口径
    k = w["close"].iloc[-1] / raw.loc[b, "close"]
    k0 = w["close"].iloc[0] / raw.loc[a, "close"]
    assert abs(k / k0 - 1) < 1e-3, (sym, k, k0)
    for c in ("open", "high", "low", "close"):
        raw[c] = raw[c] * k
    return sym, a, b, w, raw, k


def pivots(w):
    h, l = w["high"].to_numpy(), w["low"].to_numpy()
    T = len(w)
    ph, pl = [], []
    for t in range(N_PIV, T - N_PIV):
        if h[t] == h[t - N_PIV:t + N_PIV + 1].max():
            ph.append((t + 1, h[t]))
        if l[t] == l[t - N_PIV:t + N_PIV + 1].min():
            pl.append((t + 1, l[t]))
    return ph, pl


def levels(w):
    c = w["close"].iloc[-1]
    ph, pl = pivots(w)
    sup, res = [], []
    floor = c
    for i, v in sorted(pl, key=lambda x: -x[0]):          # 由近到远
        if v < floor:
            sup.append((i, v)); floor = v
        if len(sup) == 2:
            break
    ceil = c
    for i, v in sorted(ph, key=lambda x: -x[0]):
        if v > ceil:
            res.append((i, v)); ceil = v
        if len(res) == 2:
            break
    return sup, res


def chandelier(raw, end, look=22, mult=3.0, atr_n=20):
    x = raw.loc[:end]
    pc = x["close"].shift(1)
    tr = np.fmax(np.fmax(x["high"] - x["low"], (x["high"] - pc).abs()), (x["low"] - pc).abs())
    atr = tr.ewm(alpha=1 / atr_n, adjust=False, min_periods=atr_n).mean()
    return float(x["high"].rolling(look, min_periods=1).max().iloc[-1] - mult * atr.iloc[-1]), float(atr.iloc[-1])


def near(ours, theirs):
    """ours: float；theirs: float 或 (lo,hi)。"""
    if isinstance(theirs, tuple):
        lo, hi = theirs
        return lo * (1 - TOL) <= ours <= hi * (1 + TOL)
    return abs(ours / theirs - 1) <= TOL


def fmt(v):
    if v is None:
        return "给不出"
    if isinstance(v, tuple):
        return f"{v[0]:g}~{v[1]:g}"
    return f"{v:g}"


def cmp_levels(ours, theirs):
    if not ours and not theirs:
        return "一致", "两边都给不出"
    if not ours:
        return "我们少了", "Gemini 给了，我们按规矩给不出"
    if not theirs:
        return "我们多了", "我们给了，Gemini 说给不出"
    first = ours[0][1]
    if any(near(first, t) for t in theirs):
        return "一致", f"我方第一档 {first:.2f} 落在 Gemini 给的价位里（±1%）"
    return "不一致", f"我方第一档 {first:.2f}，Gemini 最近一档 {fmt(theirs[0])}"


def first_hit(fwd, stop, tgt, stop_on_close):
    """先碰到止损还是目标位。止损：按收盘（我方规则）或盘中；目标：盘中触及。"""
    for d, r in fwd.iterrows():
        s_hit = (r["close"] < stop) if stop_on_close else (r["low"] <= stop)
        t_hit = tgt is not None and r["high"] >= tgt
        if s_hit and t_hit:
            return "同一天两边都碰到", d
        if s_hit:
            return "先碰止损", d
        if t_hit:
            return "先到目标位", d
    return "20 天内都没碰到" if len(fwd) <= 20 else "60 天内都没碰到", None


rows, key, notes = [], [], []
tally = {"一致": 0, "不一致": 0, "我们多了": 0, "我们少了": 0}
for n in range(1, 9):
    sym, a, b, w, raw, k = load(n)
    g = G[n]
    st = compute_stages(raw.loc[:b, ["close"]])
    last = st.iloc[-1]
    stage = last["stage"]
    sup, res = levels(w)
    ch, atr = chandelier(raw, b)
    c = w["close"].iloc[-1]
    ours_stop = sup[0][1] if sup else None
    ours_tgt = res[0][1] if res else None

    # ① 趋势
    j1 = "一致" if FAM.get(stage) == g["fam"] else "不一致"
    # ②③
    j2, n2 = cmp_levels(sup, g["sup"])
    j3, n3 = cmp_levels(res, g["res"])
    # ④ 止损
    if ours_stop is None:
        j4, n4 = "我们少了", "窗口里没有更低的摆动低点"
    else:
        j4 = "一致" if near(ours_stop, g["stop"]) else "不一致"
        n4 = f"我方 {ours_stop:.2f}（收盘跌破算） vs Gemini {g['stop']:g}"
    # ⑤ 目标
    if ours_tgt is None and g["tgt"] is not None:
        j5, n5 = "我们少了", f"我们按规矩给不出（上方没有摆动高点）；Gemini 给 {g['tgt']:g}（区间外，公式外推）"
    elif ours_tgt is None:
        j5, n5 = "一致", "两边都给不出"
    else:
        j5 = "一致" if near(ours_tgt, g["tgt"]) else "不一致"
        n5 = f"我方 {ours_tgt:.2f} vs Gemini {g['tgt']:g}"
    # ⑥ 后面怎么走：我方按卡不选一个；Gemini 选了一个
    j6, n6 = "不一致", "我方按卡列互斥几种 + 验证条件、不选；Gemini 选了一个"
    for j in (j1, j2, j3, j4, j5, j6):
        tally[j] += 1

    def lv(x):
        return "；".join(f"{v:.2f}（第 {i} 根）" for i, v in x) if x else "给不出"

    path = []
    if res:
        path.append(f"收盘站上 {res[0][1]:.2f} → 向上那一种成立")
    else:
        path.append("已在窗口最高处，上方没有参照 → 只盯下方")
    if sup:
        path.append(f"收在 {sup[0][1]:.2f}~{(res[0][1] if res else w['high'].max()):.2f} 之间 → 区间内来回")
        path.append(f"收盘跌破 {sup[0][1]:.2f} → 失效、向下那一种成立")
    else:
        path.append("已在窗口最低处，下方没有参照 → 只能说「再创新低 = 跌势延续」，没有失效位可给")

    rows.append(dict(n=n, sym=sym, b=b, stage=f"{STAGE_PLAIN.get(stage, stage)}（{stage}；150 日线 {last['ma150']:.2f}、效率比 {last['er30']:.2f}）",
                     sup=lv(sup), res=lv(res), stop=(f"{ours_stop:.2f}（收盘跌破算）" if ours_stop else "给不出") + f"；吊灯参考 {ch:.2f}",
                     tgt=(f"{ours_tgt:.2f}（名义空间 {100*(ours_tgt/c-1):+.1f}%；净空间：我们没有价差数据）" if ours_tgt else "给不出（上方没有历史成交结构）"),
                     path=" / ".join(path), j=[j1, j2, j3, j4, j5, j6], nn=[f"我方「{STAGE_PLAIN.get(stage, stage)}」vs Gemini「{g['trend']}」", n2, n3, n4, n5, n6]))

    # ---- 答案卷：窗口之后真实发生了什么 ----
    fwd = raw.loc[b:].iloc[1:61]
    spl = (fwd["split_coefficient"].fillna(1) != 1).any()
    f20, f60 = fwd.iloc[:20], fwd
    ours_hit = first_hit(f60, ours_stop, ours_tgt, True) if ours_stop else ("—", None)
    g_hit = first_hit(f60, g["stop"], g["tgt"], False)
    hi60, lo60 = f60["high"].max(), f60["low"].min()
    sus = ""
    if g["tgt"] and g["tgt"] > w["high"].max():
        gap = g["tgt"] / hi60 - 1
        sus = f"区间外目标 {g['tgt']:g} vs 之后 60 天最高 {hi60:.2f}（差 {100*gap:+.1f}%）" + (" ★ 贴得很近，可疑" if abs(gap) <= 0.02 else "：没贴上，看不出偷看")
    key.append(dict(n=n, sym=sym, r20=100 * (f20["close"].iloc[-1] / c - 1), hi60=hi60, lo60=lo60,
                    ours=f"{ours_hit[0]}" + (f"（{ours_hit[1].date()}）" if ours_hit[1] is not None else ""),
                    gem=f"{g_hit[0]}" + (f"（{g_hit[1].date()}）" if g_hit[1] is not None else ""),
                    gpath=g["path"], sus=sus or "价位都在区间内，没有可疑的外推价", spl=spl))

# ---------------------------------------------------------------- 写文件
L = []
L.append("# 127 · B 类（实战判断）· 我方答卷 + 和 Gemini 对账 + 翻答案卷（2026-11-09）\n")
L.append("> 判据《66》· 问题单《122》· Gemini 原文《123》· 总对账《124》· 脚本 `probe/大师测试_1105/B类我方答卷_1109.py`（重跑出同一份）\n")
L.append("## ★★★ 三秒版\n\n```")
L.append(f"★ 8 段 × 6 问 = 48 格：一致 {tally['一致']} · 不一致 {tally['不一致']} · 我们多了 {tally['我们多了']} · 我们少了 {tally['我们少了']}（并排看，不打分）")
L.append("★ 其中第⑥问 8 格全是「不一致」，原因是同一个：大师卡规定「后面怎么走」只列几种可能 + 各自验证条件、不许选一个；")
L.append("  Gemini 每段都选了一个。这是**我们定的规矩**和它不同，不是抄错。")
L.append("★★★ 去掉⑥，真正差在三处：")
L.append("   ① 支撑 / 止损差最多（4 段不一致）：我们的「摆动低点」要等右边 5 根确认，最近几天的低点不算 →")
L.append("      我们的支撑、止损离现价远（例：META 我方 288.30，Gemini 309.84~310）。Gemini 用的是最近几天的低点。")
L.append("      → 按 Lin 的原则默认照 Gemini：我们的关键位要加一档「最近几天的低点 / 高点」（工程活，Claude 改）。")
L.append("   ② 趋势 2 段不一致（META、NUAN）：引擎判「震荡」（效率比低，走得不直），Gemini 判「上涨」。")
L.append("   ③ 「我们少了」5 格都是到了窗口边上：创新高的 ECL、PODD 我们按卡给不出目标位（Gemini 用公式往外推）；")
L.append("      在窗口最低处的 ENTA、EXPR 我们给不出止损位，ENTA 连支撑都给不出（Gemini 用最近几天的低点）。")
L.append("★ 翻答案卷：没有证据说明 Gemini 认出了票、偷看了后来（见第三节）。")
L.append("★★ 硬弱点：我方答卷是 1109 才按引擎口径算出来的，算之前已经看过 Gemini 的回答 ——")
L.append("   口径是写死在脚本里、按引擎已有的件拼的（没有对着 Gemini 调参数），但不是事先封存的「盲答」。")
L.append("★★ 一致多只说明两边量出来的位置像，不说明谁对。")
L.append("```\n")
L.append("## 一 · 我方口径（★ Claude 定，工程层面；跑之后不改）\n")
L.append("- ① 趋势：引擎状态机 `engine/stages.py`（生产口径，五个状态）在窗口最后一天的值。★ 大师卡写的是**六个**状态名（刚起步 / 在走 / 走到后段 / 缩在一起 / 来回摆 / 乱），引擎实际只有**五个**（上涨 / 上涨中的回调 / 下跌 / 下跌中的反弹 / 震荡）——卡和引擎对不上，先登记，这次按引擎答。")
L.append("- ②③ 支撑 / 压力：窗口内的摆动低点 / 高点（前后各 5 根的最低 / 最高；最后 5 根不算，不偷看），取离收盘最近的两档。上方没有摆动高点 → 给不出（卡第六节第三条）。")
L.append("- ④ 止损位：支撑第一档，**按收盘跌破算数**；另附吊灯止损原始值（近 22 根最高 − 3×ATR20）作参考。")
L.append("- ⑤ 目标位：压力第一档 + 名义空间%；净空间要扣价差 —— 我们没有价差数据，照实写。「这是先收一半的位置，不是我们预测它会到这儿。」")
L.append("- ⑥ 后面怎么走：列互斥的几种 + 各自验证条件，不选一个（卡 E 类）。")
L.append("- 对账：价位相差 ≤1% 或落在 Gemini 给的区间里 = 一致；趋势只比方向大类（上 / 下 / 震荡）。\n")
L.append("## 二 · 逐段对账\n")
for r in rows:
    L.append(f"### B{r['n']} · {r['sym']}（窗口截至 {r['b']}）\n")
    L.append("| 问 | 我方答案 | 判定 | 两边差在哪 |\n|---|---|---|---|")
    ans = [r["stage"], r["sup"], r["res"], r["stop"], r["tgt"], r["path"]]
    for q, a_, j, nn in zip(["①趋势", "②支撑", "③压力", "④止损位", "⑤目标位", "⑥后面怎么走"], ans, r["j"], r["nn"]):
        L.append(f"| {q} | {a_} | {j} | {nn} |")
    L.append("")
L.append("> ⑤ 目标位的注脚：这是先收一半的位置，不是我们预测它会到这儿。\n")
L.append("## 三 · 翻答案卷（★ 两边都存档之后才打开）\n")
L.append("| 段 | 之后 20 天涨跌 | 之后 60 天最高 / 最低 | 我方：止损和目标谁先到 | Gemini：止损和目标谁先到 | Gemini 选的那条路 | 后视镜：区间外的价位贴不贴后来的真实高点 |\n|---|---|---|---|---|---|---|")
for k_ in key:
    L.append(f"| B{k_['n']} {k_['sym']} | {k_['r20']:+.1f}% | {k_['hi60']:.2f} / {k_['lo60']:.2f} | {k_['ours']} | {k_['gem']} | {k_['gpath']} | {k_['sus']} |")
L.append("\n- 我方止损按**收盘**跌破算、目标按盘中碰到算；Gemini 止损按盘中碰到算（它多数没说清收盘还是盘中）。")
L.append("- ★ 这一节**不是主判据**（《66》：我们不比谁说得准），只用来查「Gemini 是不是认出了票、偷看了后来」。")
L.append("""
### 后视镜：两段「末日天量」到底是什么（1109 查公开资料）

- **B7 / C1b · ECL 2020-06-03**：当天 Ecolab 完成了把能源业务（ChampionX）分拆出去的换股要约，换股要约在当天凌晨到期、合并当天完成（来源：Ecolab 2020-06-03 新闻稿 / 8-K，SEC EDGAR）。
  Gemini 在 B7 说「单次事件驱动的流动性脉冲」、在 C1b 说「消息面异动或被动的指数基金调仓」——**方向沾边，但没点名这件事**。
  → ★ 判：**看不出它认出了票**（这类笼统说法对任何天量都能套上），但这一段不适合再当盲测素材。
- **B8 / C1c · PODD 2019-09-03**：当天公司发了 8-K（7.01 条，信息披露），次日发行 7 亿美元可转债（来源：SEC 申报列表；Drug Delivery Business 2019-09-04 报道）。**不是指数调整。**
  Gemini 在 C1c 又写了「某指数成分股被动调整」——**和事实对不上** → 更像是它的套话，不是偷看。
- **区间外的目标位**：B2 40.18（之后 60 天最高 44.93，差 −10.6%）、B8 189.81（最高 185.00，差 +2.6%）都没贴上；
  **B7 234（之后 60 天最高 231.36，差 +1.1%）贴得近**，但它写明是按箱体等距算的、而且它自己的止损 6-11 就先被碰到了。
  → ★ 判：**没有证据说明 Gemini 偷看了后来**；B7 这一格记「巧合待观察」。
""")
open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
print(tally)
for r in rows:
    print(r["n"], r["sym"], r["j"], "|", r["stage"][:30], "|", r["sup"], "|", r["res"])
for k_ in key:
    print(k_)
