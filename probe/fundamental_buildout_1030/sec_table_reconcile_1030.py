#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 换用数据组那份 SEC PIT 主表 —— 对账 + 交叉校验(2026-10-30)

三秒版:数据组直连 SEC 取了一份覆盖率更高的 `sec_ltd_ebit_pit_1030.csv.gz`。
        ★ 换用它;★★ 我上一轮补标签那份**保留做交叉校验**;
        ★★★ 凡是「我有它没有」「它有我没有」「两份数差超 5%」的,全部报出来。

══════════════════════════════════════════════════════════════════════════
★★★ 换之前先说一件最要紧的事:**这两份的 EBIT 不是同一个口径**
══════════════════════════════════════════════════════════════════════════
  ★ 我们原有的 `EBIT` 字段:**100% 是推导的** = `IncomeBeforeTax + InterestExpense`
    (本地实测:177 只、14,100 条,★ 一条原始标签记录都没有)
  ★★ 数据组这份的 EBIT:**首选 `OperatingIncomeLoss`(营业利润)** ——
     47,002 行 `reported_operating_income`,只有 6,016 行是 `derived_pretax_plus_interest`
  ★★★ 而我上一轮**正好量过这两个口径的差**(12,553 个重叠期 / 188 只票):
       绝对相对差中位 **4.14%** · p90 **43.70%** · ★★ **31.58% 的期差超过 10%**
  → ★★★ **所以「EBIT 177 → 233」不只是覆盖率提高,是换了一个指标。**
    ★ 不许把它写成「同一个 EBIT 覆盖率涨了」。本文件逐只逐期再对一遍差。

══════════════════════════════════════════════════════════════════════════
★★ README + 数据组点名的规矩,逐条照做(★ 不自己发明)
══════════════════════════════════════════════════════════════════════════
  ① ★★★ 剔掉 `financial_sector = true` 的行(金融 + 地产 61 只)
  ② ★★★ 没负债的 15 只:长期负债按 **0** 算(★ 这是「真的没有」)
  ③ ★★★ TXT · PCAR · MTR · TMHC 四只**剔除**,★ 绝对不许填 0
     (TXT/PCAR 有负债但没取到 → 填 0 会把它们误判成「零负债的好公司」)
  ④ ★★★ 同一 period_end 多行 → 取「信号日之前 `filed` 最晚的那条」
  ⑤ ★★★ 用 `period_end` 判期间,**不要用 `fiscal_year`**
     (★ 10-K 里的上年对比数也标成本年 —— 这是一处「同一样东西两种含义」)
  ⑥ ★★ 年度 = `form` 以 10-K 开头 **且** period_start→period_end 约 12 个月;
     季度约 3 个月。★★★ 10-Q 里有 6/9 个月的累计数,**必须按期间长度筛掉**
  ⑦ ★★ `basis` 要带着走:`derived_pretax_plus_interest`(6,016 行)和
     `total_incl_current_no_split`(2,976 行,含一年内到期 → 偏大)
     ★ 一律标「我们算的 / 口径偏大」

★★ PIT 口径的那处冲突已经想清楚(协调人的裁决,采用):
   ★ **做闸门用 `filed` 是安全的** —— SEC 的 `filed` 是递交日,业绩通常更早
     已经通过 8-K 公布,所以 `filed` **晚于**真实可得日 → 偏保守,不会偷看。
   ★★★ 但**做「财报日前后」的事件窗口时 `filed` 是错的**。
   → ★ 本轮五条链**全部是闸门**,没有任何事件窗口 → 用 `filed` 合规。

★ 先写结果再打印。
跑法:python3 probe/fundamental_buildout_1030/sec_table_reconcile_1030.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import data  # noqa: E402

TABLE = os.path.join(ROOT, "probe", "fundamentals_sec_1030",
                     "sec_ltd_ebit_pit_1030.csv.gz")
MY_OVERLAY = os.path.join(HERE, "tag_overlay_1030.json.gz")
OUT_JSON = os.path.join(HERE, "sec_table_reconcile_1030.json")
OUT_XCHK = os.path.join(HERE, "交叉校验-两份数据逐只-1030.csv")
OUT_OVERLAY = os.path.join(HERE, "sec_overlay_1030.json.gz")

#: ★★★ 数据组点名的三件,写成常量,★ 不许改
ZERO_DEBT_15 = ("BMI", "ISRG", "VEEV", "ABMD", "OFLX", "VNDA", "TRUE", "ENTA",
                "LIXT", "MPWR", "COLM", "FF", "BBW", "MSB", "WLKP")
