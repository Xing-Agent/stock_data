# -*- coding: utf-8 -*-
"""
★★★★★ 扫全池「**没调整的拆股/并股**」—— ★ 这一轮是**查我们自己变好看的那个结果**查出来的。

★★ 起因:基本面 33 条臂按新尺子量完,★★★ 只有 基-7 烟蒂那一族正显著(alpha t 2.16/2.00/1.98)。
   ★ 规矩④「凡是让我们数字变好看的结果，先当自己错了」→ 逐笔拆开看:
   ★★★ **一笔 QCLS 占 基-7·五毛 总盈亏的 44.5%**(+2430%,持有 8 天)。
   ★★ 查那只的面板(2024-02-15):
       收盘 0.1333 → **3.27**(×24.5)· **股数成交量 174 万 → 20 万(÷8.7,之后继续掉到 2 万)**
       · **成交额几乎不变**(约 23 万 → 65 万 → 回到 10~45 万)
   → ★★★ 真涨 24 倍会**放量**,★ 不会缩量到 1/35。★★ 开盘/最高/最低/收盘**同一天整块 ×24**
     → ★★★ 这是**并股(反向拆股)没有被调整**,不是行情。

★★★★★ 判据（★ 1107 **第二版** —— ★★ 第一版漏掉了 QCLS 本人，见下）：
   ① ★★★ **窗口中位数**的收盘跳变 ≥ `跳变门槛`（★ 后 5 日中位 ÷ 前 5 日中位）
      —— ★★ 用窗口中位数而不是单日比值：单日量价都太吵
   ② ★★★ **股数成交量朝反方向动**（价涨量缩 / 价跌量增）
      —— ★ 这是**最硬的一条**：真的涨 3 倍（收购、临床数据）**一定放量**，
        ★★★ 不可能一边涨 3 倍一边缩量。

★★★★★ 为什么第一版漏了 QCLS（★ 规矩⑥ 的活例子，必须记下来）：
   ★ 第一版还加了第三条：「**成交额基本不变**（比值在 [0.4, 2.5] 内）」——
     ★★ 理由是「拆股只换计价单位，成交额不该变」。听起来很对。
   ★★★ 但 QCLS 那天的成交额比是 **2.81** → **落在带外** → 被我自己的筛子漏掉。
   → ★ 也就是说:★★★ **我为了查一个案子写的判据，把那个案子本人筛掉了。**
   ★★ 规矩⑥ 原文:「任何预先登记的判据，必须写明**分辨力**，并问
     『假如真出了问题，这个判据会不会照样显示「过」？』」—— ★★★ 这次就是照样显示「过」。
   → ★ 处置:**成交额比降为「报出来的信息」，不当闸**。
"""
from __future__ import annotations
import glob, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "假跳变_报告_1107.json")

跳变门槛 = 3.0        # ★★ ③档我们的:3 倍以上的跳变在日线上**几乎不可能**是真行情
量反向容差 = 1.5      # ★ 股数量要朝反方向动至少 1.5 倍
窗 = 5                # ★★ 前后各 5 个交易日取中位数（★ 单日量价太吵）
# ★★★ 成交额比**不再当闸**（第一版当闸，结果把 QCLS 本人筛掉了）—— 只报出来


