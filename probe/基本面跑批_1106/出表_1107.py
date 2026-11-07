# -*- coding: utf-8 -*-
"""
★ 《99》出表:arms_1107/*.json → 基本面重测结果_1107.json + 重测表_1107.md
★★★ 每一行都带「池子 / 窗口」两个字段;失败的臂单独大声列(规矩⑯);流水哈希去重(规矩⑪)。
★★★ 不写「好 / 不好」—— 结论行一律是《99》3.3 那句。
"""
import glob, hashlib, io, json, os
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
结论行 = "窗口不够(2016~2025,不足一个完整估值周期)—— 本行只能当方向,不能当成绩。"


def 哈希(臂):
    p = os.path.join(HERE, "ledgers_1107", f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None
    d = pd.read_csv(p)
    if d.empty:
        return "空流水"
    k = d[["symbol", "entry_date", "exit_date"]].astype(str).agg("|".join, axis=1)
    return hashlib.sha256("\n".join(sorted(k)).encode()).hexdigest()[:12]


def main():
    rows, fails, full = [], [], []
    for f in sorted(glob.glob(os.path.join(HERE, "arms_1107", "*.json"))):
        r = json.load(io.open(f, encoding="utf-8"))
        full.append(r)
        if "★★★跑失败" in r:
            fails.append({"臂": r["臂"], "原因": r["★★★跑失败"]}); continue
        e, rnd = r.get("事实") or {}, r.get("★随机先买谁·10种子") or {}
        策略, 点 = r["臂"].split("·", 1)
        rows.append({
            "池子": r.get("★★★池子"), "窗口": r.get("★★★窗口"), "策略": 策略, "点": 点, "档": r.get("档"),
            "笔数": e.get("笔数"), "不同股票": e.get("不同股票数"),
            "每笔净R(均值)": e.get("每笔净R(均值)"), "每笔净R(中位)": e.get("每笔净R(中位)"),
            "净盈亏美元": e.get("净盈亏美元"), "摩擦美元": e.get("摩擦美元"),
            "持有交易日(中位)": (e.get("持有交易日") or {}).get("0.5"),
            "年换手率(倍)": e.get("年换手率(倍)"),
            "期末还拿着": e.get("★期末还拿着(引擎记成退市结算)"),
            "跨过假跳变的笔": e.get("★跨过疑似假跳变的笔"),
            "剔假跳变后每笔净R": e.get("★剔掉这些笔后每笔净R(均值)"),
            "巨头笔数": e.get("巨头进过几笔(AAPL/MSFT/AMZN/JPM/BRK.B/AVGO/NVDA)"),
            "资金年化pct": e.get("★资金年化pct(扣摩擦)"),
            "随机·资金年化均值": rnd.get("★★资金年化pct·均值"), "随机·标准差": rnd.get("★★资金年化pct·标准差"),
            "本臂减随机": rnd.get("★★★本臂减随机(资金年化)"),
            "差距在一个标准差内?": (None if rnd.get("★★资金年化pct·标准差") in (None, 0)
                           or rnd.get("★★★本臂减随机(资金年化)") is None
                           else abs(rnd["★★★本臂减随机(资金年化)"]) <= rnd["★★资金年化pct·标准差"]),
            "流水哈希": 哈希(r["臂"]), "结论行": 结论行,
        })
    df = pd.DataFrame(rows)
    dup = (df[df.duplicated("流水哈希", keep=False) & df["流水哈希"].notna()][["策略", "点", "流水哈希"]]
           .to_dict("records") if len(df) else [])
    out = {"★★★池子": "并池3834", "★★★窗口": "2016-01-04~2025-12-31", "★结论行(跑前写死)": 结论行,
           "★★★失败条数": len(fails), "失败明细": fails, "★重复版本(流水一样)": dup,
           "表": rows, "逐臂全文": full}
    io.open(os.path.join(HERE, "基本面重测结果_1107.json"), "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    if len(df):
        cols = ["策略", "点", "笔数", "每笔净R(均值)", "每笔净R(中位)", "净盈亏美元", "摩擦美元",
                "持有交易日(中位)", "年换手率(倍)", "期末还拿着", "跨过假跳变的笔", "巨头笔数",
                "资金年化pct", "随机·资金年化均值", "随机·标准差", "本臂减随机", "差距在一个标准差内?"]
        md = df[cols].to_markdown(index=False)
        io.open(os.path.join(HERE, "重测表_1107.md"), "w", encoding="utf-8").write(
            "★★★ 池子:并池3834 · 窗口:2016-01-04~2025-12-31 · " + 结论行 + "\n\n" + md)
        print(md)
    print("\n★★★ 失败:", len(fails))
    for x in fails:
        print("   ✗", x["臂"], "——", x["原因"][:200])
    print("重复版本:", dup)


if __name__ == "__main__":
    main()
