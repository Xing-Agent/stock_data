# -*- coding: utf-8 -*-
"""《488》第 4 项 ·「反抽 20 日线没过再空」搬到 SOXX 和研发池个股（只做右侧）· 引擎外
规则原样照 probe/派发楔形_1125/反抽加过滤_1125.py 的 跑()（扳机、过滤、止损、3R / 60 根出场、单边 0.05%），只换数据和开关：
  4 小时线：美股常规时段小时线拼成每天两根（9:30–13:30、13:30–16:00）；日线由常规时段小时线拼。
  开关：币那边 18 笔用的是「状态机」（五档第四版：跌势 / 见顶，或筑底期冲出过箱顶）。个股没有状态机档位，用「均线」（收在 120 日线下且 120 日线比 20 天前低）和「不加」；
        SOXX 三种都跑（状态机档位是第 2 项刚补的，箱顶按原值算，不用切换原因里取整的数）。
  过滤：比例 0.8（币那 18 笔的口径），另试 0.6、1.0，另报不过滤。
品种：SOXX 2003–2021；个股 = 研发池小时线名单（2,123 只，已经不含考卷那 1,042 只）里，每年按上一年末 60 天日均成交额排前 200，只在那一年里取信号；退市的照算。
时间：个股 2015–2021（小时线从 2015 起，头 7 个月拿来攒 130 天日线）。美股 2022 年以后不读。"""
import os, re, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
FEE = 0.0005; 封 = pd.Timestamp("2021-12-31 23:59")
HR = os.path.join(ROOT, "market_ext_1105/小时线_1119/全量_2015_2025")


