# -*- coding: utf-8 -*-
"""
★★★ 查一件事:为什么 挂闸100日 / 200日 / 300日 三条臂的结果**一模一样**。
★ 结论(本脚本给证据,不改 engine/):
    engine/matrices.py 的 index_above_ma 分支从 **rule 顶层**读 ma,
    而我们(和它的兄弟分支一样)把 ma 写在 **rule["params"]** 里 ——
    所以 ma 读不到,静默退回默认值 200。三条臂实际跑的是同一个 200 日闸。
★ 本脚本只读:比对三条臂的 json 是否逐字段相同 + 证明三个 ma 的闸本来应该不同。
"""
from __future__ import annotations
import glob, hashlib, io, json, os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import pandas as pd                                              # noqa: E402
from engine import data                                          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = os.path.join(HERE, "arms_1106")
LEDG = os.path.join(HERE, "ledgers_1106")
OUT = os.path.join(HERE, "闸参数没生效_证据_1106.json")

六数键 = ["笔数", "每笔净R", "每笔毛R"]


def main() -> int:
    # ① 三条挂闸臂的结果是不是逐字段相同
    臂 = {}
    for f in sorted(glob.glob(os.path.join(ARMS, "arm_*.json"))):
        d = json.load(io.open(f, encoding="utf-8"))
        臂[(d["族"], d["版本"])] = d["结果"]
    同不同 = {}
    for 族 in ("突破", "大波段", "震荡"):
        g = {v: 臂.get((族, f"挂闸{v}日")) for v in (100, 200, 300)}
        六 = {v: ({k: r.get(k) for k in 六数键}
                 | {"摩擦总额": (r.get("★真链美元") or {}).get("摩擦总额")})
              for v, r in g.items() if r}
        同不同[族] = {
            "三条挂闸臂的六数": 六,
            "★★★ 100与200逐字段相同": 六.get(100) == 六.get(200),
            "★★★ 300与200逐字段相同": 六.get(300) == 六.get(200),
        }
    # ② 流水文件内容哈希 —— 相同就说明连逐笔交易都一样
    流水 = {}
    for 族, 链 in (("突破", "突破·技-6-原著"), ("大波段", "大波段·技-1"),
                  ("震荡", "震荡·技-14-原著")):
        h = {}
        for v in (100, 200, 300):
            p = os.path.join(LEDG, f"REAL__{链}·挂闸{v}日.csv")
            h[v] = (hashlib.sha256(io.open(p, "rb").read()).hexdigest()[:16]
                    if os.path.exists(p) else "★文件不存在")
        流水[族] = {"逐笔流水sha256前16": h,
                   "★★★ 三份流水内容相同": len(set(h.values())) == 1}
    # ③ 三个 ma 的闸本来应该差多少天
    b = data.load_benchmark("SPY")["close"]
    b = b[(b.index >= "2015-01-01") & (b.index <= "2025-12-31")]
    mask = {n: (b > b.rolling(n, min_periods=n).mean()).fillna(False)
            for n in (100, 200, 300)}
    闸本身 = {"交易日数": int(len(b)),
             "开闸天数": {n: int(m.sum()) for n, m in mask.items()},
             "开闸占比%": {n: round(float(m.mean()) * 100, 1)
                        for n, m in mask.items()},
             "★★★ 与200日不同的天数": {
                 100: int((mask[100] != mask[200]).sum()),
                 300: int((mask[300] != mask[200]).sum())}}
    # ④ 取值方式复现
    rule = {"type": "index_above_ma",
            "params": {"symbol": "SPY", "ma": 100}, "source": "x"}
    取法 = {
        "我们写的规则形状": rule,
        "engine/matrices.py:605 的取法 rule.get('ma',200)":
            rule.get("ma", 200),
        "兄弟分支(index_above_ma_scaled / index_ma_slope)的取法 "
        "rule.get('params',rule).get('ma',200)":
            rule.get("params", rule).get("ma", 200),
    }
    payload = {
        "★★★ 结论": (
            "engine/matrices.py 第 604-607 行的 index_above_ma 分支,"
            "ma 和 symbol 都是从 **rule 顶层** 取(rule.get('ma',200)),"
            "没有像它下面的 index_above_ma_scaled / index_ma_slope 那样"
            "先 p = rule.get('params', rule)。"
            "我们按引擎自己其它分支的写法把 ma 放在 params 里,"
            "于是 ma 读不到,**静默退回默认值 200**。"
            "★★★ 所以「相邻三点 100/200/300」这一项**没有跑成** ——"
            "三条挂闸臂实际跑的是同一个 200 日闸。"),
        "★ 这件事谁的责任": (
            "★ 是 engine/matrices.py 的取值和它自己兄弟分支不一致;"
            "★★ 本轮按硬规矩 engine/ 一个字节都没改,只把事实记下来。"),
        "★★ 200 日那一版是不是有效": (
            "★ 是。默认值正好是 200,而 200 就是登记里要的那个有实证的点"
            "(Faber 2007)。★★★ 100 日和 300 日那两列记「算不出」,"
            "不许当成两个独立的闸点。"),
        "①三条挂闸臂结果是否相同": 同不同,
        "②逐笔流水内容哈希": 流水,
        "③三个ma的闸本来应该差多少天": 闸本身,
        "④取值方式复现": 取法,
    }
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(payload, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
