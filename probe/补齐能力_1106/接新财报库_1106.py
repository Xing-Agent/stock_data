# -*- coding: utf-8 -*-
"""
★★★ 把引擎接到**新财报库** `fundamentals_ext/` —— ★ engine 零改动（进程内覆盖层）。

★★ 来历：数据组 1106 17:31 指出 ——
  「A1 全池财报：不用取。`fundamentals_ext/` 已经有 4,002 家，带公开日。
    策略组量到的『300 家、7%』是老库 `pilot_300`，引擎还没切过来。」
★ 我核实了，而且两处不匹配，所以引擎读不到：
  ① **路径**：`engine/data.py:36` 写死 `PILOT = pilot_300`
  ② ★★★ **压缩**：新库是 `fundamentals.json.**gz**`，而引擎找的是没压缩的
★★ 实测：新池 2,770 只 → ★★★ **fundamentals_ext 命中 2,770 只（100%）**。

★★★ 做法：替换 `engine.data.load_fundamentals` 的函数指针（和 pat6_ops.install 同一套路）。
  ★ 新库的 `financial_versions` **本身就是引擎要的形状**（科目 → 记录表），
  ★★ 记录里 `filing_date` / `period_end` / `period_start` / `value` 全都有 → 直接返回。
"""
import functools, gzip, json, os, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EXT = os.path.join(ROOT, "fundamentals_ext")
_装过 = False


@functools.lru_cache(maxsize=8192)
def _读(symbol: str) -> dict:
    p = os.path.join(EXT, symbol, "fundamentals.json.gz")
    if not os.path.exists(p):
        p2 = os.path.join(EXT, symbol, "fundamentals.json")
        if not os.path.exists(p2):
            return {}
        with open(p2, encoding="utf-8") as fh:
            d = json.load(fh)
    else:
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
    fv = d.get("financial_versions")
    return fv if isinstance(fv, dict) else {}


def install() -> dict:
    """★ 在进程内把 load_fundamentals 换成读新库。★★★ engine 文件一个字节都没动。"""
    global _装过
    from engine import data as D, fundamentals as F
    if _装过:
        return {"★已装过": True}
    旧 = D.load_fundamentals

    def 新(symbol: str) -> dict:
        r = _读(symbol)
        if r:
            return r
        # ★★★ 新库没有这只 → 退回老库（★ 不是悄悄返回空）
        return 旧(symbol)

    D.load_fundamentals = 新
    # ★★ engine.fundamentals 里的缓存要清掉，否则读到老库的结果
    for fn in (getattr(F, "quarterly", None), getattr(F, "ttm", None),
               getattr(F, "quarter_frame", None), getattr(F, "metric_quarterly", None),
               getattr(F, "shares_quarterly", None)):
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()
    _装过 = True
    return {"★装上了": True, "库": EXT,
            "★家数": (len(os.listdir(EXT)) if os.path.isdir(EXT) else 0),
            "★★engine改动": "零 —— 只在进程内替换函数指针",
            "★★★没命中怎么办": "退回老库 pilot_300（不是悄悄返回空）"}


if __name__ == "__main__":
    sys.path.insert(0, ROOT); os.chdir(ROOT)
    print(json.dumps(install(), ensure_ascii=False, indent=1))
    from engine import fundamentals as F
    v, _ = F.quarter_frame("AAL")
    print("★ AAL quarter_frame 形状:", v.shape, "列:", sorted(v.columns))
