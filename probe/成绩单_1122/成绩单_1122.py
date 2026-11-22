# -*- coding: utf-8 -*-
"""成绩单新版（《369》拍板第 1 条）· 引擎外
五个主指标：年化÷最大回撤、溃疡绩效、最差一年、最长不创新高天数、「拿不住」模拟生存率
四行对照：标普买入不动 / 同样平均仓位的标普 / 不挂挂件的主策略（调用方传）/ 随机进场（调用方传或用 随机进场()）
用法：成绩单(eq, 流水=L) 返回一个 dict；并排(名字→dict) 出 markdown 表。
口径（拍板没写死、我定的，都写进报告）：
  - 溃疡指数 = 每天「离前高跌了百分之几」的平方的平均、再开方；溃疡绩效 =（年化 − 现金年化）÷ 溃疡指数
  - 生存率：每隔 5 个交易日取一天当「开始跟的那天」，往后看 252 个交易日；从那天起算的回撤 > 15%，或连续 150 个交易日没创（从那天起算的）新高，
    或那天之后平掉的单子连亏 8 笔，三条碰到任何一条就算放弃。生存率 = 没放弃的占比。不够 252 天的开始日不算。
  - 现金利息 = 3 个月美国国债利率（FRED DTB3，贴现口径，按 252 天摊）
  - 等仓位标普：每天按策略前一天的实际仓位比例持有 SPY（含分红），其余拿现金利息
"""
import os, gzip, json
import numpy as np, pandas as pd
ROOT = os.environ.get("XING_ROOT", "/home/claude/xing-agent-stock_data")

def 现金日收益(idx):
    d = json.load(gzip.open(os.path.join(ROOT, "market_macro_1105/DTB3/daily.json.gz")))["data"]
    s = pd.Series({pd.Timestamp(x["date"]): x["close"] for x in d if x["close"] is not None}).sort_index()
    return (s.reindex(idx, method="ffill").fillna(0) / 100 / 252)

def 标普净值(idx):
    f = os.path.join(ROOT, "market_ext_1105/指数ETF长历史_1120/SPY_日线.csv")
    s = pd.read_csv(f, parse_dates=["date"]).set_index("date")["adjusted_close"].reindex(idx).ffill()
    return s / s.iloc[0]

def 等仓位标普(idx, 仓位):
    spy = 标普净值(idx).pct_change().fillna(0); cash = 现金日收益(idx)
    w = 仓位.reindex(idx).fillna(0).clip(0, None).shift(1).fillna(0)
    r = w * spy + (1 - w).clip(0, None) * cash
    return (1 + r).cumprod()

def 生存率(eq, 流水=None, 步=5, 窗=252, 回撤线=0.15, 不新高=150, 连亏=8):
    v = eq.values.astype(float); idx = eq.index; n = len(v)
    出 = None
    if 流水 is not None and len(流水):
        L = 流水.copy(); L["exit_date"] = pd.to_datetime(L["exit_date"]); L = L.sort_values("exit_date")
        出 = (L["exit_date"].values, (L["net_pnl"].astype(float) < 0).values)
    活 = 0; 总 = 0; 因 = {"回撤": 0, "不新高": 0, "连亏": 0}
    for s in range(0, n - 窗, 步):
        seg = v[s:s + 窗 + 1] / v[s]; pk = np.maximum.accumulate(seg)
        dd = seg / pk - 1
        a = np.argmax(dd < -回撤线) if (dd < -回撤线).any() else 10**9
        prev = np.concatenate([[seg[0]], pk[:-1]]); last = 0; b = 10**9
        for k in range(1, len(seg)):
            if seg[k] > prev[k] + 1e-12: last = k          # 严格高过此前最高才算创新高
            elif k - last >= 不新高: b = k; break
        c = 10**9
        if 出 is not None:
            t0, t1 = idx[s], idx[s + 窗]
            m = (出[0] > np.datetime64(t0)) & (出[0] <= np.datetime64(t1)); los = 出[1][m]; ds = 出[0][m]; run = 0
            for j in range(len(los)):
                run = run + 1 if los[j] else 0
                if run >= 连亏: c = int(idx.searchsorted(ds[j])) - s; break
        总 += 1; x = min(a, b, c)
        if x >= 10**9: 活 += 1
        else: 因["回撤" if x == a else ("不新高" if x == b else "连亏")] += 1
    return (活 / 总 * 100 if 总 else None), {k: round(val / 总 * 100, 1) for k, val in 因.items()} if 总 else {}

