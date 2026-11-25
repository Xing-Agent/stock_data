# -*- coding: utf-8 -*-
"""《451》任务二 · 出场改吊灯移动止损（《446 拍板》第 3 条）· 引擎外 · 1 小时线
大白话：进场一点不动（照《403》「破位那根收盘直接追」：4 小时箱体被放量实体 K 线收盘突破 0.25 ATR → 那根收盘进，做多做空各一套），
只换出场：
  对照组 = 现在卡里的「第一目标（线外 1 倍箱高）平一半 + 止损移到成本，第二目标 1.618 倍」，最长 72 根（同《403》）；
  吊灯   = 从持仓以来的最高点（做空是最低点）回撤 k × ATR 就走，k = 2.0 / 2.5 / 3.0；「收回突破位就撤」保留（收盘回到箱体里面 = 当根收盘走）；
           没有目标位，最长拿 72 根（同对照）和 240 根两版。
顺手两样：止损缓冲（初始止损在分界线往里多少 ATR）0.25 / 0.35 / 0.5（《403》基准 0.5）；
          时间止损：进场后第 7 根（另试 6、8）收盘时，持仓以来最多只走出 0.5R 以内（还没离开成本区）→ 那根收盘走。有 / 没有各跑。

══ 我补的定义 ══
 J1 吊灯用的 ATR = 1 小时 ATR14（和进场同一把尺），每根收盘后更新：止损 = max(初始止损, 持仓以来最高价 − k × ATR)，只往有利方向挪；下一根碰到就走，跳空按开盘价。
 J2 「收回突破位」= 收盘回到分界线里面（做多：收盘 < 箱顶；做空：收盘 > 箱底）→ 当根收盘走。对照组原来没有这一条，对照组照原样不加。
 J3 「成本区」= 进场价 ± 0.5R；时间止损只在还没碰过第一目标 / 吊灯还没上移过初始止损时生效。
 J4 成本单边 0.05%（同《403》）。
 J5 封存：2022-01-01 到 2025-12-31 的单子单独存到 out/封存_*.csv，不打印、不进任何统计。统计段：BTC / ETH 2017–2021；ETF 2005–2014、2015–2021。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
sp = importlib.util.spec_from_file_location("b", os.path.join(ROOT, "probe/贴线整理_1122/贴线整理_1122.py")); b = importlib.util.module_from_spec(sp); sp.loader.exec_module(b)
FEE = 0.0005
封存起, 封存止 = pd.Timestamp("2022-01-01"), pd.Timestamp("2025-12-31 23:59")


def 走(O, H, L, C, A, ei, Lg, e, stp, line, tp1, tp2, 出场, k=2.5, hold=72, 时止=None):
    """出场 = '对照' 或 '吊灯'。返回 (毛R, 怎么出, 出场下标, 拿几根)。"""
    sg = 1 if Lg else -1; risk = sg * (e - stp); n = len(C)
    pnl = lambda px: sg * (px - e) / risk
    s = stp; half = False; Rm = 0.0; best = e; jj = ei; 动过 = False
    for j in range(ei + 1, min(ei + 1 + hold, n)):
        jj = j
        hit = (L[j] <= s) if Lg else (H[j] >= s)
        if hit:
            fill = O[j] if ((O[j] <= s) if Lg else (O[j] >= s)) else s
            r = (Rm + 0.5 * pnl(fill)) if half else pnl(fill)
            why = "保本" if (half and 出场 == "对照") else ("吊灯" if 动过 else "止损")
            return r, why, j, j - ei
        if 出场 == "对照":
            if not half and ((H[j] >= tp1) if Lg else (L[j] <= tp1)): half = True; Rm = 0.5 * pnl(tp1); s = e
            if half and ((H[j] >= tp2) if Lg else (L[j] <= tp2)): return Rm + 0.5 * pnl(tp2), "第二目标", j, j - ei
        else:
            if (C[j] < line) if Lg else (C[j] > line): return pnl(C[j]), "收回突破位", j, j - ei
            best = max(best, H[j]) if Lg else min(best, L[j])
            ns = best - k * A[j] if Lg else best + k * A[j]
            if (ns > s) if Lg else (ns < s): s = ns; 动过 = True
        if 时止 and j - ei == 时止 and not half and not 动过:
            mfe = max(sg * (x - e) for x in (H[ei + 1:j + 1] if Lg else L[ei + 1:j + 1])) / risk
            if mfe < 0.5: return pnl(C[j]), "时间止损", j, j - ei
    r = (Rm + 0.5 * pnl(C[jj])) if half else pnl(C[jj])
    return r, "到期", jj, jj - ei


def 跑(d, 出场, N=20, brk=0.25, stk=0.5, volx=1.5, k=2.5, hold=72, 时止=None):
    B = b.boxes(d, N=N); A = b.atr(d).values
    O, H, L, C, V = [d[c].values for c in ["open", "high", "low", "close", "volume"]]
    top, bot, ok = B.top.values, B.bot.values, B.ok.fillna(False).values.astype(bool)
    vma = pd.Series(V).rolling(20).mean().shift(1).values; n = len(d); T = []; i = 150
    while i < n - 8:
        if not ok[i] or np.isnan(A[i]) or np.isnan(vma[i]): i += 1; continue
        body = abs(C[i] - O[i]); rg = H[i] - L[i] + 1e-12
        up = C[i] > top[i] + brk * A[i] and C[i - 1] <= top[i]; dn = C[i] < bot[i] - brk * A[i] and C[i - 1] >= bot[i]
        if not (up or dn) or V[i] < volx * vma[i] or body < 0.5 * rg: i += 1; continue
        Lg = up; line = top[i] if Lg else bot[i]; bh = top[i] - bot[i]
        e = C[i]; stp = line - stk * A[i] if Lg else line + stk * A[i]; risk = (e - stp) if Lg else (stp - e)
        tp1 = line + bh if Lg else line - bh; tp2 = line + 1.618 * bh if Lg else line - 1.618 * bh
        if risk <= 0 or ((tp1 - e) if Lg else (e - tp1)) <= 0: i += 1; continue
        r, why, jj, held = 走(O, H, L, C, A, i, Lg, e, stp, line, tp1, tp2, 出场, k=k, hold=hold, 时止=时止)
        T.append({"t": d.index[i], "出场t": d.index[jj], "dir": "多" if Lg else "空", "R": r, "净R": r - 2 * FEE / (risk / e), "怎么出": why, "拿几根": held, "riskp": risk / e})
        i = jj + 1          # 同一只票同一时间只拿一笔（同《403》）
    return pd.DataFrame(T)


def 回撤R(r):
    eq = r.cumsum(); return float((eq - eq.cummax()).min())


def S(t):
    if len(t) == 0: return {"笔数": 0}
    r = t["净R"]; w = r[r > 0].sum(); l = -r[r < 0].sum()
    se = r.std(ddof=1) / np.sqrt(len(r)) if len(r) > 1 else np.nan
    return {"笔数": int(len(t)), "每笔毛R": round(float(t.R.mean()), 3), "每笔净R": round(float(r.mean()), 3), "胜率pct": round(float((r > 0).mean() * 100), 1),
            "利润因子": round(float(w / l), 2) if l > 0 else None, "t值": round(float(r.mean() / se), 2) if se and se > 0 else None,
            "按笔累计最深回撤R": round(回撤R(r.reset_index(drop=True)), 1), "平均拿几根": round(float(t["拿几根"].mean()), 1),
            "怎么出pct": {k_: round(v * 100, 1) for k_, v in t["怎么出"].value_counts(normalize=True).items()}}


组 = {"对照·第一目标平一半推保本": dict(出场="对照")}
for k in (2.0, 2.5, 3.0):
    组[f"吊灯k={k}·最长72根"] = dict(出场="吊灯", k=k, hold=72)
    组[f"吊灯k={k}·最长240根"] = dict(出场="吊灯", k=k, hold=240)
for stk in (0.25, 0.35):
    组[f"对照·止损缓冲{stk}"] = dict(出场="对照", stk=stk); 组[f"吊灯k=2.5·最长240根·止损缓冲{stk}"] = dict(出场="吊灯", k=2.5, hold=240, stk=stk)
for ts in (6, 7, 8):
    组[f"对照·时间止损{ts}根"] = dict(出场="对照", 时止=ts); 组[f"吊灯k=2.5·最长240根·时间止损{ts}根"] = dict(出场="吊灯", k=2.5, hold=240, 时止=ts)

if __name__ == "__main__":
    syms = ["BTC", "ETH", "SPY", "QQQ", "DIA", "IWM", "SMH", "KRE", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
    类 = lambda s: "币" if s in ("BTC", "ETH") else ("大指数ETF" if s in ("SPY", "QQQ", "DIA", "IWM") else "行业ETF")
    data = {s: b.load(s) for s in syms}
    out = {}
    for g, kw in 组.items():
        L = []
        for s in syms:
            t = 跑(data[s], **kw)
            if len(t): t["票"] = s; t["类"] = 类(s); L.append(t)
        T = pd.concat(L, ignore_index=True)
        T["t"] = pd.to_datetime(T["t"], utc=True).dt.tz_localize(None); T["出场t"] = pd.to_datetime(T["出场t"], utc=True).dt.tz_localize(None)
        封 = (T["t"] >= 封存起) & (T["t"] <= 封存止)
        T[封].to_csv(os.path.join(OUT, f"封存_{g}.csv"), index=False)            # 封存段：只存，不打印、不统计
        T = T[~封 & (T["t"] >= "2005-01-01") & (T["t"] < "2022-01-01")].copy()
        T["段"] = np.where(T["类"] == "币", "2017–2021", np.where(T["t"] < "2015-01-01", "2005–2014", "2015–2021"))
        T.to_csv(os.path.join(OUT, f"逐笔_{g}.csv"), index=False)
        out[g] = {f"{c}｜{a}｜{d_}": S(x) for (c, a, d_), x in T.groupby(["类", "段", "dir"])}
        out[g].update({f"币分票｜{s}｜{d_}": S(x) for (s, d_), x in T[T["类"] == "币"].groupby(["票", "dir"])})
        print(g, {k_: (v["笔数"], v["每笔净R"]) for k_, v in out[g].items() if k_.startswith("币｜")}, flush=True)
    json.dump(out, open(os.path.join(OUT, "吊灯_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DONE")
