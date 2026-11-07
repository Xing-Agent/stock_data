# -*- coding: utf-8 -*-
"""
★★★★★ 技/融那 33 条臂的**主基准（自己赛道买入持有）** —— ★ 《92》第 5 次唤醒清单第 ② 件，
   ★★ 周一交付① 剩下最大的一块硬活。

★★★ 为什么要重跑回测（★ 不是我想重跑）：
   ★ 这 33 条臂的**逐笔流水不在仓库里**（`.gitignore` 里写着：`probe/新策略_1106/ledgers_1106/`
     · `probe/挂闸_1106/ledgers_1106/` · `probe/技789_1106/arms_1106/`），
   ★★ 而「自己赛道」这把尺子要的是**每天的净值** → 没有流水就算不出。
   → ★★★ 所以本份 = **重跑回测拿流水** + **四把尺子一次量齐**，★ 每条臂单独落盘、可续跑。

★★ 四把尺子（★ 和《93》说明书完全同一批实现，不另造）：
   ① ★★★ **主基准：自己赛道买入持有**（Lin 1107 13:05 定，《93 比法规格书》第 3.1 节）
   ② ★★ 副基准：满仓 SPY（组合层 alpha + Newey-West t）
   ③ ★★ 大盘替身（逐笔同进同出买 SPY）—— ★ 旧主判据，降为第三档参考
   ④ ★ 账户百分比（利润因子 / 胜率，辅助）

★★★★★ 三处和《108》一样的保护（规矩㊲ —— ★ 不带就会重演 #73「赛道算出 +242%/年」）：
   · 赛道指数**剔脏日**（四份并集，和《93》《106》同一份，现算不手抄）
   · **成员下限 20 只**：一天不足 20 只 → 这一天不算（★★★ 不是填 0 收益）
   · **覆盖率 < 60%** → 整条臂不出数，如实写「赛道太小/太稀」

★★★★★ 一处和《108》**不同**、必须写明的口径：
   ★ 基本面那 33 条用的是 `matrices.universe_mask()`（**没过池子口径那道闸**）；
   ★★★ 本份用的是 `建矩阵()` 之后的 `m.universe` —— ★ 也就是 `universe_mask` **再与上**
     `rerun_core_1030.apply_scope(m,"large_mid")` 那道闸，★★ 因为技/融这批回测**就是在这道闸后面跑的**，
     ★★★ 赛道不跟它一致就不是「它自己的赛道」。→ ★ 两边数并排看时要记住这一条。

★ 用法：python3 probe/自己赛道技融_1107/跑自己赛道技融_1107.py [--max N] [--only 关键字]
★★ engine/ 零改动（全部进程内覆盖层）；只用研发池；留出池断言在 台_公共_1106.跑() 里。
"""
from __future__ import annotations
import copy, gc, glob, importlib.util, io, json, os, sys, time, traceback
import numpy as np, pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
for d in ("probe/挂件_1106", "probe/技789_1106", "probe/大盘替身_1106",
          "probe/账户百分比_1106", "probe/假跳变_1107", "probe/剔脏日重出_1107",
          "probe/分档单调_1107", "probe/新策略_1106", "probe/v2_rerun_1030"):
    sys.path.insert(0, os.path.join(ROOT, d))

import 台_公共_1106 as T                    # noqa: E402  ★ 建矩阵 / 跑 / 替身 / 聚类t
import 大盘替身_1106 as B                   # noqa: E402  ★ 第三档参考
import 按净值百分比_1106 as A                # noqa: E402  ★ 辅助
from engine import data                     # noqa: E402

_s = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_s); _s.loader.exec_module(M)

ARMS = os.path.join(HERE, "arms")
LEDG = os.path.join(HERE, "ledgers_clean")
RAWL = os.path.join(HERE, "ledgers_raw")
脏缓存 = os.path.join(HERE, "_脏格缓存.npz")
OUT = os.path.join(HERE, "自己赛道技融_报告_1107.json")
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"

最少成员 = 20            # ★★★ 和《108》同一个下限
最少覆盖 = 0.60          # ★★★ 和《108》同一条否决线
容差日 = 15              # ★ 和《93》剔脏日同一个容差


def 安全名(s: str) -> str:
    return s.replace("/", "／").replace(" ", "_").replace("|", "¦")


