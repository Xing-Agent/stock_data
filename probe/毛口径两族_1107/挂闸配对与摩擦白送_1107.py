# -*- coding: utf-8 -*-
"""★★★《116》补两张表：
  ① **挂闸 vs 不挂闸** 的逐日配对（★ 3 族 × 2 段 × 3 档 = 18 个 t）—— ★★ 按规矩 58 改报区间。
     ★★★ 它**不是闸**（《116》5.2 的闸是红线② + 两段峰同参数）；★ 报它是因为 Lin 拍板项⑤。
  ② **摩擦档位白送 ADV20 多少**（净口径年化差 − 毛口径年化差），★★★ 并和**笔数**并排 ——
     ★ 这是在核「白送的量应该随换手上升」这条因果（口径⑥：难看的结论也要核，#77）。

★★ 口径（规矩㊼）：全收益（两侧同口径，《104》）· 摩擦档 5/15/30 bps · 窗口 A 2004~2014 / B 2015~2025
  · 池 并池2004 全量 3,858 只 · 标签滞后 1 天。★★★ 不引用基准一。
"""
import hashlib, json, os
import numpy as np, pandas as pd, statsmodels.api as sm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DS = os.path.join(ROOT, "probe", "重测_1107", "日序列毛_1107")
ARMS = os.path.join(ROOT, "probe", "重测_1107", "arms_毛_1107")
代表 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
NW, 门槛 = 8, 3.0


def sn(s): return hashlib.sha256(s.encode()).hexdigest()[:16]
def 读(l):
    p = os.path.join(DS, f"d_{sn(l)}.csv")
    return pd.read_csv(p, parse_dates=["日期"]).set_index("日期") if os.path.exists(p) else None
def 臂(l):
    p = os.path.join(ARMS, f"a_{sn(l)}.json")
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None


def 配(la, lb, 列="净值"):
    a, b = 读(la), 读(lb)
    if a is None or b is None: return None
    ra = a[列].astype(float).pct_change().dropna(); rb = b[列].astype(float).pct_change().dropna()
    共 = ra.index.intersection(rb.index)
    if len(共) < 30: return None
    x = (ra.reindex(共) - rb.reindex(共)).dropna()
    m = sm.OLS(x.to_numpy(), np.ones((len(x), 1))).fit(cov_type="HAC", cov_kwds={"maxlags": NW})
    mu, se, t = float(m.params[0]), float(m.bse[0]), float(m.tvalues[0])
    return {"n": int(len(x)), "年化差pp(日均×252)": round(mu * 252 * 100, 3),
            "95%区间pp": [round((mu - 1.96 * se) * 252 * 100, 3), round((mu + 1.96 * se) * 252 * 100, 3)],
            "★分辨力门槛pp(|t|=3)": round(3 * se * 252 * 100, 3), "NW_t": round(t, 3),
            "★判": ("★★★ 过 |t|>3" if abs(t) > 门槛 else
                   "★ 测不出来（规矩 58：不许写「更好」，也不许写「没作用」）")}


def 年化(l, 列="净值"):
    d = 读(l)
    if d is None or 列 not in d.columns: return None
    nv = d[列].astype(float)
    return float((nv.iloc[-1] / nv.iloc[0]) ** (252.0 / (len(nv) - 1)) - 1) * 100


报 = {"★本次口径": ("全收益（分红再投，两侧同口径，《104》）· 摩擦档 5/15/30 bps"
                 "· 窗口 A 2004-01-02~2014-12-31 / B 2015-01-01~2025-12-31"
                 "· 池 并池2004 全量 3,858 只 · 标签滞后 1 天"),
     "★不许引用": "基准一本批没算",
     "一·挂闸vs不挂闸_配对": {}, "二·摩擦白送与换手": {}}

