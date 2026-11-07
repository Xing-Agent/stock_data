# -*- coding: utf-8 -*-
"""★★★《118》随机同档 —— 出数：ADV20 排序 vs **同成本档位内抽的随机排序**。

★★ 判据照《118》3.3 跑前写死：配对检验（同一天逐日相减）→ Newey-West(8) t，门槛 |t| > 3。
★★★ N=10 的硬限：不报秩检验、不报分位数区间（《115》第七节）；只报 10 条逐条 t + 范围。
★★ 分辨力闸（规矩 58）：14.9~41.1 pp/年以下的差一律写「测不出来」。
★★★ 新旧两版**并排报** —— 它们答的是两个不同的问题（《118》3.1 代价那一段）。

★ 口径（规矩㊼）：全收益 · 摩擦 5/15/30 bps · A 2004(实际2005)~2014 / B 2015~2025
  · 并池2004 全量 3,858 只 · 标签滞后 1 天。
"""
from __future__ import annotations
import glob, hashlib, io, json, os, statistics as st

import numpy as np, pandas as pd, statsmodels.api as sm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."  , ".."))
DS_新 = os.path.join(ROOT, "probe", "重测_1107", "日序列同档_1107")
DS_旧 = os.path.join(ROOT, "probe", "重测_1107", "日序列毛_1107")
A_新 = os.path.join(HERE, "arms_同档_1107")
A_旧 = os.path.join(ROOT, "probe", "重测_1107", "arms_1107")
OUT = os.path.join(HERE, "随机同档配对_报告_1107.json")
NW_LAG = 8
门槛 = 3.0
分辨力 = (14.9, 41.1)          # ★ pp/年（#88 实测）
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
段 = ["A_2004到2014", "B_2015到2025"]
族文件 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}


def 安全名(label): return hashlib.sha256(label.encode()).hexdigest()[:16]
def 标签(seg, fam, arm): return f"{seg}·并池2004·{fam}·{族文件[fam]}·{arm}"


def 读(ds, label):
    p = os.path.join(ds, f"d_{安全名(label)}.csv")
    if not os.path.exists(p): return None
    return pd.read_csv(p, parse_dates=["日期"]).set_index("日期")


