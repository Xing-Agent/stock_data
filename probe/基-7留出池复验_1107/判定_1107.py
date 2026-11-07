# -*- coding: utf-8 -*-
"""
★★★ 基-7 烟蒂 · 留出池复验 · **判定** —— ★ 判据**全部写死在《99》**,这里只照着算,
   ★★★ 跑完只能答「过 / 不过 / 样本不够」,**不许中途改判据、改闸、改参数**。

★★★ 《99》三节的判据原样抄下来(★ 下面 判据 字典就是它):
   · 主判据:对 SPY 回归 alpha 年化 > 0 **且** Newey-West t ≥ 1.96
   · 池子:留出池 583 只 · 闸:ADV20 ≥ 100 万 · 参数:**X = 0.8(八毛)一个点**
   · 先剔掉:跨过未调整并股的笔(±15 日容差,和《98》同口径)
★★★ 四条否决线(★ 任一触发 → 判不通过 / 不算):
   ① 最赚的 3 笔占总盈亏 > 50%        → 判不通过(不管 t 多少)
   ② 单独一年占总盈亏 > 50%           → 判不通过
   ③ 期末未平仓 > 总笔数 20%          → 这一轮的数不算
   ④ 笔数 < 50                        → 「样本不够,测不出」
★★ 期末未平仓怎么认(★ #48):`chain.py` 在最后一根 K 线先走退市那一支 →
   ★★★ 期末平仓的笔被贴成「退市结算」。★ 所以按**离场日 = 窗口末日**认,不看标签。
"""
from __future__ import annotations
import importlib.util, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "假跳变_1107"))
os.chdir(ROOT)

spec = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
from engine import data                                            # noqa: E402
import 扫假跳变_1107 as 扫                                          # noqa: E402

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
LED = os.path.join(HERE, "ledgers")
OUT = os.path.join(HERE, "判定_报告_1107.json")
容差日 = 15
闸 = 1_000_000
主臂 = "基-7_早期巴菲特烟蒂·八毛"
旁证 = ["基-7_早期巴菲特烟蒂·五毛", "基-7_早期巴菲特烟蒂·三分之二"]


def 脏日表(cl, vol) -> dict:
    """★ 和《98》《加流动性闸》同一套判据,★★ 不另造一套(否则两处分叉)。"""
    def 前(x): return x.shift(1).rolling(扫.窗, min_periods=扫.窗).median()
    def 后(x): return x.iloc[::-1].rolling(扫.窗, min_periods=扫.窗).median().iloc[::-1]
    pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
    疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
          | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
    脏: dict = {}
    ii, jj = np.where(疑.to_numpy())
    for i, j in zip(ii, jj):
        脏.setdefault(str(cl.columns[j]), []).append(cl.index[i])
    return 脏


def 读流水(名: str) -> pd.DataFrame:
    p = os.path.join(LED, f"HOLD__{名}.csv")
    d = pd.read_csv(p)
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("net_pnl", "shares", "entry_price", "notional_in", "adv20_at_entry"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])


def 剔脏(d: pd.DataFrame, 脏: dict) -> tuple[pd.DataFrame, int]:
    标 = np.zeros(len(d), dtype=bool)
    for k, (_, row) in enumerate(d.iterrows()):
        ds = 脏.get(row["symbol"])
        if not ds:
            continue
        a = row["entry_date"] - pd.Timedelta(days=容差日)
        b = (row["exit_date"] if pd.notna(row["exit_date"]) else row["entry_date"]) \
            + pd.Timedelta(days=容差日)
        if any(a <= t <= b for t in ds):
            标[k] = True
    return d.loc[~标].copy(), int(标.sum())


