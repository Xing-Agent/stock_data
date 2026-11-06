# -*- coding: utf-8 -*-
"""
★★★ 读 arms_1106/*.json + ledgers_1106/REAL__*.csv,算出《69》第四节要求的六个数,
    并按《69》写死的那把尺子判「改善算不算结论」。
★ 不跑回测、不碰 engine/、不改任何配置 —— 纯读+算。
"""
from __future__ import annotations
import glob, io, json, os
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ARMS = os.path.join(HERE, "arms_1106")
LEDG = os.path.join(HERE, "ledgers_1106")
OUT = os.path.join(HERE, "挂闸对照表_1106.json")

版本序 = ["不挂闸", "挂闸100日", "挂闸200日", "挂闸300日"]
族序 = ["突破", "大波段", "震荡"]


def se_from_ledger(链: str):
    """★ 每笔净R 的标准误 = std(ddof=1)/sqrt(n),从该臂的 REAL 流水算。"""
    p = os.path.join(LEDG, f"REAL__{链}.csv")
    if not os.path.exists(p):
        return None, None, "★ 算不出:流水文件不存在"
    df = pd.read_csv(p)
    if "r_multiple_net" not in df.columns:
        return None, None, "★ 算不出:流水里没有 r_multiple_net 列"
    x = pd.to_numeric(df["r_multiple_net"], errors="coerce").dropna().to_numpy()
    n = int(x.size)
    if n < 2:
        return None, n, "★ 算不出:有效笔数 < 2,标准误无定义"
    return float(x.std(ddof=1) / np.sqrt(n)), n, None


