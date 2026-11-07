# -*- coding: utf-8 -*-
"""
★★★ 《99》A 路:基本面在**并池 3834 × 2016~2025** 上重跑(★ 可续跑,一条臂一个子进程)。

★ 和 1106 那份(跑基本面_1106.py)比,只换这几件(★ 其余 import 那份,配置一份不改):
  · 面板   probe/并池_1107/ohlcv_panel_newpool.parquet(3,834 只)
  · 名单   ★★★ 面板里的**全部**股票(★ 不再用老研发池 2,224 只的名单 —— 那份里没有巨头)
  · 池表   ★★★ 本目录 pool_并池3834_1107.csv(★ 老池表里没有考卷那批,见 建并池池表_1107.py)
  · 窗口   PERF_START = 2016-01-04(《96》)
  · 尺子   ★ 不量「好不好」(《99》3.5:窗口不够,不下结论)—— 只记事实:笔数 / 每笔净R / 净盈亏 / 摩擦 /
          持有期分布 / 换手率 / 期末持仓 / 跨过假跳变的笔
  · ★★★ 规矩㊸ 噪声对照:同一套矩阵,把「先买谁」换成随机,跑 10 个种子 → 报均值和标准差
          (★ 矩阵只建一次,随机臂只重跑链,每个约 2 秒)
  · 流水   ledgers_1107/(★ 不入库,跑完压 gz 归档)
★★ 没有止损(原著没有)→ 引擎的 R = 每笔收益率(风险 = 进场价)。「每笔净R」就是**每笔扣摩擦后的收益率**。
"""
from __future__ import annotations
import copy, glob, io, json, os, subprocess, sys, time, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import 跑基本面_1106 as R0                                       # noqa: E402

R0.NEWPANEL = "probe/并池_1107/ohlcv_panel_newpool.parquet"
R0.NEWPOOL = os.path.relpath(os.path.join(HERE, "pool_并池3834_1107.csv"), ROOT)
R0.PERF_START = "2016-01-04"
ARMS = os.path.join(HERE, "arms_1107")
LED = os.path.join(HERE, "ledgers_1107")
池字段, 窗字段 = "并池3834", "2016-01-04~2025-12-31"
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
END = "2025-12-31"


def 事实(led, 脏: dict) -> dict:
    import numpy as np, pandas as pd
    if not len(led):
        return {"笔数": 0}
    hd = led["holding_days"].astype(float)
    ed = pd.to_datetime(led["exit_date"]).dt.strftime("%Y-%m-%d")
    末 = (led["reason"] == "退市结算") & (ed == END)
    真退 = (led["reason"] == "退市结算") & (ed != END)
    # ★ 换手率 = 年均买入金额 ÷ 平均在场资金(capital_days 之和 ÷ 交易日数)
    n_days = 2514
    在场 = float(led["capital_days"].sum()) / n_days
    年数 = n_days / 252
    换手 = (float(led["notional_in"].sum()) / 年数) / 在场 if 在场 > 0 else None
    跨 = []
    for s, a, b in zip(led["symbol"], led["entry_date"], led["exit_date"]):
        ds = 脏.get(str(s))
        if not ds:
            跨.append(False); continue
        a0 = pd.Timestamp(str(a)[:10]) - pd.Timedelta(days=15)
        b0 = pd.Timestamp(str(b)[:10]) + pd.Timedelta(days=15)
        跨.append(any(a0 <= pd.Timestamp(d) <= b0 for d in ds))
    跨 = np.array(跨)
    rn = led["r_multiple_net"].astype(float)
    return {
        "笔数": int(len(led)), "不同股票数": int(led["symbol"].nunique()),
        "每笔净R(均值)": round(float(rn.mean()), 5), "每笔净R(中位)": round(float(rn.median()), 5),
        "每笔毛R(均值)": round(float(led["r_multiple"].astype(float).mean()), 5),
        "净盈亏美元": round(float(led["net_pnl"].sum()), 0),
        "摩擦美元": round(float(led["friction_cost"].sum()), 0),
        "持有交易日": {k: float(v) for k, v in hd.quantile([.1, .25, .5, .75, .9]).round(1).items()},
        "持有交易日(均值)": round(float(hd.mean()), 1),
        "年换手率(倍)": round(换手, 2) if 换手 else None,
        "离场原因": led["reason"].value_counts().to_dict(),
        "★期末还拿着(引擎记成退市结算)": int(末.sum()), "★真退市结算": int(真退.sum()),
        "★跨过疑似假跳变的笔": int(跨.sum()),
        "★剔掉这些笔后每笔净R(均值)": round(float(rn[~跨].mean()), 5) if (~跨).any() else None,
        "进场年份": pd.to_datetime(led["entry_date"]).dt.year.value_counts().sort_index()
                     .astype(int).to_dict(),
        "巨头进过几笔(AAPL/MSFT/AMZN/JPM/BRK.B/AVGO/NVDA)": int(led["symbol"].isin(
            ["AAPL", "MSFT", "AMZN", "JPM", "BRK.B", "AVGO", "NVDA"]).sum()),
    }


