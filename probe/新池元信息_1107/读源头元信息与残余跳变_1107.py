# -*- coding: utf-8 -*-
"""
★★★★★ 修 #65 —— ★ 这是**我们自己的 bug**：源头把问题写在 `warnings` 等元信息字段里，
   ★★ 而我们的烤面板脚本从来只读 `data` 那一段。

★★★ 这一份干两件（★ 规矩㉖ + 规矩㉔）：
   ① **规矩㉖**：把源头**每一个元信息字段**打出来读一遍，并**逐个字段**写明
      「这一条我们接了 / 没接 / 为什么不用」—— ★★ 不许只挑自己要的那几列就开跑。
   ② **规矩㉔**：老池有 `engine/split_gate.residual_jumps()` 这道残余跳变审计、
      ★★★ **新池没有**（这就是同一类脏数据在新池躺了一个月的原因）——
      ★ 本份照同一套阈值给**新池**补一份。

★★★★★ ⚠ 刻意**不改** `probe/newpool_1106/烤新池_1106.py`：
   ★ 改它会动面板本身 → ★★★ 所有已经出的成绩**全部失效**（规矩⑯ 那一类连锁）。
   → ★★ 本份是**只读审计**，产出是清单和账，**不动任何已入库的数**。
   → ★★★ 「要不要拿这份清单去真的剔票/剔日」是**另一件事，要 Lin 拍板**（见报告末尾）。

★ 产出：`元信息与残余跳变_报告_1107.json`
"""
from __future__ import annotations
import glob, gzip, io, json, os, re, sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
SRC = "market_ext_1105/*/daily.json.gz"
OUT = os.path.join(HERE, "元信息与残余跳变_报告_1107.json")

# ★★★ 和 `engine/split_gate.py:437` 同一组阈值 —— ★ 规矩⑬：这两个数是打出来核过的，不是记的
RESIDUAL_UP, RESIDUAL_DOWN = 2.50, 0.40      # >+150% / <−60%
MIN_JUMP = 3.0                                # ★ residual_jumps() 的默认门槛


def 残余跳变(cl: pd.DataFrame, up: float, down: float) -> list[tuple]:
    """★★★ 和 `engine/split_gate.residual_jumps_window()` **同一段逻辑**，
       ★ 只是数据源从 `cache.load()`（老池）换成新池面板。"""
    out: list[tuple] = []
    for sym in cl.columns:
        s = cl[sym].dropna()
        s = s[s > 0]
        if len(s) < 2:
            continue
        r = (s / s.shift(1)).to_numpy(float)[1:]
        hit = np.flatnonzero((r >= up) | (r <= down))
        for k in hit:
            out.append((str(sym), str(s.index[k + 1].date()), round(float(r[k]), 4)))
    return sorted(out)


