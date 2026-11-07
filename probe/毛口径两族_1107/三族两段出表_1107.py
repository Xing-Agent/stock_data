# -*- coding: utf-8 -*-
"""★★★《116》出表 —— ★ 三族两段：① 挂闸三点 ② 配对差改报区间（规矩 58）。

★★ 口径（规矩㊼ 五字段）：全收益（分红再投，两侧同口径，《104》）· 摩擦档 配置自带 5/15/30 bps
  · 窗口 A 2004-01-02~2014-12-31（实际可交易 2005 起）/ B 2015-01-01~2025-12-31
  · 池 并池2004 全量 3,858 只（一档） · 标签滞后 1 天。
★★★ 对外成绩一律**净口径**；毛口径只用来回答「摩擦档位贡献了多少」。
★★★ 本份不引用基准一（本批没算）。

★★ 自校验（口径⑥）：大波段那四行必须和《115》第四节逐行对上（±0.01pp），对不上就大声报。
"""
import hashlib, json, os
import numpy as np, pandas as pd, statsmodels.api as sm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DS = os.path.join(ROOT, "probe", "重测_1107", "日序列毛_1107")
SPY = {"A_2004到2014": 7.709, "B_2015到2025": 13.465}      # ★ 对满仓SPY_报告_1107.json 原值
代表 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
NW = 8
门槛 = 3.0


def 安全名(s): return hashlib.sha256(s.encode()).hexdigest()[:16]


def 读(lab):
    p = os.path.join(DS, f"d_{安全名(lab)}.csv")
    return pd.read_csv(p, parse_dates=["日期"]).set_index("日期") if os.path.exists(p) else None


def 年化(lab, 列="净值"):
    d = 读(lab)
    if d is None or 列 not in d.columns: return None
    nv = d[列].astype(float)
    年 = (len(nv) - 1) / 252.0
    return float((nv.iloc[-1] / nv.iloc[0]) ** (1 / 年) - 1) * 100


def 敞口笔(lab):
    d = 读(lab)
    return None if d is None else float(d["敞口"].astype(float).mean())


报 = {"★本次口径": ("全收益（分红再投，两侧同口径，《104》）· 摩擦档 5/15/30 bps"
                 "· 窗口 A 2004-01-02~2014-12-31（实际 2005 起）/ B 2015-01-01~2025-12-31"
                 "· 池 并池2004 全量 3,858 只 · 标签滞后 1 天"),
     "★预先登记": "《116》（跑前定稿）· 门槛 |t|>3 · 规矩 58 分辨力闸",
     "★不许引用": "基准一（同环境随机进场）本批没算",
     "★★★对外成绩口径": "净口径（毛口径只回答「摩擦贡献了多少」，不是「更真实」）",
     "一·挂闸三点": {}, "二·配对差改报区间": {}, "★自校验": {}}

# ───────── 一 · 挂闸三点（净口径） ─────────
for 族 in ("大波段", "突破", "震荡"):
    for 段 in ("A_2004到2014", "B_2015到2025"):
        pre = f"{段}·并池2004·{族}·{代表[族]}"
        行 = {}
        for 名 in ("A原样", "B挂开关MA100", "B挂开关MA200", "B挂开关MA300"):
            a = 年化(f"{pre}·{名}")
            行[名] = None if a is None else {
                "年化%": round(a, 3),
                "对满仓SPY(pp)": round(a - SPY[段], 3),
                "平均敞口": round(敞口笔(f"{pre}·{名}"), 3)}
        三 = [行[f"B挂开关MA{m}"]["年化%"] for m in (100, 200, 300) if 行.get(f"B挂开关MA{m}")]
        if len(三) == 3:
            峰 = (100, 200, 300)[int(np.argmax(三))]
            单调 = (三[0] <= 三[1] <= 三[2]) or (三[0] >= 三[1] >= 三[2])
            行["★★★红线②相邻三点"] = {
                "三点": 三, "峰在": f"MA{峰}", "单调": bool(单调),
                "判": ("✅ 同向（单调）" if 单调 else
                       f"❌ 不同向 —— 尖峰在 MA{峰}，按《102》3.3 算**挑出来的**")}
            行["★挂闸有没有比不挂好"] = {
                f"MA{m}": round(行[f"B挂开关MA{m}"]["年化%"] - 行["A原样"]["年化%"], 3)
                for m in (100, 200, 300)}
        报["一·挂闸三点"][f"{段}·{族}"] = 行

# ★ 两段的峰在不在同一个参数上（闸二）
for 族 in ("大波段", "突破", "震荡"):
    峰 = {}
    for 段 in ("A_2004到2014", "B_2015到2025"):
        v = 报["一·挂闸三点"].get(f"{段}·{族}", {}).get("★★★红线②相邻三点")
        if v: 峰[段] = v["峰在"]
    if len(峰) == 2:
        同 = len(set(峰.values())) == 1
        报["一·挂闸三点"][f"★★★{族}·两段峰是否同参数"] = {
            "A段峰": 峰["A_2004到2014"], "B段峰": 峰["B_2015到2025"],
            "判": ("✅ 同一个参数" if 同 else
                   "❌ 不同参数 —— ★★★ 样本外不成立（规矩㊸v2 第 4 条）")}