def main() -> int:
    w = pd.read_parquet(PANEL)
    cl, vol, dv = w["close"], w["volume"], w["dollar_volume"]
    del w
    print(f"★ 面板 {cl.shape[1]} 只 × {cl.shape[0]} 天", flush=True)

    # ★★ 前 窗 日中位（不含当日）/ 后 窗 日中位（含当日）
    def 前(x):
        return x.shift(1).rolling(窗, min_periods=窗).median()

    def 后(x):
        return x.iloc[::-1].rolling(窗, min_periods=窗).median().iloc[::-1]

    pr = 后(cl) / 前(cl)
    vr = 后(vol) / 前(vol)
    dr = 后(dv) / 前(dv)          # ★★★ 只报，不当闸

    涨跳 = (pr >= 跳变门槛) & (vr <= 1 / 量反向容差)
    跌跳 = (pr <= 1 / 跳变门槛) & (vr >= 量反向容差)
    疑 = (涨跳 | 跌跳).fillna(False)

    行 = []
    idx = np.where(疑.to_numpy())
    for i, j in zip(*idx):
        行.append({"symbol": str(cl.columns[j]), "date": str(cl.index[i].date()),
                   "价比": round(float(pr.iat[i, j]), 3),
                   "股数量比": round(float(vr.iat[i, j]), 3),
                   "成交额比": round(float(dr.iat[i, j]), 3),
                   "方向": "并股(价涨量缩)" if pr.iat[i, j] >= 跳变门槛 else "拆股(价跌量增)"})
    df = pd.DataFrame(行)
    # ★★ 去重:同一只里**相邻 窗*2 天内**的多条只留一条(★ 一次并股会连着报好几天)
    if len(df):
        df["_d"] = pd.to_datetime(df["date"])
        df["_dev"] = (df["价比"] - 1.0).abs()
        df = df.sort_values(["symbol", "_d"]).reset_index(drop=True)
        keep, 上只, 上日 = [], None, None
        for i, r in df.iterrows():
            if r["symbol"] != 上只 or (r["_d"] - 上日).days > 窗 * 3:
                keep.append(i); 上只, 上日 = r["symbol"], r["_d"]
            else:
                if r["_dev"] > df.loc[keep[-1], "_dev"]:
                    keep[-1] = i
                上日 = r["_d"]
        df = df.loc[keep].drop(columns=["_d", "_dev"]).reset_index(drop=True)
    报 = {"★口径": {
        "判据": f"① 后{窗}日收盘中位 ÷ 前{窗}日中位 ≥ {跳变门槛}（或 ≤ 1/{跳变门槛}）"
              f" ② 股数成交量朝**反方向** ≥ {量反向容差} 倍",
        "★★★为什么②是最硬的一条": "★ 真的涨 3 倍一定**放量** —— ★★★ 不可能一边涨 3 倍一边缩量",
        "★★★成交额比": "**只报，不当闸** —— ★ 第一版拿它当闸（[0.4,2.5]），"
                   "★★★ 结果 QCLS 那天成交额比 2.81 落在带外，**把要查的案子本人筛掉了**（规矩⑥）",
        "档位": "★ ③我们的 —— 三个阈值原著没给（★★ 这是数据质量检查，不是策略参数）",
        "面板": PANEL,
        "★★宁可漏报": "★ 三条同时满足才算 —— 漏掉一些真拆股，但不会把真行情误判成拆股",
    }, "★疑似假跳变条数": len(df),
        "★涉及只数": int(df["symbol"].nunique()) if len(df) else 0,
        "★面板总只数": int(cl.shape[1])}
    if len(df):
        报["★按方向"] = df["方向"].value_counts().to_dict()
        报["★按年"] = df.assign(年=df["date"].str[:4])["年"].value_counts().sort_index().to_dict()
        报["最大20条"] = df.reindex(df["价比"].abs().sort_values(ascending=False).index).head(20).to_dict("records")
        报["全部只数名单"] = sorted(df["symbol"].unique().tolist())

    # ★★★ 这些票污染了哪些臂的哪些笔(★ 33 条基本面臂 + 测仓位 5 条)
    脏票 = set(df["symbol"]) if len(df) else set()
    脏日 = set(zip(df["symbol"], df["date"])) if len(df) else set()
    污 = {}
    for f in sorted(glob.glob("probe/基本面跑批_1106/ledgers/REAL__*.csv")
                    + glob.glob("probe/测仓位_1107/ledgers_1107/REAL__*.csv")):
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        if not len(d) or "symbol" not in d.columns:
            continue
        d["pct"] = d["net_pnl"] / d["notional_in"] * 100
        tot = d["net_pnl"].sum()
        # ★ 「跨过假跳变日」= 这笔持有区间里包含该票的假跳变日
        跨 = []
        for _, r in d.iterrows():
            if r["symbol"] not in 脏票:
                continue
            # ★★★ 容差 ±窗*2 个日历周:★ 窗口中位数判据会把标记日**推后几天**
            #   (★★ QCLS 那只的并股发生在 2024-02-15,判据标在 **2024-02-20** ——
            #    ★★★ 第一版没加容差,于是**漏掉了这一笔**,而它占该臂总盈亏 44.5%)
            a = (pd.Timestamp(str(r["entry_date"])[:10]) - pd.Timedelta(days=窗 * 3))
            b = (pd.Timestamp(str(r["exit_date"])[:10]) + pd.Timedelta(days=窗 * 3))
            if any(sy == r["symbol"] and a <= pd.Timestamp(dt) <= b for sy, dt in 脏日):
                跨.append(r)
        if not 跨:
            continue
        g = pd.DataFrame(跨)
        污[名] = {"总笔数": int(len(d)),
                 "★★★跨过假跳变的笔数": int(len(g)),
                 "★★★这些笔占总盈亏pct": (round(float(g["net_pnl"].sum() / tot * 100), 1)
                                   if tot else None),
                 "这些笔的净盈亏": round(float(g["net_pnl"].sum()), 0),
                 "总净盈亏": round(float(tot), 0),
                 "明细": g[["symbol", "entry_date", "exit_date", "pct",
                          "holding_days"]].round(1).to_dict("records")[:8]}
    报["★★★被污染的臂"] = 污
    报["★★★被污染的臂条数"] = len(污)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 疑似假跳变 {len(df)} 条 · 涉及 {报['★涉及只数']} 只 / {cl.shape[1]} 只")
    print(f"★★★ 被污染的臂 {len(污)} 条")
    for k, v in sorted(污.items(), key=lambda x: -(x[1]['★★★这些笔占总盈亏pct'] or 0))[:12]:
        print(f"   {k[:40]:40s} {v['★★★跨过假跳变的笔数']:3d} 笔 占总盈亏 "
              f"{v['★★★这些笔占总盈亏pct']}%")
    print(f"★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
