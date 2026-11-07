# -*- coding: utf-8 -*-
"""
★★★★★ **老池那 45 条臂的主基准（自己赛道买入持有）** —— ★ 《110》第五节 ① 那一件，
   ★★ 《93 说明书》里**最后一块没有主基准的白**（44 条，★ 第 45 条和新池那边重名已去重）。

★★★ 这 45 条是 `probe/friction_rerun_1104/` 那一轮的链（五族：
   `A0十二条 / 剔污染 / 原著离场 / 批五修正 / 技术派六条三版`）。
   ★★★★★ ⚠ **它们跑在老池上，研发池只有 198 只** —— ★ 和新池那条线（2,224 只）不是一个池；
   ★★ 这件事《93 说明书》现在只写「池：混（老池流水 + 新池流水）」，★★★ **没写 198 vs 2,224**，
   ★ 本份把它写明（见报告 `★口径`）。

★★ 做法 = 《110》那一份原样搬过来，换三处（★ 逐处都是查代码定的，不是猜的）：
   ① **不装新池覆盖层** —— 用 engine 原生 cache（`engine/cache/ohlcv_panel.parquet`，300 只）
   ② 臂表 = `run_friction_1104.chain_list()`（45 条），配置目录 `engine/configs/`
   ③ 池子 = `run_friction_1104.load_pools()`（研发 198 / 留出 49），闸 `apply_scope(m,"large_mid")`
      —— ★★★ 和 `run_friction_1104.run_one():411-413` 一模一样的三行

★★★★★ 脏日这件（★ 《110》第五节里我提了一句「怕列名对不上」，★★ 本份查实了）：
   ★ `分档单调性_1107.脏格(cl, vol)` 是**按传进去的面板现算**的：
     自己扫的那一份用 `cl/vol` 的列算，源头那三份（无事件隔夜跳 / 隔夜断层 / 代码改名）
     是**按代码名**从 `market_ext_1105/*/daily.json.gz` 读的，再 `pos.get(sym)` 对到面板列上。
   → ★★★ 所以**把老池面板传进去就是对的**，不会静默少剔；★★ 老池 300 列里有 237 列和新池同名。

★ 可续跑：每条臂单独落盘 `arms/`；★★ engine 零改动；★★★ 留出池硬断言。
★ 用法：python3 probe/自己赛道老池_1107/跑自己赛道老池_1107.py [--max N] [--only 关键字]
"""
from __future__ import annotations
import copy, gc, glob, importlib.util, io, json, os, sys, time, traceback
import numpy as np, pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
for d in ("probe/friction_rerun_1104", "probe/v2_rerun_1030", "probe/大盘替身_1106",
          "probe/账户百分比_1106", "probe/假跳变_1107", "probe/剔脏日重出_1107",
          "probe/分档单调_1107", "probe/自己赛道技融_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))

import run_friction_1104 as F                 # noqa: E402
import rerun_core_1030 as RC                  # noqa: E402
import 大盘替身_1106 as B                     # noqa: E402
import 按净值百分比_1106 as A                  # noqa: E402
from engine import matrices, chain, data, pat6_ops, ops_exits_1029   # noqa: E402

_s = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_s); _s.loader.exec_module(M)
_t = importlib.util.spec_from_file_location(
    "_jr", "probe/自己赛道技融_1107/跑自己赛道技融_1107.py")
JR = importlib.util.module_from_spec(_t); _t.loader.exec_module(JR)   # ★ 借 赛道指数/剔脏笔/安全名

ARMS = os.path.join(HERE, "arms")
LEDG = os.path.join(HERE, "ledgers_clean")
脏缓存 = os.path.join(HERE, "_脏格缓存老池.npz")
OUT = os.path.join(HERE, "自己赛道老池_报告_1107.json")
SCOPE = "large_mid"


def 脏格老池(cl, vol):
    """★★ 和《110》同一个四份并集，★ 只是面板换成老池（★★★ 缓存另存一份，不和新池混）。"""
    if os.path.exists(脏缓存):
        z = np.load(脏缓存, allow_pickle=True)
        df = pd.DataFrame(z["M"], index=pd.DatetimeIndex(z["idx"]),
                          columns=[str(c) for c in z["cols"]])
        if list(df.columns) == [str(c) for c in cl.columns] and df.index.equals(cl.index):
            return df
        print("⚠ 老池脏格缓存形状不符 —— 重算", flush=True)
    import 分档单调性_1107 as DEC
    df = DEC.脏格(cl, vol)
    np.savez_compressed(脏缓存, M=df.to_numpy(), idx=df.index.values,
                        cols=np.array([str(c) for c in df.columns]))
    return df


