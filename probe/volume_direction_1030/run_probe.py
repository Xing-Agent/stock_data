"""
★★★ 成交量的方向(进 vs 出)能不能独立判出「这是底部还是顶部」

════════════════════════════════════════════════════════════════════════════
三秒版(跑完的结论写在报告里,这里只说这个文件在干什么)
════════════════════════════════════════════════════════════════════════════
要验的假设是**策略组的原话**:
    「顶和底部的很大的区别就是这个量的进出,一个是进,一个是出。
      另外指标和形态都重要,但量最重要。」
★ 用词是「进出」不是「大小」 —— 所以测的是量的**方向性**,不是幅度。

做法:① 在**编号可信**的格子上,看量指标能不能**独立**判出同一个编号(完全不看路径)
     ② 把它用到**历史短、编号不可信**的格子上,看分歧有多大、谁对
     ③ 两段一致性(kappa)—— 不过关一律判噪音

════════════════════════════════════════════════════════════════════════════
★★★ 本轮只验,不装。不改任何 engine/ 文件,不碰别的 agent 的目录。
════════════════════════════════════════════════════════════════════════════
  · `engine/` 一行未碰(用 importlib 按文件路径只读加载上一轮 probe)
  · `probe/phaseshift_1030/` · `probe/stage_path_1030/` · `probe/timeframe_rs_1030/` 只读
  · 串行单进程,不用 nohup,每节 dump 一次(可续跑)

跑法:python3 probe/volume_direction_1030/run_probe.py            (全量)
      python3 probe/volume_direction_1030/run_probe.py --smoke 3  (先用 3 只票量耗时)
      python3 probe/volume_direction_1030/run_probe.py --force    (重算已有的节)
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)

from engine import cache, pool_scope                              # noqa: E402
from engine import state_axis_tri_1029 as tri                     # noqa: E402

sys.path.insert(0, _HERE)
import vol_dir as VD                                              # noqa: E402

# ---------------------------------------------------------------------------
# 上一轮两个 probe 只读加载 —— ★ 保证标签构造和上一轮**逐行一致**
# ---------------------------------------------------------------------------
def _load_ro(relpath: str, modname: str):
    spec = importlib.util.spec_from_file_location(
        modname, os.path.join(_REPO, *relpath.split("/")))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)              # ★ 只 import,不跑它的 main()
    return m


SP = _load_ro("probe/stage_path_1030/run_probe.py", "_sp_1030")   # 阶段号那一轮
TF = _load_ro("probe/timeframe_rs_1030/run_probe.py", "_tf_1030")  # 两套口径那一轮

OUT = {k: os.path.join(_HERE, f"results_{k}.json")
       for k in ("0血统", "1真值前提", "2真值集", "3量指标", "4短历史")}

# ═══════════════════════════════════════════════════════════════════════════
# ★ 时间尺度声明 —— 凡「天」都在这里写明是交易日还是自然日
# ═══════════════════════════════════════════════════════════════════════════
TIME_SCALE = {
    "所有量指标的窗口 10/20/30": "**交易日**",
    "量的基准均线 50": "50 个**交易日**(≈10 周,和 状-2 走平斜率回看长度对齐)",
    "「手上历史」": "**有效交易日 bar 数**(★ 不是索引距离 —— 见第一节,"
                   "这正是上一轮口径要订正的地方)",
    "「历史 ≥1,000 天」/「<400 天」": "**有效交易日 bar 数**",
    "起点偏移 o": "**交易日**(在日线网格上往右切掉多少格)",
    "可比窗口": f"{tri.START} 起",
}

#: ★★ 字段/判据含义声明 —— 今天多次「把自己工具的语义读反了」,所以逐个写明
FIELD_SEMANTICS = {
    "label(阶段号)": "tri._confirm_sequence 的逐日输出,1/2/3/4/transition/WARMUP。"
                     "★ 它是「已确认阶段」,会一直挂着到下次确认。",
    "「走平格子」": "label ∈ {1,3} 的格子 —— ★ 沿用 stage_path_1030 的定义,不另起口径。",
    "「真值」": "★ 本轮的真值 = **用全部可用历史算出来的阶段号**。"
               "★★★ 它不是上帝视角的真相(没有这种东西),"
               "它是「收敛之后的编号」—— 第一节要先证明它到底在多少历史之后才收敛。",
    "量指标的方向约定": "score > 0 = 量在进 = 判底部(阶段一);"
                       "score < 0 = 量在出 = 判顶部(阶段三)。"
                       "★★★ 这个符号是**假设给定的**,不是拟合出来的。",
    "「算不出」": "窗口内没有放量日 / 均量未成形 / score 恰好为 0。"
                 "★★★ 算不出和判错**分开统计**,不许混成一个准确率。",
}

MY_NOTES: list[str] = []


def _note(s: str) -> None:
    if s not in MY_NOTES:
        MY_NOTES.append(s)


def _dump(key: str, obj) -> None:
    with open(OUT[key], "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1, default=str)


def _load(key: str):
    if os.path.exists(OUT[key]):
        with open(OUT[key], encoding="utf-8") as fh:
            return json.load(fh)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# 零 · 血统对账 —— ★★★ 证明我这一轮的标签和上一轮同源
# ═══════════════════════════════════════════════════════════════════════════

_OLD_BRANCH_SRC = """
★ 上一轮(stage_path_1030)跑的时候,_confirm_sequence 里 FLAT 确认的 else 分支是:
      last = confirmed[-1] if confirmed else None
      if   last == "2":        stage = "3"
      elif last in ("1","3"):  stage = last
      else:                    stage = "1"     # ★ last is None 和 last=="4" 共用