def main() -> int:
    臂 = {}
    for f in sorted(glob.glob(os.path.join(ARMS, "arm_*.json"))):
        rec = json.load(io.open(f, encoding="utf-8"))
        r = rec["结果"]
        链 = rec["链"]
        se, n_led, se_note = se_from_ledger(链)
        美元 = r.get("★真链美元") or {}
        基一 = r.get("★基准一") or {}
        臂[(rec["族"], rec["版本"])] = {
            "链": 链, "文件": os.path.basename(f),
            "①笔数": r.get("笔数"),
            "②每笔净R": r.get("每笔净R"),
            "③每笔毛R": r.get("每笔毛R"),
            "④摩擦总额美元": 美元.get("摩擦总额"),
            "④b毛盈亏美元": 美元.get("毛盈亏"),
            "④c净盈亏美元": 美元.get("净盈亏"),
            "⑤基准一": 基一.get("★真信号每笔R − 随机进场每笔R"),
            "⑤b随机进场每笔R": 基一.get("随机进场_平均每笔R"),
            "⑥每笔净R的SE": se,
            "⑥b流水笔数": n_led,
            "⑥c算不出原因": se_note,
        }

    # ── 改善幅度 + 《69》的尺子 ───────────────────────────────────────
    对照 = {}
    for 族 in 族序:
        base = 臂.get((族, "不挂闸"))
        行 = {}
        for 版 in 版本序:
            a = 臂.get((族, 版))
            行[版] = a if a else {"★算不出": "这条臂没跑出来(见 失败 一节)"}
        判 = {}
        for 版 in 版本序[1:]:
            a = 臂.get((族, 版))
            if not a or not base:
                判[版] = {"★算不出": "缺臂,无法比"}
                continue
            if a["②每笔净R"] is None or base["②每笔净R"] is None:
                判[版] = {"★算不出": "缺每笔净R"}
                continue
            d = a["②每笔净R"] - base["②每笔净R"]
            if a["⑥每笔净R的SE"] is None or base["⑥每笔净R的SE"] is None:
                判[版] = {"改善幅度": d, "★算不出尺子": "缺标准误"}
                continue
            尺 = 2.0 * float(np.sqrt(a["⑥每笔净R的SE"] ** 2
                                     + base["⑥每笔净R的SE"] ** 2))
            判[版] = {
                "改善幅度": d, "尺子": 尺,
                "判定": ("★★★ 改善小于噪声" if abs(d) < 尺
                        else ("★ 改善(超过尺子)" if d > 0 else "★ 变差(超过尺子)")),
                "方向(不看尺子)": "正" if d > 0 else ("负" if d < 0 else "零"),
            }
        对照[族] = {"四版六数": 行, "挂闸 vs 不挂闸": 判}

    # ── 排序型预言的分辨力 ──────────────────────────────────────────
    # ★★★ 只有 挂闸200日 是**有效闸点**。100 日 / 300 日那两条臂的 ma 没被引擎读到
    #   (engine/matrices.py 的 index_above_ma 从 rule 顶层取 ma,我们写在 params 里),
    #   静默退回默认 200 —— 三条臂逐笔流水内容哈希完全相同。
    #   ★ 证据:probe/挂闸_1106/闸参数没生效_证据_1106.json
    有效闸点 = ["挂闸200日"]
    排序 = {}
    for 版 in 版本序[1:]:
        if 版 not in 有效闸点:
            排序[版] = {"★算不出": ("★★★ 这个闸点没跑成 —— ma 参数没被引擎读到,"
                                 "实际跑的是 200 日闸(见 闸参数没生效_证据_1106.json)。"
                                 "★ 「算不出」,不是「成绩差」。")}
            continue
        幅 = {}
        for 族 in 族序:
            j = 对照[族]["挂闸 vs 不挂闸"].get(版, {})
            if "改善幅度" in j and "尺子" in j:
                幅[族] = (j["改善幅度"], j["尺子"] / 2.0)   # 半尺 = √(SE²+SE²)
        if len(幅) < 2:
            排序[版] = {"★算不出": f"只有 {len(幅)} 条有改善幅度,排不了序"}
            continue
        名次 = sorted(幅.items(), key=lambda kv: -kv[1][0])
        # ★ 分辨力:任意两条的幅度差 vs 两条合成标准误
        两两 = {}
        分得开 = True
        ks = list(幅)
        for i in range(len(ks)):
            for j2 in range(i + 1, len(ks)):
                a, b = ks[i], ks[j2]
                dd = abs(幅[a][0] - 幅[b][0])
                合 = float(np.sqrt(幅[a][1] ** 2 + 幅[b][1] ** 2))
                两两[f"{a} vs {b}"] = {"幅度差": dd, "合成标准误": 合,
                                      "分得开": bool(dd >= 合)}
                if dd < 合:
                    分得开 = False
        排序[版] = {"幅度": {k: v[0] for k, v in 幅.items()},
                   "名次(仅在分得开时成立)": [k for k, _ in 名次],
                   "两两分辨力": 两两,
                   "★★★ 结论": ("★ 分得开,名次成立" if 分得开
                               else "★★★ 三条改善幅度分不开 —— 不许硬排名次")}

    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "★口径": {
            "预先登记": "手册/69-挂环境闸-跑前预先登记-1106.md",
            "SE算法": "该臂 ledgers_1106/REAL__<链>.csv 的 r_multiple_net 列 std(ddof=1)/sqrt(n)",
            "尺子": "|改善幅度| < 2×√(挂闸SE²+不挂闸SE²) → 改善小于噪声",
            "★★ 毛利与摩擦": "并排给两个绝对数,不给比值",
            "★★★ 闸的出处": "②档 行业改进(Faber 2007;Brock 等 1992)—— 原著没写这条闸",
        },
        "臂数": len(臂),
        "对照": 对照,
        "排序型预言的分辨力": 排序,
    }, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"臂数": len(臂), "写到": OUT}, ensure_ascii=False))
    for 族 in 族序:
        print(f"\n=== {族} ===")
        for 版 in 版本序:
            r = 对照[族]["四版六数"][版]
            if "★算不出" in r:
                print(f"  {版:10s} ★算不出")
                continue
            print(f"  {版:10s} 笔数={r['①笔数']} 净R={r['②每笔净R']} "
                  f"毛R={r['③每笔毛R']} 摩擦$={r['④摩擦总额美元']} "
                  f"毛$={r['④b毛盈亏美元']} 基准一={r['⑤基准一']} SE={r['⑥每笔净R的SE']}")
        print("  判:", json.dumps(对照[族]["挂闸 vs 不挂闸"], ensure_ascii=False))
    print("\n=== 排序分辨力 ===")
    print(json.dumps(排序, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