def 集中度(d: pd.DataFrame) -> dict:
    """★★★ 《99》必报项①:最赚的 1/3/5/10 笔各占总盈亏百分之几。"""
    tot = float(d["net_pnl"].sum())
    s = d["net_pnl"].sort_values(ascending=False)
    out = {"总盈亏": round(tot, 2)}
    for n in (1, 3, 5, 10):
        if len(s) >= n and tot != 0:
            out[f"最赚{n}笔占总盈亏pct"] = round(float(s.iloc[:n].sum() / tot * 100), 1)
        else:
            out[f"最赚{n}笔占总盈亏pct"] = None
    return out


def 逐年(d: pd.DataFrame) -> dict:
    """★★★ 《99》必报项②:逐年占总盈亏百分比。"""
    tot = float(d["net_pnl"].sum())
    g = d.groupby(d["entry_date"].dt.year)["net_pnl"].sum()
    return {"按进场年占总盈亏pct": ({int(k): round(float(v / tot * 100), 1)
                                for k, v in g.items()} if tot != 0 else None),
            "★最大单年占比pct": (round(float(g.max() / tot * 100), 1)
                            if tot != 0 and len(g) else None)}


def 期末(d: pd.DataFrame) -> dict:
    """★★★ 《99》必报项③ —— ★ 按**离场日 = 窗口末日**认(#48:标签是错的)。"""
    末 = pd.to_datetime(M.PERF1)
    是 = d["exit_date"].notna() & (d["exit_date"] >= 末 - pd.Timedelta(days=3))
    return {"★期末平仓笔数": int(是.sum()),
            "★占总笔数pct": (round(float(是.mean() * 100), 1) if len(d) else None),
            "★它们的盈亏": round(float(d.loc[是, "net_pnl"].sum()), 2),
            "★占总盈亏pct": (round(float(d.loc[是, "net_pnl"].sum()
                                    / d["net_pnl"].sum() * 100), 1)
                         if float(d["net_pnl"].sum()) != 0 else None),
            "★认法": "离场日 ≥ 窗口末日−3 天(★ #48:引擎把期末平仓贴成「退市结算」)"}


def 量(d: pd.DataFrame, cl, spy) -> dict:
    if len(d) < 10:
        return {"★跑失败": f"只剩 {len(d)} 笔 —— **样本太少,不出数**"}
    eq, 在场, _ = M.逐日净值(d, cl)
    win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
    mm = M.一条指标(eq.loc[win], 在场.loc[win], spy)
    return {"笔数": int(len(d)),
            "alpha年pct": mm.get("★★★⑧alpha年化pct"),
            "★★★alpha_t_NW": mm.get("★★★⑧alpha_t_NeweyWest"),
            "信息比率": mm.get("★★★⑦信息比率"),
            "卡玛": mm.get("★★★④卡玛比率"),
            "溃疡指数": mm.get("★★★⑤溃疡指数"),
            "最大回撤pct": mm.get("★★★③最大回撤pct"),
            "平均投入pct": mm.get("★★★⑨平均投入比例pct")}