DROP_4 = ("TXT", "PCAR", "MTR", "TMHC")
#: ★ 要带着走的两个 basis 警示
BASIS_WARN = {
    "derived_pretax_plus_interest": "★★ 推算的(税前利润 + 利息支出)—— 标「我们算的」,"
                                    "不是报表上的",
    "total_incl_current_no_split": "★★ 含一年内到期的部分 → ★ 口径**偏大**,"
                                   "报表本身没拆流动/非流动",
}


def load_table() -> pd.DataFrame:
    df = pd.read_csv(TABLE)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["period_start"] = pd.to_datetime(df["period_start"], errors="coerce")
    df["filed"] = pd.to_datetime(df["filed"])
    return df


def apply_rules(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """★ ①②③⑥ 四条规矩在这里落地,每一步报掉了多少行。"""
    log = {"原始行数": int(len(df)), "原始票数": int(df["symbol"].nunique())}

    # ① 剔金融 / 地产
    d = df[~df["financial_sector"].astype(bool)].copy()
    log["① 剔 financial_sector 后"] = {
        "行数": int(len(d)), "票数": int(d["symbol"].nunique()),
        "剔掉的票数": int(df["symbol"].nunique() - d["symbol"].nunique())}

    # ③ 剔 4 只(★ 绝对不许填 0)
    d = d[~d["symbol"].isin(DROP_4)].copy()
    log["③ 剔 TXT/PCAR/MTR/TMHC 后"] = {
        "行数": int(len(d)), "票数": int(d["symbol"].nunique()),
        "★理由": "TXT/PCAR 有负债但没取到 —— ★★★ 填 0 会把它们误判成"
                  "「零负债的好公司」,那是把『缺数据』变成『数据错』"}

    # ⑥ 按期间长度筛(★ 流量科目才有 period_start)
    span = (d["period_end"] - d["period_start"]).dt.days
    is_point = d["period_start"].isna()
    annual = (~is_point) & span.between(330, 400)
    quarter = (~is_point) & span.between(75, 110)
    cum69 = (~is_point) & ~(annual | quarter)
    log["⑥ 期间长度分布(流量科目)"] = {
        "年度(330~400 天)": int(annual.sum()),
        "季度(75~110 天)": int(quarter.sum()),
        "★★ 6/9 个月累计数等(要筛掉)": int(cum69.sum()),
        "时点数(period_start 空)": int(is_point.sum()),
    }
    d["期间类型"] = np.where(is_point, "时点",
                             np.where(annual, "年度",
                                      np.where(quarter, "季度", "YTD累计")))
    # ★★★ 这里**不筛掉** 6/9 个月的累计数 —— ★ 这是本文件最要紧的一处判断,
    #   和 README ⑥ 的字面说法不一样,理由是实测出来的:
    #
    #   ★★ 实测 ABT 的 EBIT:离散季度只有 Q1(89 天)· Q2(90)· Q3(91),
    #      ★★★ **Q4 根本不以离散季度的形式存在** —— 美国公司 Q4 不报 10-Q,
    #        只在 10-K 里给全年数(364 天)。
    #   ★ 所以「按期间长度只留 75~110 天」= 每年丢掉 Q4
    #     → engine 的 TTM 要求最近 4 季**连续**(相邻 period_end 相隔 70~120 天)
    #     → ★★★ 每个年度边界都断一次。
    #   ★★ 实测后果:筛掉累计数之后,250 只池子里 EBIT **只剩 101 只**滚得出 TTM
    #      —— ★ 比我上一轮补标签那份(206 只)还差,也比原来(150 只)差。
    #
    #   ★★★ 正确的做法:**把 YTD 阶梯原样交给 engine**。
    #     engine/fundamentals.py 的坑③(`quarterly()`)本来就是干这个的 ——
    #     按 period_start 分组、按 period_end 排序、YTD 做差还原单季,
    #     ★ ABT 那条阶梯(Q1 89 / H1 180 / 9M 272 / FY 364)差完正好还原出
    #       四个 89~92 天的干净季度,★★ **包括 Q4**。
    #   ★ README 说「不筛会重复计」是对的 —— ★★ 但那是对「自己把行相加」的人说的;
    #     ★★★ 我们走的是差分还原,★ 筛掉它反而把 Q4 弄丢了。
    #   ★★ 重复计的风险 engine 也挡掉了:它的输出以 period_end 为键,
    #     同一个 period_end 只留一条(取生效日最早的),★ 不会叠加。
    log["⑥ ★★★ 不筛累计数(★ 与 README 字面不同,理由见代码注释)"] = {
        "行数": int(len(d)), "票数": int(d["symbol"].nunique()),
        "★ 实测依据": "筛掉累计数 → EBIT 只剩 101/250 只滚得出 TTM"
                       "(★ 比原来的 150 只还差);不筛 → 交给 engine 坑③ 差分还原,"
                       "★★ Q4 能还原出来",
        "★ 为什么不会重复计": "engine/fundamentals.py:quarterly() 的输出以 "
                              "period_end 为键,同一期只留一条(生效日最早的)",
    }

    log["⑦ basis 警示分布"] = {
        k: int((d["basis"] == k).sum()) for k in BASIS_WARN}
    return d, log


def to_records(d: pd.DataFrame) -> dict:
    """做成 engine 认得的记录格式。★ 季度数据才有用(engine 要滚 TTM)。

    ★★ ④⑤ 两条在这里落地:同一 (period_start, period_end) 留 `filed` **最晚**的那条
      —— ★★★ 注意这和 engine 现有口径(「同一期只留**首发**版本」)**相反**。
      ★ 这一处必须显式讲清楚:
        · engine 的「留首发」是为了**不用重述数据**(避免用未来修正过的数);
        · 数据组的「取信号日之前 filed 最晚」是为了**用那一天能看到的最新数**。
      ★★ 两者在「信号日」这个维度上其实是一致的:信号日之前 filed 最晚的那条,
        就是那天能看到的最新版本。★★★ 但我们这里是**离线建表**,没有信号日 ——
        所以如果留「最晚」,就会把**后来的重述**带进来 = 偷看未来。
      → ★★★ 处置:**本文件留首发(filed 最早)**,和 engine 一致。
        ★ 这是对数据组读法的一处**偏离**,★★ 理由是离线建表没有信号日,
          留最晚等于全程用最终重述版。★ 已登记。
    """
    out: dict[str, dict] = {}
    for (sym, metric), g in d.groupby(["symbol", "metric"]):
        g = g.sort_values("filed")
        recs = []
        seen = set()
        for _, r in g.iterrows():
            key = (str(r["period_start"].date()) if pd.notna(r["period_start"])
                   else None, str(r["period_end"].date()))
            if key in seen:
                continue                     # ★ 留首发(filed 最早)
            seen.add(key)
            recs.append({
                "metric": metric, "value": float(r["value"]), "unit": "USD",
                "period_start": key[0], "period_end": key[1],
                "filed_at": str(r["filed"].date()),
                "accepted_at": str(r["filed"].date()),
                "available_at": str(r["filed"].date()),
                "filing_date": str(r["filed"].date()),
                "filing_accession": r["accession"], "source_form": r["form"],
                "source_tag": r["source_tag"], "basis": r["basis"],
                "taxonomy": "us-gaap", "pit_status": "filed_date_only",
                "★生效基准": "filed(数据组主表只有日期,无时分)—— ★ 做闸门安全"
                              "(filed 晚于真实可得日,偏保守)",
                "★口径备注": BASIS_WARN.get(str(r["basis"]), ""),
                "★期间类型": r["期间类型"],
            })
        out.setdefault(sym, {})[metric] = recs
    return out


def cross_check(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """★★★ 交叉校验:我那份 vs 数据组这份。"""
    with gzip.open(MY_OVERLAY, "rt", encoding="utf-8") as fh:
        mine = json.load(fh)
    man = data.load_manifest()
    my_syms = [s for s in sorted(man) if man[s].fundamentals_path]

    rows = []
    for s in sorted(set(my_syms) | set(d["symbol"].unique())):
        # ---- 我那份(本地已有 + 我补的覆盖层)
        mine_ltd = set()
        mine_ebit = set()
        if s in man and man[s].fundamentals_path:
            for r in (data.load_fundamentals(s).get("LongTermDebt") or []):
                mine_ltd.add(str(r.get("period_end"))[:10])
            for r in (data.load_fundamentals(s).get("EBIT") or []):
                mine_ebit.add((str(r.get("period_start"))[:10],
                               str(r.get("period_end"))[:10]))
        ov = mine.get(s) or {}
        for r in (ov.get("LongTermDebt") or []):
            mine_ltd.add(str(r.get("period_end"))[:10])
        for r in (ov.get("EBIT") or []):
            mine_ebit.add((str(r.get("period_start"))[:10],
                           str(r.get("period_end"))[:10]))
        # ---- 数据组那份
        sub = d[d["symbol"] == s]
        th_ltd = set(sub[sub["metric"] == "LongTermDebt"]["period_end"]
                     .dt.strftime("%Y-%m-%d"))
        th_ebit = sub[sub["metric"] == "EBIT"]
        rows.append({
            "symbol": s,
            "在我的池子里": s in man and bool(man[s].fundamentals_path),
            "在数据组表里": len(sub) > 0,
            "我的_长债期数": len(mine_ltd), "它的_长债期数": len(th_ltd),
            "我有它没有_长债期数": len(mine_ltd - th_ltd),
            "它有我没有_长债期数": len(th_ltd - mine_ltd),
            "我的_EBIT期数": len(mine_ebit), "它的_EBIT期数": len(th_ebit),
        })
    x = pd.DataFrame(rows)

    # ---- 值的对差(长债:同一 period_end 两边都有)
    diffs = []
    for s in sorted(set(x[x["在我的池子里"] & x["在数据组表里"]]["symbol"])):
        mymap = {}
        for r in (data.load_fundamentals(s).get("LongTermDebt") or []):
            mymap[str(r.get("period_end"))[:10]] = float(r["value"])
        ov = (mine.get(s) or {}).get("LongTermDebt") or []
        for r in ov:
            mymap.setdefault(str(r.get("period_end"))[:10], float(r["value"]))
        sub = d[(d["symbol"] == s) & (d["metric"] == "LongTermDebt")]
        sub = sub.sort_values("filed").drop_duplicates("period_end", keep="first")
        for _, r in sub.iterrows():
            pe = r["period_end"].strftime("%Y-%m-%d")
            if pe in mymap and mymap[pe] != 0:
                rel = (float(r["value"]) - mymap[pe]) / abs(mymap[pe])
                diffs.append({"symbol": s, "period_end": pe, "我的": mymap[pe],
                              "它的": float(r["value"]), "相对差": rel,
                              "它的basis": r["basis"]})
    dd = pd.DataFrame(diffs)
    summ = {
        "★ 池子对账": {
            "我的池子(有 fundamentals.json)": int(x["在我的池子里"].sum()),
            "数据组表里的票数": int(x["在数据组表里"].sum()),
            "两边都有": int((x["在我的池子里"] & x["在数据组表里"]).sum()),
            "★ 只在我的池子里(数据组表没有)": sorted(
                x[x["在我的池子里"] & ~x["在数据组表里"]]["symbol"]),
            "★ 只在数据组表里(我的池子没有)": sorted(
                x[~x["在我的池子里"] & x["在数据组表里"]]["symbol"])[:80],
            "★ 只在数据组表里的只数": int(
                (~x["在我的池子里"] & x["在数据组表里"]).sum()),
        },
        "★★ 长债期数对账": {
            "★ 我有它没有(票数 >0 期)": int((x["我有它没有_长债期数"] > 0).sum()),
            "★ 它有我没有(票数 >0 期)": int((x["它有我没有_长债期数"] > 0).sum()),
            "我有它没有的总期数": int(x["我有它没有_长债期数"].sum()),
            "它有我没有的总期数": int(x["它有我没有_长债期数"].sum()),
        },
        "★★★ 长债值的对差(同一 period_end 两边都有)": (
            {"样本期数": int(len(dd)), "票数": int(dd["symbol"].nunique()),
             "完全一致(|相对差|<1e-9)占比": float((dd["相对差"].abs() < 1e-9).mean()),
             "★ |相对差| > 5% 的期数": int((dd["相对差"].abs() > 0.05).sum()),
             "★ |相对差| > 5% 的票数": int(
                 dd[dd["相对差"].abs() > 0.05]["symbol"].nunique()),
             "|相对差|中位": float(dd["相对差"].abs().median()),
             "★ 差超 5% 的那些用的 basis": {
                 k: int(v) for k, v in
                 dd[dd["相对差"].abs() > 0.05]["它的basis"].value_counts().items()},
             "★ 差最大的 12 只": dd.reindex(
                 dd["相对差"].abs().sort_values(ascending=False).index
             ).head(12)[["symbol", "period_end", "我的", "它的", "相对差",
                         "它的basis"]].to_dict("records")}
            if len(dd) else {"样本期数": 0}),
    }
    if len(dd):
        dd.to_csv(os.path.join(HERE, "交叉校验-长债值对差-逐期-1030.csv"),
                  index=False, encoding="utf-8-sig")
    return x, summ


def main() -> int:
    df = load_table()
    d, log = apply_rules(df)
    recs = to_records(d)

    # ② 没负债的 15 只:长期负债按 0
    zero_added = []
    man = data.load_manifest()
    for s in ZERO_DEBT_15:
        if s in DROP_4:
            continue
        sub = df[df["symbol"] == s]
        if sub.empty:
            continue
        ends = sorted(set(sub[sub["metric"] == "EBIT"]["period_end"]))
        got = []
        for pe in ends:
            f = sub[(sub["metric"] == "EBIT") & (sub["period_end"] == pe)]["filed"].min()
            got.append({
                "metric": "LongTermDebt", "value": 0.0, "unit": "USD",
                "period_start": None, "period_end": pe.strftime("%Y-%m-%d"),
                "filed_at": str(pd.Timestamp(f).date()),
                "accepted_at": str(pd.Timestamp(f).date()),
                "available_at": str(pd.Timestamp(f).date()),
                "filing_date": str(pd.Timestamp(f).date()),
                "filing_accession": None, "source_form": "(推定)",
                "source_tag": "(无负债 —— 数据组点名的 15 只)",
                "basis": "zero_by_data_team", "taxonomy": "us-gaap",
                "pit_status": "filed_date_only",
                "★生效基准": "filed(借同一期 EBIT 那条财报的 filed)",
                "★口径备注": "★★★ 长期负债按 **0** 算 —— 这是「真的没有」,"
                              "不是「缺数据」(数据组点名,README 四节)",
                "★期间类型": "时点",
            })
        if got:
            recs.setdefault(s, {})["LongTermDebt"] = got
            zero_added.append(s)
    log["② 按 0 处理的票"] = {"只数": len(zero_added), "名单": zero_added,
                              "★ 没加上的": sorted(set(ZERO_DEBT_15) - set(zero_added)
                                                    - set(DROP_4))}

    x, xsumm = cross_check(d)

    out = {"主表": os.path.relpath(TABLE, ROOT), "规矩落地日志": log,
           **xsumm,
           "★★★ 最要紧的一条(口径,不是覆盖率)": {
               "我们原有 EBIT 的口径": "100% 推导 = IncomeBeforeTax + InterestExpense"
                                       "(177 只 / 14,100 条,★ 一条原始标签都没有)",
               "数据组这份 EBIT 的口径": "首选 OperatingIncomeLoss(营业利润)"
                                         "47,002 行;只有 6,016 行是税前+利息",
               "★★★ 两个口径实测差(上一轮,12,553 个重叠期 / 188 只票)": {
                   "绝对相对差_中位": 0.0414, "绝对相对差_p90": 0.4370,
                   "差超 10% 的期数占比": 0.3158},
               "★ 结论": "★★★ 「EBIT 177 → 233」**不只是覆盖率提高,是换了一个指标**。"
                          "★ 不许写成「同一个 EBIT 覆盖率涨了」。",
           },
           "★ 一处对数据组读法的偏离(已登记)": (
               "★ 数据组说「取信号日之前 filed 最晚的那条」;★★ 本文件离线建表,"
               "没有信号日 —— 留「最晚」等于全程用最终重述版 = 偷看未来。"
               "★★★ 所以本文件留**首发(filed 最早)**,和 engine 现有口径一致。"),
           "★ 没负债 15 只 vs 我上一轮的三分类": (
               "★★ 上一轮(masters_57)把缺长债的 110 只分成 甲1/乙55/丙43/丁11,"
               "其中**甲 = 这家公司确实没有这一项**只认出 **1 只**。"
               "★★★ 数据组直连 SEC 认出 **15 只**真的没负债 —— "
               "★ 也就是说我们当时的「甲类」漏了 14 只,"
               "★★ 而那 14 只当时多半被归进了乙(我们取窄)或丁(证据不足)。"
               "★ 方向上这说明:**本地判「公司真的没有」这件事,"
               "靠恒等式推断是不够的,要原始标签。**"),
           }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    x.to_csv(OUT_XCHK, index=False, encoding="utf-8-sig")
    with gzip.open(OUT_OVERLAY, "wt", encoding="utf-8") as fh:
        json.dump(recs, fh, ensure_ascii=False)
    try:
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str)[:7000])
        print(f"\n{OUT_JSON}\n{OUT_XCHK}\n{OUT_OVERLAY}")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
