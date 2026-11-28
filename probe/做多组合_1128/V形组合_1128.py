# -*- coding: utf-8 -*-
"""《533》第三批后半 · 做多组合「V 形反转一套」。引擎外，日线。品种、流动性池、时间同 做多组合_1128.py。
大方向 + 等待区 = 《491》的 V 形事件（《465》第 2 条转涨触发；个股跌幅门槛 20%，另试 8%、4 倍 ATR）发生后、离最低点 60 根以内；
扳机 = 《491》进场 ②：前 8 天盘涨（拍板四条）后出第一根小阴线或十字星，次日突破它的最高 + 0.1 ATR 进；止损 = min(那根最低, EMA10) − 0.4 ATR。
盈亏比够：第一目标 = L + 0.618 ×（H − L）（我定的），到它 ≥ 1.3 倍风险才做（另试 1.0、1.5）；第二目标 = 大跌起点 H。
出场：到第一目标平一半、止损移到成本，剩下到第二目标或拿满 60 天。
随机对照：同一批 V 形事件，在触发后到离最低点 60 根以内的 K 线里随机挑同样多笔，在那根收盘进；
  止损 = min(近 5 天最低, EMA10) − 0.4 ATR，目标、出场同一套，不看扳机、不看盈亏比；1,000 次。扣大盘同前。"""
import os, sys, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
Z = mod("Z", os.path.join(HERE, "做多组合_1128.py")); V = mod("V", os.path.join(ROOT, "probe/V形做多_1127/V形阶梯_1127.py"))
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); FEE = 0.0005


def 跑段(seg, 门槛="20%", 比=1.3, P=None, Mk=None):
    idx = P["close"].index; S = M4.美股日线("SPY")["close"].reindex(idx).ffill().to_numpy(); trades, cands = [], []
    for sym in P["close"].columns:
        D = pd.DataFrame({k: P[k][sym] for k in ("open", "high", "low", "close")}).dropna(subset=["close"])
        if len(D) < 300: continue
        ok = Mk[sym].reindex(D.index).fillna(False).to_numpy(); o, h, l, c = (D[k].to_numpy(float) for k in ("open", "high", "low", "close"))
        _, _, _, atr, e10, _ = V.指标(D); pos = idx.get_indexer(D.index)
        for ev in V.事件(D, 门槛):
            t, j0, H, L = ev["t"], ev["j0"], ev["H"], ev["L"]
            if not ok[t]: continue
            T1, T2 = L + 0.618 * (H - L), H
            r = V.进场们(D, ev)
            if "②" in r:
                ei, E, St, _ = r["②"]
                if E - St > 0 and T1 > E and (T1 - E) / (E - St) >= 比:
                    R_, j = Z.走(o, h, l, c, ei, E, St, T1, T2, 60)
                    trades.append(dict(sym=sym, 日=D.index[ei], R=R_ - 2 * FEE * E / (E - St), 收益pct=R_ * (E - St) / E * 100 - 0.1, 大盘pct=(S[pos[j]] / S[pos[ei]] - 1) * 100))
            for q in range(t, min(j0 + 60, len(c) - 1)):
                E = c[q]; St = min(l[max(0, q - 4):q + 1].min(), e10[q]) - 0.4 * atr[q]
                if E - St <= 0 or T1 <= E: continue
                R_, j = Z.走(o, h, l, c, q, E, St, T1, T2, 60); cands.append((R_ - 2 * FEE * E / (E - St), R_ * (E - St) / E * 100 - 0.1, (S[pos[j]] / S[pos[q]] - 1) * 100))
    return pd.DataFrame(trades), np.array(cands)


if __name__ == "__main__":
    rng = np.random.default_rng(5332); rows = []
    for seg in (sys.argv[1:] or ["一", "二"]):
        P = Z.面板(seg); Mk = Z.流动(P, "2015-01-01" if seg == "一" else "2005-01-01")
        for nm, kw in (("默认", {}), ("跌幅8%", {"门槛": "8%"}), ("跌幅4倍ATR", {"门槛": "4ATR"}), ("盈亏比1.0", {"比": 1.0}), ("盈亏比1.5", {"比": 1.5})):
            T, C = 跑段(seg, P=P, Mk=Mk, **kw)
            if len(C): C = C[np.isfinite(C).all(axis=1)]
            if len(T): T = T[np.isfinite(T.R)]
            n = len(T); 段 = "2015-2021" if seg == "一" else "2005-2014"
            if n == 0 or len(C) == 0: rows.append(dict(段=段, 参数=nm, 笔数=n, 随机候选=len(C))); print(rows[-1], flush=True); continue
            随 = np.array([C[rng.choice(len(C), n, replace=True), 0].mean() for _ in range(1000)]); w = T.R[T.R > 0].sum(); lo = -T.R[T.R < 0].sum()
            rows.append(dict(段=段, 参数=nm, 笔数=n, 每笔R=round(T.R.mean(), 3), 赚钱=round((T.R > 0).mean() * 100, 1), 利润因子=round(w / lo, 2) if lo else None, 最深一笔R=round(T.R.min(), 2),
                             每笔收益pct=round(T.收益pct.mean(), 2), 同期大盘pct=round(T.大盘pct.mean(), 2), 扣大盘后pct=round((T.收益pct - T.大盘pct).mean(), 2), 随机候选=len(C),
                             随机中位R=round(float(np.median(随)), 3), 随机95分位R=round(float(np.percentile(随, 95)), 3), 排在随机第几分位=round(float((随 < T.R.mean()).mean() * 100), 1), 随机扣大盘后pct=round(float((C[:, 1] - C[:, 2]).mean()), 2)))
            T.to_csv(os.path.join(OUT, f"V形_{seg}_{nm}.csv"), index=False); print(rows[-1], flush=True)
        del P, Mk
    pd.DataFrame(rows).to_csv(os.path.join(OUT, f"V形汇总_{''.join(sys.argv[1:]) or '全'}.csv"), index=False); print("DONE")