# ───────── 二 · 配对差改报区间（规矩 58） ─────────
for 族 in ("大波段", "突破", "震荡"):
    for 段 in ("A_2004到2014", "B_2015到2025"):
        pre = f"{段}·并池2004·{族}·{代表[族]}"
        for 列 in ("净值", "毛净值"):
            a = 读(f"{pre}·A原样")
            if a is None or 列 not in a.columns: continue
            ra = a[列].astype(float).pct_change().dropna()
            行 = []
            for s in 种子:
                b = 读(f"{pre}·R随机{s}")
                if b is None or 列 not in b.columns: continue
                rb = b[列].astype(float).pct_change().dropna()
                共 = ra.index.intersection(rb.index)
                if len(共) < 30: continue
                x = (ra.reindex(共) - rb.reindex(共)).dropna()
                m = sm.OLS(x.to_numpy(), np.ones((len(x), 1))).fit(
                    cov_type="HAC", cov_kwds={"maxlags": NW})
                mu, se, t = float(m.params[0]), float(m.bse[0]), float(m.tvalues[0])
                行.append({"种子": s, "n": int(len(x)),
                           "年化差pp(日均×252)": round(mu * 252 * 100, 3),
                           "95%区间pp": [round((mu - 1.96 * se) * 252 * 100, 3),
                                        round((mu + 1.96 * se) * 252 * 100, 3)],
                           "★分辨力门槛pp(|t|=3)": round(3 * se * 252 * 100, 3),
                           "NW_t": round(t, 3)})
            if not 行: continue
            ds = [r["年化差pp(日均×252)"] for r in 行]
            fl = [r["★分辨力门槛pp(|t|=3)"] for r in 行]
            过 = sum(1 for r in 行 if abs(r["NW_t"]) > 门槛)
            报["二·配对差改报区间"][f"{段}·{族}·{列}"] = {
                "随机臂数": len(行),
                "年化差中位pp": round(float(np.median(ds)), 3),
                "年化差范围pp": [round(min(ds), 3), round(max(ds), 3)],
                "★★★分辨力门槛中位pp": round(float(np.median(fl)), 3),
                f"|t|>{门槛}的": f"{过}/{len(行)}",
                "★★★判": ("★★★ 过门槛（这把尺子分得出）" if 过 == len(行) else
                        ("★★ 只有部分过 —— 不算站住" if 过 else
                         "★ 一条都没过 → ★★★ 规矩 58：写「**测不出来**」，不许写「更好」也不许写「没作用」")),
                "逐条": 行}

# ───────── 自校验（口径⑥）─────────
参 = {"A原样": -0.226, "B挂开关MA100": 6.098, "B挂开关MA200": 0.774, "B挂开关MA300": 3.464}
核 = {}
for 名, 期 in 参.items():
    got = 报["一·挂闸三点"]["A_2004到2014·大波段"].get(名)
    核[名] = {"《115》写的": 期, "本脚本算的": got and got["年化%"],
             "判": "✅ 对上" if got and abs(got["年化%"] - 期) <= 0.01 else "❌ 对不上"}
参B = {"A原样": 5.853, "B挂开关MA100": 14.048, "B挂开关MA200": 20.395, "B挂开关MA300": 3.304}
for 名, 期 in 参B.items():
    got = 报["一·挂闸三点"]["B_2015到2025·大波段"].get(名)
    核["B段·" + 名] = {"《115》写的": 期, "本脚本算的": got and got["年化%"],
                     "判": "✅ 对上" if got and abs(got["年化%"] - 期) <= 0.01 else "❌ 对不上"}
报["★自校验"] = {"★这是什么": "★★★ 口径⑥：先当自己错了 —— 大波段八行必须和《115》第四节逐行对上",
              "逐行": 核,
              "★★★判": "✅ 八行全对上" if all(v["判"].startswith("✅") for v in 核.values())
                       else "❌❌❌ 有对不上的 —— 先查为什么，结论不许发"}

json.dump(报, open(os.path.join(HERE, "三族两段_报告_1107.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
print("★自校验:", 报["★自校验"]["★★★判"])
for k, v in 核.items():
    print(f"   {k:16s} 《115》{v['《115》写的']:+8.3f}  本脚本 {v['本脚本算的']}  {v['判']}")
print("\n═══ 一 · 挂闸三点（净口径，年化 %，括号=对满仓SPY pp）═══")
for 族 in ("大波段", "突破", "震荡"):
    for 段 in ("A_2004到2014", "B_2015到2025"):
        r = 报["一·挂闸三点"][f"{段}·{族}"]
        s = "  ".join(f"{n.replace('B挂开关','')}={r[n]['年化%']:+7.3f}({r[n]['对满仓SPY(pp)']:+7.2f})"
                      for n in ("A原样", "B挂开关MA100", "B挂开关MA200", "B挂开关MA300") if r.get(n))
        print(f"{段[0]}·{族:4s} {s}")
        print(f"          红线②: {r['★★★红线②相邻三点']['判']}")
    print(f"   ★★★ 两段峰: {报['一·挂闸三点'][f'★★★{族}·两段峰是否同参数']}")
print("\n═══ 二 · 配对差（规矩 58 区间）═══")
for k, v in 报["二·配对差改报区间"].items():
    print(f"{k:28s} 中位 {v['年化差中位pp']:+8.2f}pp  范围 {v['年化差范围pp']}  "
          f"分辨力门槛 {v['★★★分辨力门槛中位pp']:.1f}pp  {v[f'|t|>{门槛}的']}")
