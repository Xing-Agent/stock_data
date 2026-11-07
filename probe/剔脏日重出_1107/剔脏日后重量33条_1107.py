# -*- coding: utf-8 -*-
"""
★★★★★ 把基本面 33 条臂**剔掉脏日之后**的数，在**三把尺子上一次量齐** ——
   ★ 这是周一交付① 的硬要求（《92》第三节①）：《93》说明书里基本面那 33 行现在是**脏**的。

★★ 为什么要重写一份而不是直接用 `并两份脏日_报告_1107.json`：
   ★ 那一份只量了**组合层**（alpha / NW t / 卡玛 / 回撤），
   ★★★ 而《93》说明书的**主判据是大盘替身（逐笔同进同出）** —— 那一列它没有。
   ★★ 而且它**只写了 24 条臂**（另外 9 条是「没有任何一笔跨过脏日」而被 `continue` 掉的，
      ★★★ 报告里对它们完全沉默 → 读者会以为没查）。→ ★ 本份**33 条全列**，0 剔的明写 0。

★★★ 口径（和《98》《102》一字不改，★ 不许换宽松口径 —— 规矩④）：
   · 脏日 = ① 我们自己扫的（价格跳 ≥门槛 且 股数量反向）∪ ② 源头 `warnings` 里「无事件隔夜跳 ≥50%」
   · 一笔的持有区间 ±15 个日历日内含任一脏日 → **整笔剔掉**（最保守方向）
   · 剔完 < 10 笔 → **不出数**，明写「样本太少」（规矩⑯：不打空表）

★ 产出：`剔脏日后_33条_1107.json` + `ledgers_clean/`（★ 后者不入库，.gitignore）
"""
from __future__ import annotations
import glob, gzip, importlib.util, io, json, os, re, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
for d in ("probe/大盘替身_1106", "probe/尺子C_1106", "probe/账户百分比_1106", "probe/假跳变_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))

import 大盘替身_1106 as B            # noqa: E402  ★ 主判据
import 按净值百分比_1106 as A         # noqa: E402  ★ 给用户看的（利润因子/胜率）
import 扫假跳变_1107 as 扫            # noqa: E402  ★ 只借它的门槛常数
import 并两份脏日重量_1107 as U       # noqa: E402  ★ 只借它的 源头脏日()
from engine import data              # noqa: E402

_s = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_s); _s.loader.exec_module(M)   # ★ 组合层（《91》那一份）

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
LEDG = "probe/基本面跑批_1106/ledgers"
CLEAN = os.path.join(HERE, "ledgers_clean")
OUT = os.path.join(HERE, "剔脏日后_33条_1107.json")
容差日 = 15
源跳门槛 = 50.0


def 源头改名日() -> tuple[dict, dict]:
    """
    ★★★★★ 1107 第 4 次唤醒**新加的第三、四类** —— ★ 做 #65 元信息审计时查出来的（全文《105》）。
       ★★ 源头 `warnings` 里除了「无事件隔夜跳」，还有两类**我们从来没读、也没人剔**的：
         ③ **「代码 X → Y 隔夜断层 ±N%，没核过接续系数」** —— 37 条，★★★ 最大 **+13181%**
         ④ **「代码 X → Y，隔夜 ±N%（没加接续系数）」** —— 479 条，★ 最大 ±19.9%
       ★★★ 这两类**一个阈值都不设**：★ 源头自己说「没加/没核过接续系数」的那一天，
         ★★ 我们一律当脏日 —— ★★★ 这样就没有「我们自己挑的门槛」这个口子（规矩④ 最保守方向）。
    """
    断层: dict[str, list[pd.Timestamp]] = {}
    改名: dict[str, list[pd.Timestamp]] = {}
    for p in sorted(glob.glob("market_ext_1105/*/daily.json.gz")):
        try:
            d = json.loads(gzip.open(p, "rt", encoding="utf-8").read())
        except Exception:
            continue
        sym = os.path.basename(os.path.dirname(p)).split("__")[0]
        for w in (d.get("warnings") or []):
            w = str(w)
            if "无事件隔夜跳" in w:
                continue
            md = re.search(r"(\d{4}-\d{2}-\d{2})", w)
            if not md:
                continue
            if "隔夜断层" in w:
                断层.setdefault(sym, []).append(pd.Timestamp(md.group(1)))
            elif re.search(r"代码 \S+ → \S+,隔夜", w):
                改名.setdefault(sym, []).append(pd.Timestamp(md.group(1)))
    return 断层, 改名


