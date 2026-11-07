# -*- coding: utf-8 -*-
"""
★★★ 《100》正式版 —— 并池 3,858 只 × 2004-01-02~2025-12-31(22 年,含 2008),按规矩㊸ v2

跑前写死(预先登记,不许事后改):
  宿主 4 条(本来都没有移动止损 / 时间止损 / 环境闸):
    技-1 唐奇安突破(大波段)· 技-6-原著(突破)· 技-14-原著 布林(震荡)· 技-12 康纳斯(震荡)
  A · 环境闸「暴跌档空仓」(= 切短期国债;现金不计利息,对我们不利的一侧)
      门槛相邻三点(一次只动一个旋钮,其余在中心 200/20/252)
      ① 配对检验(第一道):同一段日子,「装闸净值的日收益 − 不装的日收益」逐日相减;
         按月聚类 t + 按月块重抽样 95% 区间,两种都过才算
      ② 随机对照(第二道,100 次):把真实关闸日整体随机平移(段数、段长、天数不变)
         → 「随机闸 − 不装」的年化差的**标准差**(★ 规矩㊹:比的是一次抽样,用标准差不用标准误)
      ③ 相邻三点同向;只有中间那点好 = 尖峰,作废
  B · 挂件(出场):吊灯 2/3/4 ATR · 唐奇安低点 10/20 · 时间止损(大波段/突破 20/40/60,震荡 3/5/10)
      ① 配对检验:同一宿主装/不装,只取共同进场逐笔配对(进场日聚类 t + 月块重抽样)
      ② 随机对照 1000 次(流水级):同样多的笔、同样的「第几天砍」,随机换成别的单子砍 → 回答「它挑得比随便挑强不强」
  C · 每条宿主自己的单次噪声:排序随机 20 个种子
  ★★★ 判:差距 < 随机一个标准差 → 「分不出」;1~2 个 →「只能当方向」;≥2 个 →「超过噪声」
  ★ 只给数字,不写「建议挂 / 不挂」。
可续跑:每个(宿主, 项目)一个结果文件;流水不入库;engine 零改动。
"""
from __future__ import annotations
import copy, gc, io, json, os, sys, time, traceback
import numpy as np, pandas as pd

