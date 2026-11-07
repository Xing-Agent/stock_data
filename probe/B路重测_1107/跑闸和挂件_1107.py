# -*- coding: utf-8 -*-
"""
★ 这一份是 **2016 窗口第一版**(随机对照只有 10 次,规矩㊸ v2 之前写的)—— 要重跑须 `env B窗=2016 python3 ...`(bash 不认中文变量名,必须用 env);
  22 年正式版见 跑22年_1107.py。结果留作对照,不往外报结论。

★★★ 《100》3.5 第 2 件 + 环境闸 —— 并池 3,834 只 × 2016~2025,每一条比较都带随机对照(规矩㊸)

跑前写死(预先登记,不许事后改):
  宿主 4 条(都没有移动止损 / 时间止损 / 环境闸 → 装上去是真加装):
    技-1 唐奇安突破(大波段) · 技-6-原著(突破) · 技-14-原著 布林(震荡) · 技-12 康纳斯(震荡)
  A · 环境闸「暴跌档空仓」(= 切短期国债,现金不计利息):
      门槛相邻三点(一次只动一个旋钮,其余在中心 200/20/252):均线 100/200/300 · 波动回看 10/20/40 · 中位回看 126/252/504
      ★ 主判据:年化、最大回撤;次判据:每笔净 R
      ★ 随机对照:把真实关闸日整体随机平移 10 次(段数、段长、天数不变)→ 「随机闸 − 不装」的均值和标准差
  B · 挂件(出场):吊灯 2/3/4 ATR · 唐奇安低点 10/20 · 时间止损(大波段/突破 20/40/60,震荡 3/5/10)
      ★ 测法同《89》:同一宿主装/不装,只取共同进场逐笔配对
      ★ 随机对照:随机砍单 —— 砍掉的笔数调到和真挂件一样多,10 个种子 → 「随机砍 − 不装」的均值和标准差
  C · 每条宿主自己的单次噪声:排序随机 10 个种子(和主路量 0.0713 同一种量法)
  ★★★ 判:真差距 < 随机一个标准差 → 「分不出」;1~2 个 → 「只能当方向」;≥2 个才写「超过噪声」
  ★ 不写「建议挂 / 不挂」—— 只给数字。
可续跑(每个宿主一个结果文件);流水不入库;engine 零改动。
"""
from __future__ import annotations
import copy, gc, io, json, os, sys, time, traceback
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 台_1107 as T                                                     # noqa: E402
sys.path.insert(0, os.path.join(T.ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as P                                                # noqa: E402  ★ 只借配对比等纯函数

ARMS = os.path.join(HERE, "arms_1107")
RES = os.path.join(HERE, "res_2016窗口_1107")
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
宿主 = [("技-1·大波段", "engine/configs/技-1.yaml", [20, 40, 60]),
      ("技-6-原著·突破", "engine/configs/技-6-原著.yaml", [20, 40, 60]),
      ("技-14-原著·震荡", "engine/configs/技-14-原著.yaml", [3, 5, 10]),
      ("技-12·震荡", "engine/configs/技-12.yaml", [3, 5, 10])]
闸点 = [(200, 20, 252), (100, 20, 252), (300, 20, 252), (200, 10, 252), (200, 40, 252), (200, 20, 126), (200, 20, 504)]


def 挂件表(时间点):
    out = [(f"吊灯{k}ATR", (lambda r, k=k: P.装吊灯(r, float(k))), "止损") for k in (2, 3, 4)]
    out += [(f"唐奇安{n}日低点", (lambda r, n=n: P.装唐奇安低点(r, n)), "止损") for n in (10, 20)]
    out += [(f"时间止损{n}天", (lambda r, n=n: P.装时间止损(r, n)), "时间止损") for n in 时间点]
    return out


def 摘(p: dict) -> dict:
    r1 = p.get("①每笔净收益率") or {}; r2 = p.get("②大盘替身差(装 减 不装)") or {}
    return {"共同": p.get("★★共同进场笔数"), "收益差pct": r1.get("★差pct"), "替身差pct": r2.get("★差pct"),
            "R差": p.get("③每笔净R差"), "砍掉笔数": (p.get("★★误杀") or {}).get("被挂件提前砍掉的笔数"),
            "误杀率": (p.get("★★误杀") or {}).get("★★误杀率(不装本来会赚的占比)"),
            "在场比": (p.get("★★在场时间") or {}).get("★装÷不装")}


def 一个宿主(名, cfgp, 时间点) -> dict:
    t0 = time.time()
    raw = T.读配置(cfgp)
    m, diag = T.建矩阵(raw)
    out = {"配置": cfgp, "★巨头筛完可买天数": diag["★巨头大中盘筛完后可买天数"],
           "universe砍掉比例": diag.get("universe 票日 砍掉比例")}
    base, info, res = T.跑(raw, m)
    out["不装"] = {**info, **T.每笔(base), "基准": T.基准(res)}
    print(f"  ✓ {名} 不装 {info['笔数']} 笔 {time.time()-t0:.0f}s", flush=True)

    # ── C 排序噪声
    rs0 = m.rank_score.copy()
    rr = []
    for sd in 种子:
        T.随机排序(m, sd); l, inf, _ = T.跑(raw, m); rr.append({"种子": sd, **T.每笔(l), "年化": inf["年化"]})
    m.rank_score = rs0
    a = np.array([x["每笔净R"] for x in rr])
    out["C·排序随机10种子"] = {"每笔净R均值": round(float(a.mean()), 4), "★单次噪声一个标准差(每笔净R)": round(float(a.std(ddof=1)), 4),
                          "生产排序距随机几个标准差": round((out["不装"]["每笔净R"] - a.mean()) / a.std(ddof=1), 2),
                          "明细": rr}
    print(f"  ✓ 排序噪声 sd={a.std(ddof=1):.4f}", flush=True)

    # ── A 环境闸
    reg0 = m.regime.copy()
    i0 = int(m.index.searchsorted(pd.Timestamp(T.START)))
    A = {}
    for (ma, vl, ml) in 闸点:
        k = f"均线{ma}·波动{vl}·中位{ml}"
        g = T.加闸(raw, ma, vl, ml)
        if (ma, vl, ml) == (200, 20, 252):
            # ★ 中心点走完整 matrices.build(覆盖层真被引擎调用),并核对与直接算的一致
            # ★ 只用 20 只票走一遍 build(闸是全池共用的一条线,和票数无关;省内存,7GB 装不下两份全池矩阵)
            mg = T.matrices.build(T.chain.ChainConfig.from_dict(copy.deepcopy(g)).raw, m.symbols[:20])
            real = np.asarray(mg.regime).copy(); del mg; gc.collect()
            direct = T.matrices.regime_mask(g["regime"], m.index).to_numpy(bool)
            自证 = {"引擎build出的闸 == 直接调覆盖层": bool((real == direct).all()),
                  "关闸天数(窗口内)": int((~real[i0:]).sum())}
        else:
            real = T.matrices.regime_mask(g["regime"], m.index).to_numpy(bool)
            自证 = {"关闸天数(窗口内)": int((~real[i0:]).sum())}
        m.regime = real
        lg, ig, rg = T.跑(g, m)
        真 = {**ig, **T.每笔(lg), "基准": T.基准(rg)}
        随 = []
        for sd in 种子:
            m.regime = T.随机平移(real, sd, i0)
            lr, ir, _ = T.跑(g, m)
            随.append({**ir, **T.每笔(lr)})
        m.regime = reg0
        判 = {}
        for 指 in ("年化", "最大回撤", "每笔净R"):
            d真 = 真[指] - out["不装"][指]
            判[指] = T.噪声判(d真, [x[指] - out["不装"][指] for x in 随])
        A[k] = {"自证": 自证, "装闸": 真, "★差(装 减 不装) vs 随机闸": 判,
                "随机闸明细": [{x: y for x, y in r.items() if x in ("年化", "最大回撤", "每笔净R", "笔数")} for r in 随]}
        print(f"  ✓ 闸 {k} 年化差 {判['年化'].get('真')} z={判['年化'].get('距随机几个标准差')}", flush=True)
    # 相邻三点同向
    def 同向(ks, 指):
        v = [A[k]["★差(装 减 不装) vs 随机闸"][指].get("真") for k in ks]
        if any(x is None for x in v):
            return "算不出"
        s = [np.sign(x) for x in v]
        mid_only = (abs(v[1]) > 0 and np.sign(v[1]) != np.sign(v[0]) and np.sign(v[1]) != np.sign(v[2]))
        return {"三点": v, "★同向": bool(len(set(s)) == 1), "★只有中间那点不同(尖峰)": bool(mid_only)}
    组 = {"均线": ["均线100·波动20·中位252", "均线200·波动20·中位252", "均线300·波动20·中位252"],
         "波动回看": ["均线200·波动10·中位252", "均线200·波动20·中位252", "均线200·波动40·中位252"],
         "中位回看": ["均线200·波动20·中位126", "均线200·波动20·中位252", "均线200·波动20·中位504"]}
    A["★相邻三点同向"] = {g: {指: 同向(ks, 指) for 指 in ("年化", "最大回撤", "每笔净R")} for g, ks in 组.items()}
    out["A·环境闸暴跌档空仓"] = A
    out["★覆盖层自证"] = T.覆盖层自证()

    # ── B 挂件
    B = {}
    ex0 = np.asarray(m.exit_sig).copy()
    hd = base["holding_days"].astype(float).to_numpy()
    for 件, fn, 原因 in 挂件表(时间点):
        try:
            r = fn(raw)
            lk, ik, _ = T.跑(r, m)
            pk = P.配对比(base, lk, 原因)
            真 = 摘(pk)
            c = (真["砍掉笔数"] or 0) / max(1, 真["共同"] or 1)
            p = T.求p(hd, c) if c > 0 else 0.0
            随 = []
            for sd in 种子:
                m.exit_sig = ex0 | T.随机砍单矩阵(ex0.shape, p, sd)
                lr, _, _ = T.跑(raw, m)
                随.append(摘(P.配对比(base, lr, "离场规则")))
            m.exit_sig = ex0
            B[件] = {"装": {**ik, **T.每笔(lk)}, "★真挂件(配对)": 真, "随机砍单p": round(p, 5),
                     "★vs随机砍单": {指: T.噪声判(真[指], [x[指] for x in 随]) for 指 in ("收益差pct", "替身差pct", "R差")},
                     "随机砍单明细": 随}
            print(f"  ✓ 挂件 {件} 收益差 {真['收益差pct']} 判 {B[件]['★vs随机砍单']['收益差pct']['★判'][:10]}", flush=True)
        except Exception:
            m.exit_sig = ex0
            B[件] = {"★跑失败": traceback.format_exc(limit=3)[-500:]}
            print(f"  ✗✗✗ 挂件 {件}", flush=True)
    out["B·挂件"] = B
    base.to_csv(T.臂文件(ARMS, f"{名}|不装"), index=False)
    del m; gc.collect()
    out["耗时秒"] = round(time.time() - t0, 1)
    return out


def main() -> int:
    env = T.装池()
    os.makedirs(ARMS, exist_ok=True); os.makedirs(RES, exist_ok=True)
    print("★", json.dumps({k: v for k, v in env.items() if not k.startswith("_")}, ensure_ascii=False), flush=True)
    for 名, cfgp, 时间点 in 宿主:
        p = os.path.join(RES, f"{名}.json")
        if os.path.exists(p):
            print("⟳", 名, flush=True); continue
        try:
            r = 一个宿主(名, cfgp, 时间点)
        except Exception:
            r = {"★★★跑失败": traceback.format_exc(limit=4)[-800:]}
            print("✗✗✗", 名, r["★★★跑失败"], flush=True)
        io.open(p, "w", encoding="utf-8").write(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        gc.collect()
    print("★ 全部宿主完", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
