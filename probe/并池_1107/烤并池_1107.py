# -*- coding: utf-8 -*-
"""
★★★ 烤并池面板 —— ★ 考卷 1,042 只并回研究池（Lin 1107 13:5x 拍板）。

★★ 为什么要并（★ 另一路 B 查出来的）：
  **美股最大的 30 只里有 20 只被分进了考卷** —— 苹果、微软、亚马逊、博通、奈飞、
  伯克希尔、摩根大通等。研究池里的巨头只剩英伟达、谷歌、Meta、特斯拉。
  ★★★ 所以我们一直在「几乎不碰最大公司」的池子里测策略，
  而这十年偏偏是巨头行情 —— 很多策略跑输标普，有一部分原因在这里。
  ★★ 而且考卷 11-02 已经用过一次，严格说已经不是「没见过的数据」了。

★ Lin 的拍板：**考卷并回研究池，用全量股票做研究；以后的考试改成往后跑模拟盘**
  （规则冻结、每天真实记录信号、未来数据谁都没见过 —— ★★ 这是最干净的考卷）。

★★★ 这一份只改两件，其余**全部复用** `烤新池_1106.py`（拆股修正、退市结算、日历、
  多主体取 bar 最多的那个、没有核实证据的逐只标出来）：
   ① **扫两个数据目录**：`market_ext_1105/`（2,916 只）+ `exam_1042/`（1,043 只）
   ② **不排除考卷**（原来那一行是 `考卷名单()` → 这里传空集合）

★★ 已知边界（★ 照抄 1106 那份，不自己编近似值）：
   · **日历仍用 SPY** —— SPY 只有 2014 起，所以窗口也只能到 2014。
     ★★★ 要拉到 2008 必须先补 SPY 2008–2014 的日线 —— 另开取数单。
   · ★★ **GOOGL（A 类）两处都没有**，只有 GOOG（C 类）—— 这一只是真缺，影响可忽略。
   · 退市结算：新行情的票大多不在 delisting_gate 的核实清单里 →
     ★ 只能按「最后收盘价结算」，并**逐只标出来**，不假装有证据。

★ engine/ 一个字节都没改（进程内覆盖层）。
"""
from __future__ import annotations
import io, json, os, sys, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "newpool_1106"))
os.chdir(ROOT)
import 烤新池_1106 as B                                        # noqa: E402
import 接新基准_1107 as BM                                      # noqa: E402

_原读日线 = B.读日线
_DIRS: dict = {}          # ★ 由 目录表两处() 填，供 读日线接起来() 查

OUT = os.path.join(ROOT, "probe", "并池2004_1107")
_原目录表 = B.目录表
_原manifest = B.新manifest


def 目录表两处() -> dict:
    """★★★ 扫**四个**目录（1107 17:3x 数据组补完之后）。

    ★★ 一个坑（★ 必须先说清）：`exam_1042/`（2016~2025）和
      `exam_pre2016_1107/`（2004~2015）是**同一批票的两段时间** ——
      ★★★ 原函数遇到一个 symbol 有多个目录时会「取 bar 最多的那个」，
      ★ 那样会**只要一段、扔掉另一段**。→ 所以读的那一层也要改（见 `读日线两段`）。
    """
    global _DIRS
    m = {}
    for 根 in ("market_ext_1105", "exam_1042", "exam_pre2016_1107", "market_extra_1107"):
        full_root = os.path.join(ROOT, 根)
        if not os.path.isdir(full_root):
            raise FileNotFoundError(f"★★★ 数据目录不在：{full_root}")
        n0 = len(m)
        for d in sorted(os.listdir(full_root)):
            full = os.path.join(full_root, d)
            if not os.path.isdir(full):
                continue
            sym = d.split("__")[0]
            for fn in ("daily.json.gz", "daily.json"):
                p = os.path.join(full, fn)
                if os.path.exists(p):
                    m.setdefault(sym, []).append(p)
                    break
        print(f"★ 扫完 {根}：新增 {len(m)-n0} 只，累计 {len(m)} 只", flush=True)
    多段 = {k: v for k, v in m.items() if len(v) > 1}
    print(f"★★★ 有多段数据要拼接的票：{len(多段)} 只"
          f"（★ 例：{list(多段)[:5]}）", flush=True)
    _DIRS = m
    return m


