# -*- coding: utf-8 -*-
"""跌势中的大阳线：第二天收不住是不是死猫跳（测试单 1125）。引擎外脚本，只读数据。
用法：python3 消息大阳线_1125.py            # 默认参数，写 out/
     python3 消息大阳线_1125.py scan       # 相邻三点敏感度
2022-01-01 之后的事件照《422 拍板》单独存 out/封存段_不看.csv，不打印、不进统计。"""
import os, sys, glob, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
ETF = "QQQ SPY IWM DIA SMH KRE XLB XLC XLE XLF XLI XLK XLP XLRE XLU XLV XLY".split()
封存起 = pd.Timestamp("2022-01-01")

def 读etf(s):
    p = "market_ext_1105/SOXX_1123/日线/SOXX_日线.csv" if s == "SOXX" else f"market_ext_1105/ETF和币_1120/日线/{s}_日线.csv"
    y = pd.read_csv(os.path.join(ROOT, p), parse_dates=["date"]).set_index("date")
    return pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna()
def 读币(s):
    sp = importlib.util.spec_from_file_location("w", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py"))
    fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/币_小时线_Coinbase/*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs]); d = d[d.symbol == s]; d["t"] = pd.to_datetime(d.time_utc, utc=True); d = d.set_index("t").sort_index()
    n = d.resample("1D").size()
    D = d.resample("1D").agg({"open_adj": "first", "high_adj": "max", "low_adj": "min", "close_adj": "last", "volume_adj": "sum"}).dropna(); D.columns = ["open", "high", "low", "close", "volume"]
    D = D[n.reindex(D.index) >= 20]; D.index = D.index.tz_localize(None); return D

def 找(D, sym, 倍=2.5, 固定=0.03, 量倍=1.5, 跌=0.08, 实体="含跳空"):
    """返回 (事件表, 基准表)。第 0 天 = 大阳线；跌势在第 -1 天收盘判。"""
    c, o, h, l, v = [D[k].values for k in ["close", "open", "high", "low", "volume"]]; n = len(c)
    r = np.r_[np.nan, c[1:] / c[:-1] - 1]
    S = pd.Series
    ma50 = S(c).rolling(50).mean().values
    absr = S(np.abs(r)).rolling(20).mean().shift(1).values          # 前 20 天平均单日涨跌幅（不含当天）
    v20 = S(v).rolling(20).mean().shift(1).values
    hh20 = S(h).rolling(20).max().values
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]])))
    atr = S(tr).rolling(20).mean().values
    ll20 = S(l).rolling(20).min().values
    跌势 = np.zeros(n, bool)
    for i in range(60, n):
        跌势[i] = c[i] < ma50[i] and ma50[i] < ma50[i - 10] and c[i] / hh20[i] - 1 <= -跌
    ev, base = [], []
    def 往后(i, k): return c[i + k] / c[i] - 1 if i + k < n else np.nan
    for i in range(61, n - 1):
        if 跌势[i]:
            base.append(dict(sym=sym, date=D.index[i], f5=往后(i, 5), f10=往后(i, 10), f20=往后(i, 20)))
        if not 跌势[i - 1]: continue
        if not ((r[i] >= 倍 * absr[i] or r[i] >= 固定) and v[i] > 量倍 * v20[i] and r[i] > 0): continue
        底 = c[i - 1] if 实体 == "含跳空" else o[i]
        if c[i] <= 底: continue
        mid = (底 + c[i]) / 2; j = i + 1
        组 = "A收不住" if c[j] < mid else ("B站住" if c[j] > c[i] else "C中间")
        # 底部横盘：前 15 天高低差 < 1.5×ATR，且这 15 天的最低没有低过更早 45 天的最低
        a, b = i - 15, i
        rng = h[a:b].max() - l[a:b].min()
        横盘 = bool(rng < 1.5 * atr[i - 1] and l[a:b].min() >= l[max(0, a - 45):a].min())
        横盘宽 = bool(rng < 3.0 * atr[i - 1] and l[a:b].min() >= l[max(0, a - 45):a].min())
        e = dict(sym=sym, date=D.index[i], 涨幅=r[i], 组=组, 横盘=横盘, 横盘宽=横盘宽,
                 f5=往后(j, 5), f10=往后(j, 10), f20=往后(j, 20),
                 破低10=np.nan, 过高10=np.nan, R=np.nan, 出场="", 持有=np.nan, 风险pct=np.nan)
        if j + 10 < n:
            e["破低10"] = bool(l[j + 1:j + 11].min() < l[i]); e["过高10"] = bool(h[j + 1:j + 11].max() > h[i])
        # 做空写法：第 2 天开盘空；止损 = 大阳线最高 + 0.5ATR；目标 = 大阳线前 20 天最低；最长 10 天
        k = j + 1
        if k < n:
            ent = o[k]; stp = h[i] + 0.5 * atr[i]; tgt = ll20[i - 1]
            if stp > ent and tgt < ent:
                ex, why, kk = None, "", k
                for kk in range(k, min(k + 10, n)):
                    if o[kk] >= stp and kk > k: ex, why = o[kk], "止损(跳空)"; break
                    if h[kk] >= stp: ex, why = stp, "止损"; break
                    if o[kk] <= tgt and kk > k: ex, why = o[kk], "目标(跳空)"; break
                    if l[kk] <= tgt: ex, why = tgt, "目标"; break
                if ex is None: ex, why = c[kk], "到期"
                e.update(R=(ent - ex) / (stp - ent), 出场=why, 持有=kk - k + 1, 风险pct=(stp - ent) / ent, 进=ent, 出=ex)
            else: e["出场"] = "不成立(目标不在下方)"
        ev.append(e)
    return pd.DataFrame(ev), pd.DataFrame(base)

def 全部(**kw):
    E, B = [], []
    for s in ETF + ["SOXX"]:
        e, b = 找(读etf(s), s, **kw); e["类"] = b["类"] = "ETF"; E.append(e); B.append(b)
    kw2 = dict(kw); kw2["固定"] = kw.get("固定币", 0.05); kw2.pop("固定币", None); kw.pop("固定币", None)
    for s in ["BTC", "ETH"]:
        e, b = 找(读币(s), s, **kw2); e["类"] = b["类"] = "币"; E.append(e); B.append(b)
    return pd.concat(E, ignore_index=True), pd.concat(B, ignore_index=True)

def 段(d):
    if d >= 封存起: return "封存"
    return "2005-2014" if d < pd.Timestamp("2015-01-01") else "2015-2021"
def 熊(d): return pd.Timestamp("2007-10-01") <= d <= pd.Timestamp("2009-03-31")
def q(x): 
    x = x.dropna()
    return dict(笔=len(x), 中位=x.median(), 下四分=x.quantile(.25), 上四分=x.quantile(.75), 跌的比例=(x < 0).mean()) if len(x) else dict(笔=0)
def 做空统计(t, 成本):
    t = t.dropna(subset=["R"]).sort_values("date")
    if not len(t): return dict(笔=0)
    R = t.R - 成本 / t.风险pct
    cum = R.cumsum(); dd = (cum - cum.cummax()).min()
    return dict(笔=len(R), 胜率=(R > 0).mean(), 每笔R=R.mean(), 利润因子=R[R > 0].sum() / max(1e-9, -R[R <= 0].sum()), 最深回撤R=dd, 合计R=R.sum())

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "scan":
        rows = []
        for nm, vals in [("倍", [2.0, 2.5, 3.0]), ("量倍", [1.2, 1.5, 2.0]), ("跌", [0.06, 0.08, 0.10]), ("实体", ["含跳空", "只算开收"])]:
            for x in vals:
                E, B = 全部(**{nm: x}); E = E[(E.date < 封存起) & (E.date >= "2005-01-01") & (E.类 == "ETF")]
                A, Bb = E[E.组 == "A收不住"], E[E.组 == "B站住"]
                rows.append(dict(参数=nm, 值=x, A笔=len(A), B笔=len(Bb), A_10天中位=A.f10.median(), B_10天中位=Bb.f10.median(),
                                 A_20天中位=A.f20.median(), B_20天中位=Bb.f20.median(), A破低10=A.破低10.mean(), A过高10=A.过高10.mean(),
                                 A做空每笔R=做空统计(A, 0.001).get("每笔R")))
        pd.DataFrame(rows).to_csv(os.path.join(OUT, "敏感度_相邻三点.csv"), index=False); print(pd.DataFrame(rows).round(4).to_string()); sys.exit()
    E, B = 全部()
    E["段"] = E.date.map(段); B["段"] = B.date.map(段); E["熊2008"] = E.date.map(熊); B["熊2008"] = B.date.map(熊)
    E[E.段 == "封存"].to_csv(os.path.join(OUT, "封存段_不看.csv"), index=False)
    E = E[(E.段 != "封存") & (E.date >= "2005-01-01")]; B = B[(B.段 != "封存") & (B.date >= "2005-01-01")]
    E.to_csv(os.path.join(OUT, "逐笔.csv"), index=False)
    rows = []
    def 一组(tag, e, b):
        for g in ["A收不住", "B站住", "C中间"]:
            x = e[e.组 == g]
            d = dict(范围=tag, 组=g, 笔=len(x), 不同日子=x.date.nunique())
            for k in ["f5", "f10", "f20"]:
                s = q(x[k]); d[k + "中位"] = s.get("中位"); d[k + "下四分"] = s.get("下四分"); d[k + "上四分"] = s.get("上四分"); d[k + "跌比"] = s.get("跌的比例")
            d["10天内破大阳线最低"] = x.破低10.dropna().astype(float).mean(); d["10天内过大阳线最高"] = x.过高10.dropna().astype(float).mean()
            d["20天后是涨的"] = (x.f20.dropna() > 0).mean()
            for nm, cst in [("扣前", 0.0), ("扣后", None)]:
                c = 0.0 if cst == 0.0 else (0.002 if tag.startswith("币") else 0.001)
                s = 做空统计(x, c)
                for kk in ["笔", "胜率", "每笔R", "利润因子", "最深回撤R"]: d[f"空_{nm}_{kk}"] = s.get(kk)
            rows.append(d)
        d = dict(范围=tag, 组="基准·跌势里任意一天", 笔=len(b), 不同日子=b.date.nunique())
        for k in ["f5", "f10", "f20"]:
            s = q(b[k]); d[k + "中位"] = s.get("中位"); d[k + "下四分"] = s.get("下四分"); d[k + "上四分"] = s.get("上四分"); d[k + "跌比"] = s.get("跌的比例")
        d["20天后是涨的"] = (b.f20.dropna() > 0).mean(); rows.append(d)
    for 类 in ["ETF", "币"]:
        e, b = E[E.类 == 类], B[B.类 == 类]
        一组(f"{类}·全部(2005-2021)", e, b)
        for p in ["2005-2014", "2015-2021"]: 一组(f"{类}·{p}", e[e.段 == p], b[b.段 == p])
        if 类 == "ETF":
            一组("ETF·2008熊市(2007-10~2009-03)", e[e.熊2008], b[b.熊2008]); 一组("ETF·去掉2008熊市", e[~e.熊2008], b[~b.熊2008])
            一组("ETF·四大(QQQ SPY IWM SOXX)", e[e.sym.isin(["QQQ", "SPY", "IWM", "SOXX"])], b[b.sym.isin(["QQQ", "SPY", "IWM", "SOXX"])])
            一组("ETF·底部横盘(1.5ATR)", e[e.横盘], b); 一组("ETF·底部横盘(放宽3ATR)", e[e.横盘宽], b)
    T = pd.DataFrame(rows); T.to_csv(os.path.join(OUT, "汇总.csv"), index=False)
    pd.set_option("display.width", 250)
    print(T[["范围", "组", "笔", "不同日子", "f5中位", "f10中位", "f20中位", "f10跌比", "10天内破大阳线最低", "10天内过大阳线最高", "20天后是涨的"]].round(3).to_string())
    print(T[T.组 != "基准·跌势里任意一天"][["范围", "组", "空_扣前_笔", "空_扣前_胜率", "空_扣前_每笔R", "空_扣前_利润因子", "空_扣后_每笔R", "空_扣后_利润因子", "空_扣后_最深回撤R"]].round(3).to_string())
    print(E.groupby(E.date.dt.year).size().to_string())
