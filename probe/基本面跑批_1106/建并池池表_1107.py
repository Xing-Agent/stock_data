# -*- coding: utf-8 -*-
"""
★★★ 重建「并池」池表（大/中/小 口径用）—— ★ 原池表里**没有考卷那批**。

★ 三秒版：`pool_NEWPOOL_ALL_1106.csv` 是老池（2,807 只）建的，AAPL / MSFT / JPM 都不在里面。
  ★★ 拿它给并池做「大+中」口径，会把并回来的巨头**整批筛掉** —— 并池等于没并。

★★ 规则（★ 反推原表、逐只核过，不是猜）：
  每年基准日 = 原表同一天（每年第一个交易日）；
  排名依据 = **基准日之前 60 个交易日**（不含当天）的日均成交额（面板 dollar_volume）；
  ★ 实测 NVDA 2016/2017、XOM 2015 三个点和原表**到美元一致**。
  rank ≤ 500 → 大；501~2000 → 中；其余 → 小（★ pool_scope 以 rank 为准，≤ 2000 = 大+中）。

★★★ 唯一的口径差（③我们的，写明）：
  考卷那批数据 **2016-01-04 才开始** → 2016 基准日之前没有 60 天 →
  ★ 原规则下它们 2016 年**排不上名**（等于 2016 年巨头又不在池里）。
  → ★ 只对「基准日前不足 60 根」的票，改用**基准日起的前 60 个交易日**排名（往后看了约三个月的成交额）。
  ★★ 这只影响「属于哪个流动性档」，不进任何买卖信号；★ 每只都标在 `adv_window` 列里。

★ 自证：老池那批票用本规则重算，和原表逐年对 rank ≤ 2000 的归属 —— 结果写进报告。
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
PANEL = "probe/并池_1107/ohlcv_panel_newpool.parquet"
OLD = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
OUT = os.path.join(HERE, "pool_并池3834_1107.csv")
REP = os.path.join(HERE, "pool_并池3834_报告_1107.json")


def 建(dv: pd.DataFrame, base_dates: dict, 允许往后看: bool) -> pd.DataFrame:
    rows = []
    idx = dv.index
    for yr, bd in base_dates.items():
        i = idx.get_loc(pd.Timestamp(bd))
        前 = dv.iloc[max(0, i - 60):i]
        adv = 前.mean().where(前.notna().sum() >= 60)          # ★ 原规则:满 60 根
        how = pd.Series("前60日", index=dv.columns)
        if 允许往后看:
            后 = dv.iloc[i:i + 60]
            fill = 后.mean().where(后.notna().sum() >= 60)
            need = adv.isna() & (前.notna().sum() == 0) & fill.notna()   # ★ 只补「之前一根都没有」的
            adv = adv.where(~need, fill)
            how = how.where(~need, "★基准日起60日(往后看)")
        adv = adv.dropna()
        r = adv.rank(ascending=False, method="first").astype(int)
        for s in adv.index:
            k = int(r[s])
            rows.append({"year": int(yr), "base_date": bd, "rank": k,
                         "tier": "大" if k <= 500 else ("中" if k <= 2000 else "小"),
                         "symbol": s, "avg_dollar_volume_60d": float(adv[s]),
                         "dollar_vol_price": "close", "adv_window": how[s]})
    return pd.DataFrame(rows).sort_values(["year", "rank"]).reset_index(drop=True)


def main():
    w = pd.read_parquet(PANEL)
    dv = w["dollar_volume"]
    del w
    old = pd.read_csv(OLD)
    bds = old.groupby("year")["base_date"].first().to_dict()
    old_syms = set(old["symbol"])
    # ★★★ 自证:老池那批票,原规则(不往后看),和原表对 rank ≤ 2000 归属
    chk = 建(dv[[c for c in dv.columns if c in old_syms]], bds, False)
    a = set(zip(old.year, old.symbol, old["rank"] <= 2000))
    b = set(zip(chk.year, chk.symbol, chk["rank"] <= 2000))
    oa = old[old["rank"] <= 2000]; ob = chk[chk["rank"] <= 2000]
    sa, sb = set(zip(oa.year, oa.symbol)), set(zip(ob.year, ob.symbol))
    自证 = {"原表大+中行数": len(sa), "重算大+中行数": len(sb),
          "★两边都在": len(sa & sb), "★只在原表": len(sa - sb), "★只在重算": len(sb - sa),
          "只在原表样例": sorted(sa - sb)[:10], "只在重算样例": sorted(sb - sa)[:10],
          "rank 完全相同的行占比pct": round(100 * len(a & b) / max(1, len(a)), 2)}
    new = 建(dv, bds, True)
    new.to_csv(OUT, index=False)
    inm = new[new["rank"] <= 2000]
    巨头 = {t: inm[inm.symbol == t][["year", "tier"]].values.tolist()
          for t in ("AAPL", "MSFT", "AMZN", "JPM", "BRK.B", "NVDA")}
    rep = {"★口径": __doc__.strip()[:1800], "自证(老池票·原规则 vs 原表)": 自证,
           "并池表": {"行数": len(new), "只数": int(new.symbol.nunique()),
                    "每年大+中只数": inm.groupby("year").size().to_dict(),
                    "★往后看补排的行": int((new.adv_window != "前60日").sum()),
                    "★往后看补排的年份": new[new.adv_window != "前60日"].year.value_counts().to_dict()},
           "★巨头在不在(年,档)": 巨头}
    io.open(REP, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({k: v for k, v in rep.items() if k != "★口径"}, ensure_ascii=False, indent=1,
                     default=str)[:3000])


if __name__ == "__main__":
    main()