def 一臂(label, yml, ov, group, dev, hold, cl, spy, 脏缓) -> dict:
    rec = {"臂": label, "族": group, "配置": yml}
    t0 = time.time()
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine", "configs", yml), encoding="utf-8"))
    if ov is not None:
        raw = ov(copy.deepcopy(raw))
    cfg = chain.ChainConfig.from_dict(raw)
    # ★★★ 这三行和 run_friction_1104.run_one():411-413 一模一样
    m = matrices.build(cfg.raw, dev)
    scope诊 = RC.apply_scope(m, SCOPE)
    res = chain.run_chain(cfg, dev, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger.copy()
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & set(hold))
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")
    uni = pd.DataFrame(m.universe, index=m.index, columns=[str(s) for s in m.symbols])
    del m; gc.collect()
    rec["★回测"] = {"笔数": int(len(led)),
                   "池子口径收窄": {k: v for k, v in (scope诊 or {}).items() if "票日" in str(k)},
                   "离场原因计数": (led["reason"].value_counts().to_dict() if len(led) else {})}
    if len(led) == 0:
        rec["★跑失败"] = "★★★ 一笔都没有 —— 大声报（规矩⑯）"
        rec["耗时秒"] = round(time.time() - t0, 1)
        return rec
    d = led
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("net_pnl", "shares", "entry_price", "notional_in"):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["entry_date", "net_pnl"])
    base, n剔 = JR.剔脏笔(d, 脏缓)
    rec["★剔脏日"] = {"可用笔数": int(len(d)), "★★★剔掉笔数": n剔, "剔后笔数": int(len(base)),
                   "★剔掉占比pct": round(n剔 / len(d) * 100, 2) if len(d) else None}
    os.makedirs(LEDG, exist_ok=True)
    cp = os.path.join(LEDG, f"REAL__{JR.安全名(label)}.csv")
    base.to_csv(cp, index=False)
    if len(base) < 10:
        rec["★跑失败"] = f"★ 剔脏日后只剩 {len(base)} 笔 —— 样本太少，不出数"
        rec["耗时秒"] = round(time.time() - t0, 1)
        return rec
    eq赛, diag = JR.赛道指数(uni, cl, 脏缓)
    del uni; gc.collect()
    rec["★赛道诊断"] = diag
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
        "beta_对SPY": 副.get("⑧beta_对SPY"), "信息比率": 副.get("★★★⑦信息比率_对SPY"),
        "卡玛": 副.get("★★★④卡玛比率"), "溃疡指数": 副.get("★★★⑤溃疡指数"),
        "回本天数": 副.get("★★★⑥回本天数_交易日")}
    rec["★策略自己"] = {"年化pct": 副.get("②年化收益pct"),
                    "最大回撤pct": 副.get("★★★③最大回撤pct"),
                    "平均投入pct": 副.get("★★★⑨平均投入比例pct"), "笔数": int(len(base))}
    for 名尺, fn in (("★★③大盘替身_逐笔(第三档参考)", B.一条), ("★④账户百分比(辅助)", A.一条)):
        try:
            rec[名尺] = fn(cp)
        except Exception as ex:
            rec[名尺] = {"★跑失败": f"{type(ex).__name__}: {str(ex)[:200]}"}
    rec["耗时秒"] = round(time.time() - t0, 1)
    return rec


def 汇总(总数: int) -> dict:
    recs = [json.load(io.open(f, encoding="utf-8"))
            for f in sorted(glob.glob(os.path.join(ARMS, "*.json")))]
    def 显(向):
        o = []
        for r in recs:
            v = (r.get("★★★①主基准_对自己赛道") or {}).get("★★★alpha_t_NW")
            if isinstance(v, (int, float)) and ((v >= 1.96) if 向 > 0 else (v <= -1.96)):
                o.append(f"{r['臂']} (t={v})")
        return sorted(o)
    return {
        "★★★这一份是什么": "★ 老池那 45 条臂的**主基准（自己赛道买入持有）** —— 《110》第五节①；"
                     "★★ 《93 说明书》最后一块没有主基准的白",
        "★口径": {
            "★★★★★池子": "★ **老池研发池 198 只**（留出 49 只硬断言不进）—— "
                     "★★★ 和新池那条线（2,224 只）**不是一个池**；"
                     "★★ 《93 说明书》原来只写「混（老池流水+新池流水）」，没写 198 vs 2,224",
            "面板": "engine/cache/ohlcv_panel.parquet（300 只，★ engine 原生 cache，不装新池覆盖层）",
            "赛道": "matrices.build(cfg.raw, dev) 之后 apply_scope(m,'large_mid') 的 m.universe "
                  "—— ★★★ 和 run_friction_1104.run_one():411-413 同三行",
            "赛道指数": "每天对**前一天**在 universe 里、且这一天不脏的票取等权平均日收益，复利成净值",
            "★★★★★三处保护(规矩㊲)": f"剔脏日（四份并集，按**老池面板**现算）· "
                             f"成员下限 {JR.最少成员} 只 · 覆盖率 <{JR.最少覆盖:.0%} 整条不出数",
            "★脏日列名这件": "★★ 查实了：源头那三份按**代码名**读、再 pos.get 对到面板列 → "
                      "传老池面板就是对的，★★★ 不会静默少剔（老池 300 列有 237 列和新池同名）",
            "窗口": f"{M.PERF0.date()} → {M.PERF1.date()}",
            "摩擦": "★ 配置本体里的三档 friction_tiers（★★ 和 1104 那一轮同一份 yaml）",
            "❌赢随机": "不跑（已作废）—— ★★★ 这也是本份比 run_one 快一个量级的原因",
            "engine改动": "零",
        },
        "进度": {"臂总数": 总数, "已跑": len(recs),
               "出数": sum(1 for r in recs if "★跑失败" not in r)},
        "★★★对自己赛道_正显著": 显(+1),
        "★★★对自己赛道_负显著": 显(-1),
        "★★赛道算不出的": sorted(r["臂"] for r in recs
                           if "★算不出" in (r.get("★★★①主基准_对自己赛道") or {})),
        "逐臂": {r["臂"]: r for r in recs},
    }