def 并集脏日(cl: pd.DataFrame, vol: pd.DataFrame) -> tuple[dict, dict, dict]:
    """★★★ 现算，★ 不手抄（《92》第零节③）。★★ 和 `并两份脏日重量_1107.py` 同一段代码，
       ★★★ 外加 1107 第 4 次唤醒查出的第三、四类（见 `源头改名日()`）。"""
    def 前(x): return x.shift(1).rolling(扫.窗, min_periods=扫.窗).median()
    def 后(x): return x.iloc[::-1].rolling(扫.窗, min_periods=扫.窗).median().iloc[::-1]
    pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
    疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
          | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
    我们: dict[str, list[pd.Timestamp]] = {}
    ii, jj = np.where(疑.to_numpy())
    for i, j in zip(ii, jj):
        我们.setdefault(str(cl.columns[j]), []).append(cl.index[i])
    源 = U.源头脏日(源跳门槛)
    断层, 改名 = 源头改名日()
    并 = {k: list(v) for k, v in 我们.items()}
    for 份 in (源, 断层, 改名):
        for k, v in 份.items():
            并.setdefault(k, []).extend(v)
    return 我们, {"无事件隔夜跳": 源, "隔夜断层": 断层, "代码改名": 改名}, 并


def 组合层(dd: pd.DataFrame, cl: pd.DataFrame, spy: pd.Series) -> dict:
    if len(dd) < 10:
        return {"★跑失败": f"只剩 {len(dd)} 笔 —— **样本太少，不出数**"}
    eq, 在场, _ = M.逐日净值(dd, cl)
    win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
    mm = M.一条指标(eq.loc[win], 在场.loc[win], spy)
    # ★★★ 规矩⑬：下面每一个键名都是从 `新尺子_1106.py` 里打出来核过的，不是凭记忆写的
    return {"alpha年pct": mm.get("★★★⑧alpha年化pct"),
            "★★★alpha_t": mm.get("★★★⑧alpha_t_NeweyWest"),
            "卡玛": mm.get("★★★④卡玛比率"),
            "最大回撤pct": mm.get("★★★③最大回撤pct"),
            "溃疡指数": mm.get("★★★⑤溃疡指数"),
            "回本天数": mm.get("★★★⑥回本天数_交易日"),
            "信息比率": mm.get("★★★⑦信息比率_对SPY"),
            "平均投入pct": mm.get("★★★⑨平均投入比例pct"),
            "beta_对SPY": mm.get("⑧beta_对SPY"),
            "年化收益pct": mm.get("②年化收益pct")}


