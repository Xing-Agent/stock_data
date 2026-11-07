# -*- coding: utf-8 -*-
"""★★★ 面板元信息（panel_meta）—— ★ **第五个登记点**，之前漏了，A 段因此一条臂都跑不出来。

★★★ 查出来的两件（1107 夜）：

**① `cache.panel_meta()` 读的是老的 300 只那份，不是并池那份。**
```
engine/cache.py:34   META_PARQUET = engine/cache/panel_meta.parquet   ← ★★ 只有 **300 行**（老 pilot_300）
probe/并池2004_1107/panel_meta_newpool.parquet                        ← ★★★ 并池自己那份，**3,858 行**
```
★ `跑重测_1107.py` 的 `装池()` 只换了 `cache._PANEL`（价格）和池表，**没换 meta 指针** →
  ★★ 面板里 3,858 只，meta 里只认得 300 只，另外 3,558 只全部走 `s in meta.index` 的 False 分支。
★★★ 所以规矩㊺ 那「三处/四处登记」实际上是**五处**：
   ① 面板 ② manifest ③ 池表 ④ 分红 ⑤ **panel_meta**。
★ 旁证：`probe/exam_run_1102/run_exam_1102.py:216` 当初就是显式改 `cache.META_PARQUET` 的，
  ★★ 这个做法本来就有，重测这一批只是没做。

**② A 段 33 条臂全挂在一个「谁都不读」的字段上。**
```
engine/matrices.py:1292   z = meta.at[s, "zero_bar"] ...
engine/matrices.py:1296   zb.append(int(idx.get_loc(pd.Timestamp(z))))   ← ★★★ KeyError 就在这里
```
★ `zero_bar` = 退市股的**结算 bar**（最后一根有效 bar 之后那一天，填强制结算价）。
★★ 老那份 meta 里 16 只有 zero_bar，日期**全部在 2021~2025**：
   · B 段（2015~2025）切片里**有**这些日子 → `get_loc` 查得到 → 跑得过
   · A 段（2004~2014）切片里**没有** → ★★★ `KeyError: Timestamp('2024-04-11')` → **整段 33 条臂全废**
★★★ 而 `m.zero_bar` 这个字段 —— ★ 我把全仓库 grep 了一遍 ——
   `matrices.py:1395` 建它、`matrices.py:1248` 声明它，**没有任何一处读它**
   （chain.py 没有、analyze.py 没有、probe 下也没有）。
   → ★★★★★ **一个谁都不读的字段，炸掉了整个 A 段。**
   → ★★ 也就是说：B 段那 33 条臂**没被这件事污染**（它只影响这个死字段），
     ★ 这一条我核过才敢写 —— 不是「跑通了就算」。

★★★ 修法（engine 一个字节不改）：
   ① 把 `cache.META_PARQUET` 指到并池自己那份（3,858 行）—— ★ 这是补第五个登记点。
   ② 覆盖 `cache.panel_meta`：把**落在当前面板切片之外**的 `zero_bar` 置空。
      ★★ 这不是图方便 —— 语义上就该这样：`zero_bar` 是「这只票在这一段里被强制结算的那天」，
        ★★★ 一只 2024 年才退市的票，在 2004~2014 这一段里**根本没有结算 bar** → 置空（-1）才是对的。
      ★ 而且因为没人读这个字段，这个改动**不可能动到任何一个数**（上面已核）。
   ③ ★★ 自证要证「它起作用了」（#80）：打印 meta 行数、被置空几只、当前切片起止。
"""
from __future__ import annotations
import os

import pandas as pd

_原panel_meta = None
_自证: dict = {}


def install(meta_parquet: str) -> dict:
    """★ 换 meta 指针 + 装窗口安全的 panel_meta 覆盖层，返回 id() 自证。"""
    global _原panel_meta, _自证
    from engine import cache
    if not os.path.exists(meta_parquet):
        raise FileNotFoundError(f"★★★ panel_meta 不在：{meta_parquet}")
    if _原panel_meta is None:
        _原panel_meta = cache.panel_meta
    旧路径 = cache.META_PARQUET
    # ★★★ 必须**在换指针之前**把老那份的行数读下来 ——
    #   ★ `panel_meta()` 是在调用时才读 META_PARQUET 的，换完再读就读到新的了，
    #   ★★ 自证会印出「3858 → 3858」，把它本来要证明的那件事恰好藏起来（#80 同类）。
    try:
        旧行数 = len(pd.read_parquet(旧路径)) if os.path.exists(旧路径) else "★ 老那份不在"
    except Exception as e:
        旧行数 = f"★ 读不到：{type(e).__name__}"
    cache.META_PARQUET = meta_parquet          # ★ ① 补第五个登记点

    base = pd.read_parquet(meta_parquet)
    置空的: list = []

    def 覆盖() -> pd.DataFrame:
        m = base.copy()
        idx = None
        try:
            idx = cache._PANEL["close"].index          # ★ 当前面板切片的交易日
        except Exception:
            idx = None
        if idx is not None and "zero_bar" in m.columns:
            z = pd.to_datetime(m["zero_bar"], errors="coerce")
            在窗内 = z.isin(pd.DatetimeIndex(idx))
            要置空 = z.notna() & ~在窗内
            置空的.clear()
            置空的.extend(sorted(m.index[要置空].astype(str)))
            m.loc[要置空, "zero_bar"] = pd.NaT
        return m

    前 = id(cache.panel_meta)
    cache.panel_meta = 覆盖
    m0 = 覆盖()
    try:
        起止 = (f"{cache._PANEL['close'].index.min().date()} → "
               f"{cache._PANEL['close'].index.max().date()}")
    except Exception:
        起止 = "★ 面板还没装"
    _自证 = {
        "★原panel_meta_id": 前, "★覆盖后id": id(cache.panel_meta),
        "★真的换掉了": id(cache.panel_meta) != 前,
        "★★★meta指针": f"{旧路径} → {meta_parquet}",
        "★★★meta行数": f"{旧行数} 行（老那份）→ {len(m0)} 行（并池那份）",
        "★★★当前面板切片": 起止,
        "★★★窗外zero_bar被置空的只数": len(置空的),
        "★被置空的是哪几只": 置空的[:20],
        "★为什么置空是对的": ("zero_bar 是「这一段里被强制结算的那天」；"
                      "一只 2024 年才退市的票在 2004~2014 这一段里没有结算 bar → 置空才对"),
        "★★★动不动数": "不动 —— m.zero_bar 这个字段全仓库没有任何一处读它（已 grep 核过）",
        "★★★engine改动": "零（进程内替换函数指针 + 改 META_PARQUET 这个配置常量）",
    }
    return _自证