def main() -> int:
    w = pd.read_parquet(PANEL); cl, vol = w["close"], w["volume"]; del w
    脏 = 脏日表(cl, vol)
    spy = data.load_benchmark("SPY")["close"]

    out = {"★★★这一份是什么": "基-7 烟蒂·留出池复验的判定(判据写死在《99》,这里只算)",
           "★口径": {"池": "留出池 583 只(研发池 2,224 只已排除;考卷 1,042 只烤盘阶段已排除)",
                    "窗口": f"{M.PERF0} → {M.PERF1}", "闸": f"ADV20 ≥ {闸/1e6:.0f}00万美元/天",
                    "先剔": f"跨过未调整并股的笔(±{容差日} 日容差,和《98》同口径)",
                    "主判据": "alpha年 > 0 且 Newey-West t ≥ 1.96", "主臂": 主臂},
           "逐臂": {}}

    for 名 in [主臂] + 旁证:
        d = 读流水(名)
        base, n脏 = 剔脏(d, 脏)
        sub = base[base["adv20_at_entry"] >= 闸].copy()
        rec = {"★是主判据吗": (名 == 主臂),
               "原始笔数": int(len(d)), "★剔掉的脏笔数": n脏, "剔脏后笔数": int(len(base)),
               "★★⑰闸剔掉笔数": int(len(base) - len(sub)),
               "★★⑰剔掉那批每笔pct中位": (round(float(
                   (base[base["adv20_at_entry"] < 闸]["net_pnl"]
                    / base[base["adv20_at_entry"] < 闸]["notional_in"] * 100).median()), 2)
                   if len(base) > len(sub) else None),
               "过闸后笔数": int(len(sub))}
        rec["成绩_过闸后"] = 量(sub, cl, spy)
        rec["成绩_只剔脏未过闸(旁证)"] = 量(base, cl, spy)
        if len(sub):
            rec["★必报①集中度"] = 集中度(sub)
            rec["★必报②逐年"] = 逐年(sub)
            rec["★必报③期末平仓"] = 期末(sub)

        # ★★★ 四条否决线(★ 逐条判,★ 不许只判一条就下结论)
        否决: list[str] = []
        n = len(sub)
        if n < 50:
            否决.append(f"④ 笔数 {n} < 50 → **样本不够,测不出**")
        c = rec.get("★必报①集中度") or {}
        if c.get("最赚3笔占总盈亏pct") is not None and c["最赚3笔占总盈亏pct"] > 50:
            否决.append(f"① 最赚 3 笔占 {c['最赚3笔占总盈亏pct']}% > 50% → **判不通过**")
        y = rec.get("★必报②逐年") or {}
        if y.get("★最大单年占比pct") is not None and y["★最大单年占比pct"] > 50:
            否决.append(f"② 最大单年占 {y['★最大单年占比pct']}% > 50% → **判不通过**")
        e = rec.get("★必报③期末平仓") or {}
        if e.get("★占总笔数pct") is not None and e["★占总笔数pct"] > 20:
            否决.append(f"③ 期末平仓占 {e['★占总笔数pct']}% > 20% → **这一轮的数不算**")
        rec["★★★否决线"] = 否决 or ["★ 四条都没触发"]

        g = rec["成绩_过闸后"]
        过 = (not 否决) and ("★跑失败" not in g) \
            and (g.get("alpha年pct") or 0) > 0 and (g.get("★★★alpha_t_NW") or 0) >= 1.96
        rec["★★★★★判定"] = ("过" if 过 else
                           ("样本不够,测不出" if any("④" in x for x in 否决) else "不过"))
        out["逐臂"][名] = rec
        print(f"\n=== {名} ===", flush=True)
        print(f"   原始 {len(d)} → 剔脏 {len(base)} → 过闸 {len(sub)} 笔", flush=True)
        if "★跑失败" in g:
            print(f"   {g['★跑失败']}", flush=True)
        else:
            print(f"   alpha {g['alpha年pct']}%  t={g['★★★alpha_t_NW']}  "
                  f"卡玛 {g['卡玛']}  回撤 {g['最大回撤pct']}%", flush=True)
        for x in rec["★★★否决线"]:
            print(f"   否决线:{x}", flush=True)
        print(f"   ★★★ 判定:{rec['★★★★★判定']}", flush=True)

    # ★★★ 三点是否同向(★ 规矩② —— 原著没给的参数要报三点同向)
    三 = {k: (out["逐臂"][k]["成绩_过闸后"].get("alpha年pct")
              if "★跑失败" not in out["逐臂"][k]["成绩_过闸后"] else None)
         for k in [主臂] + 旁证}
    有 = [v for v in 三.values() if v is not None]
    out["★★三点同向(规矩②)"] = {"三点 alpha": 三,
        "★同向吗": ("★ 算不了(有点出不来数)" if len(有) < 3 else
                  ("同向(全正)" if all(v > 0 for v in 有) else
                   ("同向(全负)" if all(v < 0 for v in 有) else "★★★ 不同向")))}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
