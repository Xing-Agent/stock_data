# -*- coding: utf-8 -*-
"""
★ A 路出表:读 arms/*.json → 一张总表 + 三点同向 + 多重检验自查 + 失败大声报。
★★★ 规矩⑯:跑失败的臂**单独列出来**,不许打空表。
★★★ 规矩⑪:按**流水内容哈希**去重(名字不同、流水一样的只算一个版本)。
★★ 规矩⑫:表里每列写明是均值还是中位数。
"""
import glob, hashlib, io, json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
END = "2025-12-31"


def 哈希(臂):
    p = os.path.join(HERE, "ledgers", f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if d.empty:
        return "空流水"
    k = d[["symbol", "entry_date", "exit_date"]].astype(str).agg("|".join, axis=1)
    return hashlib.sha256("\n".join(sorted(k)).encode()).hexdigest()[:12]


def 期末持仓(臂):
    """★★ 引擎把「回测结束时还拿着的」记成「退市结算」(chain.py:642 末根判定),
       ★ 这里按 exit_date == 最后一天 把它们分出来。"""
    p = os.path.join(HERE, "ledgers", f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None, None
    d = pd.read_csv(p)
    if d.empty:
        return 0, 0
    tail = (d["reason"] == "退市结算") & (d["exit_date"].astype(str) == END)
    real = (d["reason"] == "退市结算") & (d["exit_date"].astype(str) != END)
    return int(tail.sum()), int(real.sum())


def 尾巴(臂):
    """★★ 均值会被少数几笔拉高 —— 同时给中位数、去掉最高 1% 的均值、涨 10 倍以上的笔数
       (★★★ 涨 10 倍以上的要逐笔核拆股:VRDN 2020 那笔 0.756 → 20.79 很可能是没修的反向拆股)。"""
    p = os.path.join(HERE, "ledgers", f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None, None, None
    d = pd.read_csv(p)
    if d.empty:
        return None, None, None
    r = d["net_pnl"] / d["notional_in"] * 100
    return (round(float(r.median()), 2), round(float(r[r <= r.quantile(.99)].mean()), 2),
            int((d["exit_price"] / d["entry_price"] >= 10).sum()))


def main():
    rows, fails = [], []
    for f in sorted(glob.glob(os.path.join(HERE, "arms", "*.json"))):
        r = json.load(io.open(f, encoding="utf-8"))
        if "★★★跑失败" in r:
            fails.append((r["臂"], r["★★★跑失败"]))
            continue
        bm = r.get("★★★大盘替身(主判据)") or {}
        c = (r.get("尺子C(只量进场)") or {}).get("第20日") or {}
        acc = r.get("账户百分比(给用户看)") or {}
        tail, real = 期末持仓(r["臂"])
        策略, 点 = r["臂"].split("·", 1)
        中位, 去尾, 十倍 = 尾巴(r["臂"])
        rows.append({
            "策略": 策略, "点": 点, "档": r.get("档"),
            "笔数": r.get("笔数"), "不同股票": r.get("不同股票数"),
            "比同期大盘_差pct(均值)": bm.get("★★★④差(真 减 替身)pct"),
            "t": bm.get("t值"), "判定": bm.get("★★★判定") or bm.get("★算不出") or bm.get("★跑失败"),
            "进场后20日超额pct(均值)": c.get("平均超额pct"), "20日t": c.get("t值"),
            "每笔中位pct": 中位, "去掉最高1%后均值pct": 去尾, "涨10倍以上笔数(要核拆股)": 十倍,
            "利润因子": acc.get("⑤利润因子_按净值pct"), "胜率": acc.get("②胜率"),
            "持有交易日(中位)": r.get("持有交易日_中位"),
            "期末还拿着(被记成退市结算)": tail, "真退市": real,
            "流水哈希": 哈希(r["臂"]),
        })
    df = pd.DataFrame(rows)
    out = {"失败": fails, "表": rows}
    if len(df):
        # ★ 三点同向:同一策略三个点的「比大盘差」符号是否一致
        同向 = {}
        for s, g in df.groupby("策略"):
            v = g["比同期大盘_差pct(均值)"].dropna()
            同向[s] = ("三点同向·正" if len(v) == 3 and (v > 0).all() else
                     "三点同向·负" if len(v) == 3 and (v < 0).all() else
                     f"不同向或不足三点({len(v)})")
        df["三点同向"] = df["策略"].map(同向)
        dup = df[df.duplicated("流水哈希", keep=False) & df["流水哈希"].notna()]
        out["★重复版本(流水一样)"] = dup[["策略", "点", "流水哈希"]].to_dict("records")
        tt = df["t"].dropna()
        out["★多重检验"] = {"检验个数": int(len(tt)),
                         "运气约给几个|t|>2": round(0.05 * len(tt), 1),
                         "实际正显著": int((tt > 2).sum()), "实际负显著": int((tt < -2).sum())}
        out["三点同向"] = 同向
    io.open(os.path.join(HERE, "成绩_1106.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    if len(df):
        cols = ["策略", "点", "档", "笔数", "比同期大盘_差pct(均值)", "t", "进场后20日超额pct(均值)",
                "20日t", "每笔中位pct", "去掉最高1%后均值pct", "涨10倍以上笔数(要核拆股)", "利润因子", "胜率", "持有交易日(中位)", "期末还拿着(被记成退市结算)", "三点同向"]
        md = df[cols].to_markdown(index=False)
        io.open(os.path.join(HERE, "成绩表_1106.md"), "w", encoding="utf-8").write(md)
        print(md)
    print("\n★★★ 失败:", len(fails))
    for a, b in fails:
        print("   ✗", a, "——", b[:200])
    print(json.dumps({k: out[k] for k in ("★多重检验", "★重复版本(流水一样)") if k in out},
                     ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