os.environ.setdefault("B窗", "2004")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 台_1107 as T                                                     # noqa: E402
sys.path.insert(0, os.path.join(T.ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as P                                                # noqa: E402
assert T.窗 == "2004", "★ 这一份只跑 22 年窗口"

ARMS = os.path.join(HERE, "arms_2004")
RES = os.path.join(HERE, "res_22年_1107")
N随机 = 100          # 环境闸:引擎重跑 100 次
N砍 = 1000           # 挂件:流水级随机砍单 1000 次(引擎重跑太慢:22 年一次约 8 秒)
排序种子 = list(range(1, 21))
宿主 = [("技-1·大波段", "engine/configs/技-1.yaml", [20, 40, 60]),
      ("技-6-原著·突破", "engine/configs/技-6-原著.yaml", [20, 40, 60]),
      ("技-14-原著·震荡", "engine/configs/技-14-原著.yaml", [3, 5, 10]),
      ("技-12·震荡", "engine/configs/技-12.yaml", [3, 5, 10])]
闸点 = [(200, 20, 252), (100, 20, 252), (300, 20, 252), (200, 10, 252), (200, 40, 252), (200, 20, 126), (200, 20, 504)]


def 存(p, obj):
    io.open(p, "w", encoding="utf-8").write(json.dumps(obj, ensure_ascii=False, indent=1, default=str))


def 日收益(res) -> pd.Series:
    return res.equity.pct_change().fillna(0.0)


def 配对日收益(r_a: pd.Series, r_b: pd.Series) -> dict:
    d = (r_a - r_b).dropna()
    月 = pd.Series(d.index.to_period("M").astype(str), index=d.index)
    c = P.聚类t(d, 月)
    b = P.块重抽样(d, 月)
    return {"日均差_年化pct": round(c["均值"] * 252 * 100, 3), "t(按月聚类)": round(c["t"], 2),
            "月块95%区间_年化pct": [round(x * 252 * 100, 3) for x in b["95%区间"]] if b.get("95%区间") else None,
            "★判": P.判(c["t"], b.get("区间不含0", False))}


def 随机砍单_流水级(base: pd.DataFrame, arm: pd.DataFrame, 原因: str, n: int) -> list:
    """★ 挂件的随机对照(规矩㊸ v2 第二道:「这旋钮本身有没有用」):
    真挂件在共同进场里提前砍掉了 K 笔,各自是「进场后第 k 天」砍的。
    随机版:**同样的 K 个 k**,随机分给另外 K 笔「持有超过 k 天」的单子,在第 k 天收盘砍掉。
    → 回答「挂件挑的那几笔,比随便挑同样多的单子、同样的时点砍,好不好」。
    ★ 近似:流水级重算,不重放资金占用;砍掉的价格用收盘(真挂件盘中止损/次日开盘)。"""
    A, B = P._键(base), P._键(arm)
    共 = A.index.intersection(B.index)
    a, b = A.loc[共], B.loc[共]
    砍 = (b["reason"].astype(str).str.contains(原因)) & (b["exit_date"] < a["exit_date"])
    panel = T.cache._PANEL; idx = panel["close"].index
    C = panel["close"]; cols = {s: j for j, s in enumerate(C.columns)}; Cv = C.to_numpy(float)
    spy = T.data.load_benchmark("SPY"); so = spy["open"].reindex(idx).ffill().to_numpy(float); sc = spy["close"].reindex(idx).ffill().to_numpy(float)
    ei = idx.searchsorted(a["entry_date"].values); xi = idx.searchsorted(a["exit_date"].values)
    hold = xi - ei
    k真 = (idx.searchsorted(b.loc[砍, "exit_date"].values) - idx.searchsorted(b.loc[砍, "entry_date"].values))
    jj = np.array([cols.get(s, -1) for s in a["symbol"].astype(str)])
    fr = a["friction_bps"].astype(float).to_numpy() / 1e4
    ret_a = a["ret"].to_numpy(float)
    spy_a = P.替身收益(a).to_numpy(float)
    ep = a["entry_price"].astype(float).to_numpy()
    rng = np.random.default_rng(777)
    N = len(共)
    ok_t = (jj >= 0)
    order = np.argsort(np.where(ok_t, hold, -1), kind="stable")
    hs = np.where(ok_t, hold, -1)[order]
    start = np.searchsorted(hs, k真, side="right")          # 持有 > k 的单子在排序后的起点
    cnt = N - start
    k用 = k真[cnt > 0]; st = start[cnt > 0]; ct = cnt[cnt > 0]
    out = []
    for _ in range(n):
        # ★ 向量化:每个 k 在「持有 > k」的单子里随机挑一笔(允许极少数重复,影响可忽略)
        t = order[st + (rng.random(len(k用)) * ct).astype(int)]
        px = Cv[ei[t] + k用, jj[t]]
        f = np.isfinite(px)
        t, kk, px = t[f], k用[f], px[f]
        r_new = px / ep[t] - 1 - 2 * fr[t]
        s_new = sc[ei[t] + kk] / so[ei[t]] - 1
        sa = np.where(np.isfinite(spy_a[t]), spy_a[t], s_new)
        dr = float((r_new - ret_a[t]).sum()); dx = float(((r_new - s_new) - (ret_a[t] - sa)).sum())
        out.append({"收益差pct": dr / N * 100, "替身差pct": dx / N * 100, "砍掉笔数": int(len(t))})
    return out


def 挂件表(时间点):
    out = [(f"吊灯{k}ATR", (lambda r, k=k: P.装吊灯(r, float(k))), "止损") for k in (2, 3, 4)]
    out += [(f"唐奇安{n}日低点", (lambda r, n=n: P.装唐奇安低点(r, n)), "止损") for n in (10, 20)]
    out += [(f"时间止损{n}天", (lambda r, n=n: P.装时间止损(r, n)), "时间止损") for n in 时间点]
    return out


def 摘(p: dict) -> dict:
    r1 = p.get("①每笔净收益率") or {}; r2 = p.get("②大盘替身差(装 减 不装)") or {}
    return {"共同": p.get("★★共同进场笔数"), "收益差pct": r1.get("★差pct"), "收益差t": r1.get("t"),
            "收益差区间": r1.get("按月块重抽样95%区间pct"), "收益差判": r1.get("★★★判定"),
            "替身差pct": r2.get("★差pct"), "替身差t": r2.get("t"), "替身差判": r2.get("★★★判定"),
            "R差": p.get("③每笔净R差"), "砍掉笔数": (p.get("★★误杀") or {}).get("被挂件提前砍掉的笔数"),
            "误杀率": (p.get("★★误杀") or {}).get("★★误杀率(不装本来会赚的占比)"),
            "在场比": (p.get("★★在场时间") or {}).get("★装÷不装")}


def 一个宿主(名, cfgp, 时间点):
    d = os.path.join(RES, 名); os.makedirs(d, exist_ok=True)
    raw = T.读配置(cfgp)
    t0 = time.time()
    m, diag = T.建矩阵(raw)
    print(f"★ {名} 建矩阵 {time.time()-t0:.0f}s 巨头 {diag['★巨头大中盘筛前→筛后可买天数']}", flush=True)
    base, info, res = T.跑(raw, m)
    rb = 日收益(res)
    base.to_csv(T.臂文件(ARMS, f"{名}|不装"), index=False)
    存(os.path.join(d, "0_不装.json"), {"配置": cfgp, **{k: v for k, v in diag.items() if k.startswith("★")},
                                     **info, **T.每笔(base), "基准": T.基准(res),
                                     "★覆盖层自证": T.覆盖层自证(), "池": {k: v for k, v in T.装池().items() if not k.startswith("_")}})

    # ── C 排序噪声
    p = os.path.join(d, "C_排序噪声.json")
    if not os.path.exists(p):
        rs0 = m.rank_score.copy(); rr = []
        for sd in 排序种子:
            T.随机排序(m, sd); l, inf, _ = T.跑(raw, m); rr.append({"种子": sd, **T.每笔(l), "年化": inf["年化"]})
        m.rank_score = rs0
        a = np.array([x["每笔净R"] for x in rr])
        存(p, {"每笔净R均值": round(float(a.mean()), 4), "★单次噪声一个标准差(每笔净R)": round(float(a.std(ddof=1)), 4),
              "生产排序距随机几个标准差": round((T.每笔(base)["每笔净R"] - a.mean()) / a.std(ddof=1), 2) if a.std(ddof=1) > 0 else None,
              "明细": rr})
        print(f"  ✓ 排序噪声 sd={a.std(ddof=1):.4f}", flush=True)

    # ── B 挂件
    for 件, fn, 原因 in 挂件表(时间点):
        p = os.path.join(d, f"B_{件}.json")
        if os.path.exists(p):
            continue
        tk = time.time()
        try:
            lk, ik, _ = T.跑(fn(raw), m)
            真 = 摘(P.配对比(base, lk, 原因))
            随 = 随机砍单_流水级(base, lk, 原因, N砍)
            存(p, {"装": {**ik, **T.每笔(lk)}, "★①配对检验(同进场逐笔)": 真,
                  "★②随机砍单对照(流水级·{}次·标准差)".format(N砍): {指: T.噪声判(真[指], [x[指] for x in 随]) for 指 in ("收益差pct", "替身差pct")},
                  "随机砍单说明": "被挂件砍掉的那些笔的「第几天砍」原样保留,随机换成另一批持有够久的单子在同一天数收盘砍掉(扣同样的摩擦)",
                  "随机砍单前20次": 随[:20]})
            print(f"  ✓ 挂件 {件} 配对 {真['收益差pct']}% t={真['收益差t']} {time.time()-tk:.0f}s", flush=True)
        except Exception:
            存(p.replace(".json", "_失败.json"), {"★跑失败": traceback.format_exc(limit=4)[-800:]})
            print(f"  ✗✗✗ 挂件 {件}", flush=True)
    # ── A 环境闸
    reg0 = m.regime.copy()
    i0 = int(m.index.searchsorted(pd.Timestamp(T.START)))
    for (ma, vl, ml) in 闸点:
        k = f"均线{ma}·波动{vl}·中位{ml}"
        p = os.path.join(d, f"A_{k}.json")
        if os.path.exists(p):
            continue
        tk = time.time()
        g = T.加闸(raw, ma, vl, ml)
        real = T.matrices.regime_mask(g["regime"], m.index).to_numpy(bool)
        自证 = {"关闸天数(窗口内)": int((~real[i0:]).sum())}
        if (ma, vl, ml) == (200, 20, 252):
            mg = T.matrices.build(T.chain.ChainConfig.from_dict(copy.deepcopy(g)).raw, m.symbols[:20])
            自证["★引擎build出的闸 == 直接调覆盖层"] = bool((np.asarray(mg.regime) == real).all()); del mg
        m.regime = real
        lg, ig, rg = T.跑(g, m)
        真 = {**ig, **T.每笔(lg), "基准": T.基准(rg)}
        配对 = 配对日收益(日收益(rg), rb)
        随 = []
        for sd in range(N随机):
            m.regime = T.随机平移(real, 1000 + sd, i0)
            lr, ir, _ = T.跑(g, m)
            随.append({"年化": ir["年化"], "最大回撤": ir["最大回撤"], **T.每笔(lr)})
        m.regime = reg0
        判 = {指: T.噪声判(真[指] - info[指] if 指 != "每笔净R" else 真[指] - T.每笔(base)[指],
                         [x[指] - (info[指] if 指 != "每笔净R" else T.每笔(base)[指]) for x in 随])
             for 指 in ("年化", "最大回撤", "每笔净R")}
        存(p, {"自证": 自证, "装闸": 真, "★①配对检验(日收益逐日相减)": 配对,
              "★②随机闸对照(100次·标准差)": 判, "随机闸明细": 随})
        print(f"  ✓ 闸 {k} 配对 {配对['日均差_年化pct']}% t={配对['t(按月聚类)']} | 年化差 z={判['年化'].get('距随机几个标准差')} {time.time()-tk:.0f}s", flush=True)

    del m; gc.collect()


def main() -> int:
    env = T.装池()
    os.makedirs(ARMS, exist_ok=True); os.makedirs(RES, exist_ok=True)
    print("★", json.dumps({k: v for k, v in env.items() if not k.startswith("_")}, ensure_ascii=False), flush=True)
    for 名, cfgp, 时间点 in 宿主:
        d = os.path.join(RES, 名)
        需要 = [f"A_均线{a}·波动{b}·中位{c}.json" for a, b, c in 闸点] + [f"B_{x[0]}.json" for x in 挂件表(时间点)] + ["C_排序噪声.json", "0_不装.json"]
        if os.path.isdir(d) and all(os.path.exists(os.path.join(d, f)) for f in 需要):
            print("⟳", 名, flush=True); continue
        try:
            一个宿主(名, cfgp, 时间点)
        except Exception:
            os.makedirs(d, exist_ok=True)
            存(os.path.join(d, "★★★宿主跑失败.json"), {"错": traceback.format_exc(limit=4)[-800:]})
            print("✗✗✗", 名, flush=True)
        gc.collect()
    print("★ 全部宿主完", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
