# -*- coding: utf-8 -*-
"""
★★★★★ 用**两份脏日清单的并集**重量 —— ★ 这是本轮最硬的一次清洗。

★★ 两份清单:
   ① ★ **我们自己扫的**(`扫假跳变_1107.py`):212 只 / 885 个只×日
     —— ★★ 判据保守(价格跳 ≥3 倍 **且** 股数量反向)
   ② ★★★★★ **源头自己标的**(`market_ext_1105/<票>/daily.json.gz` 的 `warnings`):
     **573 只 / 904 条**,原文写着
     「无事件隔夜跳 +X%(**可能是漏记的分拆 / 拆股**,也可能是真行情)」
     ★★★ —— 也就是说:**源头早就告诉我们了，而我们的烤面板脚本从来没读 warnings。**

★★★ 这一条比 #62 更重:★ #62 是「源头没给系数」(数据缺口,要找数据组);
   ★★★ 这一条是「**源头给了警告，我们没读**」—— ★★ 这是**我们自己的 bug**。
★ 旁证:基-7·五毛 里那笔 VRDN +1328%(占总盈亏 11.3%)——
   ★★★ 源头 warnings 原文:「VRDN 2020-11-13 无事件隔夜跳 **+1301.9%**」。

★★ 清洗口径:★ 一笔的持有区间(±15 个日历日)内含**任一份清单**的脏日 → **整笔剔掉**。
★★★ 这是**最保守**的方向(剔得最多)—— ★ 规矩④:宁可低估自己。
"""
from __future__ import annotations
import glob, gzip, importlib, importlib.util, io, json, os, re, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
from engine import data                                            # noqa: E402
import 扫假跳变_1107 as 扫                                          # noqa: E402

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "并两份脏日_报告_1107.json")
容差日 = 15
源跳门槛 = 50.0      # ★★ 源头 warnings 里隔夜跳 ≥50% 的才算脏(★ ③我们的;★★★ 跑相邻三点见下)


def 源头脏日(门槛: float) -> dict[str, list[pd.Timestamp]]:
    """★ 读源头 `warnings` 里「无事件隔夜跳」的条目。★★★ 这是源头自己标的，不是我们判的。"""
    脏: dict[str, list[pd.Timestamp]] = {}
    for p in sorted(glob.glob("market_ext_1105/*/daily.json.gz")):
        try:
            d = json.loads(gzip.open(p, "rt", encoding="utf-8").read())
        except Exception:
            continue
        sym = os.path.basename(os.path.dirname(p))
        for s in (d.get("warnings") or []):
            if "无事件隔夜跳" not in s:
                continue
            md = re.search(r"(\d{4}-\d{2}-\d{2})", s)
            mg = re.search(r"([+-]?\d+\.?\d*)%", s)
            if not (md and mg) or abs(float(mg.group(1))) < 门槛:
                continue
            脏.setdefault(sym.split("__")[0], []).append(pd.Timestamp(md.group(1)))
    return 脏


