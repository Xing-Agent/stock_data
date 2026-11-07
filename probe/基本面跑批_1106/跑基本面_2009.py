# -*- coding: utf-8 -*-
"""
★★★ 《99》+《103》A 路:基本面 23 条 · 并池2004(3858,一档)× 2009~2025 · 全收益 —— ★ 可续跑。

【本次口径】全收益 · 摩擦档 三档 5/15/30bp 单边 · 窗口 2009-01-01~2025-12-31 · 池 并池2004(3858,一档) · 标签滞后 1 天

★ 和 跑基本面_1107.py 比,改了这几件(《103》三处更正):
  ① 全收益:`data.TOTAL_RETURN_DEFAULT = True`(断言)+ ★★★ 补分红覆盖层(补分红_1107.py)——
     不补的话策略侧一分钱分红都收不到(manifest 只有 300 只),等于只给基准加了分(规矩㊽)
  ② 窗口 2009-01-01~2025-12-31(★ 财报库只能从 2009 起 —— 行情虽然能到 2004,★★ 不许写成 2004 起)
     面板按窗口裁行,前面多留 440 个交易日预热(《103》第四节);不改 dtype
  ③ 面板 probe/并池2004_1107/ · 池表 pool_MERGED2004_ALL_1107.csv · 名单 = 全量 3858(一档,不留留出池)
  ④ 基准覆盖层(接新基准_1107)装上:SPY 2004 起(★ 茨威格红绿灯要用)
  ⑤ 随机对照 100 次(规矩㊸ v2),报分位数,不报「均值 ± 2 标准差」(Gemini 清单第 11 条)
★ 「标签滞后 1 天」= 财报公布日 + 1 个交易日才生效(pit.effective);环境闸用昨收(引擎 regime 末行 shift(1))。
"""
from __future__ import annotations
import copy, io, json, os, subprocess, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import 跑基本面_1106 as R0                                       # noqa: E402
import 跑基本面_1107 as R1                                       # noqa: E402

PANEL = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
POOL = "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"
PERF_START, PERF_END = "2009-01-01", "2025-12-31"
预热 = 440
ARMS = os.path.join(HERE, "arms_2009")
LED = os.path.join(HERE, "ledgers_2009")
口径行 = ("【本次口径】全收益 · 摩擦档 三档 5/15/30bp 单边 · 窗口 2009-01-01~2025-12-31 · "
         "池 并池2004(3858,一档) · 标签滞后 1 天")
N随机 = 100


def 装层():
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    for d in ("probe/补齐能力_1106", "probe/基本面跑批_1106", "probe/v2_rerun_1030",
              "probe/friction_rerun_1104", "probe/并池_1107"):
        sys.path.insert(0, os.path.join(ROOT, d))
    import pandas as pd
    from engine import cache, data, pool_scope, pat6_ops
    pat6_ops.install()
    import 接新基准_1107 as BM
    bm = BM.install()
    import 接新财报库_1106 as EXT, 瘦身财报库_1106 as SLIM, 补股数闸_1106 as SHARE
    import 基本面零件_1106 as PARTS, 策略零件_1106 as MINE, 补分红_1107 as DIV
    import rerun_core_1030 as RC
    a = EXT.install(); b = SLIM.install(); e = SHARE.install(); c = PARTS.install(); d = MINE.install()
    wide = pd.read_parquet(PANEL)
    idx = wide.index
    i0 = max(0, int(idx.searchsorted(pd.Timestamp(PERF_START))) - 预热)
    i1 = int(idx.searchsorted(pd.Timestamp(PERF_END), side="right"))
    wide = wide.iloc[i0:i1]                                       # ★ 按窗口裁行,不改 dtype
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    del wide
    RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path=POOL)
    data.PERF_START, data.PERF_END = PERF_START, PERF_END
    data.TOTAL_RETURN_DEFAULT = True
    assert data.TOTAL_RETURN_DEFAULT is True, "★★★ 全收益没打开"
    div = DIV.install()
    assert all(v > 0 for v in div["★★自证·六只的分红条数"].values()), f"★★★ 分红还是空的:{div}"
    close = cache._PANEL["close"]
    return RC, {"财报库": a.get("★家数"), "瘦身": b.get("只数"), "股数闸": e,
                "零件": len(c.get("★★新规则") or []), "本路": d.get("新规则"),
                "★★★分红自证": div, "★基准": (bm.get("★★★基准自证") or {}).get("SPY"),
                "★面板裁行": f"{close.index[0].date()} → {close.index[-1].date()}({len(close)} 天,"
                           f"含 {预热} 天预热)",
                "★TOTAL_RETURN_DEFAULT": data.TOTAL_RETURN_DEFAULT}


def 净值年化(res, n_days):
    """★★★ 全收益只体现在**净值**里:引擎把分红记成现金(chain.py:493 起),★ 不写进逐笔流水。
       → 逐笔的数(每笔净R、资金年化)**永远是纯价格口径**;★ 含分红的只有这个。"""
    eq = res.equity.dropna()
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return None
    return round(((float(eq.iloc[-1]) / float(eq.iloc[0])) ** (252 / max(1, n_days)) - 1) * 100, 3)


