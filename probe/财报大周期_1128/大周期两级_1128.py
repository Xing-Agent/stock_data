# -*- coding: utf-8 -*-
"""《571》第五批 · 大周期（《527 拍板》第 3 条）· 引擎外 · 只读
一、黄灯分两级：
  一级 = 原条件（十三周对照_1125.py 原样）：周收盘跌破之前 13 周最低周收盘，且 40 周线不在过去 52 周的最高处。解除 = 连续 2 周收在 40 周线上、40 周线拐头向上。
  二级 = 一级亮灯以后、解除以前，下面两条先到哪条算哪条：
     ① 亮灯那周之后，再连续 K 周收在「亮灯时被跌破的那个 13 周低点」下面（K = 2，另试 1、3）。
        ★ 拍板写「连续 2 周收在 13 周低点下面」，没说亮灯那周算不算第 1 周；K=1 就是「连亮灯那周一共 2 周」，三档都报，两种读法都在里面。
     ② 亮灯后 4 周内「再跌破一次」：★ 先收回到那个低点上面（至少一周），然后又收到它下面。
  评分照 改写版_1125.py 的「评」：真大顶 = 两年新高后回落 ≥ 20%；认出 = 确认日落在「顶 → 熊底」之间；虚惊 = 不属于真顶的报警里一年内再跌不到 10%。
  标普 1928–2021、纳指 1971–2021（2022 年以后不进统计，算灯时数据就切到 2021-12-31）。
二、按灯调每笔风险：绿灯 1R、黄灯 0.5R、红灯 0.25R（另试红灯空仓 = 0）。灯看标普：黄灯 = 一级黄灯，红灯 = 日线版（《489》那版：解除不要箱底）。
  亮灯那周 / 那天收盘后才知道，所以从下一个交易日起算。套在 34 个技术类策略的单子上：按进场那天的灯给这一笔的风险倍数。
  ★ 只能在单子层面算（R 乘倍数）：每年合计多少 R、按同样风险累计的最深亏损（R）。引擎里的净值（复利、仓位上限、同时几笔）没重跑。
  另试：黄灯换成二级黄灯。两段：2005–2014（流水_二）、2015–2021（流水_一，按平仓日 ≤ 2021-12-31 挑）。"""
import os, sys, json, glob, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
G = mod("G", os.path.join(ROOT, "probe/大周期三步走_1125/改写版_1125.py"))
封 = pd.Timestamp("2021-12-31")


def 两级(D, N=13, K=2, 重破周=4, ma_n=40, 看=52, 任何时候=True):
    W = G.周线(D); c = W.close.to_numpy(float); idx = W.index; n = len(c)
    ma = pd.Series(c).rolling(ma_n, min_periods=ma_n).mean().to_numpy()
    lowN = pd.Series(c).rolling(N, min_periods=N).min().shift(1).to_numpy()
    mahi = pd.Series(ma).rolling(看, min_periods=10).max().shift(1).to_numpy()
    一, 二 = [], []; t = ma_n + 看
    while t < n:
        if c[t] < lowN[t] and ma[t] < mahi[t]:
            r = None
            for j in range(t + 1, n):
                if c[j] > ma[j] and c[j - 1] > ma[j - 1] and ma[j] > ma[j - 1]: r = j; break
            end = r if r is not None else n
            lv = lowN[t]; e1 = {"确认": idx[t], "路": f"一级", "解除": idx[r] if r is not None else None}; 一.append(e1)
            a = None
            if 任何时候:   # 黄灯期间任何时候，连续 K 周收在被跌破的那个低点下面（亮灯那周不算）
                run = 0
                for j in range(t + 1, end):
                    run = run + 1 if c[j] < lv else 0
                    if run >= K: a = j; break
            elif t + K < end and all(c[t + 1:t + K + 1] < lv): a = t + K
            b = None; 收回 = False
            for j in range(t + 1, min(t + 重破周, end - 1) + 1):
                if c[j] >= lv: 收回 = True
                elif 收回: b = j; break
            cand = [x for x in (a, b) if x is not None]
            if cand:
                j = min(cand); 二.append({"确认": idx[j], "路": "二级①连续" if j == a else "二级②再跌破", "一级": idx[t], "解除": e1["解除"]})
            t = end + 1 if r is not None else n
        else: t += 1
    return 一, 二


def 评(D, ev):
    S, T, F = G.评(D, ev); return S, T, F


def 灯(D, 黄用二级=False, K=2):
    """每个交易日（收盘后已知）的灯：0 绿、1 黄、2 红。从下一个交易日起生效。"""
    idx = D.index; s = pd.Series(0, index=idx)
    一, 二 = 两级(D, K=K)
    for e in (二 if 黄用二级 else 一):
        a = e["确认"]; b = e["解除"] or idx[-1]
        s[(idx > a) & (idx <= b)] = np.maximum(s[(idx > a) & (idx <= b)], 1)
    for e in G.日线版(D, 解除要箱底=False):
        a = e["确认"]; b = e["解除"] or idx[-1]
        s[(idx > a) & (idx <= b)] = 2
    return s