def 跑一条(arm: dict) -> dict:
    import numpy as np, pandas as pd, yaml
    RC, 层 = R0.装层()
    from engine import chain, matrices, data, cache
    syms = [s for s in cache._PANEL["close"].columns]
    raw = yaml.safe_load(io.open(os.path.join(R0.CFG, arm["配置"]), encoding="utf-8"))
    raw = copy.deepcopy(raw)
    for k, v in arm["覆盖"].items():
        R0._设(raw, k, v)
    脏 = json.load(io.open(os.path.join(HERE, "假跳变_并池_1107.json"), encoding="utf-8"))["脏日"]
    t0 = time.time()
    cfg = chain.ChainConfig.from_dict(raw)
    m = matrices.build(cfg.raw, syms)
    scope = RC.apply_scope(m, R0.SCOPE)
    t1 = time.time()
    res = chain.run_chain(cfg, syms, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger
    os.makedirs(LED, exist_ok=True)
    lp = os.path.join(LED, f"REAL__{R0.安全名(arm['臂'])}.csv")
    led.to_csv(lp, index=False)
    rec = {"臂": arm["臂"], "配置": arm["配置"], "覆盖": arm["覆盖"], "档": arm["档"],
           "★★★池子": 池字段, "★★★窗口": 窗字段, "★层": 层,
           "名单只数": len(syms), "口径": f"{R0.SCOPE}(池表 {R0.NEWPOOL})",
           "universe收窄": scope,
           "合格票日(universe)": int(m.universe.sum()),
           "建矩阵秒": round(t1 - t0, 1),
           "★结论行": "窗口不够(2016~2025,不足一个完整估值周期)—— 本行只能当方向,不能当成绩。",
           "事实": 事实(led, 脏)}
    # ★★★ 规矩㊸:只换「先买谁」为随机,其余矩阵一模一样
    rs, keep = [], m.rank_score.copy()
    for sd in 种子:
        rng = np.random.default_rng(sd)
        m.rank_score = rng.random(keep.shape)
        r2 = chain.run_chain(cfg, syms, data.PERF_START, data.PERF_END, m=m).ledger
        rs.append({"种子": sd, "笔数": int(len(r2)),
                   "每笔净R(均值)": (round(float(r2["r_multiple_net"].astype(float).mean()), 5)
                                 if len(r2) else None)})
    m.rank_score = keep
    v = [x["每笔净R(均值)"] for x in rs if x["每笔净R(均值)"] is not None]
    rec["★随机先买谁·10种子"] = {
        "逐个": rs,
        "每笔净R均值": round(float(np.mean(v)), 5) if v else None,
        "每笔净R标准差": round(float(np.std(v, ddof=1)), 5) if len(v) > 1 else None,
        "★★本臂减随机均值": (round(rec["事实"].get("每笔净R(均值)", np.nan) - float(np.mean(v)), 5)
                         if v and rec["事实"].get("笔数") else None),
        "★读法": "差距小于一个标准差 → 「分不出」(规矩㊸);★ 本轮不下结论,只报这个数",
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
            rec = {"臂": name, "★★★池子": 池字段, "★★★窗口": 窗字段,
                   "★★★跑失败": f"{type(e).__name__}: {e}", "traceback": traceback.format_exc()[-3000:]}
        io.open(臂文件(name), "w", encoding="utf-8").write(
            json.dumps(rec, ensure_ascii=False, indent=1, default=str))
        print(("✗ " if "★★★跑失败" in rec else "✓ ") + name, flush=True)
        return 0
    if "--all" in argv:
        # ★ --part k/n:两个工人分单双号跑(★ 每条臂峰值约 2.5GB,两个约 5GB < 7GB;不会重复跑同一条)
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
                    {"臂": a["臂"], "★★★池子": 池字段, "★★★窗口": 窗字段,
                     "★★★跑失败": f"子进程退出码 {r.returncode}(多半是 OOM 或环境被关)"},
                    ensure_ascii=False))
            print(f"   {a['臂']}  {time.time()-t:.0f}s", flush=True)
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
