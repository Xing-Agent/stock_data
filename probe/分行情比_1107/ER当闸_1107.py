# -*- coding: utf-8 -*-
"""
★★★ 把 ER 当环境闸测 —— ★ 「分段有超额」能不能变成**真钱**。

★★ 来历：Lin 1107 09:16：
  「我们每个策略所谓匹配的环境，适合在什么环境？不就是让大家在这个环境下面，
    这个策略能够跑得非常好嘛……所以这是一脉相承。你所谓的比较的这个东西，
    也是我们要求的这个环境该如何去比，也是我们所谓的环境开关重要的点。」

★★★ 他指出的是：卡上的「适合环境」、分行情比那条线、环境闸那条规则 ——
  **必须是同一个定义**。而我们现在是三套。

★ 这一份回答那个关键问题：**分段 alpha ≠ 能赚到的钱。**
  要收到那份超额，你得**当天就知道今天是哪一段** → 那就是挂闸。
  ★★ 昨天测的三个闸（SPY 200日线 / VIX / 宽度）改善全部小于噪声，
  ★★★ 但**没测过 ER**。这一份补上。

★★★ ⚠ 口径声明（必须跟着任何结论一起出现）：
  这是**近似**，不是真挂闸重跑。做法是：在日收益序列上，
  **ER 低于门槛的那些天把当天收益置 0（视作清仓持现金）**。
  · ★ 它和真闸的差别：真闸会改变**开仓/平仓的时点和持仓构成**，
    这里只是把那些天的收益拿掉。
  · ★★ 方向：这个近似**对我们有利**（它假设我们能在闸关的那天
    干净地不持仓、不付摩擦、不吃隔夜缺口）→ ★★★ 所以它是**上界**。
  · ★ 真数要等周末跑批里挂 ER 闸重跑引擎。**上界不好看 = 真的也不会好。**
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
for d in ("probe/组合日收益_1106", "probe/分行情比_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))
import 组合日收益_1107 as 核                      # noqa: E402
import 分行情比_1107 as 分                        # noqa: E402
import 对口指数_1107 as 对                        # noqa: E402


def 年化(r: pd.Series) -> float:
    r = r.dropna()
    return float("nan") if len(r) < 20 else float((1 + r).prod() ** (252 / len(r)) - 1) * 100


def 回撤(r: pd.Series) -> float:
    nav = (1 + r.fillna(0)).cumprod()
    return round(float((nav / nav.cummax() - 1).min()) * 100, 2)


def 一条(p: str) -> dict:
    d = pd.read_csv(p)
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("shares", "entry_price", "net_pnl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["symbol", "entry_date", "shares", "entry_price", "net_pnl"])
    eq, 敞口, _ = 核.逐日(d)
    if eq is None:
        return {"★跑失败": "面板里没有这条臂的任何票"}
    r = eq.pct_change()
    ew_r, _ = 对.等权池()
    ew_r = ew_r.reindex(eq.index)
    g = 分.行情(eq.index)
    out = {"★平均敞口pct": round(float(敞口.mean()) * 100, 1)}

    def 报(y: pd.Series, 敞: pd.Series) -> dict:
        x = (ew_r * 敞.shift(1)).reindex(y.index)
        a = 核.回归(y.dropna(), x.reindex(y.dropna().index))
        return {"★对等权同池alpha年化pct": (None if "★算不出" in a else
                                     round(a["★★★alpha_年化pct"], 2)),
                "★t": (None if "★算不出" in a else round(a["★★alpha的t值_NeweyWest"], 2)),
                "★年化pct": round(年化(y), 2), "★最大回撤pct": 回撤(y),
                "★在场交易日": int(y.notna().sum())}

    out["①不挂ER闸_原样"] = 报(r, 敞口)
    # ★★★ 相邻三点（★ 红线②：原著没给门槛，必须跑三点并报是否同向）
    for th in (0.5, 0.6, 0.7):
        开 = (g["ER"] >= th) & g["ER"].notna()
        y = r.where(开, 0.0)                     # ★ 闸关的天 = 清仓持现金（收益 0）
        敞 = 敞口.where(开, 0.0)
        out[f"②挂ER闸≥{th}"] = 报(y, 敞)
        out[f"②挂ER闸≥{th}"]["★闸开的天数占比pct"] = round(float(开.mean()) * 100, 1)
    sg = [out[f"②挂ER闸≥{t}"]["★对等权同池alpha年化pct"] for t in (0.5, 0.6, 0.7)]
    base = out["①不挂ER闸_原样"]["★对等权同池alpha年化pct"]
    if base is not None and all(v is not None for v in sg):
        改善 = [round(v - base, 2) for v in sg]
        out["★★★三点改善"] = 改善
        out["★★三点同向"] = len({v > 0 for v in 改善}) == 1
    return out


def main() -> int:
    报 = {"★这一份做什么":
          "★★★ 把 ER 当环境闸测 —— ★ 「分段有超额」能不能变成真钱（Lin 1107 09:16）。"
          "★★ 昨天测的三个闸（SPY 200日线 / VIX / 宽度）改善全部小于噪声，但没测过 ER。",
          "★★★口径声明_必须跟着结论一起出现":
          ["这是**近似**不是真挂闸重跑：ER 低于门槛的那些天把当天收益置 0（视作清仓持现金）",
           "★ 和真闸的差别：真闸会改变开仓/平仓时点和持仓构成，这里只是把那些天的收益拿掉",
           "★★★ 方向：这个近似**对我们有利**（假设闸关那天能干净不持仓、不付摩擦、不吃隔夜缺口）"
           " → **它是上界**。★ 上界不好看 = 真的也不会好。",
           "★ 真数等周末跑批挂 ER 闸重跑引擎"],
          "★标尺": "★★★ 对等权同池（对口标尺），不是 SPY",
          "★门槛": "★★ 相邻三点 0.5 / 0.6 / 0.7（红线②），并报三点改善是否同向"}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            报[名] = 一条(f)
        except Exception as e:
            报[名] = {"★跑失败": repr(e)[:200]}; 失败 += 1
            print("⚠ 失败", 名, flush=True); continue
        b = 报[名]["①不挂ER闸_原样"]; s = 报[名].get("★★★三点改善")
        print(f"✓ {名:<26} 原样 {b['★对等权同池alpha年化pct']}/{b['★t']}  "
              f"三点改善 {s} 同向={报[名].get('★★三点同向')}", flush=True)
    报["★★★失败条数"] = 失败
    with open("probe/分行情比_1107/ER当闸_报告_1107.json", "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