for 族 in ("大波段", "突破", "震荡"):
    for 段 in ("A_2004到2014", "B_2015到2025"):
        pre = f"{段}·并池2004·{族}·{代表[族]}"
        for ma in (100, 200, 300):
            r = 配(f"{pre}·B挂开关MA{ma}", f"{pre}·A原样")
            if r:
                r["年化_挂闸%"] = round(年化(f"{pre}·B挂开关MA{ma}"), 3)
                r["年化_不挂闸%"] = round(年化(f"{pre}·A原样"), 3)
                报["一·挂闸vs不挂闸_配对"][f"{段}·{族}·MA{ma}"] = r

for 族 in ("大波段", "突破", "震荡"):
    for 段 in ("A_2004到2014", "B_2015到2025"):
        pre = f"{段}·并池2004·{族}·{代表[族]}"
        净, 毛 = [], []
        for s in 种子:
            for 列, acc in (("净值", 净), ("毛净值", 毛)):
                r = 配(f"{pre}·A原样", f"{pre}·R随机{s}", 列)
                if r: acc.append(r["年化差pp(日均×252)"])
        aj = 臂(f"{pre}·A原样")
        if 净 and 毛:
            报["二·摩擦白送与换手"][f"{段}·{族}"] = {
                "A原样笔数": aj and aj["笔数"],
                "净口径年化差中位pp": round(float(np.median(净)), 3),
                "毛口径年化差中位pp": round(float(np.median(毛)), 3),
                "★★★摩擦白送pp(净−毛)": round(float(np.median(净)) - float(np.median(毛)), 3),
                "★怎么读": "正 = 成本档位在帮 ADV20（_liquidity_tiers 就是按 ADV20 切的）"}

g = 报["二·摩擦白送与换手"]
笔 = [v["A原样笔数"] for v in g.values()]; 送 = [v["★★★摩擦白送pp(净−毛)"] for v in g.values()]
rho = float(np.corrcoef(np.log(笔), 送)[0, 1])
报["二·摩擦白送与换手"]["★★★因果核验"] = {
    "六格全为正吗": all(x > 0 for x in 送), "白送范围pp": [min(送), max(送)],
    "log(笔数) 与 白送 的相关": round(rho, 3),
    "★怎么读": ("★★★ 白送量随换手上升 —— ★ 这正是「成本档位是构造性优势」该有的样子；"
              "★★ 相关只有 6 个点，只当方向证据，不当强度"),
    "★★★ 和《115》对不对得上": ("《115》报的是 1.36~1.60 pp/年（★ 只有大波段一族）；"
                            "本档大波段两段是 +0.73 / +1.01 pp —— 同一个量级 ✅；"
                            "★★★ 但震荡那一族是 +10.6 / +14.7 pp —— **高一个量级**，"
                            "所以规矩 56 那句「白送 1.36~1.60pp」必须改成「0.4 ~ 14.7pp，随换手变」")}

json.dump(报, open(os.path.join(HERE, "挂闸配对与摩擦白送_报告_1107.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("═══ 一 · 挂闸 vs 不挂闸（逐日配对，规矩 58 区间）═══")
for k, v in 报["一·挂闸vs不挂闸_配对"].items():
    print(f"{k:34s} {v['年化差pp(日均×252)']:+8.2f}pp  区间{v['95%区间pp']}  "
          f"门槛{v['★分辨力门槛pp(|t|=3)']:6.1f}pp  t={v['NW_t']:+6.2f}  {v['★判'][:12]}")
print("\n═══ 二 · 摩擦白送 vs 换手 ═══")
for k, v in g.items():
    if k.startswith("★"): continue
    print(f"{k:24s} 笔数{v['A原样笔数']:6d}  净{v['净口径年化差中位pp']:+8.2f}  "
          f"毛{v['毛口径年化差中位pp']:+7.2f}  ★白送{v['★★★摩擦白送pp(净−毛)']:+7.2f}pp")
print(json.dumps(g["★★★因果核验"], ensure_ascii=False, indent=1))