def 拼(H):
    """常规时段小时线 → 4 小时（每天两根）和日线。H 列：t(美东, tz-naive), open/high/low/close/volume（折算价）。"""
    H = H.sort_values("t"); mm = H.t.dt.hour * 60 + H.t.dt.minute; H = H.assign(d=H.t.dt.normalize(), b=np.where(mm < 13 * 60 + 30, 0, 1))
    g = H.groupby(["d", "b"]); X = pd.DataFrame({"open": g.open.first(), "high": g.high.max(), "low": g.low.min(), "close": g.close.last(), "volume": g.volume.sum()}).reset_index()
    X.index = X.d + pd.to_timedelta(np.where(X.b == 0, 9 * 60 + 30, 13 * 60 + 30), unit="m"); X = X.drop(columns=["d", "b"])
    pc = X.close.shift(1); X["atr"] = pd.concat([X.high - X.low, (X.high - pc).abs(), (X.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    g2 = H.groupby("d"); D = pd.DataFrame({"open": g2.open.first(), "high": g2.high.max(), "low": g2.low.min(), "close": g2.close.last()})
    return X, D


def 读小时(f, syms=None):
    cols = ["symbol", "time_utc", "session", "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"]
    x = pd.read_parquet(f, columns=[c for c in cols if c != "symbol"] + (["symbol"] if syms is not None else []), filters=[("symbol", "in", list(syms))] if syms is not None else None)
    x = x[x.session == "regular"]; t = pd.to_datetime(x.time_utc).dt.tz_convert("America/New_York").dt.tz_localize(None)
    return pd.DataFrame({"symbol": x["symbol"].to_numpy() if syms is not None else "SOXX", "t": t.to_numpy(), "open": x.open_adj.to_numpy(), "high": x.high_adj.to_numpy(), "low": x.low_adj.to_numpy(), "close": x.close_adj.to_numpy(), "volume": x.volume_adj.to_numpy()})


def SOXX可空():
    """状态机开关（照 反抽加过滤 的 状态可空，箱顶用原值）。"""
    R = pd.read_csv(os.path.join(ROOT, "probe/大周期五档_1123/out4/SOXX_四版_每天的档.csv"), index_col=0, parse_dates=True).loc[:封]
    sp = importlib.util.spec_from_file_location("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py")); SC = importlib.util.module_from_spec(sp); sp.loader.exec_module(SC)
    P = SC.soxx().loc[:封].reindex(R.index); h, l = P.high.to_numpy(), P.low.to_numpy(); st = R["档"].to_numpy(); why = R["切换原因"].fillna("").to_numpy(); ok = []; top = None; 冲 = False
    for i in range(len(R)):
        if why[i].startswith("进筑底期"):
            s0 = max(q for q in range(i) if st[q] == "跌势" and (q == 0 or st[q - 1] != "跌势")); li = s0 + int(np.nanargmin(l[s0:i + 1])); top = np.nanmax(h[li + 1:i + 1]) if li < i else h[i]; 冲 = False
        if st[i] != "筑底期": top = None; 冲 = False
        if top is not None and R["close"].iloc[i] > top: 冲 = True
        ok.append(st[i] in ("跌势", "见顶") or (st[i] == "筑底期" and 冲))
    return pd.Series(ok, index=R.index)


def 跑(sym, X, D, 开关, 过滤=True, 比例=0.8, 年=None, 状态=None):
    """照 反抽加过滤_1125.跑() 原样，只把 X / D / 开关 换成传进来的。年 = 只取这一年里的信号（个股按年换名单）。"""
    o, h, l, c, a4 = (X[x].to_numpy(float) for x in ("open", "high", "low", "close", "atr")); n = len(X); t = X.index
    pc = D.close.shift(1); D = D.copy(); D["atr"] = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean(); D["ma"] = D.close.rolling(20).mean()
    m120 = D.close.rolling(120).mean()
    reg = {"均线": (D.close < m120) & (m120 < m120.shift(20)), "状态机": (状态.reindex(D.index).fillna(False) if 状态 is not None else None), "不加": pd.Series(True, index=D.index)}[开关]
    平 = D.ma <= D.ma.shift(5) * 1.005; 段号 = (平 != 平.shift()).cumsum()
    rng_d = (D.high - D.low).replace(0, np.nan); 大阳 = ((D.close - D.open) > 1.5 * D.atr.shift(1)) & ((D.close - D.low) / rng_d >= 0.75); 近大阳 = 大阳.rolling(3).max().fillna(0).astype(bool)
    dl, dh = D.low.to_numpy(), D.high.to_numpy(); didx = D.index
    pos = didx.searchsorted(t.normalize()) - 1
    R = []; busy = -1; 次数 = {}
    for i in range(30, n - 2):
        if 年 is not None and t[i + 1].year != 年: continue
        p = pos[i]
        if p < 130 or not bool(reg.iloc[p]): continue
        ma = D.ma.iloc[p]; ad = D.atr.iloc[p]
        if not (ma > 0 and ad > 0): continue
        rng = h[i] - l[i]
        if rng <= 0 or i <= busy: continue
        吞没 = c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1]; 长上影 = (c[i] - l[i]) / rng <= 0.3 and (h[i] - max(o[i], c[i])) >= 0.4 * rng
        if not (吞没 or 长上影): continue
        if not (h[max(0, i - 6):i + 1].max() >= ma - 0.25 * ad and c[i] < ma and c[max(0, i - 12):i + 1].max() <= ma + 1.0 * ad): continue
        if 过滤:
            j0 = p - 40 + int(np.argmin(dl[p - 40:p + 1])); j1 = max(0, j0 - 60) + int(np.argmax(dh[max(0, j0 - 60):j0 + 1])); 弹 = p - j0; 跌 = j0 - j1
            if not (弹 >= 4 and 弹 >= 比例 * 跌): continue
            if bool(近大阳.iloc[p]): continue
            if not bool(平.iloc[p]): continue
            k_ = int(段号.iloc[p])
            if 次数.get(k_, 0) >= 2: continue
        e = o[i + 1]; stop = h[max(0, i - 30):i + 1].max() + 0.3 * a4[i]; r = stop - e
        if r <= 0 or r / e < 0.003: continue
        out = None; end = min(n - 1, i + 60)
        for j in range(i + 1, end + 1):
            if h[j] >= stop: out = -(max(o[j], stop) - e) / r if j > i + 1 else -1.0; break
            if l[j] <= e - 3 * r: out = 3.0; break
        if out is None: out = (e - c[end]) / r
        if 过滤: 次数[k_] = 次数.get(k_, 0) + 1
        busy = j; R.append(dict(sym=sym, t=t[i + 1], 进=e, 止损=stop, 风险pct=r / e * 100, R=out - 2 * FEE * e / r, 收益pct=(out * r - 2 * FEE * e) / e * 100))
    return R


配置 = [("不过滤", False, 0.8), ("过滤0.6", True, 0.6), ("过滤0.8", True, 0.8), ("过滤1.0", True, 1.0)]

if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "全部"
    if which in ("全部", "SOXX"):
        fs = sorted(f for f in os.listdir(os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线")) if f.endswith(".parquet") and int(f[5:9]) <= 2021)
        H = pd.concat([读小时(os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线", f)) for f in fs]); H = H[H.t <= 封]; X, D = 拼(H); 状 = SOXX可空(); rows = []
        for 开 in ("状态机", "均线", "不加"):
            for nm, 过, 比 in 配置: rows += [dict(r, 开关=开, 过滤=nm) for r in 跑("SOXX", X, D, 开, 过, 比, 状态=状)]
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "SOXX_逐笔.csv"), index=False); print("SOXX", len(rows), str(X.index[0]), str(X.index[-1]), flush=True)
    if which in ("全部", "个股"):
        L = pd.read_csv(os.path.join(HR, "说明_每只票.csv")); syms = set(L["代码"]); 名单 = {}
        for y in range(2015, 2022):
            u = pd.read_csv(os.path.join(ROOT, f"universe_1107/universe_{y}.csv.gz")); u = u[u.ticker.isin(syms)].sort_values("avg_dollar_volume_60d_close", ascending=False)
            名单[y] = list(u.ticker.head(200))
        全 = sorted(set(sum(名单.values(), []))); print("个股名单合计", len(全), flush=True)
        done = set()
        f_out = os.path.join(OUT, "个股_逐笔.csv")
        if os.path.exists(f_out) and "--重来" not in sys.argv: done = set(pd.read_csv(f_out).sym.unique()) | set(json.load(open(os.path.join(OUT, "个股_已跑.json"))) if os.path.exists(os.path.join(OUT, "个股_已跑.json")) else set())
        fs = [os.path.join(HR, f) for f in sorted(os.listdir(HR)) if f.endswith(".parquet") and int(f[:4]) <= 2021]
        todo = [s for s in 全 if s not in done]
        for b in range(0, len(todo), 40):                                                # 40 只一批，断点续跑
            批 = todo[b:b + 40]; H = pd.concat([读小时(f, 批) for f in fs]); H = H[H.t <= 封]; rows = []
            for s in 批:
                x = H[H.symbol == s]
                if len(x) < 2000: continue
                X, D = 拼(x.drop(columns="symbol"))
                for y in [y for y, v in 名单.items() if s in v]:
                    for 开 in ("均线", "不加"):
                        for nm, 过, 比 in 配置: rows += [dict(r, 开关=开, 过滤=nm, 名单年=y) for r in 跑(s, X, D, 开, 过, 比, 年=y)]
            if rows: pd.DataFrame(rows).to_csv(f_out, mode="a", header=not os.path.exists(f_out), index=False)
            done |= set(批); json.dump(sorted(done), open(os.path.join(OUT, "个股_已跑.json"), "w"))
            print("批", b // 40 + 1, "/", (len(todo) + 39) // 40, flush=True)
        json.dump(名单, open(os.path.join(OUT, "个股_每年名单.json"), "w"), ensure_ascii=False)
    print("DONE")