# ════════════════════════════ 臂表（33 条，三族） ════════════════════════════
代表 = {"震荡": "技-14-原著.yaml", "突破": "技-6-原著.yaml", "大波段": "技-1.yaml"}
闸均线 = [100, 200, 300]
SWEEP = {
    "融-1_震荡":   ("entry.rules.0.params.threshold", [5.0, 10.0, 15.0]),
    "融-2_突破":   ("entry.rules.0.params.lookback", [20, 40, 55]),
    "融-3_大波段": ("entry.rules.0.params.lookback", [60, 90, 120]),
}


def 改一处(raw: dict, dotted: str, val) -> dict:
    d = copy.deepcopy(raw); cur = d; ps = dotted.split(".")
    for k in ps[:-1]:
        cur = cur[int(k)] if k.isdigit() else cur[k]
    cur[ps[-1]] = val
    return d


def 臂表() -> list[tuple[str, str, dict]]:
    """★★★ 返回 (族, label, raw)。★ label 必须和《93》说明书/大盘替身报告里的键**一字不差**，
       ★★ 否则生成器 join 不上（规矩⑰ 那一类：对不上要大声报，不许悄悄少一行）。"""
    out: list[tuple[str, str, dict]] = []
    # ① 挂闸 12 条（★ 照抄 跑挂闸_1106.py 的生成法，含那条 assert）
    for 族, fn in 代表.items():
        base = yaml.safe_load(io.open(os.path.join(ROOT, "engine", "configs", fn), encoding="utf-8"))
        orig = (base.get("regime") or {}).get("rules") or []
        assert not orig, f"★ {fn} 的 regime 本来就不空（{len(orig)} 条），停下来查"
        for 名, ma in [("不挂闸", None)] + [(f"挂闸{x}日", x) for x in 闸均线]:
            raw = copy.deepcopy(base)
            if ma is not None:
                raw.setdefault("regime", {})["rules"] = [{
                    "type": "index_above_ma", "params": {"symbol": "SPY", "ma": ma},
                    "source": "★★ ②档 行业改进（Faber 2007;Brock 等 1992）。★★★ 原著没写这条闸。"}]
                raw["regime"]["flatten_when_off"] = False
            out.append(("挂闸", f"{族}·{fn[:-5]}·{名}", raw))
    # ② 融 9 条
    for name, (dotted, pts) in SWEEP.items():
        p = os.path.join(ROOT, "probe/新策略_1106/configs", f"{name}.yaml")
        base = yaml.safe_load(io.open(p, encoding="utf-8"))
        for v in pts:
            out.append(("融", f"{name}·{dotted.split('.')[-1]}={v}", 改一处(base, dotted, v)))
    # ③ 技-7/8/9 共 12 条（★ 直接借 跑技789_1106.臂表()，★★ 不重写一遍参数表）
    import 跑技789_1106 as J
    for 卡, 名, raw in J.臂表():
        out.append(("技789", f"{卡}|{名}", raw))
    return out


# ════════════════════════════ 脏格（四份并集，带磁盘缓存） ════════════════════════════
def 脏格(cl: pd.DataFrame, vol: pd.DataFrame) -> pd.DataFrame:
    """★★★ 和《93》《106》**同一个四份并集** —— ★ 借 分档单调性_1107.脏格()，不另写一段。
       ★★ 它要扫 2,968 份 daily.json.gz（约 60~90 秒）→ 本份缓存到磁盘（.gitignore）。"""
    if os.path.exists(脏缓存):
        z = np.load(脏缓存, allow_pickle=True)
        df = pd.DataFrame(z["M"], index=pd.DatetimeIndex(z["idx"]),
                          columns=[str(c) for c in z["cols"]])
        if list(df.columns) == [str(c) for c in cl.columns] and df.index.equals(cl.index):
            return df
        print("⚠ 脏格缓存和面板形状不符 —— 重算", flush=True)
    import 分档单调性_1107 as DEC
    df = DEC.脏格(cl, vol)
    np.savez_compressed(脏缓存, M=df.to_numpy(), idx=df.index.values,
                        cols=np.array([str(c) for c in df.columns]))
    return df