if __name__ == "__main__":
    res = {}
    # 一、黄灯分两级
    for nm in ("标普500指数", "纳斯达克综合指数"):
        D = G.L.读(nm).loc[:封]; o = {}
        一, _ = 两级(D); S, T, F = 评(D, 一); o["一级(原条件)"] = {"概要": S}
        for K, 任 in ((1, True), (2, True), (3, True), (1, False), (2, False), (3, False)):
            _, 二 = 两级(D, K=K, 任何时候=任); S2, T2, F2 = 评(D, 二)
            o[f"二级 K={K}" + ("" if 任 else "·只看亮灯后紧接着那几周")] = {"概要": S2, "每个真顶": T2.to_dict("records"), "别的报警": F2.to_dict("records"),
                               "二级里哪一条先到": pd.Series([e["路"] for e in 二]).value_counts().to_dict(),
                               "一级报警里升到二级的次数": len(二), "一级报警总数": len(一)}
            if K == 2:
                # 只用其中一条的对照
                pass
        o["一级·每个真顶"] = T.to_dict("records"); o["一级·别的报警"] = F.to_dict("records")
        res[nm] = o
        print(nm, "一级", S, flush=True)
        for k_ in o:
            if k_.startswith("二级"): print("  ", k_, o[k_]["概要"], o[k_]["二级里哪一条先到"], "没认出", [t["顶"] for t in o[k_]["每个真顶"] if t["认出"] == "没认出"], flush=True)
    json.dump(res, open(os.path.join(OUT, "黄灯两级_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)

    # 二、按灯调每笔风险
    A_ = os.path.join(ROOT, "probe/成绩单_1122/out_手册/")
    D = G.L.读("标普500指数").loc[:封]
    灯们 = {"黄=一级": 灯(D), "黄=二级(K=2)": 灯(D, 黄用二级=True, K=2), "黄=二级(K=1)": 灯(D, 黄用二级=True, K=1)}
    def 最深(r):
        cum = np.concatenate([[0], np.cumsum(r)]); return float((np.maximum.accumulate(cum) - cum).max())
    out2 = {}
    for 段, a, b in (("2005–2014", "2005-01-01", "2014-12-31"), ("2015–2021", "2015-01-01", "2021-12-31")):
        rows = []; 全 = []
        for f in sorted(glob.glob(A_ + ("流水_二_*.csv" if 段 == "2005–2014" else "流水_一_*.csv"))):
            nm = os.path.basename(f)[5:-4]
            if nm.startswith("buy_and_hold"): continue
            t = pd.read_csv(f, parse_dates=["entry_date", "exit_date"]); t = t[(t.exit_date <= 封) & (t.entry_date >= a) & (t.entry_date <= b)].sort_values("exit_date")
            if not len(t): continue
            yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25; r = t.r_multiple_net.to_numpy()
            row = dict(策略=nm, 笔数=len(t), 原每年R=r.sum() / yrs, 原最深R=最深(r))
            for gk, s in 灯们.items():
                L_ = s.reindex(t.entry_date, method="ffill").to_numpy()
                for 红名, 红 in (("红0.25", 0.25), ("红空仓", 0.0)):
                    m = np.where(L_ == 2, 红, np.where(L_ == 1, 0.5, 1.0)); rr = r * m
                    row[f"{gk}·{红名}·每年R"] = rr.sum() / yrs; row[f"{gk}·{红名}·最深R"] = 最深(rr)
                if gk == "黄=一级": t = t.assign(灯=L_)
            rows.append(row); 全.append(t.assign(策略=nm))
        P = pd.DataFrame(rows); X = pd.concat(全)
        o = {"策略数": len(P), "单子数": int(len(X)),
             "按进场时的灯分": {k: dict(笔数=int((X.灯 == v).sum()), 每笔R=round(float(X.r_multiple_net[X.灯 == v].mean()), 3) if (X.灯 == v).any() else None,
                                       亏超15R占比=round(float((X.r_multiple_net[X.灯 == v] < -1.5).mean() * 100), 2) if (X.灯 == v).any() else None) for k, v in (("绿", 0), ("黄", 1), ("红", 2))},
             "原_每年R中位": round(float(P.原每年R.median()), 2), "原_最深R中位": round(float(P.原最深R.median()), 1)}
        for c_ in [c for c in P.columns if c.endswith("每年R") and c != "原每年R"]:
            k = c_[:-3]; dd = k + "最深R"
            o[k] = dict(每年R中位=round(float(P[c_].median()), 2), 最深R中位=round(float(P[dd].median()), 1),
                        每年R变化中位=round(float((P[c_] - P.原每年R).median()), 2), 最深R变化中位=round(float((P[dd] - P.原最深R).median()), 1),
                        最深变浅的策略数=int((P[dd] < P.原最深R).sum()), 每年R变少的策略数=int((P[c_] < P.原每年R).sum()))
        out2[段] = o; P.round(2).to_csv(os.path.join(OUT, f"按灯调风险_{段}_每个策略.csv"), index=False)
        print(段, json.dumps(o, ensure_ascii=False, default=str)[:1500], flush=True)
    灯天 = {k: {"绿": int((s.loc["2005":] == 0).sum()), "黄": int((s.loc["2005":] == 1).sum()), "红": int((s.loc["2005":] == 2).sum())} for k, s in 灯们.items()}
    res["按灯调风险"] = out2; res["按灯调风险"]["2005–2021各灯的交易日数"] = 灯天
    json.dump(res, open(os.path.join(OUT, "黄灯两级_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
