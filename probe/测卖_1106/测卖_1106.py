# -*- coding: utf-8 -*-
"""
★★★ 测**卖**（出场规则好不好）—— ★ 固定买点，换卖法。

★★ 来历：Lin 1106 18:32 指出《83》那五步**全是在测买，一步都没测卖**。
★★★ 而我们对「卖」的结论一直是**反推**来的：
  「利润因子有 1.543，而它的进场测不出 → 所以功劳在卖」——
  ★ 这是反推，不是实测；★★ 和我今天批评 Gemini 那个「73 笔赚 66 万」
  犯的是同一类毛病：**拿一个差额去反推机制，而没有逐项对**。

★★★ 设计（★ 这是「测卖」的正确形状）：
  ① 找**同一个买点、不同卖法**的臂组（★★ 按进场日集合重叠度自动找，不靠名字猜）
  ② ★★★ **只取各臂都有的那些进场**（取交集）→ 买点被完全控住
  ③ 逐笔配对比成绩差，★★ 并按**进场日聚类**算标准误（★ 同一天的笔不独立）

★ engine 零改动；★★ 算不出单独报数，不猜不补；★★★ 失败大声报（规矩⑯）。
"""
import glob, itertools, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
OUT = "probe/测卖_1106"
最少聚类 = 3


def 读(p):
    d = pd.read_csv(p)
    need = {"symbol", "entry_date", "r_multiple_net", "net_pnl", "holding_days"}
    if d.empty or not need <= set(d.columns):
        return None
    d["entry_date"] = pd.to_datetime(d["entry_date"], errors="coerce")
    for c in ("r_multiple_net", "net_pnl", "holding_days"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["entry_date", "r_multiple_net"])
    d["键"] = d["symbol"].astype(str) + "|" + d["entry_date"].dt.strftime("%Y-%m-%d")
    # ★ 同一个键可能有多笔(同票同日重复进场)→ 取第一笔,★★ 并记下丢了多少
    n0 = len(d)
    d = d.drop_duplicates("键", keep="first")
    return d, n0 - len(d)


def 找组():
    """★ 按进场日集合重叠度 ≥ 0.80 且流水不同 → 很可能只差卖法。"""
    sig, frames = {}, {}
    for p in sorted(glob.glob("probe/**/REAL__*.csv", recursive=True)):
        r = 读(p)
        if r is None:
            continue
        d, dup = r
        名 = os.path.basename(p)[6:-4]
        if 名 in frames:
            continue
        frames[名] = (d, dup)
        sig[名] = frozenset(d["键"])
    组 = []
    for a, b in itertools.combinations(sorted(sig), 2):
        A, B = sig[a], sig[b]
        if not A or not B or A == B:
            continue
        if len(A & B) / len(A | B) >= 0.80:
            组.append((a, b))
    return frames, sig, 组


def 配对比(frames, 名单):
    """★★★ 只取各臂都有的进场（交集）→ 买点完全控住，剩下只有卖法在变。"""
    ds = {n: frames[n][0].set_index("键") for n in 名单}
    共 = set.intersection(*[set(d.index) for d in ds.values()])
    if len(共) < 20:
        return {"★算不出": f"共同进场只有 {len(共)} 笔,★ 少于 20 笔不比"}
    共 = sorted(共)
    out = {"★共同进场笔数": len(共),
           "★各臂原始笔数": {n: int(len(frames[n][0])) for n in 名单},
           "★同票同日重复被丢掉的笔数": {n: int(frames[n][1]) for n in 名单}}
    基 = 名单[0]
    for n in 名单:
        d = ds[n].loc[共]
        pnl, r = d["net_pnl"], d["r_multiple_net"]
        赢, 亏 = pnl[pnl > 0], pnl[pnl < 0]
        out[n] = {
            "每笔净R平均": round(float(r.mean()), 4),
            "胜率": round(float((pnl > 0).mean()), 4),
            "利润因子_美元": (round(float(赢.sum() / abs(亏.sum())), 3)
                         if len(亏) and 亏.sum() != 0 else None),
            "平均持有天": round(float(d["holding_days"].mean()), 1),
        }
    # ★★★ 配对差 + 按进场日聚类的标准误
    for n in 名单[1:]:
        a = ds[基].loc[共]
        b = ds[n].loc[共]
        diff = (b["r_multiple_net"] - a["r_multiple_net"]).dropna()
        日 = pd.to_datetime(
            pd.Series(共, index=共).str.split("|").str[1]).reindex(diff.index)
        g = diff.groupby(日.values).mean().dropna()
        nd = len(g)
        se = float(g.std(ddof=1) / np.sqrt(nd)) if nd >= 最少聚类 else np.nan
        m = float(diff.mean())
        t = (m / se) if (np.isfinite(se) and se > 0) else np.nan
        out[f"★★★配对差 {n} 减 {基}"] = {
            "每笔净R的差": round(m, 4),
            "★按进场日聚类的标准误": (round(se, 4) if np.isfinite(se) else None),
            "★★聚类数(不同进场日)": nd,
            "t值": (round(t, 2) if np.isfinite(t) else None),
            "★★★判定": ("★ 正且过 2 倍标准误" if (np.isfinite(t) and t > 2) else
                      ("负且过 2 倍标准误" if (np.isfinite(t) and t < -2) else
                       "★★★ 测不出（在噪声里）")),
        }
    return out


def main() -> int:
    报 = {"★这一份测什么": {
        "测的是": "★★★ **卖**（出场规则好不好）—— ★ 固定买点，换卖法",
        "为什么要它": "★★ 原来五步全在测买；★★★ 我们对「卖」的结论一直是**反推**的，"
                  "从没直接测过",
        "设计": "★ 只取各臂**都有**的那些进场（取交集）→ 买点完全控住；"
              "★★ 逐笔配对；★★★ 标准误按**进场日聚类**",
        "engine改动": "零",
    }}
    frames, sig, 组 = 找组()
    报["★自动找到的臂对数"] = len(组)
    # ★ 把两两对合并成「组」(同一个买点的若干卖法)
    邻 = {}
    for a, b in 组:
        邻.setdefault(a, set()).add(b)
        邻.setdefault(b, set()).add(a)
    做过 = set()
    n组 = 0
    for k in sorted(邻, key=lambda x: -len(邻[x])):
        if k in 做过:
            continue
        团 = sorted({k} | 邻[k])
        团 = [x for x in 团 if x not in 做过]
        if len(团) < 2:
            continue
        做过 |= set(团)
        n组 += 1
        try:
            r = 配对比(frames, 团)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
        报[f"组{n组}: " + " ｜ ".join(x[:36] for x in 团)] = r
        print(f"✓ 组{n组}（{len(团)} 条臂）", flush=True)
    报["★★★组数"] = n组
    失败 = sum(1 for v in 报.values() if isinstance(v, dict) and "★跑失败" in v)
    报["★★★失败组数"] = 失败
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "测卖_报告_1106.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★ {n组} 组;★★★ 失败 {失败} 组")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
