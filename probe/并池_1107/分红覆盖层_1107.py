# -*- coding: utf-8 -*-
"""★★★ 分红覆盖层 —— ★ 让 `data.dividends()` 能看见并池那 3,858 只的分红。

★★★ 为什么要有这一层（《24》#80）：
  ★ 今天我打开了 `TOTAL_RETURN_DEFAULT = True`，并且自证打印了「False → True」，
    ★★ 然后宣布「本批是全收益口径」。
  ★★★ 但 `data.dividends(票)` 是从 **`load_manifest()`** 里找文件路径的，
    而那份 manifest 是**默认的 300 只 pilot 名单** —— 我们换了池子（3,858 只）
    却**没换这份名单**。
  → ★★ 实测：面板 ∩ 默认 manifest = **237 只**（约 6%）；基准 SPY = **0 条分红**。
  → ★★★ 也就是说：那个开关**几乎是空转的**，口径标签是错的。

★★ 这跟 #74（池表没换，universe 掩膜把苹果微软全排除）是**同一个毛病**：
  ★ 换了池子，但**没把所有依赖池子的入口都换掉**。
  ★★★ 三个登记点 → 现在是**四个**：面板 · manifest · 池表 · **分红**。

★★★ 结构性改法（规矩㊻ —— 同类错第七次，不许再立「下次记得」）：
  ★ 自证不许再打印「我按了开关」，★★ 必须打印「**它真的起作用了**」：
    覆盖了几只 · 非零分红格子数 · 基准侧几条 —— ★★★ 覆盖率不够**直接停跑**。

★ engine 零改动：进程内替换 `data.dividends` 的函数指针，没命中原样退回原函数。
"""
from __future__ import annotations
import glob
import gzip
import json
import os
import pandas as pd

from engine import data, split_gate

# ★ 和《并池》《接新基准》同一套扫法：按目录名倒序，新交付优先
_股票目录 = ("exam_1042", "exam_pre2016_1107", "pilot_300", "pilot_50")
_基准目录 = ("market_macro_1105", "market_extra_1107", "market_ext_1105",
            "market_etf_1107", "market_etf_1106")

_原dividends = None
_路径表: dict[str, list[str]] = {}
_缓存: dict[str, pd.Series] = {}        # ★★★ 进程内缓存（见下方说明）
# ★★★★★ 1108：拆股折算的**效果**必须能被自证看到（账本 #97）——
#   ★ 之前那版把异常吞了、自证也没报，于是「折算一次没跑过」藏了一整天。
_折算生效: dict[str, int] = {}          # ★ 票 → 这只票被折算了几个拆股事件
_折算失败: dict[str, str] = {}          # ★★ 票 → 失败原因（★★★ 自证里必须报出来）
_缓存命中 = [0, 0]                      # ★ [命中, 落盘读]

# ★★★ 为什么必须缓存（1107 22:5x 实测）：
#   ★ `chain.py:493` 每跑一条臂就把 3858 只的分红**全扫一遍**建 div_mat，
#     ★★ 而 `_分红()` 每次调用都重新 gunzip + json.loads 整个日线文件
#     → ★★★ profile 实测 install() 一次就 34 秒，其中 json.raw_decode 占 21 秒。
#   ★ 一条臂多花 ~40 秒、11 条臂多花 ~8 分钟，纯属白烧。
# ★★ 缓存只省重复解码，**不改任何数字** —— 同一只票返回的 Series 完全一致。


def _扫(dirs) -> dict[str, list[str]]:
    """★ 票 → 它的日线文件列表（可能多段，★★ 比如 2004~2015 和 2016~ 两段）。"""
    出 = {}
    for d in dirs:
        if not os.path.isdir(d):
            continue
        for sub in sorted(os.listdir(d)):
            p = os.path.join(d, sub)
            if not os.path.isdir(p):
                continue
            fs = [f for f in sorted(glob.glob(os.path.join(p, "*")))
                  if "daily" in os.path.basename(f).lower()]
            if fs:
                出.setdefault(sub, []).extend(fs)
    return 出


def _读行(f: str) -> list:
    op = gzip.open if f.endswith(".gz") else open
    try:
        o = json.load(op(f, "rt", encoding="utf-8"))
    except Exception:
        return []
    if isinstance(o, list):
        return o
    return o.get("data") or o.get("results") or []


def _分红(票: str) -> pd.Series:
    """★★ 读出某只票的每股分红序列，★★★ 并按拆股系数折算到和价格同口径。

    ★ 带进程内缓存：★★ 同一只票只解码一次（★★★ 返回的内容和没缓存时逐字节相同）。
    """
    s = _缓存.get(票)
    if s is not None:
        _缓存命中[0] += 1
        return s
    _缓存命中[1] += 1
    s = _算分红(票)
    _缓存[票] = s
    return s


