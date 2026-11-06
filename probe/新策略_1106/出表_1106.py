# -*- coding: utf-8 -*-
"""★ 从 arms_1106/*.json + ledgers_1106/REAL__*.csv 出表。一个数都不估。"""
import io, json, math, os, glob
import pandas as pd

HERE = "/home/claude/xing-agent-stock_data/probe/新策略_1106"
ARMS = os.path.join(HERE, "arms_1106")
LED = os.path.join(HERE, "ledgers_1106")

ORDER = [
    ("融-1_震荡", "threshold", ["5.0", "10.0", "15.0"]),
    ("融-2_突破", "lookback", ["20", "40", "55"]),
    ("融-3_大波段", "lookback", ["60", "90", "120"]),
]

by_label = {}
for p in sorted(glob.glob(os.path.join(ARMS, "arm_*.json"))):
    d = json.load(io.open(p, encoding="utf-8"))
    by_label[d["链"]] = (d["结果"], os.path.basename(p))

rows = []
for name, key, pts in ORDER:
    for v in pts:
        label = f"{name}·{key}={v}"
        if label not in by_label:
            rows.append({"策略": name, "点": f"{key}={v}", "链": label, "状态": "★ 没有这条臂的 json"})
            continue
        r, fn = by_label[label]
        led = os.path.join(LED, f"REAL__{label}.csv")
        se_real = None
        n_led = None
        if os.path.exists(led):
            df = pd.read_csv(led)
            s = pd.to_numeric(df["r_multiple_net"], errors="coerce").dropna()
            n_led = int(len(s))
            if n_led > 1:
                se_real = float(s.std(ddof=1) / math.sqrt(n_led))
        b1 = r.get("★基准一", {})
        diff = b1.get("★真信号每笔R − 随机进场每笔R")
        se_ctrl = b1.get("★对照每笔R均值的标准误")
        ruler = None
        verdict = "★ 算不出"
        if se_real is not None and se_ctrl is not None:
            ruler = 2.0 * math.sqrt(se_real ** 2 + float(se_ctrl) ** 2)
            if diff is not None:
                if abs(diff) > ruler:
                    verdict = "赢（超出噪声）" if diff > 0 else "输（超出噪声）"
                else:
                    verdict = "小于噪声"
        usd = r.get("★真链美元", {})
        rows.append({
            "策略": name, "点": f"{key}={v}", "链": label, "状态": "跑成",
            "笔数": r.get("笔数"), "流水笔数": n_led,
            "每笔净R": r.get("每笔净R"), "每笔毛R": r.get("每笔毛R"),
            "毛盈亏美元": usd.get("毛盈亏"), "摩擦总额美元": usd.get("摩擦总额"),
            "净盈亏美元": usd.get("净盈亏"),
            "基准一差": diff, "真链SE": se_real, "对照SE": se_ctrl,
            "尺子": ruler, "判定": verdict,
            "随机每笔R": b1.get("随机进场_平均每笔R"),
            "对照笔数均值": b1.get("随机进场_对照笔数均值"),
            "耗时秒": r.get("耗时秒"), "json": fn,
        })

out = pd.DataFrame(rows)
out.to_csv("/tmp/claude-0/-home-claude/e6b5eede-2545-5921-9bbc-5820cecf2c9c/scratchpad/表_1106.csv",
           index=False, encoding="utf-8")

pd.set_option("display.width", 250, "display.max_columns", 50)
for _, r in out.iterrows():
    print("=" * 70)
    for k, v in r.items():
        print(f"  {k} = {v}")

print("\n\n########## 相邻三点是否同向（基准一差的符号） ##########")
for name, key, pts in ORDER:
    sub = out[out["策略"] == name]
    ds = [r["基准一差"] for _, r in sub.iterrows()]
    if any(d is None or (isinstance(d, float) and math.isnan(d)) for d in ds):
        print(f"{name}: ★ 有点算不出 → 同向无法判 · 差={ds}")
        continue
    sg = ["+" if d > 0 else ("-" if d < 0 else "0") for d in ds]
    print(f"{name}: 符号 {sg} → {'同向' if len(set(sg)) == 1 else '★ 三点不同向'} · 差={[round(d,6) for d in ds]}")