def nw_t(x):
    x = pd.Series(x).astype(float).dropna()
    if len(x) < 30: return {"★样本不够": len(x)}
    m = sm.OLS(x.to_numpy(), np.ones((len(x), 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": NW_LAG})
    return {"n": int(len(x)), "均值": float(m.params[0]),
            "★NW标准误": float(m.bse[0]), "★★★NW_t": float(m.tvalues[0]),
            "p": float(m.pvalues[0])}


def 年化对数(s):
    """★★★ 对数(复利)口径 —— 《111》第⑥条：算术年化系统性高估中位 2.90pp/年。"""
    r = np.log(s.astype(float)).diff().dropna()
    return float(np.exp(r.mean() * 252) - 1) if len(r) else float("nan")


def 配对(ds_a, la, ds_b, lb, 列):
    da, db = 读(ds_a, la), 读(ds_b, lb)
    if da is None or db is None or 列 not in da or 列 not in db:
        return {"★算不了": f"a={da is not None} b={db is not None} 列={列}"}
    ra = da[列].astype(float).pct_change().dropna()
    rb = db[列].astype(float).pct_change().dropna()
    共 = ra.index.intersection(rb.index)
    if len(共) < 30: return {"★算不了": f"共同交易日 {len(共)}"}
    out = nw_t(ra.reindex(共) - rb.reindex(共))
    out["★年化差pp(对数)"] = round(
        (年化对数(da[列].reindex(共.union(da.index[:1]))) -
         年化对数(db[列].reindex(共.union(db.index[:1])))) * 100, 3)
    return out


def 臂表(d):
    out = {}
    for p in glob.glob(d + "/*.json"):
        r = json.load(io.open(p, encoding="utf-8"))
        out[(r["链"].split("·")[0], r["族"], r["臂"])] = r
    return out


def main():
    新, 旧 = 臂表(A_新), 臂表(A_旧)
    报 = {"★预先登记": __doc__.strip()[:1200], "★★★门槛": 门槛,
         "★★★N": len(种子), "★★★N的硬限": "秩检验最好 p=1/(N+1)=0.0909 → 本份不报秩/分位数",
         "★分辨力pp年": 分辨力, "自证": {}, "格子": []}

    # ───────── 自证③ A原样 复现对账（★ 跨会话第五次）
    对账 = []
    for seg in 段:
        for fam in 族文件:
            a, b = 旧.get((seg, fam, "A原样")), 新.get((seg, fam, "A原样"))
            if not a or not b: 对账.append({"格": f"{seg}·{fam}", "★缺": True}); continue
            同 = all((a[k] == b[k]) if isinstance(a[k], int)
                     else abs(a[k] - b[k]) <= 1e-12 * max(1, abs(a[k]))
                     for k in ("笔数", "每笔净R", "每笔毛R", "净盈亏", "摩擦"))
            对账.append({"格": f"{seg}·{fam}", "笔数": a["笔数"], "★★★逐点相等": 同})
    报["自证"]["③A原样复现对账"] = {"明细": 对账,
        "★★★全部逐点相等": all(x.get("★★★逐点相等") for x in 对账),
        "★说明": "跨会话第五次独立对账（和 arms_1107/ 那六条比）"}

    # ───────── 自证② 结果级：每笔摩擦 R 比
    fr = lambda r: r["每笔毛R"] - r["每笔净R"]
    摩擦 = []
    for seg in 段:
        for fam in 族文件:
            A = 新.get((seg, fam, "A原样"))
            if not A: continue
            frA = fr(A)
            新比 = [fr(新[(seg, fam, f"R同档随机{s}")]) / frA
                   for s in 种子 if (seg, fam, f"R同档随机{s}") in 新]
            旧比 = [fr(旧[(seg, fam, f"R随机{s}")]) / fr(旧[(seg, fam, "A原样")])
                   for s in 种子 if (seg, fam, f"R随机{s}") in 旧]
            摩擦.append({"格": f"{seg}·{fam}",
                "A原样每笔摩擦R": round(frA, 6),
                "★★★新随机比_中位": round(st.median(新比), 3),
                "★★★新随机比_范围": [round(min(新比), 3), round(max(新比), 3)],
                "★★旧随机比_中位": round(st.median(旧比), 3) if 旧比 else None,
                "★★旧随机比_范围": [round(min(旧比), 3), round(max(旧比), 3)] if 旧比 else None,
                "★★★★★落进0.85~1.20": all(0.85 <= x <= 1.20 for x in 新比)})
    报["自证"]["②每笔摩擦贴上了吗"] = {"明细": 摩擦,
        "★★★★★六格全部落进带": all(x["★★★★★落进0.85~1.20"] for x in 摩擦),
        "★预先登记的带": "0.85~1.20（《118》3.5②，跑前写死）",
        "★落不进就作废": "是"}

    # ───────── 自证① 格子级（从各段报告里读覆盖层自证）
    格子自证 = []
    for f in sorted(glob.glob(os.path.join(HERE, "重测结果_*_1107.json"))):
        r = json.load(io.open(f, encoding="utf-8"))
        z = r.get("★★★随机同档自证") or {}
        for d in (z.get("明细") or []):
            格子自证.append({"段": os.path.basename(f), **{k: d[k] for k in d
                if "档位" in k or "比例" in k or "格子" in k or "分布" in k}})
    报["自证"]["①格子级"] = {"明细": 格子自证,
        "★说明": "第一段(B)跑在加这段落盘代码之前 → 它那份只在进程内；后面各段有"}

    # ───────── 主判据：配对检验（新 / 旧 并排，净 / 毛各一版）
    for seg in 段:
        for fam in 族文件:
            la = 标签(seg, fam, "A原样")
            格 = {"段": seg, "族": fam, "★★★问题": "ADV20 排序 vs 同档位内随机抽"}
            for 版, ds, 臂名 in (("新_同档随机", DS_新, "R同档随机"),
                               ("旧_全池随机", DS_旧, "R随机")):
                for 列, 口 in (("净值", "净"), ("毛净值", "毛")):
                    ts, 年化 = [], []
                    for s in 种子:
                        lb = 标签(seg, fam, f"{臂名}{s}")
                        ds_a = DS_新 if 版.startswith("新") else DS_旧
                        r = 配对(ds_a, la, ds, lb, 列)
                        if "★★★NW_t" in r:
                            ts.append(r["★★★NW_t"]); 年化.append(r["★年化差pp(对数)"])
                    if not ts: 格[f"{版}·{口}"] = {"★算不了": True}; continue
                    过 = sum(1 for t in ts if abs(t) > 门槛)
                    格[f"{版}·{口}"] = {
                        "★★★过门槛": f"{过}/{len(ts)}",
                        "★t中位": round(st.median(ts), 3),
                        "★t范围": [round(min(ts), 3), round(max(ts), 3)],
                        "★★年化差pp中位": round(st.median(年化), 2),
                        "★★年化差pp范围": [round(min(年化), 2), round(max(年化), 2)],
                        "★★★规矩58": ("测不出来（差小于分辨力 14.9pp/年）"
                                   if abs(st.median(年化)) < 分辨力[0] else "差大于分辨力下限，可谈"),
                    }
            报["格子"].append(格)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("★ 写完", OUT)
    return 报


if __name__ == "__main__":
    r = main()
    print("\n★★★ 自证③ A原样 全部逐点相等:", r["自证"]["③A原样复现对账"]["★★★全部逐点相等"])
    print("★★★ 自证② 六格全部落进 0.85~1.20:", r["自证"]["②每笔摩擦贴上了吗"]["★★★★★六格全部落进带"])
    print(f"\n{'段':<13}{'族':<7}{'版':<14}{'口':<3}{'过门槛':>7}{'t中位':>9}{'t范围':>20}{'年化差pp中位':>13}")
    for g in r["格子"]:
        for k, v in g.items():
            if "·" in k and isinstance(v, dict) and "★★★过门槛" in v:
                版, 口 = k.split("·")
                print(f"{g['段']:<13}{g['族']:<7}{版:<14}{口:<3}{v['★★★过门槛']:>7}"
                      f"{v['★t中位']:>9.3f}{str(v['★t范围']):>20}{v['★★年化差pp中位']:>13.2f}")
