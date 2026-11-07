# -*- coding: utf-8 -*-
"""★★★ 第四档 · 挂环境开关 —— ★ 严格照《102》跑前预先登记（已定稿，一个字不许改）。

★ 三秒版：**同一条策略，一条不挂开关、一条挂开关，同一天同一批信号，逐日相减，看差别大不大。**

★★★ 口径（《102》第二节，规矩㊼ 五字段）：
   全收益（分红再投，两侧同口径）· 摩擦档跟原样臂完全一样 · **窗口 = B 段 2015-01-01~2025-12-31**
   （★★ 必须和原样臂同窗口，否则无法配对）· 池 = 并池2004 全量 3,858 只 · 标签滞后 1 天

★★★ 开关定义（《102》3.1，跑前写死，三个都不许调）：
   `regime.rules = [{type: index_above_ma, params: {symbol: SPY, ma: N}}]`
   `flatten_when_off: false`（★ 关闸只是不开新仓，不强制平掉已有仓）
   ★ 出处：Brock, Lakonishok & LeBaron (1992) —— 200 日均线是有文献出处的标准做法，
     ★★ 不是我们自己发明的阈值（红线①）。

★★★ 三点检验（《102》3.3 / 红线②）：**100 / 200 / 300 日**三档都跑，报三点是否同向。
   ★★ 并且**逐字节比流水哈希**确认三条真的不一样 ——
   ★ 1106 栽过一次：参数写在规则顶层会静默退回默认 200，三档流水逐字节相同
     （`engine/matrices.py:605` 的 1106 修已经把它改成 `p = rule.get("params", rule)`，
      ★★★ 但「修了」和「这次真的生效了」是两件事，必须自证 —— #80 的教训）。

★★★ 门槛（《102》第六节，跑前写死，不许报的时候放宽）：
   本档检验次数 = 3 族 × 3 个均线档 = **9 次** → 按 HLZ (2016) 取 **|t| > 3**。

★ 还要附的两样（《102》4.1）：① 关闸天数占比 ② 挂开关前后的持仓画像。
"""
from __future__ import annotations
import copy, hashlib, io, json, os, sys, time

import pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
for d in ("probe/friction_rerun_1104", "probe/v2_rerun_1030",
          "probe/选票层_1107", "probe/newpool_1106", "probe/并池_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.path.insert(0, HERE)
os.chdir(ROOT)
from engine import cache, data, pool_scope, pat6_ops                 # noqa: E402
import rerun_core_1030 as RC                                        # noqa: E402
import 回看期覆盖层_1107 as OV                                       # noqa: E402
import 接新基准_1107 as BM                                          # noqa: E402
import 分红覆盖层_1107 as DV                                         # noqa: E402
import 日序列覆盖层_1107 as DS                                        # noqa: E402
import 跳过基准一_1107 as SK                                          # noqa: E402
pat6_ops.install()

SRC = os.path.join(ROOT, "engine", "configs")
CFGDIR = os.path.join(HERE, "configs")
ARMS = os.path.join(HERE, "arms_1107")
PANEL = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
POOLTAB = "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"
代表 = {"大波段": "技-1.yaml", "突破": "技-6-原著.yaml", "震荡": "技-14-原著.yaml"}
均线三点 = [100, 200, 300]          # ★★★ 红线②：相邻三点，报是否同向
窗口名, 窗口起, 窗口止 = "B_2015到2025", "2015-01-01", "2025-12-31"
OUT = os.path.join(HERE, "第四档_挂环境开关_结果_1107.json")


def 臂路径(label):
    return os.path.join(ARMS, f"a_{hashlib.sha256(label.encode()).hexdigest()[:16]}.json")


def main() -> int:
    t0 = time.time()
    OV.install()
    旧TR = data.TOTAL_RETURN_DEFAULT
    data.TOTAL_RETURN_DEFAULT = True
    print(f"★★★ 全收益口径：TOTAL_RETURN_DEFAULT {旧TR} → {data.TOTAL_RETURN_DEFAULT}", flush=True)
    assert data.TOTAL_RETURN_DEFAULT is True, "★★★ 全收益没打开，停"
    自证基准 = BM.install()
    assert 自证基准["★★★基准自证"]["SPY"].startswith("2004-"), "★★★ SPY 没拉到 2004，停"

    wide = pd.read_parquet(PANEL)
    预热 = pd.Timestamp(窗口起) - pd.Timedelta(days=640)
    wide = wide.loc[(wide.index >= 预热) & (wide.index <= pd.Timestamp(窗口止))]
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path=POOLTAB)
    data.PERF_START, data.PERF_END = 窗口起, 窗口止
    dev = sorted(cache._PANEL["close"].columns)
    自证分红 = DV.install(需覆盖=dev)
    assert 自证分红["★★★基准侧分红"]["SPY"].startswith("90 条"), "★★★ 基准侧分红空转，停"

    import run_friction_1104 as F                                   # noqa: E402
    自证日序列 = DS.install(); assert 自证日序列["★真的换掉了"]
    自证跳过 = SK.install(); assert 自证跳过["★真的换掉了"]
    F.CONFIG_DIR = CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_1107")
    F.OUT = OUT
    for d in (CFGDIR, ARMS, F.PER_CHAIN, F.LEDGERS):
        os.makedirs(d, exist_ok=True)
    hold = json.load(io.open("probe/新策略_1106/holdout_newpool_1106.json", encoding="utf-8"))
    F.load_pools = lambda d=dev, h=set(): (d, h, hold)

    # ★★★ 关闸天数占比（《102》4.1 ①）—— ★ 三档各报一次；情形三：<5% 或 >50% 整档作废
    闸 = {}
    b = data.load_benchmark("SPY")["close"]
    idx = cache._PANEL["close"].loc[窗口起:窗口止].index
    bb = b.reindex(idx).ffill()
    for n in 均线三点:
        on = (bb > bb.rolling(n, min_periods=n).mean()).shift(1).fillna(False)
        闸[f"ma{n}"] = {"开闸天数占比": round(float(on.mean()), 4),
                       "★★★关闸天数占比": round(float(1 - on.mean()), 4)}
    print(f"★★★ 关闸天数占比: {json.dumps(闸, ensure_ascii=False)}", flush=True)

    报 = {"★★★这一档是什么": __doc__.strip()[:1800],
         "【本次口径】": ("全收益（分红再投，两侧同口径）· 摩擦档跟原样臂一致 · "
                    f"窗口 {窗口起}~{窗口止} · 池 并池2004 全量 {len(dev)} 只 · 标签滞后 1 天"),
         "★★★关闸天数占比": 闸, "★门槛": "|t| > 3（9 次检验，HLZ 2016）—— 跑前写死",
         "结果": [], "失败明细": [], "★流水哈希": {}}

    for 族, fn in 代表.items():
        base = yaml.safe_load(io.open(os.path.join(SRC, fn), encoding="utf-8"))
        assert not (base.get("regime") or {}).get("rules"), \
            f"★★★ {fn} 原样臂的 regime.rules 本来就不空，这一档的「不挂开关」前提不成立，停"
        for n in 均线三点:
            raw = copy.deepcopy(base)
            raw["regime"] = {"rules": [{"type": "index_above_ma",
                                        "params": {"symbol": "SPY", "ma": n}}],
                             "flatten_when_off": False,
                             "source": "《102》3.1 跑前写死 · Brock/Lakonishok/LeBaron 1992"}
            label = f"{窗口名}·并池2004·{族}·{fn[:-5]}·B挂闸{n}日"
            tmp = f"_g4_{族}_ma{n}.yaml"
            io.open(os.path.join(CFGDIR, tmp), "w", encoding="utf-8").write(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            p = 臂路径(label)
            if os.path.exists(p) and DS.已有(label):
                报["结果"].append(json.load(io.open(p, encoding="utf-8"))); continue
            DS.开始新臂(label)
            print(f"▶ {label}", flush=True)
            try:
                r = F.run_one(label, tmp, None, "第四档_1107", dev, set(), {})
            except Exception as e:
                报["失败明细"].append({"臂": label, "错": f"{type(e).__name__}: {e}"})
                print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True); continue
            rec = {"链": label, "池": "并池2004", "族": 族, "臂": f"B挂闸{n}日",
                   "笔数": r["笔数"], "每笔净R": r["每笔净R"], "每笔毛R": r["每笔毛R"],
                   "净盈亏": r["★真链美元"]["净盈亏"], "摩擦": r["★真链美元"]["摩擦总额"]}
            io.open(p, "w", encoding="utf-8").write(
                json.dumps(rec, ensure_ascii=False, indent=1, default=str))
            报["结果"].append(rec)
            print(f"   ✓ B挂闸{n}日 笔数 {r['笔数']} 每笔净R {r['每笔净R']:+.4f}", flush=True)
            # ★★★ 逐字节比流水哈希 —— 自证这三档**真的不一样**（1106 栽过）
            lp = os.path.join(F.LEDGERS, f"REAL__{F.safe_name(label)}.csv")
            if os.path.exists(lp):
                报["★流水哈希"][label] = hashlib.sha256(
                    io.open(lp, "rb").read()).hexdigest()[:16]
            io.open(OUT, "w", encoding="utf-8").write(
                json.dumps({**报, "★进行中": True}, ensure_ascii=False, indent=1, default=str))

    # ★★★ 三档流水必须互不相同
    h = 报["★流水哈希"]
    报["★★★三档流水是否真的不同"] = {}
    for 族 in 代表:
        hs = {k: v for k, v in h.items() if f"·{族}·" in k}
        报["★★★三档流水是否真的不同"][族] = (
            f"{len(set(hs.values()))}/{len(hs)} 个不同的哈希"
            + ("  ✅" if len(set(hs.values())) == len(hs) and hs else
               "  ⛔ 有重复 → 参数没生效，这一档作废（1106 同类错）"))
    报["★★★失败条数"] = len(报["失败明细"])
    报["★用时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完;★★★ 失败 {len(报['失败明细'])} 条;"
          f"三档是否不同: {json.dumps(报['★★★三档流水是否真的不同'], ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
