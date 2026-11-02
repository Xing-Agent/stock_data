#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 第十七条 · 标准答案集(第二道卡口)—— 2026-11-02

三秒版:**挑 10 条策略,把现在的输出冻成「标准答案」。以后改底层先跑这一条,
        结果必须一模一样 —— 不一样就指出是哪条链、哪个量、差多少。**

为什么要有这一条(★ 外部评审 Gemini 开的药):
   今天一天撞出 35 个坑,最大一类是「改了 A,静默弄坏了 B,而且不报错」。
   前 16 道闸是「照规矩查值对不对」,这一条不同 —— 它**不懂任何规矩**,
   只记得「上次是这个数」。★★ 所以它能抓到我们**没想到要查**的那一类。

★★★ 这道检查真的重跑引擎,不是读死文件自己和自己比。
   ★ 实测单条真链 0.8~4.0 秒(10 条合计约 30 秒),所以跑得起。
   ★★ 如果改成「读 bench1_rerun_1031.json 和答案文件比」,那是冻结值和冻结值比,
      **永远 PASS,等于没有这道检查** —— 这个坑必须说在最前面。

══════════════════════════════════════════════════════════════════════════
★★★ 两档量,分开对待(★ 这是本检查最需要先看懂的一件事)

  甲档 · **重算比对** —— 真的跑引擎算出来,再和答案比。**这才是回归闸。**
      笔数 · 合格进场信号 · 代码数 · 真链退化笔数 · 每笔净R · 每笔毛R ·
      总R净 · 最大单笔R净 · 持仓天数中位数

  乙档 · **只记录,不比对** —— 要 50 个种子的随机对照才算得出来(约 13 分钟),
      这道检查**跑不起**,所以老老实实不比,只把上一轮的值抄在答案文件里留痕。
      基准一数值 · 对照笔数偏差 · 对照侧退化笔数 · 基准一能不能用
      ★★ 待 `probe/bench1_rerun_1102/` 那一轮出来后补冻(策略组 11-02 已拍板另开)。
      ★★★ 乙档**不参与 PASS/FAIL** —— 把算不出来的量假装比过了,比不比更糟。
══════════════════════════════════════════════════════════════════════════

★★ 为什么基准一的**数值**这一轮不冻(★ 不是偷懒,是它现在是坏数):
   `bench1_rerun_1031.json` 是 10-31 **11:22** 跑的,而退化 R 的修复
   (策略组拍板「甲:剔掉这一笔」)是同日 **14:25** 提交的 ——
   ★ 那份结果在修复**之前**,45 条里有 35 条的基准一不可用,
     技-10 三档分别算出 −31 亿 / −53 亿 / −60 亿。★★ 冻它等于把垃圾当标准答案。
   ★★★ 而且修复落地后这些数**本来就会变** —— 一道会把「正确的修复」
      报成「回归」的检查,用两次就没人信了。

★★★ 冻结时实测到的一件事(★ 它正好证明这道检查有用):
   答案**不能照抄** `bench1_rerun_1031.json` —— 10 条里有 1 条已经和那份不一样了。
   `批五修正/技-14 · RSI(2)≤10(不带带宽熔断)` 这一条:
       笔数 379 没变 · 退化笔数 1 没变,但
       总R净  25.2969 → 39.9650  (差 +14.6681)
       每笔净R 0.0669 → 0.1057
       最大单笔R净 14.6681 → 6.1377
   原因是那一笔 `MPWR 2019-05-13`:止损离进场价只有 9.613e-3 / $131.4 = 7.3e-5,
   退化 R 修复(commit 95e293b)把它的 R 排除出聚合了,所以 −14.6681 这个垃圾值
   不再拖累总和。★★ 如果照抄 1031 的数当答案,**这道检查上线第一天就会对着
   一个完全正确的 engine 报 FAIL**。所以 --freeze 一律现场重跑。

