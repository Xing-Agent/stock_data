# -*- coding: utf-8 -*-
"""
★ 《99》+《103》出表:arms_2009/*.json → 基本面重测结果_2009.json + 重测表_2009.md
★★★ 头一行就是「本次口径」(规矩㊼);每行带池子/窗口;失败大声列(规矩⑯);流水哈希去重(规矩⑪)。
★★★ 不写好坏 —— 结论行一律跑前写死那句。
★★ 和随机比用「净值年化(全收益)」+ 分位数;逐笔的数(每笔净R)是纯价格,只当事实列。
"""
import glob, hashlib, io, json, os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
口径行 = ("【本次口径】全收益 · 摩擦档 三档 5/15/30bp 单边 · 窗口 2009-01-01~2025-12-31 · "
         "池 并池2004(3858,一档) · 标签滞后 1 天")
结论行 = "窗口不够(2009~2025,不足一个完整估值周期)—— 本行只能当方向,不能当成绩。"


def 哈希(臂):
    p = os.path.join(HERE, "ledgers_2009修接缝", f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if d.empty:
        return "空流水"
    k = d[["symbol", "entry_date", "exit_date"]].astype(str).agg("|".join, axis=1)
    return hashlib.sha256("\n".join(sorted(k)).encode()).hexdigest()[:12]


def main():
    rows, fails, full = [], [], []
    for f in sorted(glob.glob(os.path.join(HERE, "arms_2009修接缝", "*.json"))):
        r = json.load(io.open(f, encoding="utf-8"))
        full.append({k: v for k, v in r.items() if k != "traceback"})
        if r.get("★本次口径") != 口径行:
            fails.append({"臂": r.get("臂"), "原因": "★★★ 口径行不对 —— 这条作废"}); continue
        if "★★★跑失败" in r:
            fails.append({"臂": r["臂"], "原因": r["★★★跑失败"]}); continue
        e = r.get("事实") or {}
        rd = (r.get("★随机先买谁·100次") or {}).get("★★★净值年化(全收益)") or {}
        策略, 点 = r["臂"].split("·", 1)
        yrs = e.get("进场年份") or {}
        rows.append({
            "策略": 策略, "点": 点, "档": r.get("档"),
            "笔数": e.get("笔数"), "第一笔进场年": min(map(int, yrs)) if yrs else None,
            "★净值年化%(全收益)": r.get("★★★净值年化pct(全收益,含分红)"),
            "随机2.5%": rd.get("2.5%"), "随机中位": rd.get("中位"), "随机97.5%": rd.get("97.5%"),
            "本臂在随机里的分位": rd.get("★★本臂排第几分位"),
            "落在随机带内?": ("★随机无区分(候选从没多过槽位,先买谁不影响)" if rd.get("2.5%") is not None
                         and rd.get("2.5%") == rd.get("97.5%") else None if rd.get("2.5%") is None or r.get("★★★净值年化pct(全收益,含分红)") is None
                         else rd["2.5%"] <= r["★★★净值年化pct(全收益,含分红)"] <= rd["97.5%"]),
            "每笔净R均值(纯价格)": e.get("每笔净R(均值)"), "每笔净R中位(纯价格)": e.get("每笔净R(中位)"),
            "净盈亏美元(纯价格)": e.get("净盈亏美元"), "摩擦美元": e.get("摩擦美元"),
            "持有交易日中位": (e.get("持有交易日") or {}).get("0.5"), "年换手率": e.get("年换手率(倍)"),
            "期末还拿着": e.get("★期末还拿着(引擎记成退市结算)"), "跨假跳变笔": e.get("★跨过疑似假跳变的笔"),
            "巨头笔数": e.get("巨头进过几笔(AAPL/MSFT/AMZN/JPM/BRK.B/AVGO/NVDA)"),
            "流水哈希": 哈希(r["臂"]), "池子": r.get("★★★池子"), "窗口": r.get("★★★窗口"), "结论行": 结论行,
        })
    df = pd.DataFrame(rows)
    dup = (df[df.duplicated("流水哈希", keep=False) & df["流水哈希"].notna()][["策略", "点", "流水哈希"]]
           .to_dict("records") if len(df) else [])
    带外 = df[df["落在随机带内?"] == False][["策略", "点", "★净值年化%(全收益)", "本臂在随机里的分位"]] \
        .to_dict("records") if len(df) else []
    out = {"★本次口径": 口径行, "★结论行(跑前写死)": 结论行, "★★★失败条数": len(fails), "失败明细": fails,
           "★重复版本(流水一样)": dup, "★落在随机带外的臂(只报事实)": 带外,
           "★多重检验提醒": f"{len(df)} 条臂 × 双侧 5% → 纯运气约 {round(len(df)*0.05,1)} 条会落在带外",
           "表": rows, "逐臂全文": full}
    io.open(os.path.join(HERE, "基本面重测结果_2009.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    if len(df):
        cols = ["策略", "点", "笔数", "第一笔进场年", "★净值年化%(全收益)", "随机2.5%", "随机中位", "随机97.5%",
                "本臂在随机里的分位", "落在随机带内?", "每笔净R中位(纯价格)", "摩擦美元", "持有交易日中位", "年换手率",
                "期末还拿着", "跨假跳变笔", "巨头笔数"]
        md = df[cols].to_markdown(index=False)
        io.open(os.path.join(HERE, "重测表_2009.md"), "w", encoding="utf-8").write(
            口径行 + "\n\n★ " + 结论行 + "\n\n" + md)
        print(md)
    print("\n★★★ 失败:", len(fails))
    for x in fails:
        print("   ✗", x["臂"], "——", str(x["原因"])[:160])
    print("重复:", dup); print("带外:", 带外)


if __name__ == "__main__":
    main()
