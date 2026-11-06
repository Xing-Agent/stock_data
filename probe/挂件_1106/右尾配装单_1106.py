# -*- coding: utf-8 -*-
"""
★★★ 右尾配装单 —— 每条策略的收益,有多少来自最大的那几笔。

★ 这不是「挂件有没有用」的否决票(Lin 1106 10:24 说这件他有实操依据)。
★★ 这是**配装单**:决定哪个挂件装在哪条策略上。
   · 收益高度集中在少数几笔 → ★★★ **不能装提前止盈**(砍右尾 = 砍掉收益来源)
     ★ 该装的是「让赢单跑得更久」那一类
   · 收益分布平均 → ★★ 提前止盈才划算

★★ 口径:
   · 流水 = probe/friction_rerun_1104/ledgers_1104/REAL__*.csv(摩擦口径统一后)
   · 用 **net_pnl(美元)** 算集中度 —— ★ 不用每笔 R,因为 R 不等权、加总没有意义
   · 同时报 r_multiple_net 的集中度做交叉对照
   · ★★★ 只报数,不写「建议装什么」—— 判断留给 Lin

★★★ 1106 修 Bug ①(和环境分档那两个脚本同一个 bug):
   45 份 REAL__*.csv 里按内容 sha256 只有 32 份是唯一的(11 组是一模一样的副本),
   原来 `glob` 一遍全吃进去 → 逐链会列出重复链、方法级卷起来时同一笔被加两三次。
   ★ 现在 import `去重流水_1106` 按内容去重,★★ 明细写进 json 口径节,不许静默去重。
"""
from __future__ import annotations
import io, json, os, re, sys
import numpy as np, pandas as pd

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "环境分档_1105"))
from 去重流水_1106 import 去重后的流水文件, 去重报告   # noqa: E402

LED = "probe/friction_rerun_1104/ledgers_1104"
OUT = "probe/挂件_1106"


def 集中度(x: np.ndarray) -> dict:
    """★ 正收益里,前 1%/5%/10% 笔贡献了多少。★★ 分母用「正收益总和」,
    不用净额 —— 净额接近 0 时比例会爆(和《54》摩擦占毛利那个坑同一类)。"""
    pos = x[x > 0]
    if len(pos) == 0 or pos.sum() <= 0:
        return {"★状态": "算不出(没有正收益)"}
    s = np.sort(pos)[::-1]
    tot = float(s.sum())
    o = {"正收益笔数": int(len(pos)), "正收益合计": round(tot, 2)}
    for p in (1, 5, 10, 20):
        k = max(1, int(np.ceil(len(s) * p / 100)))
        o[f"前{p}%笔占正收益"] = round(float(s[:k].sum() / tot), 4)
        o[f"前{p}%笔数"] = k
    # ★ 基尼:0 = 完全平均,1 = 全在一笔上
    n = len(s)
    a = np.sort(pos)
    o["基尼"] = round(float((2 * np.arange(1, n + 1) - n - 1) @ a / (n * a.sum())), 4)
    return o


def main() -> int:
    rows = []
    报告 = 去重报告(LED)                      # ★★★ Bug ①:去重,且全过程记进 json
    用的流水 = 去重后的流水文件(LED)
    for f in 用的流水:
        链 = os.path.basename(f)[len("REAL__"):-len(".csv")]
        m = re.search(r"(技-\d+)", 链)
        d = pd.read_csv(f)
        if "net_pnl" not in d.columns:
            continue
        rec = {"链": 链, "方法": (m.group(1) if m else "其他"), "总笔数": len(d),
               "净盈亏合计": round(float(d.net_pnl.sum()), 2),
               "按美元": 集中度(d.net_pnl.astype(float).to_numpy())}
        if "r_multiple_net" in d.columns:
            rec["按每笔R(交叉对照)"] = 集中度(
                d.r_multiple_net.dropna().astype(float).to_numpy())
        rows.append(rec)

    # ★ 按方法卷起来(把该方法所有版本的流水合在一起)
    by = {}
    for f in 用的流水:
        m = re.search(r"(技-\d+)", os.path.basename(f))
        k = m.group(1) if m else "其他"
        d = pd.read_csv(f)
        if "net_pnl" in d.columns:
            by.setdefault(k, []).append(d.net_pnl.astype(float).to_numpy())
    方法级 = {k: {"总笔数": int(sum(len(a) for a in v)),
                 "净盈亏合计": round(float(sum(a.sum() for a in v)), 2),
                 **集中度(np.concatenate(v))} for k, v in by.items()}

    os.makedirs(OUT, exist_ok=True)
    payload = {"口径": {
        "流水": LED, "集中度分母": "正收益之和(不用净额 —— 净额近 0 时比例会爆)",
        "主口径": "net_pnl 美元", "交叉对照": "r_multiple_net",
        "★这份文件是什么": "配装单(哪个挂件装哪条策略),不是「挂件有没有用」的判断",
        "★不写什么": "不写建议装什么挂件 —— 只给数字,判断留给策略组",
        "★★★1106修的bug": "Bug ①:45 份 REAL__*.csv 里按内容 sha256 只有 32 份唯一"
                           "(11 组重复副本),原来全吃进去 → 逐链有重复链、方法级笔数虚高。"
                           "★ 现在按内容去重,明细见「★流水去重」。",
        "★流水去重": 报告,
    }, "方法级": 方法级, "逐链": rows}
    p = os.path.join(OUT, "右尾配装单_1106.json")
    io.open(p, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1))
    print(f"★ 写到 {p} · 流水 {报告['原始份数']} 份 → 去重后 {报告['去重后份数']} 份"
          f"(丢掉 {报告['被丢掉的份数']} 份 / {报告['重复组数']} 组重复)\n")
    print(f"{'方法':7s} {'总笔数':>7s} {'前1%占':>8s} {'前5%占':>8s} {'前10%占':>8s} {'基尼':>7s}")
    for k in sorted(方法级, key=lambda x: (len(x), x)):
        v = 方法级[k]
        if "前5%笔占正收益" not in v:
            print(f"{k:7s} {v['总笔数']:7d}   {v.get('★状态','')}"); continue
        print(f"{k:7s} {v['总笔数']:7d} {v['前1%笔占正收益']:8.1%} "
              f"{v['前5%笔占正收益']:8.1%} {v['前10%笔占正收益']:8.1%} {v['基尼']:7.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