★★ 顺带一个口径细节,以后看数的人容易踩:上面那条链 `笔数 = 379`,
   但 `每笔净R` 是 nanmean,分母是 **378**(退化那一笔是 NaN)。
   ★ 「笔数」和「R 的分母」在有退化笔的链上**不是同一个数** —— 这不是 bug,
     是修复的后果,但报告里要说清,不然下一个人会以为算错了。

跑法:
   python3 -m engine.checks.golden_answers              # 比对(在仓库根,不加 -I)
   python3 -m engine.checks.golden_answers --selftest   # 只跑反向自测
   python3 -m engine.checks.golden_answers --freeze     # ★ 重新冻结答案(慎用)

★ 本文件**只读** engine,不改 engine 任何东西;只写 engine/checks/golden_answers.json
  (而且只在显式 --freeze 时写)。
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import os
import sys
import time

import numpy as np
import yaml

# ★ run_all.py 的 _load() 不往 sys.modules 注册 → **本文件不许用 @dataclass**
#   (仓库里已踩过 6 次「两种跑法只测了一种」)。所以下面一律用 namedtuple / 普通 dict。
Problem = collections.namedtuple("Problem", "链 量 答案 实算 差 说明")

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(_HERE))
ANSWERS = os.path.join(_HERE, "golden_answers.json")

#: ★★ 答案来源那一轮的产物目录(乙档的值抄自这里;甲档不依赖它)
BENCH1 = os.path.join(ROOT, "probe", "bench1_rerun_1031")

#: ★ 题目指纹 —— 冻结那一刻的 engine 内容。答案文件里也记一份,便于看 diff。
EXPECT_FINGERPRINT = ("ea289aba709287e33b761f55b569c171cdac0e06b5e87d0b4399"
                      "e51408c39ee6")

SCOPE = "large_mid"

#: ★★★ 「退化 R」判据 —— 照抄 probe/bench1_rerun_1031/degenerate_r_1031.py,
#   **不许在这里另立一个阈值**(「阈值有两份权威副本」已经坑过我们一次:
#   只改 yaml、跑一次生成器就被静默冲掉)。
DEGEN_REL = 1e-4

#: ★★★ 容差。整数零容差;浮点 1e-9 相对误差。
#   ★ 用 max(1,|b|) 而不是 |b|:有些量本身就在 0 附近,纯相对误差在那里会炸。
FLOAT_RTOL = 1e-9

#: 哪些量是整数(必须完全相同),哪些是浮点(1e-9)
#  ★★ 后三个整数项是池子口径诊断(universe收窄)。★★★ 本来怀疑
#    「改名对上」靠名字匹配、可能依赖字典遍历顺序 → 2026-11-02 **实测过**:
#    **3 个独立进程**(Python 的字符串 hash 逐进程随机,同一进程里跑 3 次测不出来)
#    跑出来 285 / 2008 / 83 三次完全一样,两个比例也一样 → 稳定,收进答案集。
INT_KEYS = ("笔数", "合格进场信号", "代码数", "真链退化笔数",
            "票×年_直接", "票×年_改名对上", "票×年_当年不在池")
FLOAT_KEYS = ("每笔净R", "每笔毛R", "总R净", "最大单笔R净", "持仓天数中位数",
              "掩膜为真的票日比例", "universe票日砍掉比例")

#: ★★ 乙档:只抄不比(算不起)。放在答案文件里是为了留痕,**不参与判定**。
REFERENCE_ONLY_KEYS = ("基准一数值", "对照笔数偏差", "对照侧退化笔数",
                       "基准一能不能用")

#: ★ 上一轮 45 条链的 VARIANTS 来源 —— 和 run_bench1_1031.py 同一份,
#   ★★ 这样覆盖函数(ov,例如技-10 的持仓天数)**不用在这里抄第二遍**。
VARIANT_MODULES = [
    ("A0十二条", "engine.run_a0_12"),
    ("技术派六条三版", "engine.pat6_run"),
    ("批五修正", "engine.run_p5_1029"),
    ("原著离场", "engine.run_orig_exits_1029"),
    ("剔污染", "engine.run_declean_1030"),
]