★★ 2026-10-30 的 commit 8163aa7 把 `last is None` 拆出去编成**不确认任何阶段**
   (落到 transition)—— 理由:「从来没确认过任何阶段」被缺省成「底部=该买」
   是一个我们没有依据的看多判断。
"""


def _confirm_old(raw: np.ndarray, min_bars: int):
    """★ 把**修复前**的分支复制出来(只在本节用,用来证明血统)。"""
    n = len(raw)
    daily = np.full(n, tri.WARMUP, dtype=object)
    events: list[dict] = []
    confirmed: list[str] = []
    cur_raw, run = None, 0
    cur_stage = tri.WARMUP
    for i in range(n):
        r = raw[i]
        if r == tri.WARMUP:
            daily[i] = tri.WARMUP
            cur_raw, run = None, 0
            continue
        if r == cur_raw:
            run += 1
        else:
            cur_raw, run = r, 1
        if run == min_bars and r in ("FLAT", "ADV", "DEC"):
            if r == "ADV":
                stage = "2"
            elif r == "DEC":
                stage = "4"
            else:
                last = confirmed[-1] if confirmed else None
                if last == "2":
                    stage = "3"
                elif last in ("1", "3"):
                    stage = last
                else:
                    stage = "1"          # ★ 修复前的那一行
            if not confirmed or confirmed[-1] != stage:
                events.append({"i": i, "stage": stage,
                               "prev": confirmed[-1] if confirmed else None,
                               "prev2": confirmed[-2] if len(confirmed) >= 2 else None})
                confirmed.append(stage)
            cur_stage = stage
        daily[i] = cur_stage if cur_stage != tri.WARMUP else "transition"
        if cur_stage == tri.WARMUP:
            daily[i] = "transition"
    return daily, events


def lineage(cl: pd.DataFrame, syms: list[str]) -> dict:
    """
    ★★★ 上一轮那套数(90.50% / 86.42% / [134294,10850,10258] / 54313)
    在**现在的代码**上复不出来 —— 本节证明原因**只有**那一个已提交的修复,
    不是我这一轮换了口径。

    测法:把 tri._confirm_sequence 临时换成修复前的版本,再跑上一轮的 reconcile。
          ★ 对上 → 血统确认;对不上 → raise,不许往下跑。
    """
    out: dict = {"★ 上一轮报的": {"全五档一致率": 0.9050, "Jaccard": 0.8642,
                                 "逐位": [134294, 10850, 10258], "不一致格子": 54313}}
    # ① 现在的代码
    try:
        SP.reconcile(cl, syms)
        out["现在的代码能不能复现上一轮"] = "能(那就不存在差异,下面这步多余)"
        out["现在的代码"] = "逐位一致"
    except RuntimeError as e:
        out["现在的代码能不能复现上一轮"] = "★ 不能"
        out["现在的代码差在哪"] = str(e).replace("\n", " ")

    # ② 换回修复前的分支
    orig = tri._confirm_sequence
    tri._confirm_sequence = _confirm_old
    try:
        rec_old = SP.reconcile(cl, syms)
        out["★★★ 换回修复前的分支之后"] = "逐位复现上一轮 → 血统确认"
        out["复现明细"] = rec_old
    except RuntimeError as e:
        raise RuntimeError(
            "★★ 换回修复前的分支也复不出上一轮的数 —— 说明差异不只是那个修复,"
            "停下来查,不许往下跑。\n" + str(e)) from e
    finally:
        tri._confirm_sequence = orig

    out["★★ 差异的唯一来源"] = _OLD_BRANCH_SRC.strip()
    out["★ 本轮用哪一版"] = (
        "★★★ 用**现在的代码**(修复后)。理由:修复后「从来没有历史」会落到 "
        "transition,不会被缺省成「底部」—— 而本轮正是在验「底 vs 顶」,"
        "用一个会把无依据格子塞进「底部」的版本,会直接把真值污染成偏底。")
    return out


# ═══════════════════════════════════════════════════════════════════════════
# 一 · ★★★ 真值前提复核 —— 「历史 ≥1,000 天 → 错号率 0.01%」这句话站不站得住
# ═══════════════════════════════════════════════════════════════════════════

def first_valid_idx(cl: pd.DataFrame, syms: list[str]) -> dict[str, int]:
    """每只票第一根**有效** bar 的索引位置。"""
    out = {}
    for s in syms:
        a = cl[s].notna().to_numpy()
        out[s] = int(a.argmax()) if a.any() else len(a)
    return out


def truth_premise(cl: pd.DataFrame, syms: list[str], fv: dict[str, int],
                  offsets: tuple[int, ...]) -> dict:
    """
    ★★★ 本节是本轮的地基,必须先过 —— 它查的是**任务给的前提本身**。

    任务里的前提是:「历史 ≥1,000 个交易日的格子,编号错误率只有 0.01%,
    所以那些格子的编号可以当成真值用。」

    ★★ 实测发现的问题(所以必须复核):
       上一轮算「手上历史」用的是 `np.arange(len(b)) - o`,★ 这是**索引距离**。
       而这份面板 2014-01-02 ~ 2015-12-31 **整段是空的**(数据从 2016-01-04 起,
       索引位置 504)。→ 索引距离比**真实有效 bar 数**多算了约 504 根。
    ★★★ 后果:上一轮点名的四个起点(0/60/120/250)全都切在空白段里,
       喂进去的序列**一模一样** → 「0/571,570 格变号」是个**恒等式**,
       不是稳健性的证据。本节逐票证明这一点。

    所以本节重做校准曲线,两处订正:
      ① 「手上历史」改成**真实有效 bar 数** = t − max(o, 该票第一根有效 bar)
      ② 只用**真的切掉了数据**的起点(o > 该票第一根有效 bar)
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))
    n = len(idx_d)

    # ① 恒等式验证:任务点名的四个起点,输入是不是同一个
    ident = {"比了多少只票": 0, "逐格完全相同的票数": 0, "有差异的票": []}
    for s in syms:
        base, _r, _e = SP.daily_labels(cl[s].to_numpy(), 0)
        same = True
        for o in (60, 120, 250):
            lab, _r2, _e2 = SP.daily_labels(cl[s].to_numpy(), o)
            m = (base != None) & (lab != None)          # noqa: E711
            if not bool((base[m] == lab[m]).all()):
                same = False
        ident["比了多少只票"] += 1
        ident["逐格完全相同的票数"] += int(same)
        if not same:
            ident["有差异的票"].append(s)
    ident["★★★ 结论"] = (
        f"300 只票里 {ident['逐格完全相同的票数']} 只在起点 0/60/120/250 上"
        f"**逐格完全相同** —— ★★★ 因为这三个偏移全切在 2014–2015 的空白段里,"
        f"喂进去的有效序列一个 bar 都没少。"
        f"所以上一轮「点名的四个起点 0 格变号」**是个恒等式**,"
        f"★ 不能当成「阶段号不依赖路径」的证据。")

    # ② 订正后的校准曲线
    BK = ((0, 250), (250, 400), (400, 550), (550, 700), (700, 1000),
          (1000, 10 ** 9))
    c_fl = {b: 0 for b in BK}
    w_fl = {b: 0 for b in BK}
    c_all = {b: 0 for b in BK}
    w_all = {b: 0 for b in BK}
    per_off = []

    base_lab = {}
    for s in syms:
        base_lab[s], _r, _e = SP.daily_labels(cl[s].to_numpy(), 0)

    pos = np.arange(n)
    for o in offsets:
        ncmp = ndiff = 0
        for s in syms:
            f = fv[s]
            if o <= f:
                continue            # ★ 这个起点对这只票**没切掉任何有效 bar**,跳过
            lab, _r, _e = SP.daily_labels(cl[s].to_numpy(), o)
            b = base_lab[s]
            ok = (keep & (b != tri.WARMUP) & (b != None)            # noqa: E711
                  & (lab != tri.WARMUP) & (lab != None))            # noqa: E711
            d = ok & (b != lab)
            ncmp += int(ok.sum())
            ndiff += int(d.sum())
            hist = pos - max(o, f)              # ★★★ 真实有效 bar 数
            flat = ok & np.isin(lab.astype(str), ["1", "3"])
            for lo, hi in BK:
                m1 = ok & (hist >= lo) & (hist < hi)
                c_all[(lo, hi)] += int(m1.sum())
                w_all[(lo, hi)] += int((m1 & d).sum())
                m2 = flat & (hist >= lo) & (hist < hi)
                c_fl[(lo, hi)] += int(m2.sum())
                w_fl[(lo, hi)] += int((m2 & d).sum())
        per_off.append({"起点偏移(交易日)": o, "可比格子": ncmp,
                        "与全历史不同": ndiff,
                        "比例": round(ndiff / max(1, ncmp), 6)})

    def _tab(c, w):
        return [{"手上历史(**有效交易日 bar 数**)":
                 f"{lo}~{hi if hi < 10**9 else '∞'}",
                 "格子": c[(lo, hi)], "阶段号与全历史不同": w[(lo, hi)],
                 "错号率": (round(w[(lo, hi)] / c[(lo, hi)], 4)
                           if c[(lo, hi)] else None)}
                for lo, hi in BK]

    tab_fl = _tab(c_fl, w_fl)
    # ★ H* 的选法(★★ 事先定好的规则,不是看着数挑的):
    #   从小到大取第一个满足「**它自己和比它更长的每一个桶**都:
    #   格子数 ≥1,000 且错号率 <1%」的桶的下界。
    #   ★ 为什么要「以及更长的全部」:单看一个桶会被小样本和非单调噪声骗 ——
    #     今天已经踩过一次「挑最好的那一点」的坑。
    MIN_CELLS = 1000
    hstar = None
    for a_i, (lo, hi) in enumerate(BK):
        tail = BK[a_i:]
        good = all(c_fl[b] >= MIN_CELLS and w_fl[b] / c_fl[b] < 0.01 for b in tail)
        if good:
            hstar = lo
            break
    return {
        "★★★ 恒等式验证(上一轮点名的四个起点)": ident,
        "★ 面板的空白段": {
            "面板索引范围": f"{idx_d[0].date()} ~ {idx_d[-1].date()}(共 {n} 个交易日格)",
            "★★★ 第一根有效 bar": "2016-01-04(索引 504)—— 2014/2015 整段为空",
            "第一根有效 bar 的索引分布": dict(Counter(fv.values()).most_common(6)),
            "后果": "「索引距离」比「真实有效 bar 数」多算约 504 根 —— "
                   "上一轮那张校准表的横轴整体右移了这么多。",
        },
        "订正后_逐起点(只用真的切掉了数据的起点)": per_off,
        "订正后_校准曲线_全部格子": _tab(c_all, w_all),
        "★★★ 订正后_校准曲线_只看走平格子": tab_fl,
        "★★★ H*(真值门槛)": hstar,
        "H* 的选法": "★【XING 填的】事先定好的规则:从小到大第一个满足"
                    "「它自己和比它更长的每一个桶都:格子数 ≥1,000 且错号率 <1%」"
                    "的桶的下界。★ 不是看着数挑的,也不许只看一个桶。",
    }


