# -*- coding: utf-8 -*-
"""《511》第 2 件：币和科技股是不是一起跌。BTC、ETH（币日线，7×24，按美股交易日对齐）；QQQ、SPY（日线，折算含分红那份 M4.美股日线）、SOXX（SC.soxx()）。
重叠只有 2017-01 ~ 2021-12（美股 2022 年以后封存）。日收益：只取两边都有收盘的美股交易日，币取当天美东 16:00 前最后一根日线收盘的近似 = 同一个日历日的收盘（币日线按 UTC 切，差几小时，写明）。
周收益：按自然周（周五收盘）算。"""
import os, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
起, 止 = "2017-01-01", "2021-12-31"
C = {}
for s in ("BTC", "ETH"): C[s] = M4.币日线(s).close
for s in ("QQQ", "SPY"): C[s] = M4.美股日线(s).close
C["SOXX"] = SC.soxx().close
for k in C: C[k] = C[k].copy(); C[k].index = pd.to_datetime(C[k].index).tz_localize(None) if getattr(C[k].index, "tz", None) is not None else pd.to_datetime(C[k].index); C[k] = C[k].loc[起:止]
美 = C["QQQ"].index
D = pd.DataFrame({k: v.reindex(美) if k in ("BTC", "ETH") else v.reindex(美) for k, v in C.items()}).dropna()
日 = D.pct_change().dropna(); 周 = D.resample("W-FRI").last().pct_change().dropna()
R = {}; pd.set_option("display.width", 250)
pairs = [("BTC", "QQQ"), ("BTC", "SOXX"), ("BTC", "SPY"), ("ETH", "QQQ"), ("ETH", "SOXX"), ("QQQ", "SOXX")]
rows = []
for a, b in pairs:
    r = dict(对=f"{a}–{b}", 日_全段=round(日[a].corr(日[b]), 2), 周_全段=round(周[a].corr(周[b]), 2))
    for y in range(2017, 2022): r[f"周_{y}"] = round(周.loc[str(y), a].corr(周.loc[str(y), b]), 2); r[f"日_{y}"] = round(日.loc[str(y), a].corr(日.loc[str(y), b]), 2)
    rows.append(r)
A = pd.DataFrame(rows); print(A.to_string(index=False)); R["相关"] = A.to_dict("records")
rows = []
for 主, 阈, 看 in (("QQQ", -0.05, ["BTC", "ETH", "SOXX"]), ("QQQ", -0.04, ["BTC", "ETH"]), ("QQQ", -0.06, ["BTC", "ETH"]), ("SOXX", -0.07, ["BTC", "ETH"]), ("BTC", -0.15, ["QQQ", "SOXX", "SPY"]), ("BTC", -0.12, ["QQQ", "SOXX"]), ("BTC", -0.20, ["QQQ", "SOXX"])):
    w = 周[周[主] <= 阈]
    for x in 看:
        rows.append(dict(大跌的=f"{主} 单周跌 ≥{-阈:.0%}", 周数=len(w), 看=x, 同周平均=f"{w[x].mean():+.1%}", 同周也跌的占比=f"{(w[x] < 0).mean():.0%}", 同周中位=f"{w[x].median():+.1%}", 平常一周平均=f"{周[x].mean():+.1%}",
                         哪几周=" ".join(f"{d.date()}({w.loc[d, 主]:+.0%}/{w.loc[d, x]:+.0%})" for d in w.index) if len(w) <= 12 else ""))
B = pd.DataFrame(rows); print(B.drop(columns="哪几周").to_string(index=False)); print(B[B.看.isin(["BTC", "QQQ"])][["大跌的", "看", "哪几周"]].to_string(index=False)); R["大跌周"] = B.to_dict("records")
rows = []
for nm, a, b in (("2018 全年", "2018-01-01", "2018-12-31"), ("2018 年 10~12 月美股大跌", "2018-10-01", "2018-12-24"), ("2020 年 2-19 ~ 3-23", "2020-02-19", "2020-03-23"), ("2020 年 3-12 那一周", "2020-03-06", "2020-03-13")):
    x = D.loc[a:b]; r = dict(段=nm, 天数=len(x))
    for k in D.columns:
        r[k] = f"{x[k].iloc[-1] / x[k].iloc[0] - 1:+.0%}"; r[k + "最深"] = f"{(x[k] / x[k].cummax() - 1).min():.0%}"
    r["这段日相关 BTC–QQQ"] = round(日.loc[a:b, "BTC"].corr(日.loc[a:b, "QQQ"]), 2); rows.append(r)
S = pd.DataFrame(rows); print(S.to_string(index=False)); R["两段"] = S.to_dict("records")
json.dump(R, open(os.path.join(HERE, "out", "币和科技股.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