def main(argv) -> int:
    上限 = 2
    if "--max" in argv:
        上限 = int(argv[argv.index("--max") + 1])
    only = argv[argv.index("--only") + 1] if "--only" in argv else None
    os.makedirs(ARMS, exist_ok=True)
    # ★★★★★ 两层覆盖都要装（★ 查代码定的：`run_friction_1104.py:566-567` 两行并排）——
    #   ★★ 本份第一版**只装了 pat6**，结果 8 条臂报 NotImplementedError / ValueError
    #      （`td_countdown_13_exit` · `day_low_minus_tick`）；
    #   ★★★ 我当时差点写成「现在的 engine 不认这两个类型了」—— ★ 规矩「先查代码再喊结论」救的：
    #      它们在 `engine/ops_exits_1029.py` 里，是**另一层运行时挂钩**，不装就不存在。
    pat6_ops.install()                 # ★ pat6 零件是运行时挂钩；非 pat6 类型原样转回
    ops_exits_1029.install()           # ★★★ 技-10 的 day_low_minus_tick / 技-13 的 td_countdown_13_exit
    tbl = F.chain_list()
    待 = [t for t in tbl
         if not os.path.exists(os.path.join(ARMS, JR.安全名(F.safe_name(t[0])) + ".json"))
         and (only is None or only in t[0])]
    print(f"★ 臂表 {len(tbl)} 条；待跑 {len(待)} 条；本轮最多 {上限} 条", flush=True)
    if not 待:
        io.open(OUT, "w", encoding="utf-8").write(
            json.dumps(汇总(len(tbl)), ensure_ascii=False, indent=1, default=str))
        print("★★★ 全部跑完 → 已出汇总", OUT, flush=True)
        return 0
    dev, hold, _ = F.load_pools()
    from engine import cache as ecache
    cl = ecache.field("close")
    vol = ecache.field("volume")
    print(f"★ 老池面板 {cl.shape[1]} 只 × {cl.shape[0]} 天；研发池 {len(dev)} / 留出 {len(hold)}",
          flush=True)
    脏缓 = 脏格老池(cl, vol)
    del vol; gc.collect()
    spy = data.load_benchmark("SPY")["close"]
    for label, yml, ov, group in 待[:上限]:
        名 = F.safe_name(label)
        fp = os.path.join(ARMS, JR.安全名(名) + ".json")
        try:
            rec = 一臂(名, yml, ov, group, dev, hold, cl, spy, 脏缓)
        except Exception as e:
            rec = {"臂": 名, "族": group, "配置": yml,
                   "★跑失败": f"{type(e).__name__}: {str(e)[:300]}",
                   "★回溯": traceback.format_exc(limit=4)[-800:]}
            print("  ✗✗✗", 名, type(e).__name__, str(e)[:160], flush=True)
        io.open(fp, "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        主 = rec.get("★★★①主基准_对自己赛道") or {}
        print(f"  {'✗' if '★跑失败' in rec else '✓'} {名[:44]:44s} "
              f"赛道alpha {主.get('alpha年pct')} t={主.get('★★★alpha_t_NW')} "
              f"{str(rec.get('★跑失败',''))[:46]} ({rec.get('耗时秒')}s)", flush=True)
        gc.collect()
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(汇总(len(tbl)), ensure_ascii=False, indent=1, default=str))
    print(f"★ 已跑 {len(glob.glob(os.path.join(ARMS,'*.json')))}/{len(tbl)} → {OUT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