def manifest两处(exclude: set, dirs: dict) -> dict:
    """★★★ 读**两份** manifest。

    ★★ 这是第二个坑（★ 第一次跑踩到了）：原函数只读 `market_ext_1105/manifest.csv`，
      ★★★ 考卷那 1,042 只不在那份清单里 → 全被丢掉
      （第一次跑「新池候选」只有 2,823 只，和老池 2,807 几乎一样 —— 并池等于没并）。
    ★ 修法：两份清单都读，★★ 并**自证各贡献多少只**，不许悄悄少一批。
    """
    import csv as _csv
    out = {}
    计 = {}
    for 根 in ("market_ext_1105", "exam_1042"):
        before = len(out)
        B.EXT = os.path.join(ROOT, 根)          # ★ 原函数按 B.EXT 拼 manifest 路径
        part = _原manifest(exclude, dirs)
        # ★ origin 标上真实来源（原函数写死 market_ext_1105）
        for k, v in part.items():
            if k not in out:
                out[k] = v._replace(origin=根) if hasattr(v, "_replace") else v
        计[根] = len(out) - before
    print(f"★★★ 两份清单各贡献：{计}；合计 {len(out)} 只", flush=True)
    return out


def 读日线接起来(path: str, symbol: str):
    """★★★ 把同一只票的**多段数据接起来**，而不是只取一段。

    ★★ 为什么必须这么做：`exam_1042/`（2016~2025）和 `exam_pre2016_1107/`（2004~2015）
      是**同一批票的两段时间**。★★★ 原函数在 main 里用
      `sorted(cand, key=lambda q: -len(读日线(q, sym)))[0]` —— 只取 bar 最多的**那一段**，
      ★ 另一段直接扔掉 → 窗口照样拉不回 2004。

    ★ 做法：不管传进来的是哪一个 path，★★ 都按 symbol 去 `_DIRS` 查**全部段**，
      逐段读、按日期排序、**重复日期保留后读到的那一段**（★★★ 新数据优先）。
    ★ 查不到就退回原函数读这一个 path（不许返回空）。
    """
    import pandas as _pd
    cands = _DIRS.get(symbol) or [path]
    dfs = []
    for p in cands:
        try:
            d = _原读日线(p, symbol)
        except Exception:
            continue
        if d is not None and not d.empty:
            dfs.append(d)
    if not dfs:
        return _原读日线(path, symbol)
    out = _pd.concat(dfs).sort_index()
    return out[~out.index.duplicated(keep="last")]


def main() -> int:
    t0 = time.time()
    # ★★★ 四处覆盖，都在本进程内
    B.目录表 = 目录表两处
    B.新manifest = manifest两处
    B.读日线 = 读日线接起来
    # ★ 自证：基准已换成 2004 版
    自证基准 = BM.install()
    print("★ 基准覆盖层:", json.dumps(自证基准, ensure_ascii=False), flush=True)
    # ★★★ 1107 夜 修：#75 把覆盖层的返回字段从 ★★★SPY 改成了 ★★★基准自证，
    #   ★ 这一行没跟着改 → KeyError，烤盘脚本当场炸（规矩㊼ 末句：改返回字段名必须 grep 谁在用）。
    #   ★★ 自证现在是一行字符串 "2004-01-02 → 2026-11-04 · 5747 根"，取开头那个日期。
    _spy = 自证基准["★★★基准自证"]["SPY"]
    assert _spy.startswith("2004-"), f"★★★ SPY 还没拉到 2004（{_spy}），停"
    B.考卷名单 = lambda: set()        # ★★★ 不排除考卷 —— 这就是「并池」
    B.OUT = OUT
    os.makedirs(OUT, exist_ok=True)
    # ★ 自证：换掉了，而且原函数还留着
    print(json.dumps({"★目录表换掉了": B.目录表 is not _原目录表,
                      "★manifest换掉了": B.新manifest is not _原manifest,
                      "★考卷排除已关": len(B.考卷名单()) == 0,
                      "★★★engine改动": "零",
                      "★输出目录": OUT}, ensure_ascii=False), flush=True)
    rc = B.main()
    print(f"★ 并池烤盘完 用时 {time.time()-t0:.0f}s", flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