def main() -> int:
    os.makedirs(CLEAN, exist_ok=True)
    w = pd.read_parquet(PANEL)
    cl, vol = w["close"], w["volume"]
    del w
    我们, 源各类, 并 = 并集脏日(cl, vol)
    源 = 源各类["无事件隔夜跳"]
    del vol
    spy = data.load_benchmark("SPY")["close"]

    out = {"★口径": {
        "★★★这一份干什么": "★ 基本面 33 条臂**剔掉脏日之后**，三把尺子一次量齐（主判据 = 大盘替身）",
        "脏日四份清单": {
            "①我们扫的": {"只数": len(我们), "条数": sum(len(v) for v in 我们.values()),
                      "判据": f"价格跳 ≥{扫.跳变门槛} 倍 **且** 股数量反向"},
            "★★★②源头「无事件隔夜跳」": {
                "只数": len(源), "条数": sum(len(v) for v in 源.values()),
                "门槛": f"隔夜跳 ≥{源跳门槛:.0f}%"},
            "★★★★★③源头「代码改名隔夜断层·没核过接续系数」": {
                "只数": len(源各类["隔夜断层"]),
                "条数": sum(len(v) for v in 源各类["隔夜断层"].values()),
                "门槛": "★★★ 不设门槛 —— 源头说没核过就算脏",
                "★这一类是 1107 第 4 次唤醒才查出来的": "★★ 最大一条 +13181%（CJES → CJ）"},
            "★★★④源头「代码改名·没加接续系数」": {
                "只数": len(源各类["代码改名"]),
                "条数": sum(len(v) for v in 源各类["代码改名"].values()),
                "门槛": "★★★ 不设门槛 —— 同上",
                "★幅度": "★ 中位 1.7% · p90 9.1% · 最大 19.9%"},
            "并集": {"只数": len(并), "条数": sum(len(v) for v in 并.values())}},
        "剔法": f"★ 持有区间 ±{容差日} 日内含任一份清单的脏日 → **整笔剔掉**（最保守）",
        "三把尺子": {
            "★★★大盘替身": "逐笔同进同出买 SPY，差值 + 按进场日聚类 t（★ 主判据）",
            "★★组合层": "每天合成一个组合 → 对 SPY 回归 alpha + Newey-West t（★ 《83》第三步）",
            "账户百分比": "利润因子 / 胜率（★ 给用户看，Lin 1107_17:20 口径，辅助）"},
        "★★★两列可能打架": "★ 技-7/8/9 上实测在 5 条臂上符号相反（全文《103》第三节）—— "
                    "★★★ 两套都要报，谁也不许单独报",
        "★尺子版本": "大盘替身 = 1106 21:45 修后口径（当天进当天出不扔 + 时点对齐，《24》#47）",
    }, "逐条": {}, "★★★汇总": {}}

    for f in sorted(glob.glob(os.path.join(LEDG, "REAL__*.csv"))):
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        n0 = len(d)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("net_pnl", "shares", "entry_price", "notional_in"):
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "net_pnl"])
        脏标 = np.zeros(len(d), dtype=bool)
        for k, (_, row) in enumerate(d.iterrows()):
            ds = 并.get(row["symbol"])
            if not ds:
                continue
            a0 = row["entry_date"] - pd.Timedelta(days=容差日)
            b0 = (row["exit_date"] if pd.notna(row["exit_date"]) else row["entry_date"]) \
                + pd.Timedelta(days=容差日)
            if any(a0 <= t <= b0 for t in ds):
                脏标[k] = True
        base = d.loc[~脏标].copy()
        cp = os.path.join(CLEAN, f"REAL__{名}.csv")
        base.to_csv(cp, index=False)

        rec = {"原笔数": int(n0), "可用笔数": int(len(d)),
               "★★★剔掉笔数": int(脏标.sum()), "剔后笔数": int(len(base)),
               "★剔掉占比pct": round(float(脏标.sum()) / len(d) * 100, 2) if len(d) else None}
        if len(base) < 10:
            rec["★★★大盘替身"] = {"★跑失败": f"剔后只剩 {len(base)} 笔 —— **样本太少，不出数**"}
            rec["★★组合层"] = {"★跑失败": f"剔后只剩 {len(base)} 笔"}
            rec["账户百分比"] = {"★跑失败": f"剔后只剩 {len(base)} 笔"}
        else:
            for 名尺, fn in (("★★★大盘替身", B.一条), ("账户百分比", A.一条)):
                try:
                    rec[名尺] = fn(cp)
                except Exception as e:
                    rec[名尺] = {"★跑失败": f"{type(e).__name__}: {str(e)[:260]}"}
            try:
                rec["★★组合层"] = 组合层(base, cl, spy)
            except Exception as e:
                rec["★★组合层"] = {"★跑失败": f"{type(e).__name__}: {str(e)[:260]}"}
        out["逐条"][名] = rec
        bm = rec.get("★★★大盘替身") or {}
        pz = rec.get("★★组合层") or {}
        print(f"✓ {名[:32]:32s} 剔{rec['★★★剔掉笔数']:4d}/{rec['可用笔数']:4d} "
              f"| 替身 {bm.get('★★★④差(真 减 替身)pct')} t={bm.get('t值')} "
              f"| 组合 a={pz.get('alpha年pct')} t={pz.get('★★★alpha_t')}", flush=True)

    def 显(尺, 键, 向):
        return sorted(k for k, v in out["逐条"].items()
                      if isinstance((v.get(尺) or {}).get(键), (int, float))
                      and (v[尺][键] >= 1.96 if 向 > 0 else v[尺][键] <= -1.96))
    out["★★★汇总"] = {
        "臂数": len(out["逐条"]),
        "出不了数的臂": sorted(k for k, v in out["逐条"].items()
                         if "★跑失败" in (v.get("★★★大盘替身") or {})),
        "★★★大盘替身_正显著": 显("★★★大盘替身", "t值", +1),
        "★★★大盘替身_负显著": 显("★★★大盘替身", "t值", -1),
        "★★组合层_正显著": 显("★★组合层", "★★★alpha_t", +1),
        "★★组合层_负显著": 显("★★组合层", "★★★alpha_t", -1),
    }
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print("\n★★★ 汇总:", json.dumps(out["★★★汇总"], ensure_ascii=False, indent=1))
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