def main() -> int:
    w = pd.read_parquet(PANEL); cl, vol = w["close"], w["volume"]; del w

    def 前(x): return x.shift(1).rolling(扫.窗, min_periods=扫.窗).median()
    def 后(x): return x.iloc[::-1].rolling(扫.窗, min_periods=扫.窗).median().iloc[::-1]
    pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
    疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
          | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
    我们: dict[str, list[pd.Timestamp]] = {}
    ii, jj = np.where(疑.to_numpy())
    for i, j in zip(ii, jj):
        我们.setdefault(str(cl.columns[j]), []).append(cl.index[i])
    源 = 源头脏日(源跳门槛)
    并 = {k: list(v) for k, v in 我们.items()}
    for k, v in 源.items():
        并.setdefault(k, []).extend(v)
    print(f"★ 我们扫的 {len(我们)} 只 / {sum(len(v) for v in 我们.values())} 条", flush=True)
    print(f"★★★ 源头标的(≥{源跳门槛:.0f}%) {len(源)} 只 / {sum(len(v) for v in 源.values())} 条", flush=True)
    print(f"★★ 并集 {len(并)} 只 / {sum(len(v) for v in 并.values())} 条", flush=True)
    print(f"★ 只有源头标、我们没扫到的: {len(set(源) - set(我们))} 只", flush=True)

    spy = data.load_benchmark("SPY")["close"]
    out = {"★口径": {
        "两份清单": {"我们扫的": {"只数": len(我们), "条数": sum(len(v) for v in 我们.values())},
                 "★★★源头自己标的": {"只数": len(源), "条数": sum(len(v) for v in 源.values()),
                              "门槛": f"隔夜跳 ≥{源跳门槛:.0f}%",
                              "原文": "无事件隔夜跳 +X%（可能是漏记的分拆 / 拆股，也可能是真行情）"},
                 "并集": {"只数": len(并), "条数": sum(len(v) for v in 并.values())},
                 "★只有源头标到的": sorted(set(源) - set(我们))[:40]},
        "剔法": f"★ 持有区间 ±{容差日} 日内含**任一份清单**的脏日 → 整笔剔掉",
        "★★★方向": "★ 最保守（剔得最多）—— 规矩④：宁可低估自己",
        "★★★这一条为什么比 #62 重": "★ #62 是源头没给系数（数据缺口）；"
                             "★★★ 这一条是**源头给了警告、我们的烤面板脚本没读** —— 我们自己的 bug",
    }, "逐条": {}}

    def 量(dd):
        if len(dd) < 10:
            return {"★跑失败": f"只剩 {len(dd)} 笔 —— **样本太少，不出数**"}
        eq, 在场, _ = M.逐日净值(dd, cl)
        win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
        mm = M.一条指标(eq.loc[win], 在场.loc[win], spy)
        分母 = eq.reindex(dd["entry_date"]).to_numpy()
        ok = np.isfinite(分母) & (分母 > 0)
        pct = pd.Series(np.where(ok, dd["net_pnl"].to_numpy() / 分母 * 100.0, np.nan)).dropna()
        赢, 亏 = pct[pct > 0], pct[pct < 0]
        s = dd.sort_values("net_pnl", ascending=False)
        tot = dd["net_pnl"].sum()
        return {"笔数": int(len(dd)),
                "alpha年pct": mm.get("★★★⑧alpha年化pct"),
                "★★★alpha_t": mm.get("★★★⑧alpha_t_NeweyWest"),
                "卡玛": mm.get("★★★④卡玛比率"),
                "最大回撤pct": mm.get("★★★③最大回撤pct"),
                "平均投入pct": mm.get("★★★⑨平均投入比例pct"),
                "利润因子": (round(float(赢.sum() / abs(亏.sum())), 3)
                         if len(亏) and 亏.sum() != 0 else None),
                # ★★★ 《99》预先登记的否决线①:最赚 3 笔占比
                "★★★最赚3笔占总盈亏pct": (round(float(s["net_pnl"].head(3).sum() / tot * 100), 1)
                                 if tot else None),
                "最赚10笔占总盈亏pct": (round(float(s["net_pnl"].head(10).sum() / tot * 100), 1)
                                if tot else None)}

    for f in sorted(glob.glob("probe/基本面跑批_1106/ledgers/REAL__*.csv")):
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("net_pnl", "shares", "entry_price", "notional_in", "adv20_at_entry"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
        if len(d) < 10:
            continue
        脏标 = np.zeros(len(d), dtype=bool)
        for k, (_, row) in enumerate(d.iterrows()):
            ds = 并.get(row["symbol"])
            if not ds:
                continue
            a = row["entry_date"] - pd.Timedelta(days=容差日)
            b = (row["exit_date"] if pd.notna(row["exit_date"]) else row["entry_date"]) \
                + pd.Timedelta(days=容差日)
            if any(a <= t <= b for t in ds):
                脏标[k] = True
        if not 脏标.any():
            continue
        base = d.loc[~脏标].copy()
        rec = {"总笔数": int(len(d)), "★★★剔掉笔数": int(脏标.sum()),
               "剔前": 量(d), "★★★剔后": 量(base)}
        if 名.startswith("基-7"):
            rec["再加流动性闸100万"] = 量(base[base["adv20_at_entry"] >= 1_000_000])
        out["逐条"][名] = rec
        a, b2 = rec["剔前"].get("★★★alpha_t"), rec["★★★剔后"].get("★★★alpha_t")
        print(f"✓ {名[:34]:34s} 剔 {rec['★★★剔掉笔数']:4d}/{len(d):4d} | t {a} → {b2}", flush=True)

    正 = [k for k, v in out["逐条"].items() if (v["★★★剔后"].get("★★★alpha_t") or -9) >= 1.96]
    out["★★★剔后正显著"] = 正
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\n★★★ 两份清单并集剔完之后，正显著的: {正 or '**一条都没有**'}")
    print(f"★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
