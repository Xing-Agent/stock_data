# -*- coding: utf-8 -*-
"""
★★★ 重测第一批 —— ★ 老池 vs 并池，**同窗口 2016~2025**（《98》第三节第 1 条）。

★★ 为什么必须同窗口：并池带来的代价是窗口从 2015 缩到 2016（考卷那批数据只有 2016 起）。
  ★★★ 如果老池跑 2015~2025、并池跑 2016~2025，那差异里混了「窗口变短」——
  ★ 分不清是「巨头进来」还是「少了一年」造成的。

★★★ 跑前预先登记（写死，不许事后改；★ 按规矩㊸ v2 改过）：
  · **主判据 = 条件 alpha（交互项回归）**：策略日收益 ~ 指数日收益 + 环境×指数日收益，
    ★ 看**交互项**的 Newey-West t，门槛 **|t| > 2.5**（Gemini 第 50 轮给的）。
    ★★ 这一道只产生**一个 t 值** → 多重检验的问题消失，也不用挑「哪一段」。
  · ★★★ **「A 比 B 好」一律先做配对检验**（同一天同一批信号逐日相减），
    ★ 配对没做之前，一律写「**待配对检验**」—— 不许写「更好」，也不许写「分不出」。
  · ★★ 随机对照（本批 10 个种子）回答的是**另一个**问题：「这个旋钮本身有没有用」；
    ★★★ 比的时候用**随机单次的标准差**，不是均值的标准误（★ #73 我在这里用错过）。
  · ★ 池子/窗口两个字段必须跟着每一个数走。
  · ★★★ 预先写下两种结果各对应什么话（Lin 1107 17:26 的核心判断）：
    · 趋势/突破类交互项 **t > 2.5 且为正**、震荡类**符号相反**
      → ★★ 「**不同环境配不同策略**」这个判断**有实测支持**
    · 两类交互项**都测不出** → ★★★ **不是环境不重要，是「我们这批实现」对环境不敏感**
      → ★ 那时候该改的是**策略的实现**，不是继续修测法
  · engine 零改动（进程内覆盖层）；可续跑

★ 本批跑哪几条（★★ 照 B 路拍板的优先顺序）：
  大波段·技-1 · 突破·技-6-原著 · 震荡·技-14-原著 · 融-2_突破
"""
from __future__ import annotations
import copy, io, json, os, sys, time
import pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
for d in ("probe/friction_rerun_1104", "probe/v2_rerun_1030",
          "probe/选票层_1107", "probe/newpool_1106"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
os.chdir(ROOT)
from engine import cache, data, pool_scope, pat6_ops            # noqa: E402
import rerun_core_1030 as RC                                    # noqa: E402
import 回看期覆盖层_1107 as OV                                   # noqa: E402
import 接新基准_1107 as BM                                      # noqa: E402
import 分红覆盖层_1107 as DV                                     # noqa: E402
sys.path.insert(0, HERE)
import 日序列覆盖层_1107 as DS                                    # noqa: E402
import 跳过基准一_1107 as SK                                      # noqa: E402
import 面板元信息覆盖层_1107 as MT                                 # noqa: E402
pat6_ops.install()

SRC = os.path.join(ROOT, "engine", "configs")
CFGDIR = os.path.join(HERE, "configs")
ARMS = os.path.join(HERE, "arms_1107")
OUT = os.path.join(HERE, f"重测结果_{os.environ.get('XING_WIN_NAME','B')}_1107.json")
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"

池 = {"并池2004": ("probe/并池2004_1107/ohlcv_panel_newpool.parquet",
                 # ★★★ 池表必须换成 22 年那张 —— ★ 老池表里考卷股是 0/1042，
                 #   universe 掩膜会把苹果微软全排除（《24》#74）
                 "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv")}
代表 = {"大波段": "技-1.yaml", "突破": "技-6-原著.yaml",
       "震荡": "技-14-原著.yaml"}
随机种子 = [424242, 20181001, 20220101, 777013, 31337,
         90210, 10007, 31415926, 27182818, 65537]      # ★ 10 个（时间换覆盖面）
# ★★★ 22 年一次跑不动（机器 7 GB，10 年 × 2,807 只峰值就 3.3 GB，
#   22 年 × 3,858 只约需 9 GB → OOM 被杀，exit 137）。
# ★★ 所以切成两段，★★★ 而且这正好是最简单的那种「滚动前推」：
#   A 段挑参数 / B 段只验证 —— 本来就是规矩㊸v2 第 4 条要求的一道检验。
窗口 = {"A_2004到2014": ("2004-01-02", "2014-12-31"),
       "B_2015到2025": ("2015-01-01", "2025-12-31")}
窗口起 = os.environ.get("XING_WIN_START", "2015-01-01")
窗口止 = os.environ.get("XING_WIN_END", "2025-12-31")
窗口名 = os.environ.get("XING_WIN_NAME", "B_2015到2025")


def 可买名单(名: str) -> list:
    """★★★ 一档：全量可买，不再留静态留出池（Lin 1107 16:58 问出来的）。

    ★★ 原来这里用的是旧的「研发池 2,224 只」当可买名单 ——
      ★★★ 而并池新进来的 1,035 只（含苹果微软）**不在那份名单里** → 一只都买不到，
      那样跑完等于白跑：面板里有巨头，但策略碰不到它们。
    ★ B 路拍板原文：「以后还要不要留一份历史考卷：**不留**。
      往后跑的模拟盘就是考卷。需要样本外检验的地方，用滚动前推或 CPCV。」
    ★★ 所以两边都改成**全量可买**，这样差异才只来自「池子大小和成分」。
    """
    return sorted(cache._PANEL["close"].columns)


def 装池(名: str) -> dict:
    """★★★ 按窗口切片再喂给引擎 —— ★ 否则 OOM（机器只有 7 GB）。

    ★★ 真因：面板是 **5,747 天 × 3,858 只**（444 MB parquet，展开约 1 GB），
      ★ 而一次回测只用其中十年 → ★★★ 整张加载是浪费，而且直接撑爆内存
      （exit 137，今天栽了两次）。
    ★ 做法：读进来之后**立刻按窗口裁掉用不到的行**，再放进 `cache._PANEL`。
      ★★ 多留 400 个交易日的「预热期」，★★★ 因为 200 日均线这类指标要回看
      —— 裁太紧会让窗口开头的指标全是 NaN。
    ★★ 不改 dtype（★ 保持 float64，免得和之前的结果产生精度差异）。
    """
    panel, pooltab = 池[名]
    wide = pd.read_parquet(panel)
    预热 = pd.Timestamp(窗口起) - pd.Timedelta(days=640)   # ★ 约 440 个交易日
    keep = (wide.index >= 预热) & (wide.index <= pd.Timestamp(窗口止))
    裁前, 裁后 = len(wide), int(keep.sum())
    wide = wide.loc[keep]
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    idx = pool_scope.PoolIndex(path=pooltab)
    RC._IDX_CACHE["idx"] = idx
    data.PERF_START = 窗口起                             # ★★★ 两段各自的窗口
    data.PERF_END = 窗口止
    close = cache._PANEL["close"]
    # ★★★ 1107 夜补：第五个登记点 —— panel_meta。
    #   ★ 不补的话 `cache.panel_meta()` 读的是老的 300 只那份，而且 A 段会在
    #     `matrices.py:1296 idx.get_loc(zero_bar)` 上 KeyError → **整段 33 条臂全废**。
    #   ★★ 全文（含「为什么置空是对的」「为什么动不到数」）见 面板元信息覆盖层_1107.py。
    自证meta = MT.install(os.path.join(ROOT, "probe", "并池2004_1107",
                                     "panel_meta_newpool.parquet"))
    print(f"★★★ 面板元信息覆盖层: {json.dumps(自证meta, ensure_ascii=False)}", flush=True)
    assert 自证meta["★真的换掉了"], "★★★ panel_meta 覆盖层没装上，停"
    有 = [t for t in ("AAPL", "MSFT", "AMZN", "BRK.B", "JPM") if t in close.columns]
    return {"池": 名, "★★★窗口": 窗口名, "面板只数": int(close.shape[1]),
            "★★★面板裁剪": f"{裁前} 天 → {裁后} 天（含 440 个交易日预热）",
            "★池表": os.path.basename(pooltab), "池表行数": idx.rows,
            "★★★窗口起": data.PERF_START, "PERF_END": data.PERF_END,
            "★★★可买名单": f"全量 {close.shape[1]} 只（★ 一档，无静态留出池）",
            "★★★面板元信息(第五个登记点)": 自证meta,
            "★巨头在不在": {"查的5只里有几只": len(有), "明细": 有}}


def 臂路径(label):
    import hashlib
    return os.path.join(ARMS, f"a_{hashlib.sha256(label.encode()).hexdigest()[:16]}.json")


def main() -> int:
    t0 = time.time()
    OV.install()
    # ★★★ 全收益口径（Gemini 第 55 轮补 · 尺子清单第 10 条）
    #   ★ 引擎 10-29 就支持了，但 `TOTAL_RETURN_DEFAULT = False`，
    #     而我们的配置和跑批**从来没传过它** → ★★ 所有旧结果都是价格口径。
    #   ★★★ 实测 SPY 2015~2025：价格 **+11.55%/年** vs 全收益 **+13.46%/年**
    #     = 差 **1.91 个百分点/年**（十一年累计约 23%）。
    #   ★ 我们平均敞口只有 50~70% → 少收的分红约 1.1%/年
    #     → ★★★ **价格口径让我们好看约 0.8 个百分点/年**。
    #   ★★ `run_one` 不收这个参数 → 走 chain.py 的默认开关（它在 total_return is None 时读）。
    旧TR = data.TOTAL_RETURN_DEFAULT
    data.TOTAL_RETURN_DEFAULT = True
    print(f"★★★ 全收益口径：TOTAL_RETURN_DEFAULT {旧TR} → {data.TOTAL_RETURN_DEFAULT}", flush=True)
    assert data.TOTAL_RETURN_DEFAULT is True, "★★★ 全收益口径没打开，停"
    # ★★★ 基准也要换成 2004 版，否则日历还卡在 2014（engine 零改动）
    自证基准 = BM.install()
    print("★ 基准覆盖层:", json.dumps(自证基准, ensure_ascii=False), flush=True)
    # ★ 覆盖层改成自动扫目录后，返回字段从 ★★★SPY 改成了 ★★★基准自证（#75）
    _spy = 自证基准["★★★基准自证"]["SPY"]
    assert _spy.startswith("2004-"), f"★★★ SPY 没拉到 2004（{_spy}），停"
    for _k in ("VIX", "DTB3"):
        print(f"   ★ {_k}: {自证基准['★★★基准自证'].get(_k)}", flush=True)
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    for d in (CFGDIR, ARMS):
        os.makedirs(d, exist_ok=True)
    import run_friction_1104 as F                                # noqa: E402
    # ★★★ 1107 夜补：存每日净值/敞口 —— ★ 没有它，本脚本**自己写死的主判据**
    #   「条件 alpha 交互项回归」和规矩㊸v2 第①道「配对检验」都算不出来
    #   （run_one 只存逐笔流水，res.equity / res.exposure 拿到就扔）。全文见 日序列覆盖层_1107.py。
    自证日序列 = DS.install()
    print(f"★★★ 日序列覆盖层: {json.dumps(自证日序列, ensure_ascii=False)}", flush=True)
    assert 自证日序列["★真的换掉了"], "★★★ 日序列覆盖层没装上，停"
    报_日序列 = 自证日序列
    # ★★★ 1107 夜：跳过基准一（同环境随机进场）—— ★ 不跳这一批 11 天跑不完，
    #   而本批臂文件一个字都不记它。实测的账和「为什么跳不动结论」见 跳过基准一_1107.py。
    自证跳过 = SK.install()
    print(f"★★★ 跳过基准一: {json.dumps(自证跳过, ensure_ascii=False)}", flush=True)
    assert 自证跳过["★真的换掉了"] and 自证跳过["★bootstrap真的换掉了"], "★★★ 跳过桩没装上，停" 
    # ★★★ dev/hs 在每个池装好后再定（全量可买）
    F.CONFIG_DIR = CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_1107")
    F.OUT = OUT
    for d in (F.PER_CHAIN, F.LEDGERS):
        os.makedirs(d, exist_ok=True)

    # ★★★ 提速（1107 23:0x 实测定位）—— ★ 不改任何进结论的数字。
    #   ★★ `run_one` 每条臂内部还要跑 **N_SEEDS = 50** 次「随机进场基准」→ 一条臂 = 51 次回测。
    #   ★★★ 但对 **R随机** 那 10 条臂来说，这个基准是「随机挑股 vs 随机进场」——
    #     ★ 它不进任何结论句，纯属白烧 50 倍算力。
    #   → ★★ 只对随机对照臂跳过；★★★ A原样 那条**照跑**（它的「基准一_同环境随机进场」要用）。
    #   ★ 跳过走的是 run_one 本来就有的 `BenchmarkPremiseBroken` 分支，不是新加的口子。
    # ★★★★★ 逐日净值必须落盘（1107 23:1x 补）—— ★ 不补的话这批**跑完也配不了对**。
    #   ★★ 《102》第四节的主做法是「两条臂的**每日组合收益序列**逐日相减」，
    #     ★ 可流水里只有**逐笔**（entry/exit/net_pnl），没有逐日净值。
    #   ★★★ 引擎其实一直有 —— `ChainResult.equity / equity_gross / exposure` 都是日频序列，
    #     ★ 只是 run_one 只存了 ledger，**没人存它**。
    #   → ★★ 这里把真链那一次的日净值存下来；★★★ engine 零改动（只换 run_one 用的函数指针）。
    #   ★ 只存**真链第一次调用**：后面 50 次是随机进场基准，不是这条臂。
    曲线目录 = os.path.join(HERE, "日净值_1107")
    os.makedirs(曲线目录, exist_ok=True)
    _原跑链 = F._ORIG_RUN_CHAIN

    def _跑链(*a, **kw):
        r = _原跑链(*a, **kw)
        if _当前臂.get("label") and not _当前臂.get("已存"):
            _当前臂["已存"] = True
            try:
                df = pd.DataFrame({"equity": r.equity,
                                   "equity_gross": r.equity_gross,
                                   "exposure": r.exposure})
                df.index.name = "date"
                df.to_csv(os.path.join(曲线目录,
                                       f"{F.safe_name(_当前臂['label'])}.csv"))
            except Exception as e:                       # ★ 存不下来要喊出来，不许静默
                print(f"⚠⚠ 日净值没存下来 {_当前臂['label']} —— "
                      f"{type(e).__name__}: {e}", flush=True)
        return r
    F._ORIG_RUN_CHAIN = _跑链

    _当前臂 = {"名": ""}
    _原随机进场 = F.analyze.random_entry_benchmark

    def _随机进场(*a, **k):
        if _当前臂["名"].startswith(("R随机", "B挂开关")):
            raise F.analyze.BenchmarkPremiseBroken(
                "★ 本批主动跳过：随机对照臂的内部随机进场基准不进任何结论；"
                "★★ 跳过只省时间，**不改这条臂的每笔R / 笔数 / 美元数**。")
        return _原随机进场(*a, **k)
    F.analyze.random_entry_benchmark = _随机进场

    报 = {"★预先登记": __doc__.strip()[:1500], "★★★窗口": f"{窗口起} ~ {窗口止}",
         "★★★口径": "**全收益**（两边都算分红；★ 旧结果全是价格口径，差 1.91pp/年）",
         "池自证": {}, "结果": [], "失败明细": []}
    for 池名 in 池:
        自证 = 装池(池名)
        dev = 可买名单(池名); hs = set()        # ★★★ 一档：全量可买
        # ★★★ #80：开关打开 ≠ 它起作用。分红必须覆盖整个池子，★ 覆盖不到直接抛。
        自证分红 = DV.install(需覆盖=dev)
        print(f"★★★ 分红覆盖层: {json.dumps(自证分红, ensure_ascii=False)}", flush=True)
        报["分红自证"] = 自证分红
        自证["★★★分红覆盖"] = 自证分红["★★★查得到文件的比例"]
        自证["★★★基准侧SPY分红"] = 自证分红["★★★基准侧分红"]["SPY"]
        F.load_pools = lambda d=dev, h=hs: (d, h, hold)
        报["池自证"][池名] = 自证
        print(f"★ {json.dumps(自证, ensure_ascii=False)}", flush=True)
        # ★★★ 一族一个进程：22 年 × 3,858 只整批跑会 OOM（exit 137，今天栽了三次）。
        #   ★ 用 XING_FAM 指定只跑一族，★★ 跑完进程退出 → 内存彻底还给系统。
        #   ★★★ 不设这个变量就跑全部（本地小池子调试用）。
        只跑 = os.environ.get("XING_FAM") or ""
        for 族, fn in 代表.items():
            if 只跑 and 族 != 只跑:
                continue
            base = yaml.safe_load(io.open(os.path.join(SRC, fn), encoding="utf-8"))
            # ★ 臂 = (名字, 要往配置里打的补丁)。★★ 补丁是**顶层键**，None 表示原样。
            臂 = [("A原样", None)]
            臂 += [(f"R随机{sd}",
                    {"ranking": {"primary": {"formula": "random", "order": "desc",
                                             "random_seed": sd},
                                 "source": "★★★ 规矩㊸v2 随机对照"
                                           "（回答「这旋钮本身有没有用」）"}})
                   for sd in 随机种子]
            # ★★★★★ 《102》第四档：挂环境开关。★ 这是 Lin 1107 一整天在讲的那条判断。
            #   ★★ 参数**跑前写死**：SPY / flatten_when_off: false（《102》3.1）。
            #   ★★★ 红线②：200 日虽有出处（Brock/Lakonishok/LeBaron 1992），
            #     仍要跑相邻三点 100/200/300，★ 报三点是否同向。
            #   ★★ 1106 的坑：params 写在 rule 顶层会**静默退回默认 200** ——
            #     ★★★ 所以必须写在 `params:` 里，并在出数时**逐字节比流水哈希**确认三条真的不同。
            臂 += [(f"B挂开关MA{ma}",
                    {"regime": {"rules": [{"type": "index_above_ma",
                                           "params": {"symbol": "SPY", "ma": ma}}],
                                "flatten_when_off": False}})
                   for ma in (100, 200, 300)]
            for 名, 补丁 in 臂:
                raw = copy.deepcopy(base)
                if 补丁 is not None:
                    for k, v in 补丁.items():
                        raw[k] = copy.deepcopy(v)
                label = f"{窗口名}·{池名}·{族}·{fn[:-5]}·{名}"
                tmp = f"_rt_{池名}_{族}_{名}.yaml"
                io.open(os.path.join(CFGDIR, tmp), "w", encoding="utf-8").write(
                    yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
                p = 臂路径(label)
                # ★★★ 续跑判据：臂文件**和**日序列两个都在才算这条跑过了。
                #   ★ 只看臂文件会把「旧批跑出来但没存日序列」的臂当成跑过 →
                #     配对检验那一步再发现缺，就要整批重跑（1107 夜踩过的那件）。
                if os.path.exists(p) and DS.已有(label):
                    报["结果"].append(json.load(io.open(p, encoding="utf-8"))); continue
                DS.开始新臂(label)          # ★ 显式重置「本臂第几次调用」，不靠猜
                print(f"▶ {label}", flush=True)
                _当前臂["名"] = 名
                _当前臂["label"] = label
                _当前臂["已存"] = False
                try:
                    r = F.run_one(label, tmp, None, "重测_1107", dev, hs, {})
                except Exception as e:
                    报["失败明细"].append({"臂": label, "错": f"{type(e).__name__}: {e}"})
                    print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True); continue
                rec = {"链": label, "池": 池名, "族": 族, "臂": 名,
                       "笔数": r["笔数"], "每笔净R": r["每笔净R"], "每笔毛R": r["每笔毛R"],
                       "净盈亏": r["★真链美元"]["净盈亏"], "摩擦": r["★真链美元"]["摩擦总额"]}
                io.open(p, "w", encoding="utf-8").write(
                    json.dumps(rec, ensure_ascii=False, indent=1, default=str))
                报["结果"].append(rec)
                print(f"   ✓ {名} 笔数 {r['笔数']} 每笔净R {r['每笔净R']:+.4f}", flush=True)
                io.open(OUT, "w", encoding="utf-8").write(
                    json.dumps({**报, "★进行中": True}, ensure_ascii=False, indent=1, default=str))

    报["★日序列覆盖层自证"] = 报_日序列
    报["★★★本批没算基准一"] = {**自证跳过, "★实际调用次数": SK.调用次数()}
    报["★★★日序列已存"] = DS.已存清单()
    报["★★★失败条数"] = len(报["失败明细"])
    报["★用时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完;★★★ 失败 {len(报['失败明细'])} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
