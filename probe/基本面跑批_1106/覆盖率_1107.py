# -*- coding: utf-8 -*-
"""
★★★ 《99》3.4 第 1、2 条:覆盖率 + 可跑率(★ 不受窗口限制,照常下结论)。

  第一部分「科目覆盖率」(--科目):并池 3,834 只里,每个原始科目有多少家在 2016~2025 有记录
      ★ 只读瘦身库,不建面板,内存很小 —— 跑批同时也能跑。
  第二部分「每条策略的可跑率」(--策略):★ 在「大+中」口径的票日上,每条策略要用的每个零件
      **算得出**的比例;★★ 再算「全部零件都算得出」的比例 = 可跑率;最拖后腿的那个 = 缺哪个科目。
      ★★★ 「算不出」(零件 NaN)和「算得出但没过闸」(分数差)**分开记**(《99》3.4 第 4 条)。
"""
from __future__ import annotations
import io, json, os, pickle, sys, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SLIM = os.path.join(HERE, "_slim_fund")

# ★ 每条策略用到的零件(★ 照 configs/ 里写的闸逐条列;派生指标括号里是它要的原始科目)
零件 = {
    "基-1_格雷厄姆防御七条": ["rev_ttm", "current_ratio", "ltd_over_nwc", "ni_pos_years", "div_years",
                        "eps3_avg_ps", "bvps"],
    "基-2_施洛斯极度分散": ["bvps", "liab_to_eq"],
    "基-3_F分数原著版": ["bvps", "f_score"],
    "基-4_神奇公式": ["roc", "ebit_ttm_ps", "netdebt_ps"],
    "基-5_德雷曼低市盈率": ["eps_ttm_ps"],
    "基-6_收购者倍数": ["ebit_ttm_ps", "netdebt_ps"],
    "基-7_早期巴菲特烟蒂": ["ncav_ps"],
    "基-8_茨威格GARP红绿灯": ["zweig_growth_ok_3", "eps_ttm_ps"],
    "基-12_回购筛选": ["net_dilution_pct", "fcf_ttm"],
    "基-16_特里史密斯": ["roce", "fcf_conv", "liab_to_eq", "fcf_per_share"],
    "基-20_价值动量双因子": ["bvps"],
}


def 科目():
    import pandas as pd
    syms = list(pd.read_parquet(os.path.join(ROOT, "probe/并池_1107/panel_meta_newpool.parquet")).index)
    有库, 计 = 0, Counter()
    for s in syms:
        p = os.path.join(SLIM, f"{s}.pkl")
        if not os.path.exists(p):
            continue
        有库 += 1
        d = pickle.load(open(p, "rb"))
        for m, rs in d.items():
            if any((r[4] or "") >= "2015-01-01" and r[5] is not None for r in rs):
                计[m] += 1
    return {"并池只数": len(syms), "★财报库里有这只": 有库,
            "★财报库里没有(代码改名/改类,见报告)": len(syms) - 有库,
            "每个科目_2015年后有记录的家数": dict(计.most_common()),
            "每个科目_占并池pct": {k: round(v / len(syms) * 100, 1) for k, v in 计.most_common()}}


def 策略():
    sys.path.insert(0, HERE)
    import 跑基本面_1107 as R            # noqa: F401  (★ 只为让面板/池表/窗口用 1107 口径)
    RC, _ = R.R0.装层()
    import numpy as np
    from engine import fundamentals as F, cache, matrices as M
    import 策略零件_1106 as MINE
    syms = list(cache._PANEL["close"].columns)
    close = cache.field("close", syms)
    mask, _ = RC.scope_mask(syms, close.index, R.R0.SCOPE)
    在 = (mask & close.notna()).loc[R.R0.PERF_START:]
    分母 = int(在.to_numpy().sum())
    单 = {}
    need = sorted({z for v in 零件.values() for z in v})
    for z in need:
        t = time.time()
        p = F.get(z, syms).reindex(index=close.index, columns=syms).loc[R.R0.PERF_START:]
        ok = p.notna() & 在
        单[z] = {"算得出pct": round(float(ok.to_numpy().sum()) / 分母 * 100, 1),
                "秒": round(time.time() - t, 1)}
        print(z, 单[z], flush=True)
        F.panel.cache_clear()
    out = {"分母(大+中口径·在场票日)": 分母, "单个零件": 单, "策略": {}}
    for s, zs in 零件.items():
        全 = None
        for z in zs:
            p = F.get(z, syms).reindex(index=close.index, columns=syms).loc[R.R0.PERF_START:]
            ok = p.notna()
            全 = ok if 全 is None else (全 & ok)
            F.panel.cache_clear()
        全 = 全 & 在
        rate = round(float(全.to_numpy().sum()) / 分母 * 100, 1)
        worst = min(zs, key=lambda z: 单[z]["算得出pct"])
        out["策略"][s] = {"★可跑率pct(全部零件算得出的票日)": rate,
                        "最拖后腿的零件": f"{worst}({单[worst]['算得出pct']}%)",
                        "零件": {z: 单[z]["算得出pct"] for z in zs}}
    return out


if __name__ == "__main__":
    os.chdir(ROOT); sys.path.insert(0, ROOT)
    rep = {}
    path = os.path.join(HERE, "覆盖率_1107.json")
    if os.path.exists(path):
        rep = json.load(io.open(path, encoding="utf-8"))
    rep["★★★池子"], rep["★★★窗口"] = "并池3834", "2016-01-04~2025-12-31"
    if "--科目" in sys.argv:
        rep["科目覆盖率"] = 科目()
    if "--策略" in sys.argv:
        rep["策略可跑率"] = 策略()
    io.open(path, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1))
    print(json.dumps({k: (v if k != "科目覆盖率" else {kk: vv for kk, vv in v.items()
                                                    if kk != "每个科目_2015年后有记录的家数"})
                      for k, v in rep.items()}, ensure_ascii=False, indent=1)[:4000])
