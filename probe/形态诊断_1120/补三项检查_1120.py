#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《331》补三项检查（2026-11-20 · 问 Gemini 的 chat 看过后提的）
1. 股票池里有没有退市的票（做空对「只剩活下来的票」最敏感）
2. 单独看 2022 年（这十年里唯一一段跌得久的熊市）
3. 形态之后 20 天的涨跌，减去同一只票同一年随便一天之后 20 天的涨跌
只读已有的逐笔结果和行情面板，不跑新回测。engine/ 没碰。
"""
import io, json, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import numpy as np, pandas as pd, pyarrow.parquet as pq
out = {}
meta = pd.read_parquet(os.path.join(ROOT, "probe/newpool_1106/panel_meta_newpool.parquet"))
MK = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet")); pool = [s for s in MK.columns if MK[s].any()]
m = meta.reindex(pool); 没到期末 = m[pd.to_datetime(m.last_bar) < pd.Timestamp("2025-12-01")]
X = pd.read_parquet(os.path.join(HERE, "顶部形态_逐笔_1120.parquet"))
out["一_退市"] = {"进过中档池的票": len(pool), "其中行情在2025年12月前就结束的": int(len(没到期末)), "占比pct": round(len(没到期末) / len(pool) * 100, 1),
                 "其中标了退市": int(m.delisted.fillna(False).astype(bool).sum()), "其中按0价结算的_破产类": int(m.zero_bar.notna().sum()),
                 "按结束年份": {int(k): int(v) for k, v in pd.to_datetime(没到期末.last_bar).dt.year.value_counts().sort_index().items()},
                 "结算方式": {str(k): int(v) for k, v in 没到期末.settlement_basis.fillna("").replace("", "没写").value_counts().items()}}
X["已退市的票"] = X["票"].isin(set(没到期末.index))
def st(g):
    r = g.R; return {"笔": int(len(g)), "每笔R": round(float(r.mean()), 3), "赚钱pct": round(float((r > 0).mean() * 100), 1)}
out["一_退市"]["等确认_按票分"] = {("后来退市的票" if k else "活到期末的票"): st(g) for k, g in X[X["进法"] == "等确认"].groupby("已退市的票")}
out["一_退市"]["不等确认_按票分"] = {("后来退市的票" if k else "活到期末的票"): st(g) for k, g in X[X["进法"] == "不等确认"].groupby("已退市的票")}
out["二_2022年"] = {f"{a}_{b}": {"2022年": st(g[g["年"] == 2022]), "其余年份": st(g[g["年"] != 2022])} for (a, b), g in X.groupby(["形态", "进法"])}
out["二_分年_等确认"] = {a: {int(y): {"笔": int(len(gg)), "每笔R": round(float(gg.R.mean()), 3)} for y, gg in g.groupby("年")} for a, g in X[X["进法"] == "等确认"].groupby("形态")}
# 三：普通日子的 20 天涨跌（同一只票、同一年、当天在池子里的所有日子）
_names = pq.ParquetFile(os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet")).schema_arrow.names
_want = {f"('close', '{s}')": s for s in pool}
_t = pq.read_table(os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet"), columns=[n for n in _names if n in _want] + [n for n in _names if n.startswith("__index") or n in ("date", "index")]).to_pandas()
_t.columns = [c[1] if isinstance(c, tuple) else _want.get(c, c) for c in _t.columns]
C = _t[[s for s in pool if s in _t.columns]].astype(float)
f20 = (C.shift(-20) / C - 1).reindex(MK.index).where(MK[list(C.columns)]); f20 = f20.iloc[:-61]
_b = f20.groupby(pd.DatetimeIndex(f20.index).year).mean(); _b.columns = [str(c) for c in _b.columns]; _b.insert(0, "年", [int(y) for y in _b.index]); _b = _b.reset_index(drop=True)
base = _b.melt(id_vars="年", var_name="票", value_name="普通日子后20天").dropna()
Y = X.merge(base, on=["年", "票"], how="left"); Y["超出"] = Y["后20天"] - Y["普通日子后20天"]
out["三_后20天减普通日子"] = {f"{a}_{b}": {"笔": int(len(g)), "形态后20天pct": round(float(g["后20天"].mean() * 100), 2), "同票同年普通日子pct": round(float(g["普通日子后20天"].mean() * 100), 2),
                                    "差pct": round(float(g["超出"].mean() * 100), 2), "差的中位pct": round(float(g["超出"].median() * 100), 2)} for (a, b), g in Y.groupby(["形态", "进法"])}
io.open(os.path.join(HERE, "补三项检查_结果_1120.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
print(json.dumps(out, ensure_ascii=False, indent=1))