def _算分红(票: str) -> pd.Series:
    recs: dict[pd.Timestamp, float] = {}
    rows_all: list = []
    for f in _路径表.get(票, []):
        rows = _读行(f)
        rows_all.extend(rows)
        for r in rows:
            v = r.get("dividend_amount")
            if v in (None, "", 0, 0.0, "0", "0.0"):
                continue
            try:
                x = float(v)
            except (TypeError, ValueError):
                continue
            if x == 0.0 or x != x:
                continue
            recs[pd.Timestamp(str(r["date"])[:10])] = x      # ★ 多段重叠按后读到的为准
    if not recs:
        return pd.Series(dtype=float)
    s = pd.Series(recs).sort_index()
    # ★★★★★ 1108 修（审计线第 1 次 · R1）—— ★ 这一段之前**一次都没执行过**。
    #   ★★ 两处错叠在一起：
    #     ① `ratio_events_from_rows` 要 **2 个参数**(symbol, rows)，我只传了 1 个
    #        → 每次 TypeError → ★★★ 被 `except Exception: pass` **吃掉**。
    #     ② 就算参数补上，方向还是**反的**：engine 是 `s * ev.ratio`（乘），我写的是 `/=`（除）
    #        → ★★★ 折算会做到相反方向去，**比不折算更糟**。
    #     ★★★★★ ③ **主路 1108 复核时又查出第三层**（《130》第三节，有运行时证据）：
    #        就算①的参数补上，原来下一行写的是 `日, 比 = ev[0], ev[1]` —— ★ 而 `SplitEvent`
    #        是 `@dataclass(frozen=True)`，**不能下标** → `TypeError: not subscriptable`。
    #        → ★★★ 所以是「**一次都没执行过**」，不是「有时候没执行」。
    #        ★ 证据：probe/审计复核_1108/R1运行时证据_1108.json（隔离 import，没跑回测）。
    #   ★★★★★ 而我当时在 except 后面写的注释是「自证里会写出来」—— ★ 自证里根本没写。
    #     → ★★ 这正是 #80 的同一种病（「以为自证会兜住，其实它没兜」），
    #        ★★★ 而且是我**在修 #80 的代码里**又犯一次。账本 #97。
    #   → ★ 现在：★★ 严格照抄 `engine/data.dividends` 的写法（**乘**），
    #     ★★★ 并且**不再吞异常** —— 失败就记进 `_折算失败`，自证里**必须报出来**。
    # ★★★ 1108：只为了**量这个 bug 值多少**而留的开关（XING_NO_SPLIT_ADJ=1 → 关掉折算）。
    #   ★ 干净的测法只有一个：**同一份代码跑两遍，只开关这一项**。
    #   ★★ 默认是开（正确口径）；★★★ 关掉只许用于对照跑，**对照跑的数不许进结论**。
    if os.environ.get("XING_NO_SPLIT_ADJ") == "1":
        return s                      # ★ 不碰 _折算生效 —— ★★★ 让硬闸照常看到「0 只生效」
    try:
        evs = split_gate.ratio_events_from_rows(票, rows_all)
    except Exception as e:                      # ★ 只兜「读事件」这一步
        _折算失败[票] = f"{type(e).__name__}: {e}"
        return s
    n = 0
    for ev in evs:
        ts = pd.Timestamp(ev.date)
        m = s.index < ts
        if m.any():
            s.loc[m] = s.loc[m] * ev.ratio      # ★★★ 乘 —— 和 engine 逐字一致
            n += 1
    if n:
        _折算生效[票] = n
    return s