def 剔脏笔(d: pd.DataFrame, 脏: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """★ 和《93》同一条剔法：持有区间 ±15 日内含任一脏日 → **整笔剔掉**（最保守）。
       ★★ 脏格已经把 ±15 日摊开了 → 这里只要看持有区间内有没有 True。"""
    idx = 脏.index
    pos = {str(c): j for j, c in enumerate(脏.columns)}
    Mz = 脏.to_numpy()
    脏标 = np.zeros(len(d), dtype=bool)
    ed = d["entry_date"].to_numpy("datetime64[ns]")
    xd = d["exit_date"].fillna(d["entry_date"]).to_numpy("datetime64[ns]")
    for k, sym in enumerate(d["symbol"].astype(str).to_numpy()):
        j = pos.get(sym)
        if j is None:
            continue
        a = int(np.searchsorted(idx.values, ed[k], "left"))
        b = int(np.searchsorted(idx.values, xd[k], "right"))
        if b > a and Mz[a:b, j].any():
            脏标[k] = True
    return d.loc[~脏标].copy(), int(脏标.sum())


# ════════════════════════════ 赛道指数 ════════════════════════════
def 赛道指数(uni: pd.DataFrame, cl: pd.DataFrame, 脏: pd.DataFrame):
    cols = [c for c in uni.columns if c in cl.columns]
    u = uni[cols].shift(1).fillna(False)                 # ★★★ 规矩㉙：资格滞后一天
    z = 脏.reindex(index=u.index, columns=cols).fillna(False)
    u = u & (~z)
    r = cl[cols].pct_change().where(lambda x: np.isfinite(x))
    masked = r.where(u)
    n = masked.notna().sum(axis=1)
    够 = n >= 最少成员
    覆盖 = float(够.sum()) / len(n) if len(n) else 0.0
    diag = {"赛道成员数_中位": float(n.median()), "赛道成员数_最少": int(n.min()),
            "赛道成员数_最多": int(n.max()), "总天数": int(len(n)),
            "★★★成员数为0的天数": int((n == 0).sum()),
            f"★★★成员数≥{最少成员}的天数": int(够.sum()),
            "★★★覆盖率": round(覆盖, 4)}
    if 覆盖 < 最少覆盖:
        diag["★★★★★算不出"] = (f"★ 赛道一天够 {最少成员} 只的天数只占 {覆盖:.1%}"
                         f"（要 ≥{最少覆盖:.0%}）—— ★★★ 赛道太小/太稀，构不成一个指数")
        return None, diag
    d = masked.mean(axis=1, skipna=True).where(够)
    return (1.0 + d.dropna()).cumprod(), diag


# ════════════════════════════ 一条臂 ════════════════════════════
def 一臂(族: str, label: str, raw: dict, cl, spy, 脏缓) -> dict:
    rec = {"臂": label, "族": 族}
    t0 = time.time()
    # ① 重跑回测拿流水
    m, scope诊 = T.建矩阵(raw)
    led, info = T.跑(raw, m)
    uni = pd.DataFrame(m.universe, index=m.index, columns=[str(s) for s in m.symbols])
    del m; gc.collect()
    rec["★回测"] = {"笔数": int(len(led)), "流水哈希": T.流水哈希(led),
                   "池子口径收窄": {k: v for k, v in (scope诊 or {}).items()
                              if "票日" in str(k) or "口径" in str(k)},
                   "平均仓位": info.get("平均仓位(净值曲线敞口均值)"),
                   "离场原因计数": info.get("离场原因计数")}
    if len(led) == 0:
        rec["★跑失败"] = "★★★ 一笔都没有 —— 大声报（规矩⑯）"
        rec["耗时秒"] = round(time.time() - t0, 1)
        return rec
    os.makedirs(RAWL, exist_ok=True)
    led.to_csv(os.path.join(RAWL, f"REAL__{安全名(label)}.csv.gz"), index=False,
               compression="gzip")
    # ② 剔脏日
    d = led.copy()
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("net_pnl", "shares", "entry_price", "notional_in"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["entry_date", "net_pnl"])
    base, n剔 = 剔脏笔(d, 脏缓)
    rec["★剔脏日"] = {"可用笔数": int(len(d)), "★★★剔掉笔数": n剔, "剔后笔数": int(len(base)),
                   "★剔掉占比pct": round(n剔 / len(d) * 100, 2) if len(d) else None}
    os.makedirs(LEDG, exist_ok=True)
    cp = os.path.join(LEDG, f"REAL__{安全名(label)}.csv")
    base.to_csv(cp, index=False)
    if len(base) < 10:
        rec["★跑失败"] = f"★ 剔脏日后只剩 {len(base)} 笔 —— 样本太少，不出数"
        rec["耗时秒"] = round(time.time() - t0, 1)
        return rec
    # ③ 赛道指数
    eq赛, diag = 赛道指数(uni, cl, 脏缓)
    del uni; gc.collect()
    rec["★赛道诊断"] = diag
    # ④ 四把尺子
    eq, 在场, _ = M.逐日净值(base, cl)
    win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
    e, zz = eq.loc[win], 在场.loc[win]
    副 = M.一条指标(e, zz, spy.reindex(e.index).ffill())
    if eq赛 is None:
        rec["★★★①主基准_对自己赛道"] = {"★算不出": diag["★★★★★算不出"]}
    else:
        主 = M.一条指标(e, zz, eq赛.reindex(e.index).ffill())
        rec["★★★①主基准_对自己赛道"] = {
            "alpha年pct": 主.get("★★★⑧alpha年化pct"),
            "★★★alpha_t_NW": 主.get("★★★⑧alpha_t_NeweyWest"),
            "beta_对赛道": 主.get("⑧beta_对SPY"),
            "信息比率_对赛道": 主.get("★★★⑦信息比率_对SPY")}
        es = eq赛.loc[(eq赛.index >= M.PERF0) & (eq赛.index <= M.PERF1)]
        yrs = (es.index[-1] - es.index[0]).days / 365.25 if len(es) > 1 else 0
        rec["★★★赛道自己"] = {
            "年化pct": (round(float(es.iloc[-1] / es.iloc[0]) ** (1 / yrs) * 100 - 100, 3)
                     if yrs > 0 else None),
            "最大回撤pct": round(float((es / es.cummax() - 1).min()) * 100, 2)}
    rec["★★②副基准_对满仓SPY_组合层"] = {
        "alpha年pct": 副.get("★★★⑧alpha年化pct"),
        "★★★alpha_t_NW": 副.get("★★★⑧alpha_t_NeweyWest"),
        "beta_对SPY": 副.get("⑧beta_对SPY"),
        "信息比率": 副.get("★★★⑦信息比率_对SPY"),
        "卡玛": 副.get("★★★④卡玛比率"), "溃疡指数": 副.get("★★★⑤溃疡指数"),
        "回本天数": 副.get("★★★⑥回本天数_交易日")}
    rec["★策略自己"] = {"年化pct": 副.get("②年化收益pct"),
                    "最大回撤pct": 副.get("★★★③最大回撤pct"),
                    "平均投入pct": 副.get("★★★⑨平均投入比例pct"),
                    "笔数": int(len(base))}
    try:
        rec["★★③大盘替身_逐笔(第三档参考)"] = B.一条(cp)
    except Exception as ex:
        rec["★★③大盘替身_逐笔(第三档参考)"] = {"★跑失败": f"{type(ex).__name__}: {str(ex)[:200]}"}
    try:
        rec["★④账户百分比(辅助)"] = A.一条(cp)
    except Exception as ex:
        rec["★④账户百分比(辅助)"] = {"★跑失败": f"{type(ex).__name__}: {str(ex)[:200]}"}
    rec["耗时秒"] = round(time.time() - t0, 1)
    return rec


def 汇总() -> dict:
    recs = [json.load(io.open(f, encoding="utf-8"))
            for f in sorted(glob.glob(os.path.join(ARMS, "*.json")))]
    def 显(向):
        o = []
        for r in recs:
            v = (r.get("★★★①主基准_对自己赛道") or {}).get("★★★alpha_t_NW")
            if isinstance(v, (int, float)) and ((v >= 1.96) if 向 > 0 else (v <= -1.96)):
                o.append(f"{r['臂']} (t={v})")
        return sorted(o)
    算不出 = sorted(r["臂"] for r in recs
                 if "★算不出" in (r.get("★★★①主基准_对自己赛道") or {}))
    return {
        "★★★这一份是什么": "★ 技/融 33 条臂的**主基准（自己赛道买入持有）** —— "
                     "《92》第 5 次唤醒清单 ②；★★ 周一交付① 的硬路径",
        "★口径": {
            "赛道": "★★★ 建矩阵() 之后的 m.universe —— universe_mask **与上** "
                  "apply_scope(large_mid)；★ 和《108》基本面那 33 条**不同**（那边没过池子闸），"
                  "★★ 因为技/融这批回测就是在这道闸后面跑的",
            "赛道指数": "每天对**前一天**在 universe 里、且这一天不脏的票取等权平均日收益，复利成净值",
            "★★★★★三处保护(规矩㊲)": f"剔脏日（四份并集）· 成员下限 {最少成员} 只 · "
                             f"覆盖率 <{最少覆盖:.0%} 整条不出数",
            "流水": "★★★ 本份**重跑回测**拿的（★ 原流水在 .gitignore 里，不在仓库）；"
                  "★★ 剔脏日后那一份在 ledgers_clean/",
            "窗口": f"{M.PERF0.date()} → {M.PERF1.date()}",
            "池子": "新池研发池 2,224 只（留出 583 只 + 考卷 1,042 只都不碰）",
            "engine改动": "零 —— 进程内覆盖层",
            "⚠#70": "★★★ 挂闸9 条 + 融9 条带「环境闸偷看一天」—— 本份数同样受影响，"
                   "★★ 判定一列仍按《93》标「数不可用」，★ 等 Lin 拍板后重跑",
        },
        "进度": {"臂总数": 33, "已跑": len(recs),
               "出数": sum(1 for r in recs if "★跑失败" not in r)},
        "★★★对自己赛道_正显著": 显(+1),
        "★★★对自己赛道_负显著": 显(-1),
        "★★赛道算不出的": 算不出,
        "逐臂": {r["臂"]: r for r in recs},
    }


def main(argv) -> int:
    上限 = 2
    if "--max" in argv:
        上限 = int(argv[argv.index("--max") + 1])
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    os.makedirs(ARMS, exist_ok=True)
    tbl = 臂表()
    待 = [(f, l, r) for f, l, r in tbl
         if not os.path.exists(os.path.join(ARMS, 安全名(l) + ".json"))
         and (only is None or only in l)]
    print(f"★ 臂表 {len(tbl)} 条；待跑 {len(待)} 条；本轮最多 {上限} 条", flush=True)
    if not 待:
        io.open(OUT, "w", encoding="utf-8").write(
            json.dumps(汇总(), ensure_ascii=False, indent=1, default=str))
        print("★★★ 全部跑完 → 已出汇总", OUT, flush=True)
        return 0
    T.装覆盖层()
    import 技789覆盖层_1106 as O
    O.install()                       # ★ 技-7/8/9 的零件是运行时挂钩；非该类型原样转回
    w = pd.read_parquet(PANEL)
    cl, vol = w["close"], w["volume"]
    del w; gc.collect()
    脏缓 = 脏格(cl, vol)
    del vol; gc.collect()
    spy = data.load_benchmark("SPY")["close"]
    for 族, label, raw in 待[:上限]:
        fp = os.path.join(ARMS, 安全名(label) + ".json")
        try:
            rec = 一臂(族, label, raw, cl, spy, 脏缓)
        except Exception as e:
            rec = {"臂": label, "族": 族,
                   "★跑失败": f"{type(e).__name__}: {str(e)[:300]}",
                   "★回溯": traceback.format_exc(limit=4)[-800:]}
            print("  ✗✗✗", label, type(e).__name__, str(e)[:160], flush=True)
        io.open(fp, "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        主 = rec.get("★★★①主基准_对自己赛道") or {}
        print(f"  {'✗' if '★跑失败' in rec else '✓'} {label[:40]:40s} "
              f"赛道alpha {主.get('alpha年pct')} t={主.get('★★★alpha_t_NW')} "
              f"{str(rec.get('★跑失败',''))[:50]} ({rec.get('耗时秒')}s)", flush=True)
        gc.collect()
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(汇总(), ensure_ascii=False, indent=1, default=str))
    print(f"★ 已跑 {len(glob.glob(os.path.join(ARMS,'*.json')))}/33 → {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
