# -*- coding: utf-8 -*-
"""
★★★ 《100》3.5 第 3 件 —— 环境卡 9 整 + 3 半,按第 46 轮「调仓位、不当开关」,每条带随机对照

跑前写死(预先登记):
  · 宿主流水 = 跑闸和挂件_1107.py 里四个宿主的「不装」(并池 3,834 × 2016~2025)
  · 每张卡事先登记「差档」(★ 按卡上文字的意思定方向 —— ③ 我们定的,不是原著数字):
      差档 → 仓位减半(0.5),其余 1.0(《87》问题 F 的选项①「环境差就减半」)
  · 效果 = 「按仓位加权后的每笔成绩」−「等权的每笔成绩」(成绩 = 比同期大盘,修正口径 C;另报每笔净 R)
  · ★★★ 随机对照:差档标签在**同一个月里**随机打乱 100 次(2016 第一版是 20 次)(减半的笔数和月份分布不变,只是换了哪几笔)
      → 效果的随机均值和标准差;差距 < 随机一个标准差 = 「分不出」
  · ★ 只在流水上重新加权(资金占用不重放)—— 这是近似,写进报告
  · 状-3 按第 46 轮改用 Kaufman 效率比 ER(10),门槛 0.5 / 0.6 / 0.7 三点(《24》#50)
  · 状-9 这一张:昨天在老池上看到过「放巨量更差」—— 方向是看过数据后才知道的,★ 本次不算预先登记,单独标出
"""
from __future__ import annotations
import io, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 台_1107 as T                                                        # noqa: E402
sys.path.insert(0, os.path.join(T.ROOT, "probe", "挂件_1106"))
sys.path.insert(0, os.path.join(T.ROOT, "probe", "环境卡_1106"))
import 台_公共_1106 as P                                                   # noqa: E402
import 环境卡_1106 as K                                                    # noqa: E402

OUT = os.path.join(HERE, "环境卡结果_2016窗口_1107.json" if T.窗 == "2016" else "环境卡结果_22年_1107.json")
ARMS = os.path.join(HERE, "arms_1107" if T.窗 == "2016" else "arms_2004")
宿主 = ["技-1·大波段", "技-6-原著·突破", "技-14-原著·震荡", "技-12·震荡"]
N随机 = 20 if T.窗 == "2016" else 100      # ★ 规矩㊸ v2:随机对照 ≥100 次

差档 = {   # 卡 → (差档标签集合, 理由)
    "状-1 道氏高低点排列": ({"下跌"}, "高低点都在降 = 下跌趋势"),
    "状-2 温斯坦四阶段": ({"阶段3", "阶段4"}, "温斯坦只买阶段二;三、四阶段不买"),
    "状-3 ER(10)·门槛0.5": ({"震荡"}, "效率比低 = 锯齿行情"),
    "状-3 ER(10)·门槛0.6": ({"震荡"}, "同上"),
    "状-3 ER(10)·门槛0.7": ({"震荡"}, "同上"),
    "状-4 威科夫区间结构(半)": ({"近10日有上冲回落"}, "上冲回落(Upthrust)= 区间顶部派发迹象"),
    "状-5 相对强度": ({"更弱"}, "大盘回撤时比大盘跌得多"),
    "状-6 共振计数(半)": ({"弱支撑(≤1类)"}, "下方没有共振支撑"),
    "状-7 跳空缺口": ({"向下缺口"}, "信号日向下跳空"),
    "状-8 区间年龄与假突破": ({"区间内·假突破≥2"}, "区间里反复假突破"),
    "状-9 相对成交量": ({"极值放量"}, "★ 方向看过老池数据才定的,不算预先登记"),
    "状-10 可交易性": ({"不合格"}, "日均成交额不足 1000 万美元"),
    "状-11 板块趋势一致性": ({"低(<0.25)"}, "同行业多数票不在阶段二"),
    "状-12 空间位置": ({"下三分之一"}, "处在 52 周区间下三分之一"),
}


def 补两张(d, idx, panel):
    """★ 状-3 改用 ER(10);状-4 加上冲回落;状-8 加假突破计数档。只在信号日算。"""
    ei = idx.searchsorted(pd.to_datetime(d["entry_date"]).values) - 1
    er = np.full(len(d), np.nan); up = np.array([None] * len(d), dtype=object); fb = np.full(len(d), np.nan)
    for s, g in d.groupby(d["symbol"].astype(str)).groups.items():
        c = panel["close"][s].to_numpy(float); h = panel["high"][s].to_numpy(float); l = panel["low"][s].to_numpy(float)
        a = K.atr(h, l, c)
        net = np.abs(c - np.r_[np.full(10, np.nan), c[:-10]])
        path = pd.Series(np.abs(np.diff(c, prepend=np.nan))).rolling(10, min_periods=10).sum().to_numpy()
        e = net / np.where(path > 0, path, np.nan)
        inr, age, fbc, sp10, upth, _ = K.区间(c, h, l, a)
        u10 = pd.Series(upth.astype(float)).rolling(10, min_periods=1).sum().to_numpy() > 0
        for k in g:
            t = ei[d.index.get_loc(k)]
            if t < 0:
                continue
            er[d.index.get_loc(k)] = e[t]
            up[d.index.get_loc(k)] = ("不在区间" if not inr[t] else ("近10日有上冲回落" if u10[t] else "区间内无上冲回落"))
            fb[d.index.get_loc(k)] = fbc[t] if inr[t] else np.nan
    return er, up, fb