# ══════════════════════════════════════════════════════════════════════════
# ★★★ 挑链规则 —— 写下来的,不是凭感觉挑的
# ══════════════════════════════════════════════════════════════════════════
#
# 规则按优先级排,冲突时上面的赢。照这几条,换个人也会挑出同一批。
#
#   规则 0 · 先去重
#       45 条里只有 33 份独立结果(★ 任务书写 32 份,实测 33 份 ——
#       12 行是同配置同结果换批次标签,不是 13 行)。同组只留最早那一批。
#       ★ 理由:同样的数冻两遍抓不到任何多余的 bug,只会让失败报告里出现重复。
#
#   规则 1 · 必须包含「曾经出过问题的」(★★★ 优先级最高)
#       技-10 族(退化 R 重灾区)· 技-3(周线换算 150→145)·
#       trend_following(署名海龟、三部件都不是)· buy_and_hold(无止损写成 pct 0.999)
#       ★★ 标准答案集的用途是「改坏了会报警」,不是「展示我们跑得好」。
#
#   规则 2 · 笔数两端各一条
#       最多 3989(技-14 原著版)· 最少 111(技-11 行业版)
#       ★ 理由:大样本抓「浮点累加顺序」类,小样本抓「少一笔就差很多」类。
#
#   规则 3 · 离场类型必须覆盖五种
#       固定止损 / 吊灯 / 均线 / 时间止损 / 无止损
#       ★★ 判离场类型看 **yaml 槽位**,不看流水的 reason 列 ——
#          那一列只有 5 种笼统值(离场规则/止损/时间止损/退市结算/止盈),
#          ★★★ 分不出吊灯和均线。
#       ★★★ 实测:全 45 条里**只有 trend_following 一条带吊灯**
#          (stop_trail.stages[].type = chandelier)——
#          所以「要覆盖吊灯」和「要包含那条装错的」是同一个答案。
#
#   规则 4 · 同一个 yaml 不超过 2 条
#       ★ 理由:答案集的价值在覆盖面,不在同一个配置的三档参数。
#
#: ★ 名单只在这里有一份(代码管「该测哪几条」,JSON 管「数是多少」)——
#  ★★ 两边各管一件事,避免「两份权威副本」。
CHAINS = [
    # (链名, 为什么选它, 离场类型)
    ("A0十二条/技-1 · 海龟 System 1(20 日入 / 10 日出)",
     "正宗海龟,当 trend_following 的对照", "固定止损2ATR+反向通道"),
    ("原著离场/技-1 · ★★装错的那一版对照:trend_following(吊灯 3ATR + MA50)",
     "★ 唯一的吊灯;署名海龟但三部件都不是", "吊灯+均线50"),
    ("技术派六条三版/技-3 · 行业版(放量 1.55× · 中值)",
     "★ 周线换算(30 周线 150→145 修正过)", "均线145"),
    ("原著离场/技-10 · ★原著离场 · 持仓 3 天(中值)",
     "★ 退化 R 重灾区", "时间止损"),
    ("剔污染/buy_and_hold(锚点)",
     "★ 无止损写成 pct:0.999,机械检查抓不到", "无止损(pct 0.999)"),
    ("A0十二条/技-2 · 法伯月线择时(10 月线)",
     "唯一的月频离场", "无止损+月线"),
    ("A0十二条/技-12 · 康纳斯(RSI2 < 5)",
     "无止损的 type:none 写法(和 buy_and_hold 的 0.999 写法成对)",
     "无止损+均线5"),
    ("技术派六条三版/技-14 · 原著版(Method III 近似:W 底 + MFI 底背离)",
     "★ 笔数最多(3989)", "固定止损+中轨"),
    ("技术派六条三版/技-11 · 行业版(后人量化版:下刺 0.15~0.80 ATR + 收复 + 缩量)",
     "★ 笔数最少(111);唯一带 profit_target_r", "固定止损+均线20+止盈2R"),
    ("批五修正/技-14 · ★新组合 RSI(2)≤10(★ 不带带宽熔断)",
     "★ 真链里有 1 笔退化 R", "固定止损+中轨"),
]

