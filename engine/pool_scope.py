#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 池子口径(POOL_SCOPE)—— 全仓库**唯一**一个「我们做哪些票」的开关。

三秒版:**只做大盘+中盘(当年成交额排名 1–2,000 名),小盘不做。**
        这件事实现成**一个参数**:`DEFAULT_SCOPE`。
        以后要把小盘加回来 = 把那个值从 `"large_mid"` 改成 `"full"`,★ 改完就完,
        **不需要重新建池、不需要删任何一行数据、不需要改任何别的代码。**

────────────────────────────────────────────────────────────────────────
★★★ 为什么是一个参数,而不是另存一份池子文件
────────────────────────────────────────────────────────────────────────
策略组 2026-10-30 拍板选了「乙:初期只做大+中」,原话是
    「乙,这个初期没问题,**以后可以再加**。」
★ 「以后可以再加」是一条**硬性设计约束**:
    · 小盘的数据**一行都不许删** —— `pool_FULL_ALL.csv` 74,268 行保持原样,只读;
    · 不许另存一份 `pool_LARGEMID.csv` —— 那样「加回来」就变成重建池子,
      而重建池子就会产生第二份口径,于是又回到「同一样东西两种写法」那个坑;
    · 筛选只用池子里**本来就有**的 `rank` 列(和它派生的 `tier` 列)。

────────────────────────────────────────────────────────────────────────
★ 三档口径(排名都是「当年年初回看 60 个**交易日**的日均成交额排名」)
────────────────────────────────────────────────────────────────────────
    large_mid : 1–2,000 名   ★ **新的默认值**(策略组拍板的「乙」)
    full      : 全池         ★ 保留 —— 旧结论要能复现对比,不然没法说「作废」
    large     : 1–500 名     ★ 顺手留着 —— 流动性那一轮测出「大盘档在
                               $5,000 万/日门槛下一笔都挡不掉」,所以这一档
                               是「完全不需要流动性门槛」的那个极端参照

★ 排名带和 `tier` 列的关系(见 probe/survivorship_1029/README-全量池-1030.md):
    大 = 1–500   中 = 501–2,000   小 = 2,001 以后
  所以 `rank <= 2000` 和 `tier in ("大","中")` 在这份池子里**恒等**。
  ★ 本模块以 `rank` 为准(它是定义),并提供 `tier_in_scope()` 做交叉核对 ——
    两者对不上就是池子文件被动过,调用方应当停下来查。

────────────────────────────────────────────────────────────────────────
★★ 一样东西两种写法(engine/checks/four_slot_complete.py 顶部那张表)
   本模块直接相关的两条:
────────────────────────────────────────────────────────────────────────
  ① 池子里的 symbol 是**当年年初那一刻**的代码(2018 年的安泰保险 = `ANTM`),
     流水里的 symbol 是**最终**代码(`ELV`)。★★★ 按 symbol 对会直接对丢
     8,554 笔(5.8%),而且**几乎全是小票** → 用 `company_id` + 年份双条件。
     本模块的 `PoolIndex` 就是干这件事的,★ 不要自己再写一遍按 symbol 对的版本。
  ② 池子的 `tier`(大/中/小)和流水的 `liquidity_tier`(高/中/低流动性)
     ★ **口径不同,不可混用** —— 前者按当年成交额排名,后者按当日横截面三分位。