def 调仓位效果(x: pd.Series, bad: pd.Series) -> float:
    w = np.where(bad, 0.5, 1.0)
    ok = x.notna().to_numpy()
    return float((w[ok] * x[ok]).sum() / w[ok].sum() - x[ok].mean())


def 月内打乱(bad: pd.Series, 月: pd.Series, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    out = bad.copy()
    for _, ix in bad.groupby(月.values).groups.items():
        v = out.loc[ix].to_numpy().copy(); rng.shuffle(v); out.loc[ix] = v
    return out


def main() -> int:
    t0 = time.time()
    T.装池()
    panel = T.cache._PANEL; idx = panel["close"].index
    L = {}
    for 名 in 宿主:
        p = T.臂文件(ARMS, f"{名}|不装")
        if os.path.exists(p):
            L[名] = pd.read_csv(p)
    if len(L) < len(宿主):
        print(f"⚠⚠⚠ 宿主流水只有 {len(L)}/{len(宿主)} 条:{list(L)}", flush=True)
    if not L:
        raise SystemExit("★★★ 一条宿主流水都没有 —— 先跑 跑闸和挂件_1107.py")
    syms = sorted(set().union(*[set(v["symbol"].astype(str)) for v in L.values()]) & set(panel["close"].columns))
    res, extra, 映射 = K.算所有卡(syms, panel, idx)
    print(f"★ 卡算完 {len(syms)} 只 {time.time()-t0:.0f}s", flush=True)
    报 = {"★预先登记": __doc__.strip(), "★差档登记": {k: [sorted(v[0]), v[1]] for k, v in 差档.items()},
          "★卡定义(逐张标档)": K.卡定义, "★宿主": list(L), "★★★失败": []}
    n检 = 0; 过 = []
    for 名, led in L.items():
        d = P._键(led).reset_index(drop=True)
        d["x"] = d["ret"] - P.替身收益(d).to_numpy()
        d["R"] = d["r_multiple_net"].astype(float)
        lab = K.档位(res, extra, d, idx, 映射)
        er, up, fb = 补两张(d, idx, panel)
        for th in (0.5, 0.6, 0.7):
            lab[f"状-3 ER(10)·门槛{th}"] = np.where(np.isnan(er), None, np.where(er >= th, "趋势", "震荡"))
        lab["状-4 威科夫区间结构(半)"] = up
        lab["状-8 区间年龄与假突破"] = np.where(np.isnan(fb), "不在区间", np.where(fb >= 2, "区间内·假突破≥2", "区间内·假突破<2"))
        月 = d["entry_date"].dt.to_period("M").astype(str)
        h = {"笔数": len(d)}
        for 卡, (bset, _) in 差档.items():
            try:
                g = pd.Series(lab[卡], index=d.index)
                bad = g.isin(bset)
                nb = int(bad.sum())
                r = {"各档笔数": {str(k): int(v) for k, v in g.value_counts(dropna=False).items()},
                     "减半笔数": nb, "减半占比": round(nb / len(d), 4)}
                if nb < 30 or nb > len(d) - 30:
                    r["★判"] = "★算不出(减半那档 <30 笔或几乎全部)"; h[卡] = r; continue
                for 量, col in (("比大盘pct", "x"), ("每笔净R", "R")):
                    真 = 调仓位效果(d[col], bad) * (100 if col == "x" else 1)
                    随 = [调仓位效果(d[col], 月内打乱(bad, 月, sd)) * (100 if col == "x" else 1) for sd in range(N随机)]
                    r[f"调仓位效果·{量}"] = T.噪声判(真, 随)
                    # 差档 vs 其余 的分辨力(原始差值)也给出来
                    r[f"差档减其余·{量}"] = round(float(d.loc[bad, col].mean() - d.loc[~bad, col].mean()) * (100 if col == "x" else 1), 4)
                # ★ 规矩㊸ v2 第一道:同一批单子里「差档 vs 其余」—— 进场日聚类 t + 月块重抽样(两种都过才算)
                g2 = pd.Series(np.where(bad, "差档", "其余"), index=d.index)
                r["①配对检验·差档减其余·比大盘"] = K.对比(d["x"], g2, d["entry_date"].dt.strftime("%Y-%m-%d"), "差档", "其余")
                n检 += 1
                j = r["调仓位效果·比大盘pct"]["★判"]
                if "超过随机" in j:
                    过.append(f"{名} · {卡}:{j} 真 {r['调仓位效果·比大盘pct']['真']} 随机 {r['调仓位效果·比大盘pct']['随机均值']}±{r['调仓位效果·比大盘pct']['随机标准差']}")
                h[卡] = r
            except Exception as e:
                报["★★★失败"].append(f"{名}·{卡}: {type(e).__name__}: {e}")
        报[名] = h
        print("✓", 名, flush=True)
    报["★★★对账"] = {"有效检验数(按比大盘)": n检, "超过随机 2 个标准差的": 过,
                   "★说明": "随机对照已经把「运气」量进去了;但 N 张卡 × 4 宿主一起看,仍可能有 1~2 个是碰巧 —— 只看相邻三点同向和跨宿主同向的"}
    报["耗时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("★ 写到", OUT, "失败", len(报["★★★失败"]), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