CHAIN_NAMES = [c[0] for c in CHAINS]


# ══════════════════════════════════════════════════════════════════════════
# 一 · 重算一条链(★ 甲档的唯一一份计算逻辑)
# ══════════════════════════════════════════════════════════════════════════

_VARIANTS_CACHE: dict = {}


def _variants() -> dict:
    """label -> (yml, ov, group)。★ 和 run_bench1_1031.py 同一份 VARIANTS。"""
    if _VARIANTS_CACHE:
        return _VARIANTS_CACHE
    for batch, modname in VARIANT_MODULES:
        mod = __import__(modname, fromlist=["VARIANTS"])
        for v in getattr(mod, "VARIANTS"):
            _VARIANTS_CACHE.setdefault(f"{batch}/{v[0]}", (v[1], v[2], v[4]))
    return _VARIANTS_CACHE


def _setup():
    """★ 跑链前的固定装配 —— 照 run_bench1_1031.py main() 的顺序。

    ★★ 漏掉这两个 install() 的后果很具体:技-11 会抛
       `NotImplementedError: entry 规则 pat6_spring 还没法跑`(本次实测踩到过)。
    """
    V2 = os.path.join(ROOT, "probe", "v2_rerun_1030")
    for p in (ROOT, V2, BENCH1):
        if p not in sys.path:
            sys.path.insert(0, p)
    from engine import ops_exits_1029, pat6_ops           # noqa: PLC0415
    pat6_ops.install()
    ops_exits_1029.install()


def _dev_pool() -> list:
    """研发池 198 只(留出池 49 只不许进)。"""
    with open(os.path.join(BENCH1, "holdout_1031.json"), encoding="utf-8") as fh:
        d = json.load(fh)
    dev, hold = list(d["研发池名单"]), set(d["留出池名单"])
    if set(dev) & hold:
        raise RuntimeError("★ 研发池和留出池有交集,停")
    return dev, hold