★ 「天」一律是**交易日**:排名用的 60d、流水里的 20d ADV,全是交易日。
"""
from __future__ import annotations

import csv
import inspect
import os
import subprocess
from collections import defaultdict

# ══════════════════════════════════════════════════════════════════════════
# ★★★ 这就是那个参数 —— 改这一个值 = 换池子口径
# ══════════════════════════════════════════════════════════════════════════

#: 口径名 -> (排名下界, 排名上界;None = 不设上界)
SCOPES: dict[str, tuple[int, int | None]] = {
    "large_mid": (1, 2000),
    "full": (1, None),
    "large": (1, 500),
}

#: ★★★ 当前口径。策略组 2026-10-30 拍板:只做大+中。
#  ★ 把小盘加回来 = 把这一行改成 "full"。就这一行。
DEFAULT_SCOPE = "large_mid"

#: 临时换口径不用改文件:环境变量 XING_POOL_SCOPE=full
ENV_VAR = "XING_POOL_SCOPE"

#: 口径名 -> 给人看的说法(报告里的「池子口径」那一行直接用这个)
SCOPE_LABELS: dict[str, str] = {
    "large_mid": "大盘+中盘(成交额排名 1–2000)",
    "full": "全池(不设排名上限,含小盘)",
    "large": "只做大盘(成交额排名 1–500)",
}

#: 池子文件(相对仓库根)—— ★ 只读,一行都不许删
POOL_REL = os.path.join("probe", "survivorship_1029", "pool_FULL_ALL.csv")

#: 已知行数(纪律:读到的数要和已知数核对)
POOL_KNOWN_ROWS = 74_268

#: `tier` 列和排名带的对应(只用来交叉核对,不用来筛)
TIER_BANDS: dict[str, tuple[int, int | None]] = {
    "大": (1, 500),
    "中": (501, 2000),
    "小": (2001, None),
}

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def pool_path() -> str:
    return os.path.join(ROOT, POOL_REL)


def active_scope(scope: str | None = None) -> str:
    """当前口径名:显式传入 > 环境变量 > DEFAULT_SCOPE。"""
    s = scope or os.environ.get(ENV_VAR) or DEFAULT_SCOPE
    if s not in SCOPES:
        raise ValueError(f"未知池子口径 {s!r};可用:{sorted(SCOPES)}")
    return s


# ══════════════════════════════════════════════════════════════════════════
# ★ 筛选判据本体 —— 报告里要「写出实际代码里的那一行」,就是下面这一行
# ══════════════════════════════════════════════════════════════════════════

def in_scope(rank: int | None, scope: str | None = None) -> bool:
    lo, hi = SCOPES[active_scope(scope)]
    return rank is not None and rank >= lo and (hi is None or rank <= hi)


def tier_in_scope(tier: str | None, scope: str | None = None) -> bool:
    """★ 只用来和 in_scope() 交叉核对,**不要**拿它当筛选条件。"""
    lo, hi = SCOPES[active_scope(scope)]
    band = TIER_BANDS.get((tier or "").strip())
    if band is None:
        return False
    blo, bhi = band
    return blo >= lo and (hi is None or (bhi is not None and bhi <= hi))


def filter_source_line() -> str:
    """筛选条件的**实际源码**(给口径戳用,不会和代码走样)。"""
    src = inspect.getsource(in_scope).strip().splitlines()
    return " ".join(x.strip() for x in src[-2:])


# ══════════════════════════════════════════════════════════════════════════
# ★★ 池子索引:(symbol, year) + (company_id, year) 双条件对账
# ══════════════════════════════════════════════════════════════════════════

class PoolIndex:
    """读 pool_FULL_ALL.csv,给出 (symbol, 年) -> rank / tier 的解析。

    ★ 解析顺序:先按 (代码, 年) 直接对;对不上再按 company_id 对
      (代码别名从 symbol 列 + renamed_to 列两边一起收),
      ★ 并且必须再加「那一年确实有这家公司」这个条件 ——
      456 个代码被不同公司重复用过,少了这个条件就会张冠李戴。
    """

    def __init__(self, path: str | None = None):
        self.path = path or pool_path()
        self.rank: dict[tuple[str, str], int] = {}
        self.tier: dict[tuple[str, str], str] = {}
        self.by_company: dict[tuple[str, str], int] = {}
        self.company_tier: dict[tuple[str, str], str] = {}
        self.alias: dict[str, set] = defaultdict(set)
        self.rows = 0
        self.tier_mismatch: list[tuple] = []
        # ★ encoding='utf-8-sig':这批文件里有带 BOM 的
        with open(self.path, newline="", encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                self.rows += 1
                sym = (r["symbol"] or "").strip()
                yr = (r["year"] or "").strip()
                t = (r["tier"] or "").strip()
                try:
                    rk = int(float(r["rank"]))
                except (TypeError, ValueError):
                    continue
                cid = (r.get("company_id") or "").strip()
                self.rank[(sym, yr)] = rk
                self.tier[(sym, yr)] = t
                if cid:
                    self.by_company[(cid, yr)] = rk
                    self.company_tier[(cid, yr)] = t
                    self.alias[sym].add(cid)
                    rt = (r.get("renamed_to") or "").strip().strip('"')
                    if rt:
                        self.alias[rt].add(cid)
                # 交叉核对:rank 带 和 tier 列必须一致
                band = TIER_BANDS.get(t)
                if band and not (band[0] <= rk and (band[1] is None or rk <= band[1])):
                    self.tier_mismatch.append((yr, sym, rk, t))

    def resolve(self, symbol: str, year: str) -> tuple[int | None, str | None, str]:
        """-> (rank, tier, 解析方式)。方式:直接 / 改名对上 / 代码歧义 / 当年不在池"""
        k = (symbol, year)
        if k in self.rank:
            return self.rank[k], self.tier.get(k), "直接"
        cands = [c for c in self.alias.get(symbol, ()) if (c, year) in self.by_company]
        if len(cands) == 1:
            ck = (cands[0], year)
            return self.by_company[ck], self.company_tier.get(ck), "改名对上"
        return None, None, ("代码歧义" if len(cands) > 1 else "当年不在池")


# ══════════════════════════════════════════════════════════════════════════
# ★★★ 口径戳 —— 任何一份结果文件(csv / json / md)都必须盖
# ══════════════════════════════════════════════════════════════════════════

def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", ROOT, "rev-parse", "--short", "HEAD"],
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "(无法取得)"


def stamp(scope: str | None = None, extra: dict | None = None,
          when: str | None = None) -> dict:
    """口径戳(结构化)。调用方把它写进 json / csv 表头 / md 开头。

    ★ 为什么必须有:2026-10-30 已经因为「哪个数是哪个口径跑的」出过错 ——
      朴素基准那次读了未修序列,结论反了。
    """
    import datetime
    s = active_scope(scope)
    d = {
        "池子口径": f"{s} = {SCOPE_LABELS[s]}",
        "池子文件": POOL_REL,
        "筛选条件(实际代码)": filter_source_line(),
        "口径参数位置": "engine/pool_scope.py: DEFAULT_SCOPE"
                        f"(当前 {DEFAULT_SCOPE!r};"
                        f"环境变量 {ENV_VAR} 可临时覆盖)",
        "生成时间": when or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "提交号": git_commit(),
    }
    if extra:
        d.update(extra)
    return d


def stamp_text(scope: str | None = None, extra: dict | None = None,
               prefix: str = "") -> str:
    """口径戳(文本)—— md 开头 / csv 注释行直接用。"""
    return "\n".join(f"{prefix}{k} = {v}" for k, v in stamp(scope, extra).items())


if __name__ == "__main__":
    idx = PoolIndex()
    print(f"[核对] 池子 {idx.rows} 行(已知 {POOL_KNOWN_ROWS}) "
          f"{'✓' if idx.rows == POOL_KNOWN_ROWS else '✗ 不一致,停'}")
    print(f"[核对] rank 带 vs tier 列 不一致 {len(idx.tier_mismatch)} 行 "
          f"{'✓' if not idx.tier_mismatch else '✗'}")
    cnt = defaultdict(int)
    for k, rk in idx.rank.items():
        cnt[idx.tier.get(k)] += 1
    for s in ("large_mid", "full", "large"):
        n = sum(1 for rk in idx.rank.values() if in_scope(rk, s))
        print(f"  {s:10s} {SCOPE_LABELS[s]:28s} 只×年 {n:7,d} "
              f"({n/idx.rows:.1%})")
    print(f"  tier 分布:{dict(cnt)}")
    print("\n" + stamp_text())