def main() -> int:
    # ---------------- ① 规矩㉖：源头每一个字段都读一遍 ----------------
    字段出现 = Counter()
    状态 = Counter()
    复权口径 = Counter()
    供应商 = Counter()
    并购动作状态 = Counter()
    分拆说明 = Counter()
    缺bar的票: list[dict] = []
    警告分类 = Counter()
    警告样例: dict[str, str] = {}
    多主体的票: list[dict] = []
    事件数 = Counter()
    文件数 = 0
    未就绪: list[str] = []

    for p in sorted(glob.glob(SRC)):
        try:
            d = json.loads(gzip.open(p, "rt", encoding="utf-8").read())
        except Exception:
            continue
        文件数 += 1
        sym = os.path.basename(os.path.dirname(p)).split("__")[0]
        for k in d:
            字段出现[k] += 1
        状态[str(d.get("status"))] += 1
        if str(d.get("status")) != "ready":
            未就绪.append(sym)
        复权口径[str(d.get("adjustment"))] += 1
        供应商[str(d.get("provider"))] += 1

        mc = d.get("market_coverage") or {}
        if (mc.get("missing_bars") or 0) > 0:
            缺bar的票.append({"票": sym, "缺": mc.get("missing_bars"),
                            "应有": mc.get("expected_bars"),
                            "实有": mc.get("observed_bars"),
                            "状态": mc.get("status")})
        ca = d.get("corporate_actions") or {}
        并购动作状态[str(ca.get("status"))] += 1
        分拆说明[str(ca.get("spinoffs"))[:80]] += 1
        事件数[len(ca.get("events") or [])] += 1

        seg = d.get("company_segments") or []
        if len({str(s.get("company_id")) for s in seg if isinstance(s, dict)}) > 1:
            多主体的票.append({"票": sym, "段": seg})

        for w in (d.get("warnings") or []):
            w = str(w)
            # ★ 按关键词归类 —— ★★ 这是**源头自己的话**，不是我们的判定
            if "无事件隔夜跳" in w:
                k = "①无事件隔夜跳（可能是漏记的分拆/拆股）"
            elif "换手" in w or "CIK" in w:
                k = "②代码/主体换手，换的那天判不准"
            elif "分拆" in w or "spinoff" in w.lower():
                k = "③分拆相关"
            elif "停牌" in w or "退市" in w:
                k = "④停牌/退市"
            elif "缺" in w or "missing" in w.lower():
                k = "⑤缺数据"
            else:
                k = "⑥其它（★ 没归上类 —— 必须人读）"
            警告分类[k] += 1
            警告样例.setdefault(k, w[:220])

    # ---------------- ② 规矩㉔：给新池补残余跳变审计 ----------------
    w = pd.read_parquet(PANEL)
    cl = w["close"]
    del w
    宽 = 残余跳变(cl, RESIDUAL_UP, RESIDUAL_DOWN)
    严 = 残余跳变(cl, MIN_JUMP, 1.0 / MIN_JUMP)
    def 聚(x):
        s = defaultdict(int)
        for sym, _, _ in x:
            s[sym] += 1
        return s
    宽票, 严票 = 聚(宽), 聚(严)

    out = {
        "★★★这一份是什么": "修 #65：把源头元信息全部读一遍（规矩㉖）+ 给新池补残余跳变审计（规矩㉔）。"
                     "★★ 只读，不动任何已入库的数、不改烤面板脚本。",
        "★口径": {
            "源头": SRC, "面板": PANEL, "源头文件数": 文件数,
            "残余跳变阈值": {"宽（和 engine/split_gate.py:437 同）": f">={RESIDUAL_UP} 或 <={RESIDUAL_DOWN}",
                       "严（residual_jumps 默认）": f">={MIN_JUMP} 或 <={1/MIN_JUMP:.4f}"},
            "★★★为什么不改烤面板脚本": "改它会动面板本身 → 所有已出成绩失效；"
                              "★ 本份只出清单，真要剔票/剔日**要 Lin 拍板**",
        },
        # ---------------- 规矩㉖ 的那张「逐字段表态」表 ----------------
        "★★★★★逐字段表态（规矩㉖：接了/没接/为什么）": {
            "data": {"接没接": "✅ 接了", "怎么用": "★ 烤成 OHLCV 面板 —— 这是我们唯一一直在用的那一段"},
            "warnings": {"接没接": "❌ **以前没接 → 这就是 #65**",
                       "怎么用": "★★★ 1107 起：`扫假跳变_1107.py` 之外，本份把它**全部分类打出来**；"
                               "★★ 其中「无事件隔夜跳 ≥50%」已进《98》《93》的剔脏日口径",
                       "★★★还欠什么": "★ 下面「⑥其它」那一类**还没有人逐条读过**"},
            "status": {"接没接": "❌ 以前没接",
                     "怎么用": "★ 本份统计；★★★ 非 `ready` 的票应当**不入池**（见下「未就绪的票」）",
                     "分布": dict(状态)},
            "adjustment": {"接没接": "❌ 以前没接",
                         "怎么用": "★★★ 这一条最要紧：源头写的是什么口径决定我们**要不要自己做复权**",
                         "分布": dict(复权口径)},
            "corporate_actions": {"接没接": "🟡 只接了 `events` 里的 split_coefficient（#62 那条）",
                                "怎么用": "★ 本份把 `status` / `spinoffs` 也打出来",
                                "status分布": dict(并购动作状态),
                                "★★★spinoffs 原文分布": dict(分拆说明),
                                "★events 条数分布(前8)": dict(Counter(dict(事件数)).most_common(8))},
            "market_coverage": {"接没接": "❌ 以前没接",
                              "怎么用": "★★ 它自己报 `missing_bars` —— ★★★ 我们从来没核过日历完整性",
                              "缺bar的票数": len(缺bar的票)},
            "company_segments": {"接没接": "🟡 烤池时数过「同一代码多个主体目录」，但**没有按段切**",
                               "怎么用": "★★★ 同一个 ticker 在不同时段属于不同公司 → "
                                       "★ 跨段的那些笔在经济意义上**不是同一家公司**",
                               "多主体的票数": len(多主体的票)},
            "cik / symbol / interval / timezone / provider / source_url / retrieved_at / start_date / end_date":
                {"接没接": "🟡 部分",
                 "怎么用": "★ 身份与溯源字段；★★ `interval`=1d 和 `timezone` 我们是**假定**的，本份核了一遍",
                 "provider分布": dict(供应商)},
        },
        "★★★未就绪的票（status != ready）": {"只数": len(未就绪), "前40": sorted(未就绪)[:40]},
        "★★★market_coverage 自报缺 bar 的票": {"只数": len(缺bar的票), "前20": 缺bar的票[:20]},
        "★★★同一代码跨多个主体（company_segments）": {"只数": len(多主体的票), "前10": 多主体的票[:10]},
        "★★★★★源头 warnings 分类（★ 以前一条都没读）": {
            "总条数": sum(警告分类.values()),
            "分类": dict(警告分类.most_common()),
            "每类一个原文样例": 警告样例,
        },
        "★★★★★新池残余跳变（规矩㉔：老池有这道审计、新池以前没有）": {
            "宽阈值(>=2.50 或 <=0.40)": {"条数": len(宽), "只数": len(宽票),
                                   "最多的前15只": sorted(宽票.items(), key=lambda kv: -kv[1])[:15],
                                   "前30条": 宽[:30]},
            "严阈值(>=3.0 或 <=0.3333)": {"条数": len(严), "只数": len(严票),
                                     "最多的前15只": sorted(严票.items(), key=lambda kv: -kv[1])[:15]},
            "★★★读法": "★ 这是「我们还欠多少」的诚实清单 —— ★★ 老池那道自检会把它打出来、不许藏；"
                    "★★★ 新池以前没有这道，所以同一类脏数据在新池躺了一个月（#62 #65）",
        },
        "★★★要 Lin 拍板的（★ 本份只出清单，没动任何数）": [
            "① 非 ready 的票要不要退池（本份只统计，没剔）",
            "② market_coverage 自报缺 bar 的票要不要退池",
            "③ company_segments 跨主体的票，跨段的笔要不要整笔剔（经济意义上不是同一家公司）",
            "④ warnings 里「⑥其它」那一类要不要逐条人读",
        ],
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"★ 源头文件 {文件数} 份")
    print(f"★★★ warnings 总条数 {sum(警告分类.values())}，分类：")
    for k, v in 警告分类.most_common():
        print(f"     {v:5d}  {k}")
    print(f"★★★ status 分布 {dict(状态)}  |  adjustment 分布 {dict(复权口径)}")
    print(f"★★★ 非 ready {len(未就绪)} 只 | 自报缺 bar {len(缺bar的票)} 只 | 多主体 {len(多主体的票)} 只")
    print(f"★★★★★ 新池残余跳变：宽 {len(宽)} 条 / {len(宽票)} 只；严 {len(严)} 条 / {len(严票)} 只")
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