def 成绩单(eq, 流水=None, 仓位=None):
    eq = eq.dropna(); eq = eq / eq.iloc[0]; idx = eq.index
    yrs = (idx[-1] - idx[0]).days / 365.25
    ann = eq.iloc[-1] ** (1 / yrs) - 1; dd = eq / eq.cummax() - 1; mdd = float(dd.min())
    ui = float(np.sqrt(((dd * 100) ** 2).mean())); cash = float((1 + 现金日收益(idx)).prod() ** (1 / yrs) - 1)
    水下 = (eq < eq.cummax()).astype(int); 最长 = int(水下.groupby((水下 == 0).cumsum()).sum().max())
    yr = eq.groupby(idx.year).last(); yret = yr / yr.shift(1).fillna(1.0) - 1
    sv, why = 生存率(eq, 流水)
    out = {"时间段": f"{idx[0].date()} → {idx[-1].date()}", "每年赚pct": round(ann * 100, 2), "最深亏损pct": round(mdd * 100, 1),
           "每年赚除以最深亏损": round(ann / abs(mdd), 2) if mdd < 0 else None, "溃疡指数": round(ui, 2), "溃疡绩效": round((ann - cash) * 100 / ui, 2) if ui > 0 else None,
           "最差一年pct": round(float(yret.min()) * 100, 1), "最长多少个交易日没创新高": 最长, "拿得住的占比pct": round(sv, 1) if sv is not None else None, "放弃的原因pct": why}
    if 仓位 is not None: out["平均仓位pct"] = round(float(仓位.reindex(idx).fillna(0).mean() * 100), 1)
    if 流水 is not None and len(流水):
        p = 流水["net_pnl"].astype(float); w = p[p > 0].sum(); l = -p[p < 0].sum()
        out.update({"笔数": int(len(p)), "赚钱的笔pct": round(float((p > 0).mean() * 100), 1), "利润因子": round(float(w / l), 2) if l > 0 else None})
    return out

def 随机进场(流水, 收盘宽表, 可选掩膜, eq, 种子=0):
    """同样的笔数、同样的进场日、同样拿多少天、同样占多大仓位，只把「买哪只」换成当天可选池里随机一只。返回日净值。"""
    rng = np.random.default_rng(种子); idx = eq.index; C = 收盘宽表.reindex(idx).ffill()
    ret = C.pct_change().fillna(0).values; cols = np.array(C.columns); M = 可选掩膜.reindex(index=idx, columns=C.columns).fillna(False).values
    W = np.zeros(len(idx)); R = np.zeros(len(idx)); e = eq.values
    L = 流水.copy(); L["entry_date"] = pd.to_datetime(L["entry_date"]); L["exit_date"] = pd.to_datetime(L["exit_date"])
    for _, x in L.iterrows():
        a = idx.searchsorted(x.entry_date); b = min(idx.searchsorted(x.exit_date), len(idx) - 1)
        if a >= len(idx) or b <= a: continue
        cand = np.where(M[a])[0]
        if len(cand) == 0: continue
        j = rng.choice(cand); w = float(x.notional_in) / e[a]
        R[a + 1:b + 1] += w * ret[a + 1:b + 1, j]; W[a + 1:b + 1] += w
    cash = 现金日收益(idx).values
    return pd.Series(np.cumprod(1 + R + np.clip(1 - W, 0, None) * cash * 0), index=idx)   # 现金不计息，和引擎口径一致

行 = [("每年赚pct", "每年赚"), ("最深亏损pct", "最深亏损"), ("每年赚除以最深亏损", "每年赚 ÷ 最深亏损"), ("溃疡绩效", "溃疡绩效"), ("最差一年pct", "最差一年"),
      ("最长多少个交易日没创新高", "最长没创新高（交易日）"), ("拿得住的占比pct", "拿得住的占比"), ("平均仓位pct", "平均仓位"), ("笔数", "笔数")]
def 并排(表):
    names = list(表); L = ["| | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for k, zh in 行:
        L.append(f"| {zh} | " + " | ".join(("" if 表[n].get(k) is None else (f"{表[n][k]}%" if k.endswith("pct") else str(表[n][k]))) for n in names) + " |")
    return "\n".join(L)

if __name__ == "__main__":
    # 自检：标普、同池子全买不动（2005–2014 那条已有的日净值）
    eq = pd.read_csv(os.path.join(ROOT, "probe/两段时间_1120/宽基2004_中_日净值.csv"), index_col=0, parse_dates=True).iloc[:, 0]
    a = 成绩单(eq); b = 成绩单(标普净值(eq.index)); c = 成绩单(等仓位标普(eq.index, pd.Series(0.5, index=eq.index)))
    print(并排({"同池子全买不动": a, "标普买入不动": b, "一半仓位的标普（自检用）": c}))
    print(a["放弃的原因pct"], b["放弃的原因pct"])
