# -*- coding: utf-8 -*-
"""
★★★★★ 规矩④ 自查：**我这一轮算出的「赛道年化 10.57%」是不是偏低？**

★★★ 为什么必须查（★ 这是「让我们好看」的方向，按规矩先当自己错了）：
   ★ 技术面策略的 `universe` 段只有流动性/市值闸，**不挑股** →
     ★★ 实测赛道成员中位 **1,417 只**，几乎就是整个大中研发池；
   ★★★ 可是《107》量过「**等权同池买入持有年化 19.251%**」—— 两个数差 **8~9 个百分点**。
   → ★★★★★ 如果我的赛道线被系统性压低了，那「对赛道的 alpha」就会被系统性抬高 = 我们好看。

★★ 四个候选原因，本份逐个量开（★ 全部在同一个面板、同一个大中闸上）：
   ① **窗口**：我用 2018-01-01→2025-12-31（新尺子 PERF0/PERF1），《107》那个数是别的窗口
   ② **每天等权再平衡 vs 第一天买下来不动** —— ★★★ 这两个不是同一个东西
   ③ **剔脏日**（四份并集）剔掉的格子
   ④ **大中闸**（large_mid）vs 全池
"""
from __future__ import annotations
import importlib.util, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
for d in ("probe/v2_rerun_1030", "probe/分档单调_1107", "probe/假跳变_1107",
          "probe/剔脏日重出_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))
import rerun_core_1030 as RC          # noqa: E402
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "自查_赛道年化_1107.json")
_s = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_s); _s.loader.exec_module(M)


def 年化(eq: pd.Series) -> float | None:
    e = eq.dropna()
    if len(e) < 2:
        return None
    y = (e.index[-1] - e.index[0]).days / 365.25
    return round(float(e.iloc[-1] / e.iloc[0]) ** (1 / y) * 100 - 100, 3) if y > 0 else None


def 每天等权(r: pd.DataFrame, u: pd.DataFrame, 下限: int = 20):
    masked = r.where(u)
    n = masked.notna().sum(axis=1)
    够 = n >= 下限
    d = masked.mean(axis=1, skipna=True).where(够)
    return (1.0 + d.dropna()).cumprod(), int(够.sum()), int(len(n))


def 买下来不动(cl: pd.DataFrame, u: pd.DataFrame):
    """★★★ 第一天把当天合格的票等权买下来，**一直不动**（★ 退市/停更的票按最后一个有价日结算后持现）。
       ★★ 这是 Lin 原话里那个「只买不动」的字面意思 —— ★ 和每天再平衡**不是同一个东西**。"""
    第一天 = u.index[0]
    成员 = [c for c in u.columns if bool(u.loc[第一天, c])]
    px = cl[成员]
    起 = px.loc[第一天]
    ok = 起.notna() & (起 > 0)
    成员 = [c for c in 成员 if ok.get(c, False)]
    px = px[成员]
    if not 成员:
        # ★★★ 规矩⑯：第一天一个合格成员都没有 → **大声报**，不许返回一条平线
        return pd.Series(dtype=float), 0
    份 = 1.0 / len(成员)
    rel = px.div(px.loc[第一天], axis=1)
    rel = rel.ffill()                       # ★ 停更后按最后一个有价日冻住（★★ 不是归零，也不是剔掉）
    return (rel * 份).sum(axis=1), len(成员)


def main() -> int:
    w = pd.read_parquet(PANEL)
    cl, vol = w["close"], w["volume"]
    del w
    syms = [str(c) for c in cl.columns]
    大中, sdiag = RC.scope_mask(syms, cl.index, "large_mid")
    大中 = pd.DataFrame(np.asarray(大中), index=cl.index, columns=syms)
    hold = json.load(io.open("probe/新策略_1106/holdout_newpool_1106.json", encoding="utf-8"))
    dev = set(hold["研发池名单"])
    研 = pd.Series([s in dev for s in syms], index=syms)
    import 分档单调性_1107 as DEC
    脏 = DEC.脏格(cl, vol)
    del vol
    r = cl.pct_change().where(lambda x: np.isfinite(x))

    out = {"★★★这一份干什么": "★ 规矩④ 自查：赛道年化 10.57% 是不是被我压低了（压低 = 我们的 alpha 被抬高）",
           "★口径": {"面板": PANEL, "池": "新池研发池（留出 + 考卷都不碰）",
                   "大中闸": {k: v for k, v in (sdiag or {}).items() if "票日" in str(k)},
                   "脏日": "四份并集（和《93》《106》《110》同一份）"},
           "逐项": {}}

    窗 = {"新尺子窗口(2018-01-01→2025-12-31)": (M.PERF0, M.PERF1),
          "全面板窗口": (cl.index[0], cl.index[-1])}
    for 窗名, (t0, t1) in 窗.items():
        sel = (cl.index >= t0) & (cl.index <= t1)
        rr = r.loc[sel]
        for 闸名, base in (("大中闸(large_mid)", 大中.loc[sel]), ("全研发池(不加大中闸)",
                                                            pd.DataFrame(
                                                                np.tile(研.to_numpy(), (int(sel.sum()), 1)),
                                                                index=cl.index[sel], columns=syms))):
            u0 = base & pd.DataFrame(np.tile(研.to_numpy(), (int(sel.sum()), 1)),
                                     index=cl.index[sel], columns=syms)
            for 脏名, u in (("剔脏日", u0 & (~脏.loc[sel].reindex(columns=syms).fillna(False))),
                           ("不剔脏日", u0)):
                eq, 够, 总 = 每天等权(rr, u.shift(1).fillna(False))
                bh, nm = 买下来不动(cl.loc[sel], u)
                out["逐项"][f"{窗名} | {闸名} | {脏名}"] = {
                    "★★★每天等权再平衡_年化pct": 年化(eq),
                    "★★★第一天买下来不动_年化pct": 年化(bh),
                    "★差(不动 减 再平衡)pct": (None if 年化(eq) is None or 年化(bh) is None
                                        else round(年化(bh) - 年化(eq), 3)),
                    "够格天数": 够, "总天数": 总, "第一天成员数": nm,
                }
                _r = out["逐项"][f"{窗名} | {闸名} | {脏名}"]
                print(f"  {窗名[:28]:28s}|{闸名[:20]:20s}|{脏名:6s} "
                      f"再平衡 {str(_r['★★★每天等权再平衡_年化pct']):>8} "
                      f"不动 {str(_r['★★★第一天买下来不动_年化pct']):>8} "
                      f"(成员 {nm})"
                      + ("  ★★★ 第一天 0 成员 → 不动那一列算不出" if nm == 0 else ""), flush=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