def 跑一条(arm: dict) -> dict:
    import numpy as np, pandas as pd, yaml
    RC, 层 = 装层()
    from engine import chain, matrices, data, cache
    syms = list(cache._PANEL["close"].columns)
    raw = yaml.safe_load(io.open(os.path.join(R0.CFG, arm["配置"]), encoding="utf-8"))
    raw = copy.deepcopy(raw)
    for k, v in arm["覆盖"].items():
        R0._设(raw, k, v)
    脏 = json.load(io.open(os.path.join(HERE, "假跳变_并池2004_1107.json"), encoding="utf-8"))["脏日"]
    t0 = time.time()
    cfg = chain.ChainConfig.from_dict(raw)
    m = matrices.build(cfg.raw, syms)
    scope = RC.apply_scope(m, R0.SCOPE)
    t1 = time.time()
    res = chain.run_chain(cfg, syms, PERF_START, PERF_END, m=m)
    led = res.ledger
    os.makedirs(LED, exist_ok=True)
    lp = os.path.join(LED, f"REAL__{R0.安全名(arm['臂'])}.csv")
    led.to_csv(lp, index=False)
    n_days = int(len(data.perf_window(m.index, PERF_START, PERF_END)))
    事 = R1.事实(led, 脏)
    # ★ 换手率按本窗口天数重算(R1 里写死的是 2016 窗口的 2514 天)
    if len(led):
        在场 = float(led["capital_days"].sum()) / n_days
        事["年换手率(倍)"] = round((float(led["notional_in"].sum()) / (n_days / 252)) / 在场, 2) if 在场 else None
    rec = {"★本次口径": 口径行, "臂": arm["臂"], "配置": arm["配置"], "覆盖": arm["覆盖"], "档": arm["档"],
           "★★★池子": "并池2004(3858,一档)", "★★★窗口": "2009-01-01~2025-12-31", "★层": 层,
           "名单只数": len(syms), "口径": f"{R0.SCOPE}(池表 {POOL})", "universe收窄": scope,
           "合格票日(universe)": int(m.universe.sum()), "绩效窗口交易日": n_days,
           "建矩阵秒": round(t1 - t0, 1),
           "★结论行": "窗口不够(2009~2025,不足一个完整估值周期)—— 本行只能当方向,不能当成绩。",
           "事实": 事,
           "★★★净值年化pct(全收益,含分红)": 净值年化(res, n_days),
           "★分红入账(引擎留言)": [x for x in res.notes if "分红口径" in x],
           "★★逐笔数的口径": "每笔净R / 资金年化 = 纯价格(★ 引擎的分红只进净值,不进流水)"}
    rs, keep = [], m.rank_score.copy()
    for k in range(N随机):
        sd = 1000003 * (k + 1)
        rng = np.random.default_rng(sd)
        m.rank_score = rng.random(keep.shape)
        rr = chain.run_chain(cfg, syms, PERF_START, PERF_END, m=m)
        r2 = rr.ledger
        rs.append({"种子": sd, "笔数": int(len(r2)), "资金年化pct": R1.资金年化(r2),
                   "净值年化pct": 净值年化(rr, n_days),
                   "每笔净R(均值)": (round(float(r2["r_multiple_net"].astype(float).mean()), 5)
                                 if len(r2) else None)})
    m.rank_score = keep
    def 分位(key, me):
        va = np.array([x[key] for x in rs if x[key] is not None], dtype=float)
        if not len(va):
            return None
        return {"2.5%": round(float(np.quantile(va, .025)), 3), "中位": round(float(np.median(va)), 3),
                "97.5%": round(float(np.quantile(va, .975)), 3),
                "★★本臂排第几分位": round(float((va < me).mean()), 3) if me is not None else None}
    rec["★随机先买谁·100次"] = {
        "★★★净值年化(全收益)": 分位("净值年化pct", rec["★★★净值年化pct(全收益,含分红)"]),
        "资金年化(纯价格,逐笔)": 分位("资金年化pct", 事.get("★资金年化pct(扣摩擦)")),
        "★读法": "★★ 只报事实:落在随机 2.5%~97.5% 之间 =「和随机挑分不出」(规矩㊸ v2);★ 本轮不下结论",
        "逐个": rs,
    }
    return rec


def 臂文件(name):
    return os.path.join(ARMS, f"{R0.安全名(name)}.json")


def main(argv) -> int:
    if "--arm" in argv:
        name = argv[argv.index("--arm") + 1]
        arm = next(a for a in R0.臂表() if a["臂"] == name)
        os.makedirs(ARMS, exist_ok=True)
        try:
            rec = 跑一条(arm)
        except Exception as e:
            rec = {"★本次口径": 口径行, "臂": name, "★★★跑失败": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-3000:]}
        io.open(臂文件(name), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("✗ " if "★★★跑失败" in rec else "✓ ") + name, flush=True)
        return 0
    if "--all" in argv:
        k, n = (map(int, argv[argv.index("--part") + 1].split("/")) if "--part" in argv else (0, 1))
        for i, a in enumerate(R0.臂表()):
            if i % n != k:
                continue
            if os.path.exists(臂文件(a["臂"])):
                continue
            t = time.time()
            r = subprocess.run([sys.executable, __file__, "--arm", a["臂"]], cwd=ROOT)
            if not os.path.exists(臂文件(a["臂"])):
                io.open(臂文件(a["臂"]), "w", encoding="utf-8").write(json.dumps(
                    {"★本次口径": 口径行, "臂": a["臂"],
                     "★★★跑失败": f"子进程退出码 {r.returncode}(多半是 OOM 或环境被关)"}, ensure_ascii=False))
            print(f"   {a['臂']}  {time.time()-t:.0f}s", flush=True)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
