# -*- coding: utf-8 -*-
"""
★★★★★ 把「跨过假跳变日」的那些笔**剔掉**，再按《91》那套组合层指标重量一遍。

★★ 为什么必须做这一步:★ 基本面 33 条臂里唯一正显著的是 基-7 烟蒂那一族
   (alpha t 2.16/2.00/1.98),★★★ 而它们**32~53% 的总盈亏来自跨过假跳变的笔**。
→ ★ 所以「剔掉之后还剩多少」才是真成绩。

★★★ 剔法（★ 口径写死，不许含糊）：
   ★ 一笔只要**持有区间（±15 个日历日容差）内包含该票的疑似假跳变日**，就剔掉整笔。
   ★★★ 这是**保守方向**:★ 它会连带剔掉一些真实的笔(容差带来的)——
     ★★ 但方向是**让我们的数字变差**,★★★ 符合规矩④(宁可低估自己)。
★★ 规矩⑰:剔了多少笔、剔的那批和留下的那批成绩差多少,**两样都要报**。
"""
from __future__ import annotations
import glob, importlib.util, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
from engine import data                                            # noqa: E402

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
报告 = os.path.join(HERE, "假跳变_报告_1107.json")
OUT = os.path.join(HERE, "剔污染重量_报告_1107.json")
容差日 = 15


def main() -> int:
    r = json.load(io.open(报告, encoding="utf-8"))
    脏 = {}
    for x in (r.get("最大20条") or []):
        pass
    # ★ 完整脏日清单:报告里只存了最大 20 条 → ★★ 重新从名单 + 全量扫一遍太贵,
    #   ★★★ 所以这里直接读扫描脚本重算一次脏日(保持同一份实现,规矩:不许两份)
    sys.path.insert(0, HERE)
    import importlib
    扫 = importlib.import_module("扫假跳变_1107")
    w = pd.read_parquet(PANEL)
    cl, vol = w["close"], w["volume"]; del w

    def 前(x): return x.shift(1).rolling(扫.窗, min_periods=扫.窗).median()
    def 后(x): return x.iloc[::-1].rolling(扫.窗, min_periods=扫.窗).median().iloc[::-1]
    pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
    疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
          | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
    ii, jj = np.where(疑.to_numpy())
    for i, j in zip(ii, jj):
        脏.setdefault(str(cl.columns[j]), []).append(cl.index[i])
    print(f"★ 脏日 {sum(len(v) for v in 脏.values())} 条 · 涉及 {len(脏)} 只", flush=True)

    spy = data.load_benchmark("SPY")["close"]
    out = {"★口径": {
        "剔法": f"★ 一笔的持有区间(±{容差日} 个日历日容差)内含该票疑似假跳变日 → **整笔剔掉**",
        "★★★方向": "★ 保守 —— 会连带剔掉一些真实的笔，但方向是**让我们的数字变差**（规矩④）",
        "判据": f"① 后{扫.窗}日收盘中位 ÷ 前{扫.窗}日中位 ≥ {扫.跳变门槛}"
              f" ② 股数量朝反方向 ≥ {扫.量反向容差} 倍",
        "★已核过的样本": "★★ QCLS/PVLA/MULN/YYAI/WLL/CIVI 六只回源头核过："
                    "`split_coefficient` 全是 **1.0**、`corporate_actions.events` 里"
                    "**附近没有拆股事件** → ★★★ 源头确实没给系数",
        "指标": "《91》同一套实现",
    }, "逐条": {}}

    for f in sorted(glob.glob("probe/基本面跑批_1106/ledgers/REAL__*.csv")):
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("net_pnl", "shares", "entry_price", "notional_in"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
        if not len(d):
            continue
        脏标 = np.zeros(len(d), dtype=bool)
        for k, (_, row) in enumerate(d.iterrows()):
            ds = 脏.get(row["symbol"])
            if not ds:
                continue
            a = row["entry_date"] - pd.Timedelta(days=容差日)
            b = (row["exit_date"] if pd.notna(row["exit_date"]) else row["entry_date"]) \
                + pd.Timedelta(days=容差日)
            if any(a <= t <= b for t in ds):
                脏标[k] = True
        if not 脏标.any():
            continue
        干 = d.loc[~脏标].copy()
        脏笔 = d.loc[脏标].copy()
        rec = {"总笔数": int(len(d)),
               "★★★剔掉笔数": int(脏标.sum()),
               "剔掉占总盈亏pct": round(float(脏笔["net_pnl"].sum()
                                       / d["net_pnl"].sum() * 100), 1)
               if d["net_pnl"].sum() else None,
               # ★ 规矩⑰:两批成绩差多少
               "★⑰剔掉那批每笔pct中位": round(float((脏笔["net_pnl"]
                                              / 脏笔["notional_in"] * 100).median()), 2),
               "★⑰留下那批每笔pct中位": round(float((干["net_pnl"]
                                              / 干["notional_in"] * 100).median()), 2)
               if len(干) else None}
        for 标, dd in (("剔前", d), ("★★★剔后", 干)):
            if not len(dd):
                rec[标] = {"★跑失败": "剔完一笔不剩"}
                continue
            eq, 在场, _ = M.逐日净值(dd, cl)
            win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
            mm = M.一条指标(eq.loc[win], 在场.loc[win], spy)
            分母 = eq.reindex(dd["entry_date"]).to_numpy()
            ok = np.isfinite(分母) & (分母 > 0)
            pct = pd.Series(np.where(ok, dd["net_pnl"].to_numpy() / 分母 * 100.0,
                                     np.nan)).dropna()
            赢, 亏 = pct[pct > 0], pct[pct < 0]
            rec[标] = {"笔数": int(len(dd)),
                       "alpha年pct": mm.get("★★★⑧alpha年化pct"),
                       "alpha_t": mm.get("★★★⑧alpha_t_NeweyWest"),
                       "卡玛": mm.get("★★★④卡玛比率"),
                       "最大回撤pct": mm.get("★★★③最大回撤pct"),
                       "平均投入pct": mm.get("★★★⑨平均投入比例pct"),
                       "利润因子": (round(float(赢.sum() / abs(亏.sum())), 3)
                                if len(亏) and 亏.sum() != 0 else None)}
        out["逐条"][名] = rec
        a, b = rec["剔前"].get("alpha_t"), rec["★★★剔后"].get("alpha_t")
        print(f"✓ {名[:36]:36s} 剔 {rec['★★★剔掉笔数']:3d} 笔 | "
              f"alpha_t {a} → {b}", flush=True)

    # ★★★ 汇总:剔后还有几条正显著
    正前 = [k for k, v in out["逐条"].items()
           if (v["剔前"].get("alpha_t") or -9) >= 1.96]
    正后 = [k for k, v in out["逐条"].items()
           if (v["★★★剔后"].get("alpha_t") or -9) >= 1.96]
    out["★★★汇总"] = {"被污染的臂": len(out["逐条"]),
                   "剔前正显著": 正前, "★★★剔后正显著": 正后}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\n★★★ 剔前正显著 {正前}\n★★★ 剔后正显著 {正后}")
    print(f"★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