def measure_one(label: str, dev: list, hold: set) -> dict:
    """跑一条真链,算出甲档那几个量。★ 这是**唯一**一份计算逻辑。

    ★ 不跑 50 种子随机对照(约 13 分钟/10 条),所以乙档的量这里不产出。
    """
    from engine import chain, data, matrices                # noqa: PLC0415
    import rerun_core_1030 as RC                            # noqa: PLC0415

    yml, ov, _group = _variants()[label]
    with open(os.path.join(ROOT, "engine", "configs", yml), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if ov is not None:
        raw = ov(copy.deepcopy(raw))
    cfg = chain.ChainConfig.from_dict(raw)

    m = matrices.build(cfg.raw, dev)
    scope_diag = RC.apply_scope(m, SCOPE)
    res = chain.run_chain(cfg, dev, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger

    # ★★★ 留出池一笔都不许进 —— 照上一轮的硬断言
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & hold)
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")

    if not len(led):
        raise RuntimeError(f"★ {label} 跑出 0 笔 —— 答案集不收 0 笔的链")

    rn = led["r_multiple_net"].astype(float)
    deg = int((led["risk_per_share"].astype(float)
               / led["entry_price"].astype(float) < DEGEN_REL).sum())
    # ★ 池子口径诊断(实测 3 个独立进程稳定,见 INT_KEYS 上面的注释)
    cnt = scope_diag.get("票×年 解析方式计数") or {}
    return {
        "配置": f"engine/configs/{yml}",
        "笔数": int(len(led)),
        "合格进场信号": int((m.entry & m.universe).sum()),
        "代码数": int(led["symbol"].nunique()),
        "真链退化笔数": deg,
        "每笔净R": float(np.nanmean(rn)),
        "每笔毛R": float(np.nanmean(led["r_multiple"].astype(float))),
        "总R净": float(np.nansum(rn)),
        "最大单笔R净": float(np.nanmax(np.abs(rn))),
        "持仓天数中位数": float(led["holding_days"].astype(float).median()),
        "票×年_直接": int(cnt.get("直接", -1)),
        "票×年_改名对上": int(cnt.get("改名对上", -1)),
        "票×年_当年不在池": int(cnt.get("当年不在池", -1)),
        "掩膜为真的票日比例": float(scope_diag.get("掩膜为真的票日比例", float("nan"))),
        "universe票日砍掉比例": float(scope_diag.get("universe 票日 砍掉比例",
                                                     float("nan"))),
    }


def measure_all(labels=None, say=print) -> dict:
    """跑 N 条链。-> {链名: 甲档量}。★ 实测 10 条合计约 30 秒。"""
    labels = list(labels or CHAIN_NAMES)
    _setup()
    dev, hold = _dev_pool()
    out, t0 = {}, time.time()
    for i, lb in enumerate(labels, 1):
        t = time.time()
        out[lb] = measure_one(lb, dev, hold)
        try:
            say(f"  [{i}/{len(labels)}] {time.time()-t:5.1f}s "
                f"{out[lb]['笔数']:>5}笔  {lb[:52]}")
        except Exception:                                   # noqa: BLE001
            pass
    try:
        say(f"  ★ 合计 {time.time()-t0:.1f}s")
    except Exception:                                       # noqa: BLE001
        pass
    return out


# ══════════════════════════════════════════════════════════════════════════
# 二 · 比对
# ══════════════════════════════════════════════════════════════════════════

def _close(a: float, b: float) -> bool:
    """|a − b| ≤ 1e-9 × max(1, |b|)。★ max(1,·) 防 0 附近炸掉。"""
    return abs(float(a) - float(b)) <= FLOAT_RTOL * max(1.0, abs(float(b)))


def compare(frozen: dict, measured: dict) -> list:
    """-> 问题清单(空 = PASS)。★ 每条都指出:哪条链、哪个量、差多少。"""
    probs = []
    fchains = frozen.get("逐链") or {}

    # ---- 名单先对:少一条 / 多一条
    for lb in CHAIN_NAMES:
        if lb not in fchains:
            probs.append(Problem(lb, "(整条)", "缺失", "应有", None,
                                 "★★ 答案集少了一条"))
    for lb in sorted(fchains):
        if lb not in CHAIN_NAMES:
            probs.append(Problem(lb, "(整条)", "多出", "名单里没有", None,
                                 "★★ 答案集多了一条"))

    # ---- 逐链逐量
    for lb in CHAIN_NAMES:
        if lb not in fchains or lb not in measured:
            continue
        f, g = fchains[lb], measured[lb]
        if f.get("配置") != g["配置"]:
            probs.append(Problem(lb, "配置", f.get("配置"), g["配置"], None,
                                 "★ 配置路径变了"))
        for k in INT_KEYS:
            if k not in f:
                probs.append(Problem(lb, k, "缺失", g[k], None,
                                     "★ 答案集里没有这个量"))
            elif int(f[k]) != int(g[k]):
                probs.append(Problem(lb, k, int(f[k]), int(g[k]),
                                     int(g[k]) - int(f[k]),
                                     "★★ 整数量必须完全相同"))
        for k in FLOAT_KEYS:
            if k not in f:
                probs.append(Problem(lb, k, "缺失", g[k], None,
                                     "★ 答案集里没有这个量"))
            elif not _close(g[k], f[k]):
                d = float(g[k]) - float(f[k])
                rel = abs(d) / max(1.0, abs(float(f[k])))
                probs.append(Problem(lb, k, float(f[k]), float(g[k]), d,
                                     f"★★ 相对误差 {rel:.3e} > 容差 {FLOAT_RTOL:.0e}"))
    return probs


def render(probs: list, say=print) -> None:
    if not probs:
        return
    say("")
    say("=" * 78)
    say(f"★★★ 标准答案集对不上 —— {len(probs)} 处")
    say("=" * 78)
    for p in probs:
        say(f"\n★ 链 : {p.链}")
        say(f"  量 : {p.量}")
        say(f"  答案: {p.答案}")
        say(f"  实算: {p.实算}")
        if p.差 is not None:
            say(f"  差 : {p.差:+.12g}")
        say(f"  → {p.说明}")


# ══════════════════════════════════════════════════════════════════════════
# 三 · 冻结(★ 只在显式 --freeze 时写盘)
# ══════════════════════════════════════════════════════════════════════════

def _fingerprint() -> str:
    """重算那 133 个题目文件的指纹。★ 冻结时记一份,便于看答案是哪版 engine 产的。"""
    import hashlib                                          # noqa: PLC0415
    fp = os.path.join(ROOT, "手册", "V2题目指纹-20261101.json")
    with open(fp, encoding="utf-8") as fh:
        man = json.load(fh)
    acc = {}
    for e in man["逐份"]:
        h = hashlib.sha256()
        with open(os.path.join(ROOT, e["file"]), "rb") as f2:
            for blk in iter(lambda: f2.read(1 << 20), b""):
                h.update(blk)
        acc[e["file"]] = h.hexdigest()
    agg = hashlib.sha256()
    for n in sorted(acc):
        agg.update(acc[n].encode())
    return agg.hexdigest()


def _reference_only() -> dict:
    """乙档:从上一轮产物里抄。★ 只留痕,不参与判定。"""
    out = {}
    try:
        b = json.load(open(os.path.join(BENCH1, "bench1_rerun_1031.json"),
                           encoding="utf-8"))
        dg = json.load(open(os.path.join(BENCH1, "degenerate_r_1031.json"),
                            encoding="utf-8"))
    except Exception:                                       # noqa: BLE001
        return out
    by = {r["链"]: r for r in b["逐链"]}
    dgby = {r["链"]: r for r in dg["逐链"]}
    for lb in CHAIN_NAMES:
        r, d = by.get(lb, {}), dgby.get(lb, {})
        b1 = r.get("★基准一") or {}
        out[lb] = {
            "基准一数值": b1.get("★真信号每笔R − 随机进场每笔R"),
            "对照笔数偏差": r.get("★对照笔数偏差"),
            "对照侧退化笔数": (d.get("对照流水") or {}).get("退化笔数"),
            "基准一能不能用": d.get("★基准一能不能用"),
        }
    return out


def freeze(say=print) -> dict:
    say("★ 重跑 10 条链,把**现在的输出**冻成标准答案 ——")
    measured = measure_all(say=say)
    ref = _reference_only()
    doc = {
        "这是什么": ("★★★ 标准答案集(第二道卡口)—— 改底层先跑这一条,"
                     "结果必须一模一样。"),
        "生成日期": time.strftime("%Y-%m-%d"),
        "生成时的题目指纹": _fingerprint(),
        "答案来源": ("甲档 = 本机现场重跑 engine(真链,不含 50 种子对照);"
                     "乙档 = 抄 probe/bench1_rerun_1031/(★ 只留痕不比对)"),
        "池子口径": f"{SCOPE} · 研发池 198 只(留出池 49 只已排除)",
        "容差": {
            "整数": "0(必须完全相同)",
            "浮点": f"相对 {FLOAT_RTOL:.0e} —— |a−b| ≤ {FLOAT_RTOL:.0e} × max(1,|b|)",
            "整数项": list(INT_KEYS),
            "浮点项": list(FLOAT_KEYS),
        },
        "★乙档_只记录不比对": {
            "是哪些量": list(REFERENCE_ONLY_KEYS),
            "为什么不比": ("★ 要 50 个种子的随机对照才算得出来(约 13 分钟/10 条),"
                           "这道检查跑不起。★★ 把算不出来的量假装比过了,比不比更糟。"),
            "★待补冻": ("基准一数值待 probe/bench1_rerun_1102/ 那一轮完成后补冻 —— "
                         "★ 1031 那一轮(11:22)在退化 R 修复(同日 14:25,commit "
                         "95e293b)之**前**,45 条里 35 条的基准一不可用,"
                         "技-10 三档算出 −31 亿 / −53 亿 / −60 亿。"),
        },
        "挑链规则": [
            "规则 0 · 先去重:45 条只有 33 份独立结果,同组只留最早那一批",
            "规则 1 · 必须包含出过问题的:技-10 退化R · 技-3 周线换算 · "
            "trend_following 装错 · buy_and_hold 的 pct:0.999",
            "规则 2 · 笔数两端各一条:最多 3989 · 最少 111",
            "规则 3 · 离场类型覆盖五种:固定止损/吊灯/均线/时间止损/无止损"
            "(★ 看 yaml 槽位,不看流水 reason 列;★★ 全库只有 "
            "trend_following 一条带吊灯)",
            "规则 4 · 同一个 yaml 不超过 2 条",
        ],
        "逐链": {},
    }
    for lb, why, exit_type in CHAINS:
        doc["逐链"][lb] = dict(measured[lb], **{
            "为什么选它": why,
            "离场类型": exit_type,
            "★乙档(只记录不比对)": ref.get(lb, {}),
        })
    with open(ANSWERS, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)
    say(f"\n★ 已写 {ANSWERS}")
    return doc


def load_answers() -> dict:
    with open(ANSWERS, encoding="utf-8") as fh:
        return json.load(fh)


# ══════════════════════════════════════════════════════════════════════════
# ★★★ 四 · 反向自测 —— 一道检查如果自己不会报警,它就是假的
# ══════════════════════════════════════════════════════════════════════════

def _selftest() -> None:
    """★★★ 故意制造偏差,确认这道检查真的 FAIL。

    ★★ 只跑引擎**一次**(约 30 秒),5 项自测都复用这一份实算结果 ——
       不然 5 项就是 5 × 30 秒,而考卷正在同一台 2 核机器上跑。
    """
    print("★ 先重跑 10 条链(5 项自测复用这一份实算,只跑一次):")
    measured = measure_all()
    frozen = load_answers()

    # ---- 第 0 项:不动任何东西,必须 PASS(★ 没有这一项,下面的 FAIL 不说明问题)
    probs = compare(frozen, measured)
    assert not probs, f"★★★ 原样比对就对不上({len(probs)} 处)—— 先修这个:\n{probs[:3]}"
    print("\n[0/5] 原样比对 → PASS ✅(★ 基线成立,下面的 FAIL 才有意义)")

    # ★ 挑一条「每笔净R 绝对值够大」的链做 1e-6 / 1e-12 那两项 ——
    #   不然 max(1,|b|) 的保护会让 1e-6 的改动落在容差内、第 2 项假通过。
    big = max(CHAIN_NAMES,
              key=lambda lb: abs(frozen["逐链"][lb]["每笔净R"]))
    lb0 = CHAIN_NAMES[0]

    # ---- 第 1 项:笔数 +1 → 必须 FAIL,且指出是那一条
    f = copy.deepcopy(frozen)
    f["逐链"][lb0]["笔数"] += 1
    probs = compare(f, measured)
    hit = [p for p in probs if p.链 == lb0 and p.量 == "笔数"]
    assert hit, "★★★ 笔数 +1 居然没 FAIL"
    assert len(probs) == 1, f"★ 应该只报这一处,实际 {len(probs)} 处"
    assert hit[0].差 == -1, f"★ 差应为 -1,实际 {hit[0].差}"
    print(f"[1/5] 笔数 +1            → FAIL ✅  指出:{lb0[:34]} · 笔数 · 差 {hit[0].差}")

    # ---- 第 2 项:每笔净R 改 1e-6 → 必须 FAIL(超 1e-9 容差)
    f = copy.deepcopy(frozen)
    f["逐链"][big]["每笔净R"] += 1e-6
    probs = compare(f, measured)
    hit = [p for p in probs if p.链 == big and p.量 == "每笔净R"]
    assert hit, "★★★ 每笔净R 改 1e-6 居然没 FAIL"
    print(f"[2/5] 每笔净R 改 1e-6    → FAIL ✅  {hit[0].说明}")

    # ---- 第 3 项:每笔净R 改 1e-12 → 必须 PASS(容差内)
    f = copy.deepcopy(frozen)
    f["逐链"][big]["每笔净R"] += 1e-12
    probs = compare(f, measured)
    assert not probs, f"★★★ 1e-12 应在容差内却 FAIL 了:{probs}"
    print("[3/5] 每笔净R 改 1e-12   → PASS ✅(★ 在 1e-9 容差内)")

    # ---- 第 4 项:删掉一条 → 必须 FAIL 并说「答案集少了一条」
    f = copy.deepcopy(frozen)
    del f["逐链"][lb0]
    probs = compare(f, measured)
    hit = [p for p in probs if "少了一条" in p.说明]
    assert hit, f"★★★ 删掉一条居然没报「少了一条」:{probs}"
    assert hit[0].链 == lb0
    print(f"[4/5] 删掉一条           → FAIL ✅  「{hit[0].说明}」:{hit[0].链[:34]}")

    # ---- 第 5 项:多一条不存在的 → 必须 FAIL 并说「答案集多了一条」
    f = copy.deepcopy(frozen)
    f["逐链"]["技-99 · 这条链不存在(自测用)"] = dict(frozen["逐链"][lb0])
    probs = compare(f, measured)
    hit = [p for p in probs if "多了一条" in p.说明]
    assert hit, f"★★★ 多一条居然没报「多了一条」:{probs}"
    print(f"[5/5] 多一条不存在的     → FAIL ✅  「{hit[0].说明}」:{hit[0].链}")

    print("\n✅ 反向自测 5 项(+基线 1 项)全过 —— "
          "★ 这道检查真的会报警,不是摆设")


# ══════════════════════════════════════════════════════════════════════════
# 五 · main
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--freeze", action="store_true",
                    help="★ 重新冻结答案(慎用:会覆盖 golden_answers.json)")
    ap.add_argument("--selftest", action="store_true", help="只跑反向自测")
    args = ap.parse_args()

    if args.freeze:
        freeze()
        return 0
    if args.selftest:
        _selftest()
        return 0

    if not os.path.exists(ANSWERS):
        print(f"★★★ 没有答案文件 {ANSWERS} —— 先跑 --freeze")
        return 1
    frozen = load_answers()
    print(f"★ 标准答案集:{len(frozen.get('逐链') or {})} 条链 · "
          f"冻于 {frozen.get('生成日期')} · "
          f"题目指纹 {str(frozen.get('生成时的题目指纹'))[:16]}…")
    fp_now = _fingerprint()
    if fp_now != frozen.get("生成时的题目指纹"):
        print(f"★★ 注意:engine 内容已和冻结时不同 "
              f"(现在 {fp_now[:16]}…)—— ★ 下面的差异可能是**预期的改动**,"
              f"请人工过一眼再决定是不是回归")
    print("★ 重跑 10 条链:")
    measured = measure_all()
    probs = compare(frozen, measured)
    if probs:
        render(probs)
        print(f"\n★★★ FAIL —— {len(probs)} 处对不上")
        return 1
    print(f"\n✅ PASS —— 10 条链、{len(INT_KEYS)+len(FLOAT_KEYS)} 个量全部一致 "
          f"(整数零容差 · 浮点 {FLOAT_RTOL:.0e} 相对)")
    print(f"★ 乙档 {len(REFERENCE_ONLY_KEYS)} 个量只记录未比对 —— "
          f"待 probe/bench1_rerun_1102/ 出来后补冻")
    return 0


if __name__ == "__main__":
    sys.exit(main())
