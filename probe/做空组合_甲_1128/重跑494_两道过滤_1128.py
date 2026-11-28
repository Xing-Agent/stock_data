# -*- coding: utf-8 -*-
"""《570》第二批另一版 =《527 拍板》第 4 条：把《494》那批美股个股做空（反抽 20 日线没过再空）原样重跑，
只加两道过滤：「大盘开关」（标普 SPY 收在 200 日线下、且 50 日线在 200 日线下，前一天收盘判）和「下面 1.2R 以内没有支撑」。
规则、名单、出场、成本全部照 probe/反抽搬家_1127/反抽搬家_1127.py 的 跑()（直接载入原函数，原文件不改）。
支撑 = 日线前低（分形低点，左右各 5 天，进场前已确认），回看 250 天（我定的，另试 120、500）；离进场价 < 1.2R 就算有支撑、不做（1.2 是拍板的数，另报 1.0、1.5）。
另报拍板第 4 条里个股的另两条（这只票自己收在 200 日线下；财报前 5 个交易日不做），单列，不混进「两道过滤」那一行。
时间 2015–2021（个股小时线 2015 年才有），2022 以后不读。断点续跑：40 只一批，跑完一批记一批。"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out_494"); os.makedirs(OUT, exist_ok=True)
sp = importlib.util.spec_from_file_location("搬家", os.path.join(ROOT, "probe/反抽搬家_1127/反抽搬家_1127.py")); M = importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
封 = M.封; HR = M.HR


def 大势():
    y = pd.read_csv(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线/SPY_日线.csv"), parse_dates=["date"]).set_index("date").close_adj.loc[:封]
    s50, s200 = y.rolling(50).mean(), y.rolling(200).mean(); return ((y < s200) & (s50 < s200)).shift(1).fillna(False).astype(bool)


def 财报日():
    e = pd.read_csv(os.path.join(ROOT, "probe/fund_expand_1103/earnings_calendar_8k202_1103.csv.gz"), usecols=["symbols", "effective_trade_date", "is_main_release"])
    e = e[e.is_main_release]; e["d"] = pd.to_datetime(e.effective_trade_date); out = {}
    for s, g in e.groupby("symbols"):
        for x in str(s).split(","): out.setdefault(x.strip(), []).append(g.d.values)
    return {k: np.sort(np.concatenate(v)) for k, v in out.items()}


if __name__ == "__main__":
    势 = 大势(); 财 = 财报日()
    L = pd.read_csv(os.path.join(HR, "说明_每只票.csv")); syms = set(L["代码"]); 名单 = {}
    for y in range(2015, 2022):
        u = pd.read_csv(os.path.join(ROOT, f"universe_1107/universe_{y}.csv.gz")); u = u[u.ticker.isin(syms)].sort_values("avg_dollar_volume_60d_close", ascending=False); 名单[y] = list(u.ticker.head(200))
    全 = sorted(set(sum(名单.values(), []))); print("名单合计", len(全), flush=True)
    f_out = os.path.join(OUT, "逐笔.csv"); f_done = os.path.join(OUT, "已跑.json"); done = set(json.load(open(f_done))) if os.path.exists(f_done) else set()
    fs = [os.path.join(HR, f) for f in sorted(os.listdir(HR)) if f.endswith(".parquet") and int(f[:4]) <= 2021]
    todo = [s for s in 全 if s not in done]
    for b in range(0, len(todo), 40):
        批 = todo[b:b + 40]; H = pd.concat([M.读小时(f, 批) for f in fs]); H = H[H.t <= 封]; rows = []; 池 = {}
        for s in 批:
            x = H[H.symbol == s]
            if len(x) < 2000: continue
            X, D = M.拼(x.drop(columns="symbol")); dl = D.low.to_numpy(); N = 5
            SLd = np.array([j for j in range(N, len(D) - N) if dl[j] == dl[j - N:j + N + 1].min()], dtype=int)
            s200 = D.close.rolling(200).mean(); 自下 = (D.close < s200).shift(1).fillna(False)
            ed = 财.get(s, np.array([], dtype="datetime64[ns]")); didx = D.index
            for y in [y for y, v in 名单.items() if s in v]:
                for 开 in ("均线", "不加"):
                    for nm, 过, 比 in M.配置:
                        for r in M.跑(s, X, D, 开, 过, 比, 年=y):
                            t = pd.Timestamp(r["t"]); d0 = t.normalize(); p = didx.searchsorted(d0)          # p = 进场那天在日线里的位置（只用它之前的）
                            e, st = r["进"], r["止损"]; R_ = st - e; out = {}
                            for LB in (120, 250, 500):
                                sl = SLd[(SLd + N < p) & (SLd >= p - LB)]; below = dl[sl][dl[sl] < e]
                                out[f"支撑R_{LB}"] = float((e - below.max()) / R_) if len(below) else np.inf
                            # 财报：进场那天起 5 个交易日内有财报
                            k5 = didx[min(len(didx) - 1, p + 4)] if p < len(didx) else d0
                            有财 = bool(len(ed) and ((ed >= np.datetime64(d0)) & (ed <= np.datetime64(k5))).any())
                            ia = X.index.searchsorted(t) - 1
                            rows.append(dict(r, 开关=开, 过滤=nm, 名单年=y, 大盘开关=bool(势.reindex([d0], method="ffill").iloc[0]) if d0 >= 势.index[0] else False,
                                             自己在200下=bool(自下.iloc[p]) if p < len(自下) else False, 财报5天内=有财, atr4=float(X.atr.iloc[ia]) if ia >= 0 else np.nan, **out))
            # 随机对照的池：4 小时根里「均线开关 + 大盘开关」都满足、且在名单年里的
            m120 = D.close.rolling(120).mean(); 均 = ((D.close < m120) & (m120 < m120.shift(20)))
            dd = X.index.normalize(); ok = 均.reindex(dd).fillna(False).to_numpy(bool) & 势.reindex(dd).fillna(False).to_numpy(bool) & np.isin(X.index.year, [y for y, v in 名单.items() if s in v])
            ok &= X.atr.to_numpy() > 0; ok[:30] = False; ok[-2:] = False
            if ok.any(): 池[s] = (X.open.to_numpy(float), X.high.to_numpy(float), X.low.to_numpy(float), X.close.to_numpy(float), X.atr.to_numpy(float), np.where(ok)[0])
        if rows: pd.DataFrame(rows).to_csv(f_out, mode="a", header=not os.path.exists(f_out), index=False)
        pd.to_pickle(池, os.path.join(OUT, f"池_{len(done) // 40:03d}_{b}.pkl"))
        done |= set(批); json.dump(sorted(done), open(f_done, "w")); print("批", b // 40 + 1, "/", (len(todo) + 39) // 40, flush=True)
    print("DONE")
