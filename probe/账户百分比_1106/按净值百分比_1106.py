# -*- coding: utf-8 -*-
"""
★★★ 把「赢亏比 / 利润因子 / 每笔期望」改成**账户百分比**口径。

★★ 来历:**Lin 1106 17:20 自己拍板的** ——
  「说明书和产品里给用户看的赢亏比、利润因子、每笔期望,
    一律按『这一笔让账户涨跌了百分之几』来算。内部研发照旧看 R。」
★ 分母用**进场时**的账户净值(★★ 不用平仓时的):
  这笔的风险是按进场时的净值定的,★★★ 分母要和它对上。

★★★ 账户净值怎么来的:流水里**没有存**,所以**逐日重建**(不是估算):
   净值(t) = 初始 100 万
            + 平仓日 < t 的那些笔的累计 net_pnl        ← ★ 流水里有
            + 持仓中那些笔的浮动盈亏(按 t 日收盘价)   ← ★★ 流水 shares/entry_price × 面板收盘
   ★ 只差分红和摩擦落账的时点,量级极小(已在报告里写明)。

★ engine 零改动。
"""
import os, sys, json, glob
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)

EQ0 = 1_000_000.0
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = "probe/账户百分比_1106"
_CLOSE = None


def 收盘面板(syms=None):
    """★★★ 1106 修:原来写 `columns=[("close", 代码)]` —— ★★ 这版 pyarrow **不认元组列名**
       (报 TypeError: expected bytes, tuple found),★ 结果 21 条臂全报跑失败。
       ★★★ 这是今天**第四次猜接口用法** —— 已登记。
       ★ 改成整张读一次再切 close(约 400MB,内存够),★★ 只读一次缓存住。"""
    global _CLOSE
    if _CLOSE is None:
        p = pd.read_parquet(PANEL)
        _CLOSE = p["close"]
        del p
    return _CLOSE


def 逐日净值(d: pd.DataFrame) -> pd.Series:
    """★★★ 重建逐日账户净值。"""
    cl = 收盘面板(d["symbol"].astype(str).unique())
    idx = cl.index
    # ① 已实现:按平仓日累加
    实现 = pd.Series(0.0, index=idx)
    g = d.dropna(subset=["exit_date"]).groupby("exit_date")["net_pnl"].sum()
    for t, v in g.items():
        if t in 实现.index:
            实现.loc[t] += float(v)
    实现 = 实现.cumsum()
    # ② 未实现:逐笔在持仓区间内按收盘价算浮盈
    浮 = pd.Series(0.0, index=idx)
    for _, r in d.iterrows():
        s = str(r["symbol"])
        if s not in cl.columns:
            continue
        a, b = r["entry_date"], r["exit_date"]
        if pd.isna(a):
            continue
        b = b if pd.notna(b) else idx[-1]
        # ★★★ 1106 修:原来没 dropna —— ★★ 某只票某天缺价格(NaN),
        #   相加之后**整条净值曲线那一天变成 NaN** → ★★★ 那天进场的笔分母全废。
        #   ★ 实测后果:融-3 lookback=60 有 1,108 / 1,713 笔(65%)算不出。
        #   ★★ 只用**有价格的那些天**;★★★ **不用 0 填**(填 0 等于假装那天没涨没跌)。
        seg = cl[s].loc[(cl.index >= a) & (cl.index < b)].dropna()
        if seg.empty:
            continue
        浮.loc[seg.index] += (seg - float(r["entry_price"])) * float(r["shares"])
    eq = (EQ0 + 实现.shift(1).fillna(0.0) + 浮).rename("净值")
    # ★★★ 规矩⑯:算不出要大声报,不许静悄悄
    if eq.isna().any():
        print(f"   ⚠ 净值曲线里仍有 {int(eq.isna().sum())} 天是 NaN —— 查!", flush=True)
    return eq


def 一条(f: str):
    d = pd.read_csv(f)
    if d.empty:
        return None
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("net_pnl", "shares", "entry_price", "r_multiple_net"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
    if d.empty:
        return None
    eq = 逐日净值(d)
    分母 = eq.reindex(d["entry_date"]).to_numpy()
    算得出 = np.isfinite(分母) & (分母 > 0)
    pct = pd.Series(np.where(算得出, d["net_pnl"].to_numpy() / 分母 * 100.0, np.nan),
                    index=d.index).dropna()
    if pct.empty:
        return None
    赢, 亏 = pct[pct > 0], pct[pct < 0]
    out = {
        "①笔数": int(len(pct)),
        "★算不出笔数": int(len(d) - len(pct)),
        "②胜率": round(float((pct > 0).mean()), 4),
        "③每笔期望_占净值pct": round(float(pct.mean()), 4),
        "④赢亏比_按净值pct": (round(float(赢.mean() / abs(亏.mean())), 3)
                          if len(赢) and len(亏) else None),
        "⑤利润因子_按净值pct": (round(float(赢.sum() / abs(亏.sum())), 3)
                           if len(亏) and 亏.sum() != 0 else None),
        "★平均赢_占净值pct": (round(float(赢.mean()), 4) if len(赢) else None),
        "★平均亏_占净值pct": (round(float(亏.mean()), 4) if len(亏) else None),
        "★★净值区间": [round(float(eq.min()), 0), round(float(eq.max()), 0)],
        "★★★对比_每笔净R平均": round(float(d["r_multiple_net"].mean()), 4),
    }
    pf = out["⑤利润因子_按净值pct"]
    out["★★★读法"] = ("★★★ 利润因子 < 1 → **这条策略在亏**" if (pf is not None and pf < 1)
                   else ("★ 利润因子 ≥ 1 → 赚的那部分盖得住亏的" if pf is not None
                         else "★ 算不出"))
    return out


def main() -> int:
    报 = {"★口径": {
        "谁定的": "★★ Lin 1106 17:20 拍板:给用户看的一律按「这一笔让账户涨跌了百分之几」",
        "分母": "★★★ **进场时**的账户净值（不用平仓时的 —— 风险是按进场时的净值定的）",
        "净值怎么来的": "★★ 流水里没存 → 逐日**重建**：100 万 + 已平仓累计 net_pnl "
                   "+ 持仓中按当日收盘价的浮动盈亏",
        "★已知偏差": "★ 只差分红与摩擦落账的时点，量级极小；★★ 不是估算，是重建",
        "内部研发": "★ 照旧看 R —— 这一份只管**给用户看的**那几个数",
        "初始本金": EQ0,
    }}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            r = 一条(f)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
        if r:
            报[名] = r
            print("✓", 名, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "按净值百分比_报告_1106.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print("★ 写到", os.path.join(OUT, "按净值百分比_报告_1106.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