def install(需覆盖: list[str] | None = None, 最低覆盖率: float = 0.90) -> dict:
    """★ 装上覆盖层并返回自证。★★★ `需覆盖` 给面板的票列表时，覆盖率不足会抛。"""
    global _原dividends, _路径表
    if _原dividends is None:
        _原dividends = data.dividends
    _路径表 = _扫(_股票目录)
    _路径表.update(_扫(_基准目录))                     # ★ 基准也要能取到分红
    _缓存.clear()                                      # ★★ 路径表换了，缓存必须跟着清（否则读旧交付）
    _缓存命中[0] = _缓存命中[1] = 0
    _折算生效.clear()
    _折算失败.clear()

    def dividends(票: str) -> pd.Series:
        s = _分红(票)
        if len(s):
            return s
        return _原dividends(票)                        # ★★ 没命中原样退回，不悄悄返回空
    前 = id(data.dividends)
    data.dividends = dividends
    try:
        import engine.chain as _chain
        if hasattr(_chain, "data"):
            pass                                       # ★ chain 用的是 data.dividends 属性，已换
    except Exception:
        pass

    # ---- ★★★ 自证：证明「它真的起作用了」，不是「我按了开关」
    基准自证 = {}
    for b in ("SPY", "QQQ", "IWM", "IWD", "IWF"):
        s = dividends(b)
        基准自证[b] = f"{len(s)} 条" + (f" · {s.index[0].date()} → {s.index[-1].date()}"
                                      if len(s) else "  ★★★ 零！")
    自证 = {"★原dividends_id": 前, "★覆盖后id": id(data.dividends),
           "★真的换掉了": 前 != id(data.dividends),
           "★★★扫到的票": len(_路径表),
           "★★★基准侧分红": 基准自证,
           "★★★engine改动": "零（进程内替换函数指针）",
           "★没命中怎么办": "原样退回原函数，不悄悄返回空"}

    # ---- ★★★ 缓存自证：证明「缓存没改数字」，★ 不是「我加了缓存」（#80 的教训）
    抽样 = [t for t in sorted(_路径表)[:40]] + [b for b in ("SPY", "QQQ", "IWD")
                                               if b in _路径表]
    不一致 = []
    for t in 抽样:
        甲 = _分红(t)                                  # ★ 走缓存
        乙 = _算分红(t)                                # ★★ 绕过缓存重算
        if not (len(甲) == len(乙) and 甲.equals(乙)):
            不一致.append(t)
    自证["★★★缓存逐只对账"] = (f"抽 {len(抽样)} 只，缓存与重算"
                           + ("**完全一致**" if not 不一致 else f"★★★不一致 {不一致}"))
    if 不一致:
        raise AssertionError(f"★★★ 缓存改变了数字：{不一致} —— 停跑")

    if 需覆盖:
        有 = [t for t in 需覆盖 if len(dividends(t))]
        率 = len(有) / max(1, len(需覆盖))
        抽 = 需覆盖[: min(300, len(需覆盖))]
        格子 = int(sum(len(dividends(t)) for t in 抽))
        自证["★★★覆盖率"] = (f"{len(有)}/{len(需覆盖)} 只有分红记录 = {率*100:.1f}%"
                          f"（★ 抽前 {len(抽)} 只共 {格子} 个非零分红格子）")
        # ★★ 注意：不是每只票都付息（成长股、ETF 以外的很多票本来就零分红），
        #   ★★★ 所以这里的「覆盖率」指的是**能查到文件**的比例，不是付息比例。
        查得到 = [t for t in 需覆盖 if t in _路径表]
        自证["★★★查得到文件的比例"] = (f"{len(查得到)}/{len(需覆盖)} = "
                                 f"{len(查得到)/max(1,len(需覆盖))*100:.1f}%")
        # ★★★★★ 1108（账本 #97）：**拆股折算也必须证明它真的跑了。**
        #   ★ 之前那版这一段是静默失败的 —— ★★ 自证里只有「有没有分红」，
        #     ★★★ 没有「分红有没有和价格对齐口径」→ 口径标签又一次是假的。
        自证["★★★拆股折算生效"] = (f"{len(_折算生效)} 只被折算过，"
                             f"共 {sum(_折算生效.values())} 个拆股事件")
        自证["★★★拆股折算失败"] = (f"{len(_折算失败)} 只" +
                             (f"（例：{list(_折算失败.items())[:3]}）" if _折算失败 else "（无）"))
        if _折算失败:
            raise AssertionError(
                f"★★★ 拆股折算有 {len(_折算失败)} 只失败 —— 停跑。"
                f"★ 例：{list(_折算失败.items())[:3]}（#97：不许再吞这个异常）")
        if not _折算生效:
            # ★★★ 对照跑（故意关掉折算）走这一支：★ 不抛，但**必须在自证里喊出来**，
            #   ★★★ 不许让它看起来像一次正常的跑。
            if os.environ.get("XING_NO_SPLIT_ADJ") == "1":
                自证["★★★★★对照跑_折算被故意关掉"] = (
                    "★ XING_NO_SPLIT_ADJ=1 —— ★★ 这是**错口径的对照跑**，"
                    "★★★ 只用于量「这个 bug 值多少」；**这一跑的数不许进任何结论句**。")
            else:
                raise AssertionError(
                    "★★★★★ 拆股折算**一只都没生效** —— 停跑。"
                    "★ 池子里不可能一只有拆股的票都没有（抽样实测约 29% 同时有分红和拆股），"
                    "★★★ 所以这几乎一定是又一次静默失败（#97 就是这么藏了一整天）。")
        if len(查得到) / max(1, len(需覆盖)) < 最低覆盖率:
            raise AssertionError(
                f"★★★ 分红文件只覆盖 {len(查得到)}/{len(需覆盖)}，"
                f"低于 {最低覆盖率*100:.0f}% —— 停跑（#80：别再宣布空转的口径）")
    return 自证


def 全收益基准(符号: str = "SPY") -> pd.Series:
    """★★★ 基准的**全收益净值**（分红再投），★ 给条件 alpha 回归和懒人基准用。

    ★★ 规矩㊽：口径改动**两侧一起改**。★★★ 只给策略侧补分红、基准侧不补，
      等于**单方面给自己加分**（B 路 #77 实测过反方向的版本）。
    """
    px = data.load_benchmark(符号)["close"].dropna()
    dv = data.dividends(符号).reindex(px.index).fillna(0.0)
    r = px.pct_change().fillna(0.0) + (dv / px.shift(1)).fillna(0.0)
    return (1.0 + r).cumprod()


__all__ = ["install", "全收益基准"]