# ═══════════════════════════════════════════════════════════════════════════
# 二 · 真值集 + 类别分布 + 池子口径
# ═══════════════════════════════════════════════════════════════════════════

def build_truth(cl: pd.DataFrame, syms: list[str], fv: dict[str, int],
                hstar: int) -> dict:
    """
    真值集 = 走平格子(label ∈ {1,3})× 真实有效历史 ≥ H* × 可比窗口内。
    ★ 同时按**池子口径(大+中池,rank ≤ 2000)**切一份,两份都报。
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))
    pos = np.arange(len(idx_d))
    years = np.asarray([str(y) for y in idx_d.year])
    pi = pool_scope.PoolIndex()

    cells = {"sym": [], "t": [], "truth": []}
    inscope = []
    ev_rows = []
    scope_ctr = Counter()
    labs_all = {}
    for s in syms:
        lab, _raw, ev = SP.daily_labels(cl[s].to_numpy(), 0)
        labs_all[s] = lab
        hist = pos - fv[s]
        m = (keep & (hist >= hstar)
             & np.isin(np.asarray([str(x) for x in lab]), ["1", "3"]))
        tt = np.flatnonzero(m)
        # 池子口径:按 (symbol, 当年) 查排名 —— ★ 用 PoolIndex(它管改名,ANTM/ELV)
        rk_by_year = {}
        for y in set(years[tt].tolist()) if len(tt) else set():
            r, _tier, how = pi.resolve(s, y)
            rk_by_year[y] = (r is not None and r <= 2000)
            scope_ctr[how] += 1
        for t in tt:
            cells["sym"].append(s)
            cells["t"].append(int(t))
            cells["truth"].append(str(lab[t]))
            inscope.append(bool(rk_by_year.get(years[t], False)))
        for e in ev:
            i = int(e["i"])
            if e["stage"] in ("1", "3") and keep[i] and (i - fv[s]) >= hstar:
                ev_rows.append({"sym": s, "t": i, "truth": e["stage"],
                                "prev": e["prev"]})
    nz = len(cells["t"])
    tr = np.asarray(cells["truth"])
    isc = np.asarray(inscope)
    return {
        "_cells": cells, "_inscope": inscope, "_events": ev_rows,
        "_labs": labs_all,
        "H*": hstar,
        "★★ 真值集(全 300 只)": {
            "格子数": nz,
            "阶段一(底部)": int((tr == "1").sum()),
            "阶段三(顶部)": int((tr == "3").sum()),
            "★★★ 多数类占比(= 真正的「瞎猜上限」)":
                round(max((tr == "1").sum(), (tr == "3").sum()) / max(1, nz), 4),
            "涉及票数": len(set(cells["sym"])),
            "日期范围": [str(idx_d[min(cells['t'])].date()),
                       str(idx_d[max(cells['t'])].date())] if nz else [],
        },
        "★★ 真值集(只要大+中池,rank ≤ 2000)": {
            "格子数": int(isc.sum()),
            "阶段一(底部)": int(((tr == "1") & isc).sum()),
            "阶段三(顶部)": int(((tr == "3") & isc).sum()),
            "多数类占比": (round(max(((tr == "1") & isc).sum(),
                                   ((tr == "3") & isc).sum()) / max(1, int(isc.sum())), 4)),
            "占全 300 只的比例": round(float(isc.mean()), 4) if nz else None,
        },
        "池子口径": pool_scope.SCOPE_LABELS[pool_scope.active_scope()],
        "池子查表方式": dict(scope_ctr),
        "★ 为什么两份都报": "任务纪律要求大+中池;但上一轮(stage_path/phaseshift)"
                          "的数字是全 300 只口径。两份并列 → 两轮数字都可比,"
                          "也看得出小票有没有在带节奏。",
        "★★ 确认事件数(每段阶段一/三只算一次)": len(ev_rows),
        "事件里阶段一 / 阶段三": [sum(1 for e in ev_rows if e["truth"] == "1"),
                               sum(1 for e in ev_rows if e["truth"] == "3")],
    }


# ═══════════════════════════════════════════════════════════════════════════
# 三 · 量指标评分(Arena A:真值可信的格子)
# ═══════════════════════════════════════════════════════════════════════════

def offset_independence_selftest(p: dict, syms: list[str]) -> dict:
    """
    ★★★ 必须先证明的一件事:量指标**不依赖起点**。
    (如果它也依赖起点,那它就不是「独立于路径」的判据,整轮作废。)

    测法:对同一只票,用全序列和从第 o 个交易日切开的序列各算一遍,
          在 t − o ≥ 50 + W + 1 的格子上比,**必须逐格相同**。
    ★ 对不上 → raise。
    """
    bad = 0
    tot = 0
    for s in syms[:12]:
        cols = {f: p[f][s].to_numpy() for f in ("open", "high", "low", "close", "volume")}
        P_full = VD.bar_prims(cols["open"], cols["high"], cols["low"],
                              cols["close"], cols["volume"])
        for o in (700, 1400):
            P_cut = VD.bar_prims(*[cols[f][o:] for f in
                                   ("open", "high", "low", "close", "volume")])
            for name, spec in VD.INDICATORS.items():
                W, k = spec["variants"][0]
                a = VD.score_panel(P_full, name, W, k)
                b = VD.score_panel(P_cut, name, W, k)
                lo = o + VD.VOL_BASE + W + 2
                x = a[lo:]
                y = b[lo - o:]
                n = min(len(x), len(y))
                x, y = x[:n], y[:n]
                tot += n
                # ★★ 判据要严:**「一边算得出、另一边算不出」也算不一致**。
                #   ★ 第一版用 np.nansum 写的,那样 NaN↔有值 会被静默跳过 ——
                #     这正是今天反复踩的那一类(「没查」被当成「查了没问题」)。
                fx, fy = np.isfinite(x), np.isfinite(y)
                bad += int((fx != fy).sum())
                both = fx & fy
                # ★ 指标 3/4 是累积线的斜率 —— 累积起点不同会整体平移,
                #   但 OLS 斜率只看窗口内的形状,所以也该逐格相同。
                bad += int((np.abs(x[both] - y[both]) > 1e-9).sum())
    return {"比了多少格": tot, "不一致的格子": bad,
            "★★★ 结论": ("量指标逐格不依赖起点 → 它是真正独立于路径的判据"
                         if bad == 0 else "★★ 量指标也依赖起点,本轮结论作废")}


def arena_a(p: dict, truth: dict, cl: pd.DataFrame) -> dict:
    """
    ★★★ Arena A:在真值可信的格子上,量指标能不能**独立**判出同一个编号。

    ★★ 一个必须先讲清的事(否则第四问会被答成循环论证):
       在这个场子里,**「只用形态(现有路径规则)」的准确率是 100%** ——
       因为真值**就是**那条路径规则在全历史上的输出。
       ★★★ 所以「量 vs 形态」的较量**不能在这里比**,只能在第四节(短历史)比。
    """
    idx_d = cl.index
    cells = truth["_cells"]
    isc = np.asarray(truth["_inscope"])
    tr_all = np.asarray(cells["truth"])
    syms_cell = np.asarray(cells["sym"])
    t_cell = np.asarray(cells["t"])
    dates = idx_d.to_numpy()[t_cell]

    ev = truth["_events"]
    ev_sym = np.asarray([e["sym"] for e in ev])
    ev_t = np.asarray([e["t"] for e in ev])
    ev_tr = np.asarray([e["truth"] for e in ev])
    ev_dates = idx_d.to_numpy()[ev_t] if len(ev_t) else np.asarray([])

    # 逐票算分 → 填进格子向量
    variants = [(nm, W, k) for nm, spec in VD.INDICATORS.items()
                for (W, k) in spec["variants"]]
    sc_cell = {v: np.full(len(t_cell), np.nan) for v in variants}
    sc_ev = {v: np.full(len(ev_t), np.nan) for v in variants}

    for s in sorted(set(cells["sym"]) | set(ev_sym.tolist())):
        cols = [p[f][s].to_numpy() for f in ("open", "high", "low", "close", "volume")]
        P = VD.bar_prims(*cols)
        mc = syms_cell == s
        me = ev_sym == s
        tc = t_cell[mc]
        te = ev_t[me]
        for v in variants:
            nm, W, k = v
            sc = VD.score_panel(P, nm, W, k)
            if len(tc):
                sc_cell[v][mc] = sc[tc]
            if len(te):
                sc_ev[v][me] = sc[te]

    res: dict = {
        "★★★ 这个场子里「只用形态」的准确率": "100%(循环) —— "
            "真值**就是**路径规则在全历史上的输出。★ 所以「量 vs 形态」只能在第四节比。",
        "逐指标": {},
    }
    for nm, spec in VD.INDICATORS.items():
        vs = [(nm, W, k) for (W, k) in spec["variants"]]
        entry = {"归属": spec["attr"], "大白话": spec["plain"], "参数点": {}}
        for v in vs:
            _nm, W, k = v
            key = f"窗口{W}" + (f"×放量{k}倍" if k is not None else "")
            e_all = VD.evaluate(sc_cell[v], tr_all)
            e_isc = VD.evaluate(np.where(isc, sc_cell[v], np.nan), tr_all)
            e_ev = (VD.evaluate(sc_ev[v], ev_tr) if len(ev_tr) else {"★ 跑不了": "没有事件"})
            seg = VD.two_segment(sc_cell[v], tr_all, dates)
            seg_ev = (VD.two_segment(sc_ev[v], ev_tr, ev_dates)
                      if len(ev_tr) else {"★ 跑不了": "没有事件"})
            entry["参数点"][key] = {
                "格子级_全300只": e_all,
                "格子级_大中池": e_isc,
                "★★ 事件级(每段只算一次 —— 格子级有严重自相关)": e_ev,
                "★★★ 两段一致性_格子级": seg,
                "★★★ 两段一致性_事件级": seg_ev,
            }
        # 三点同向(★ 窗口三点,放量倍数固定 2.0;有 k 的指标另报倍数三点)
        def _trio(sel):
            return VD.same_direction([entry["参数点"][x]["格子级_全300只"] for x in sel])
        keys = list(entry["参数点"])
        if spec["needs_k"]:
            win_trio = [f"窗口{W}×放量2.0倍" for W in VD.WINDOWS]
            k_trio = [f"窗口20×放量{k}倍" for k in VD.VOL_MULTS]
            entry["★★★ 三点同向_窗口(10/20/30,倍数固定2.0)"] = _trio(win_trio)
            entry["★★★ 三点同向_放量倍数(1.5/2.0/2.5,窗口固定20)"] = _trio(k_trio)
            entry["★★★ 三点同向(两组都要过)"] = bool(
                entry["★★★ 三点同向_窗口(10/20/30,倍数固定2.0)"]["三点同向"]
                and entry["★★★ 三点同向_放量倍数(1.5/2.0/2.5,窗口固定20)"]["三点同向"])
        else:
            entry["★★★ 三点同向_窗口(10/20/30)"] = _trio(keys)
            entry["★★★ 三点同向(两组都要过)"] = bool(
                entry["★★★ 三点同向_窗口(10/20/30)"]["三点同向"])
        res["逐指标"][nm] = entry

    # 指标之间的相关性 —— ★ 防「假独立」(六个指标其实是同一个东西的六种写法)
    base_v = [(nm, 20, 2.0 if VD.INDICATORS[nm]["needs_k"] else None)
              for nm in VD.INDICATORS]
    M = np.vstack([sc_cell[v] for v in base_v])
    corr = {}
    for i in range(len(base_v)):
        for j in range(i + 1, len(base_v)):
            a, b = M[i], M[j]
            m = np.isfinite(a) & np.isfinite(b)
            if m.sum() > 1000:
                corr[f"{base_v[i][0]} vs {base_v[j][0]}"] = round(
                    float(np.corrcoef(a[m], b[m])[0, 1]), 3)
    res["★★ 六个指标互相的相关系数(窗口20)"] = corr
    res["★ 为什么要报相关系数"] = (
        "★★ 「同一样东西几种写法」今天已经累计 27 处。"
        "六个指标如果互相 0.9+,那「六个指标都这么说」就不是六份证据,是一份。")
    res["_sc_cell_best"] = None
    res["_variants"] = [f"{a}|{b}|{c}" for a, b, c in variants]
    return res


# ═══════════════════════════════════════════════════════════════════════════
# 四 · Arena B:历史 <400 天的格子 —— 量 / 形态 / 量+形态 三种并列
# ═══════════════════════════════════════════════════════════════════════════

def arena_b(p: dict, cl: pd.DataFrame, syms: list[str], fv: dict[str, int],
            hstar: int, offsets: tuple[int, ...], picks: list[tuple]) -> dict:
    """
    ★★★ 这一节才是「量最重要」能不能成立的唯一场子。

    构造:把序列从第 o 个交易日切开(o 真的切掉有效 bar)→ 得到一个「历史很短」的
          运行态。于是同一个格子 t 上有三样东西:
            · **真值**     = 全历史算出来的阶段号(要求全历史 ≥ H*)
            · **形态判断** = 截断后的路径规则算出来的阶段号(历史 <400)
            · **量判断**   = 量指标(★ 已证明不依赖起点)
    ★★ 三种做法并列:只用量 / 只用形态 / 量+形态(组合规则事先定好,见下)
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))
    pos = np.arange(len(idx_d))
    BUCKETS = ((0, 250), (250, 400))
    rows = {pk: {b: Counter() for b in BUCKETS} for pk in picks}
    disagree_detail = {pk: Counter() for pk in picks}

    base_lab = {}
    scores = {}
    for s in syms:
        base_lab[s], _r, _e = SP.daily_labels(cl[s].to_numpy(), 0)
        cols = [p[f][s].to_numpy() for f in ("open", "high", "low", "close", "volume")]
        P = VD.bar_prims(*cols)
        scores[s] = {pk: VD.score_panel(P, pk[0], pk[1], pk[2]) for pk in picks}

    n_off_used = 0
    for o in offsets:
        used = False
        for s in syms:
            f = fv[s]
            if o <= f:
                continue
            used = True
            lab_t, _r, _e = SP.daily_labels(cl[s].to_numpy(), o)
            b = base_lab[s]
            hist = pos - o                       # ★ 截断后真实有效历史
            hist_full = pos - f
            bs = np.asarray([str(x) for x in b])
            ts = np.asarray([str(x) for x in lab_t])
            # ★★★ 评分集合 = **真值有话说**的格子(base ∈ {1,3} 且全历史 ≥H*)。
            #   ★ 不许再要求「形态也有话说」—— 那样会只在形态敢开口的地方给它打分,
            #     把它的覆盖率问题藏起来。★★ 这一条是改过的:第一版就犯了这个错。
            ok = keep & np.isin(bs, ["1", "3"]) & (hist_full >= hstar)
            for lo, hi in BUCKETS:
                m = ok & (hist >= lo) & (hist < hi)
                if not m.any():
                    continue
                truth_a = bs
                for pk in picks:
                    sc = scores[s][pk]
                    cnt = rows[pk][(lo, hi)]
                    cnt["★ 评分集合(真值有话说的格子)"] += int(m.sum())
                    # —— 形态这边:它可能「说不清」
                    sh_has = m & np.isin(ts, ["1", "3"])
                    cnt["形态有话说"] += int(sh_has.sum())
                    cnt["形态判对(在它有话说的格子上)"] += int(
                        (sh_has & (ts == truth_a)).sum())
                    for lv in ("1", "2", "3", "4", "transition", "WARMUP"):
                        cnt[f"形态说成_{lv}"] += int((m & (ts == lv)).sum())
                    # —— 量这边
                    vh = m & np.isfinite(sc) & (sc != 0.0)
                    volp_full = np.where(sc > 0, "1", "3")
                    cnt["量有话说"] += int(vh.sum())
                    cnt["量判对(在它有话说的格子上)"] += int(
                        (vh & (volp_full == truth_a)).sum())
                    # —— 量+形态(组合规则:一致取一致;分歧取量;只有一方有话说取那一方)
                    comb_ok = m & (sh_has | vh)
                    comb = np.where(vh, volp_full, ts)
                    cnt["量+形态有话说"] += int(comb_ok.sum())
                    cnt["量+形态判对"] += int((comb_ok & (comb == truth_a)).sum())
                    # —— 分歧只在**两边都有话说**的格子上算
                    both = sh_has & vh
                    dis = both & (ts != volp_full)
                    cnt["两边都有话说"] += int(both.sum())
                    cnt["分歧格子"] += int(dis.sum())
                    cnt["分歧里量说底(1)"] += int((dis & (volp_full == "1")).sum())
                    cnt["分歧里量说顶(3)"] += int((dis & (volp_full == "3")).sum())
                    cnt["分歧里量对了"] += int((dis & (volp_full == truth_a)).sum())
                    cnt["分歧里形态对了"] += int((dis & (ts == truth_a)).sum())
                    # ★★★ 两种错分开:底判成顶 / 顶判成底
                    cnt["量_真底判成顶"] += int((vh & (truth_a == "1")
                                              & (volp_full == "3")).sum())
                    cnt["量_真顶判成底"] += int((vh & (truth_a == "3")
                                              & (volp_full == "1")).sum())
                    cnt["形态_真底判成顶"] += int((sh_has & (truth_a == "1")
                                                & (ts == "3")).sum())
                    cnt["形态_真顶判成底"] += int((sh_has & (truth_a == "3")
                                                & (ts == "1")).sum())
                    cnt["真底"] += int((m & (truth_a == "1")).sum())
                    cnt["真顶"] += int((m & (truth_a == "3")).sum())
                    disagree_detail[pk][f"{lo}~{hi}"] += int(dis.sum())
        n_off_used += int(used)

    out = {"用了多少个起点": n_off_used, "起点集合": list(offsets),
           "组合规则(★ 事先定好的)": "两边一致 → 取一致值;★ 分歧 → **取量**;"
                                   "只有一方有话说 → 取那一方。"
                                   "★ 分歧时取量的理由:这个场子里形态的历史 <400 天,"
                                   "上一轮报过它在这一档错号率三到五成。",
           "★★★ 「准确率」在这一节怎么读": (
               "★ 覆盖率和准确率**分开报**:准确率的分母是「它有话说的格子」,"
               "不是全部格子。★★★ 一个覆盖 5% 的指标即使准确率 90%,"
               "也不等于它能替掉一个覆盖 80% 的 —— 两个数必须一起看。"),
           "逐指标": {}}
    for pk in picks:
        e = {}
        for b in BUCKETS:
            c = rows[pk][b]
            N = c["★ 评分集合(真值有话说的格子)"]
            if N == 0:
                e[f"历史 {b[0]}~{b[1]} 个交易日"] = {"★ 跑不了": "没有格子"}
                continue
            sh, vh, ch = c["形态有话说"], c["量有话说"], c["量+形态有话说"]
            e[f"历史 {b[0]}~{b[1]} 个交易日"] = {
                "★ 评分集合(真值有话说的格子)": N,
                "其中真底 / 真顶": [c["真底"], c["真顶"]],
                "★★★ 只用形态": {
                    "覆盖率": round(sh / N, 4), "有话说的格子": sh,
                    "准确率(在它有话说的格子上)":
                        (round(c["形态判对(在它有话说的格子上)"] / sh, 4) if sh else None),
                    "★★ 它说不清的时候说成了什么": {
                        lv: c[f"形态说成_{lv}"] for lv in
                        ("2", "4", "transition", "WARMUP") if c[f"形态说成_{lv}"]},
                },
                "★★★ 只用量": {
                    "覆盖率": round(vh / N, 4), "有话说的格子": vh,
                    "准确率(在它有话说的格子上)":
                        (round(c["量判对(在它有话说的格子上)"] / vh, 4) if vh else None),
                },
                "★★★ 量+形态": {
                    "覆盖率": round(ch / N, 4), "有话说的格子": ch,
                    "准确率(在它有话说的格子上)":
                        (round(c["量+形态判对"] / ch, 4) if ch else None),
                },
                "★★ 分歧(只在两边都有话说的格子上算)": {
                    "两边都有话说": c["两边都有话说"],
                    "★★★ 分歧率": (round(c["分歧格子"] / c["两边都有话说"], 4)
                                 if c["两边都有话说"] else None),
                    "分歧格子": c["分歧格子"],
                    "★★★ 分歧里量说底(阶段一)": c["分歧里量说底(1)"],
                    "★★★ 分歧里量说顶(阶段三)": c["分歧里量说顶(3)"],
                    "分歧里量对了": c["分歧里量对了"],
                    "分歧里形态对了": c["分歧里形态对了"],
                    "★★ 分歧里量的胜率": (round(c["分歧里量对了"] / c["分歧格子"], 4)
                                       if c["分歧格子"] else None),
                },
                "★★★ 两种错分开(代价完全不同)": {
                    "量_真底判成顶(会让人在底部卖出)": c["量_真底判成顶"],
                    "量_真顶判成底(会让人在顶部买入)": c["量_真顶判成底"],
                    "形态_真底判成顶": c["形态_真底判成顶"],
                    "形态_真顶判成底": c["形态_真顶判成底"],
                },
            }
        out["逐指标"][f"{pk[0]}|窗口{pk[1]}" + (f"×{pk[2]}倍" if pk[2] else "")] = e
    return out


# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", type=int, default=0, help="先用 N 只票量耗时")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    t0 = time.time()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO,
                            capture_output=True, text=True).stdout.strip()
    p = cache.load()
    cl = p["close"]
    syms = list(cl.columns)
    if a.smoke:
        syms = syms[:a.smoke]
        cl = cl[syms]
    print(f"池子 {len(syms)} 只 × {len(cl)} 个交易日 "
          f"({cl.index[0].date()} ~ {cl.index[-1].date()})")
    fv = first_valid_idx(cl, syms)

    # ---- 零 · 血统 ----
    if a.smoke:
        lin = {"★ smoke 模式跳过(血统对账必须全 300 只)": True}
    else:
        lin = None if a.force else _load("0血统")
        if lin is None:
            print("零 · 血统对账 …")
            lin = lineage(cl, syms)
            _dump("0血统", lin)
    print("   " + str(lin.get("★★★ 换回修复前的分支之后", lin))[:90])

    # ---- 一 · 真值前提 ----
    OFF_CURVE = tuple(range(520, 2301, 120))
    tp = None if a.force else _load("1真值前提")
    if tp is None:
        print(f"一 · 真值前提复核({len(OFF_CURVE)} 个起点)…")
        tp = truth_premise(cl, syms, fv, OFF_CURVE)
        _dump("1真值前提", tp)
    hstar = tp["★★★ H*(真值门槛)"]
    print(f"   H* = {hstar} 个有效交易日 bar")
    if hstar is None:
        raise RuntimeError("★★ 没有任何历史长度桶的错号率 <1% → 真值立不住,"
                           "本轮不许往下跑。这本身就是结论。")

    # ---- 二 · 真值集 ----
    print("二 · 真值集 …")
    truth = build_truth(cl, syms, fv, hstar)
    pub = {k: v for k, v in truth.items() if not k.startswith("_")}
    _dump("2真值集", pub)
    print(f"   真值格子 {pub['★★ 真值集(全 300 只)']['格子数']} 个;"
          f"多数类 {pub['★★ 真值集(全 300 只)']['★★★ 多数类占比(= 真正的「瞎猜上限」)']}")

    # ---- 三 · 量指标 ----
    print("三 · 量指标不依赖起点 自测 …")
    st = offset_independence_selftest(p, syms)
    print("   " + st["★★★ 结论"])
    if st["不一致的格子"] != 0:
        raise RuntimeError("★★ 量指标也依赖起点 → 它不是独立判据,本轮结论作废。"
                           f" {st}")

    aa = None if a.force else _load("3量指标")
    if aa is None:
        print("三 · Arena A 评分 …")
        aa = arena_a(p, truth, cl)
        aa["量指标不依赖起点_自测"] = st
        aa.pop("_sc_cell_best", None)
        _dump("3量指标", aa)
    for nm, e in aa["逐指标"].items():
        k0 = [x for x in e["参数点"] if x in (f"窗口20×放量2.0倍", "窗口20")]
        if k0:
            g = e["参数点"][k0[0]]["格子级_全300只"]
            print(f"   {nm:22s} 覆盖 {g.get('★★ 覆盖率')} "
                  f"准确率 {g.get('★★★ 准确率')} (多数类 "
                  f"{g.get('★★ 多数类基线(真正的「瞎猜上限」)')}) "
                  f"AUC {g.get('★★ AUC(与阈值无关)')} "
                  f"三点同向 {e.get('★★★ 三点同向(两组都要过)')}")

    # ---- 四 · Arena B ----
    # ★ 挑谁进 Arena B:① 过了三点同向的全部;② 若一个都没过,
    #   也要把 AUC 离 0.5 最远的那个拿进去 —— 因为必答第三问要这个分歧数。
    def _base(nm):
        return (nm, 20, 2.0 if VD.INDICATORS[nm]["needs_k"] else None)

    why = []
    # ★★★ ① 策略组自己的那一条**一律进场** —— 必答第三问问的就是它。
    picks = [_base("1-放量日方向性")]
    why.append("★★★ 1-放量日方向性 无条件进场 —— 它就是策略组「进 vs 出」那条主张,"
               "不管过不过关都要把分歧数报出来。")
    # ② 过了三点同向的
    for nm, e in aa["逐指标"].items():
        if e.get("★★★ 三点同向(两组都要过)") and _base(nm) not in picks:
            picks.append(_base(nm))
            why.append(f"★ {nm} 过了三点同向 → 进场。")
    # ③ 基准参数点上 |AUC−0.5| 最大的两个(信息量最大的,哪边都算)
    rank = []
    for nm, e in aa["逐指标"].items():
        kk = f"窗口20×放量2.0倍" if VD.INDICATORS[nm]["needs_k"] else "窗口20"
        au = e["参数点"].get(kk, {}).get("格子级_全300只", {}).get("★★ AUC(与阈值无关)")
        if au is not None:
            rank.append((abs(au - 0.5), nm, au))
    for d, nm, au in sorted(rank, reverse=True)[:2]:
        if _base(nm) not in picks:
            picks.append(_base(nm))
            why.append(f"★ {nm} 在基准参数点上 AUC={au}(离 0.5 最远)→ 进场。"
                       f"{'★★ 注意 AUC <0.5 = 信息方向和假设**相反**。' if au < 0.5 else ''}")
    forced = why
    OFF_B = tuple(range(1120, 2601, 80))
    ab = None if a.force else _load("4短历史")
    if ab is None:
        print(f"四 · Arena B(短历史,{len(OFF_B)} 个起点,{len(picks)} 个指标)…")
        ab = arena_b(p, cl, syms, fv, hstar, OFF_B, picks)
        ab["进 Arena B 的指标是怎么挑的"] = (forced or
                                          ["过了三点同向的全部指标"])
        _dump("4短历史", ab)
    print("   " + json.dumps({k: v for k, v in list(ab["逐指标"].items())[:1]},
                             ensure_ascii=False)[:300])

    summary = {
        "git_commit": commit,
        "池子": f"{len(syms)} 只 × {len(cl)} 个交易日",
        "池子口径": pool_scope.SCOPE_LABELS[pool_scope.active_scope()],
        "时间尺度声明": TIME_SCALE,
        "★★ 字段/判据含义声明(我是这样理解的,可反驳)": FIELD_SEMANTICS,
        "★ 实现口径登记(我自己填的,逐条)": MY_NOTES + VD.__doc__.strip().split("\n")[:1],
        "用了多少秒": round(time.time() - t0, 1),
    }
    _dump("2真值集", {**pub, "_summary": summary})
    print(f"\n全部跑完,用了 {time.time()-t0:.1f} 秒")
    print("产物:" + ", ".join(os.path.basename(v) for v in OUT.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
